# Voyager AI — Agentic Tour Planner

An AI-powered travel planning agent that generates detailed, structured trip itineraries using live web search, real-time weather data, and a multi-provider LLM gateway. Built with a Streamlit frontend, an MCP tool server, and a custom LLM gateway that routes across Gemini, Groq, Cerebras, NVIDIA, and more.

---

## Architecture

```
┌─────────────────────┐        ┌──────────────────────────┐        ┌────────────────────────────┐
│    Streamlit UI     │        │      Travel Agent         │        │     LLM Gateway V2         │
│      (app.py)       │───────▶│   (travel_agent.py)       │───────▶│      (port 8099)           │
└─────────────────────┘        └────────────┬─────────────┘        └────────────┬───────────────┘
                                            │ MCP stdio                          │ routes to
                                            ▼                                    ▼
                                ┌──────────────────────────┐        Gemini · Gemini2 · Groq
                                │    MCP Tool Server        │        Cerebras · NVIDIA
                                │    (mcp_server.py)        │        OpenRouter · GitHub · Ollama
                                └──────────────────────────┘
                                Tools: web_search, get_weather,
                                       get_travel_advice,
                                       save/load/list_tour_plans
```

**Data flow in one sentence:** The Streamlit UI builds a query → the Travel Agent connects to the MCP server over stdio, fetches tools, and enters an agentic loop → each loop sends messages + tools to the LLM Gateway → the gateway picks the best available LLM → tool calls come back → the agent executes them on the MCP server → results are fed back into the next loop → when the LLM returns no more tool calls, the final itinerary is streamed to the UI.

---

## Components

### 1. `app.py` — Streamlit Frontend

The UI layer. Responsible for:

- **Input collection:** Origin, destination, duration (1–14 days), budget level, interests, transport mode, accommodation style, and free-text preferences.
- **Query construction:** Assembles all inputs into a single natural-language query string passed to the agent.
- **Live telemetry log:** Renders a dark terminal-style box that updates in real time as each agent event fires (`mcp_connect`, `llm_start`, `tool_start`, `tool_end`, `agent_success`).
- **Itinerary display:** On `agent_success`, stores the response in `st.session_state` and renders it with `st.markdown` — preserving all formatting, emojis, and headers.
- **Save as PDF:** A `st.download_button` appears after the itinerary renders. Clicking it calls `generate_pdf()`, which converts the markdown to a formatted PDF using `fpdf2` with the Arial Unicode font (to support emojis and special characters), and downloads it locally. **No save happens unless the user clicks the button.**
- **Sidebar:** Lists previously saved plans (JSON via MCP) and lets the user load them into the "View Loaded Plan" tab. Allows forcing a specific LLM provider.

**Key function:**
```python
async def run_planner(agent, query, history=None):
    async for event in agent.run_agent_loop(query):
        # update telemetry log on every event
        # on agent_success → store in st.session_state
```

---

### 2. `travel_agent.py` — Agentic Loop

The brain. Contains one class, `TravelAgent`, with one method: `run_agent_loop()`.

**How it works — step by step:**

```
1. Connect to mcp_server.py over stdio (StdioServerParameters)
2. Call session.list_tools() → get all 6 MCP tools as JSON schemas
3. Translate tool schemas into the Gateway V2 ToolDef shape
4. Build the messages list (inject chat history if multi-turn)
5. Enter the agentic loop (max 20 iterations):
   a. POST to http://localhost:8099/v1/chat with messages + tools + system prompt
   b. Parse response: text, tool_calls[], provider, model, latency_ms
   c. If no tool_calls → yield agent_success and exit
   d. If tool_calls exist:
      - Append assistant message (with tool_calls) to messages
      - For each tool call: execute via session.call_tool() on MCP server
      - Append tool result message to messages
      - Continue to next loop iteration
```

**System prompt design** — structured to pass 9 prompt evaluation criteria:

| Section | Purpose |
|---|---|
| Step-by-step reasoning | Forces the LLM to reason before acting |
| Two-phase approach | GATHER (tools first) → SYNTHESIZE (write after) |
| Reasoning type tags | `[LOOKUP]` `[PLANNING]` `[ESTIMATION]` `[SYNTHESIS]` |
| Output format template | Exact markdown skeleton the LLM must follow |
| Day format example | Concrete Morning/Afternoon/Evening example |
| Self-verification checklist | LLM verifies its own output before finalizing |
| Fallback rules | What to do when tools fail or data is uncertain |
| Multi-turn instruction | How to handle follow-up refinements |
| Save rule | Never auto-save; only on explicit user request |

**Temperature:** `0.2` — low, for factual consistency.  
**Timeout:** `180s` per gateway call.

---

### 3. `mcp_server.py` — MCP Tool Server

Built with `FastMCP`. Runs as a subprocess spawned by `travel_agent.py` over stdio. Exposes 6 tools:

#### `get_weather(city: str)`
- **When called:** Phase 1 (GATHER), always on first loop.
- **How:** Geocodes the city via `open-meteo.com/v1/search` → fetches current conditions + 5-day forecast via `api.open-meteo.com/v1/forecast`.
- **Returns:** Markdown table with temperature, humidity, wind speed, weather condition (mapped from WMO weather codes), and a 5-day min/max/rain forecast.
- **No API key required** — Open-Meteo is free.

#### `web_search(query: str)`
- **When called:** Phase 1 (GATHER), batched with `get_weather` and `get_travel_advice`.
- **How:** Uses `duckduckgo_search` (DDGS) to fetch top 5 results for the query string.
- **Returns:** Markdown list of result titles, URLs, and snippets.
- **No API key required** — DuckDuckGo is free.

#### `get_travel_advice(destination: str, interest: Optional[str])`
- **When called:** Phase 1 (GATHER), batched with the others.
- **How:** Fires 2–3 DuckDuckGo searches internally: best time to visit, safety/customs, and optionally interest-specific spots. Aggregates all results.
- **Returns:** Markdown sections for each sub-query.

#### `save_tour_plan(plan_name: str, itinerary_data: str)`
- **When called:** Only when the user explicitly asks the agent to save.
- **How:** Sanitizes the plan name (alphanumeric + `-_` only), tries to parse `itinerary_data` as JSON, falls back to wrapping it as `{"raw_text": ..., "plan_name": ...}`. Saves to `saved_plans/<name>.json`.

#### `load_tour_plan(plan_name: str)`
- **When called:** When the user loads a plan from the sidebar or asks the agent to recall one.
- **How:** Reads `saved_plans/<name>.json` and returns its JSON content as a string.

#### `list_saved_plans()`
- **When called:** On sidebar render (called directly from `app.py`, not via agent) and occasionally by the agent when checking existing plans.
- **How:** Globs `saved_plans/*.json` and returns a JSON array of stem names.

---

### 4. `llm_gatewayV2/` — Multi-Provider LLM Gateway

A FastAPI server running on port `8099`. Accepts a single `/v1/chat` endpoint and handles everything else internally.

**Providers and routing order** (defined in `LLM_ORDER` env var):

| Priority | Provider | Default Model | RPM | Context |
|---|---|---|---|---|
| 1 | Ollama (local) | gemma4:31b | unlimited | 32K |
| 2 | Gemini (primary) | gemini-3-flash-preview | 15 | 1M |
| 3 | Gemini2 (fallback) | gemini-2.5-flash | 15 | 1M |
| 4 | NVIDIA | deepseek-ai/deepseek-v4-pro | 40 | 100K |
| 5 | Groq | llama-3.3-70b-versatile | 30 | 100K |
| 6 | Cerebras | qwen-3-235b-a22b-instruct-2507 | 30 | 8K |
| 7 | OpenRouter | nvidia/nemotron-3-super-120b | 20 | 100K |
| 8 | GitHub Models | openai/gpt-4.1-mini | 10 | 8K |

**Router logic (`router.py`):**
```
For each provider in order:
  1. Check capability match (tools support required)
  2. Check context window vs. estimated token count
  3. Check rate limits: RPM, RPD, TPM, daily token cap, cooldown, backoff
  4. First provider that passes all checks → selected
  5. If all fail → 503 with full attempt log
```

**Rate limit bookkeeping:**
- RPM: sliding 60-second window using a `deque` of timestamps
- RPD: daily counter reset at UTC midnight
- TPM: sliding 60-second window of `(timestamp, token_count)` pairs
- Backoff: providers that return 429/401/5xx are marked unavailable for N seconds

**Normalization:** Every provider adapter translates its native response format into a unified dict:
```python
{
  "text": str,
  "tool_calls": [{"id", "name", "arguments"}],
  "input_tokens": int,
  "output_tokens": int,
  "stop_reason": "tool_use" | "end_turn" | "max_tokens",
  "provider": str,
  "model": str,
  "latency_ms": int
}
```

---

## Prompt Engineering — Evaluation Criteria

The system prompt was designed to score well on a structured prompt evaluation rubric:

| Criterion | Approach |
|---|---|
| Explicit Reasoning | "Reason step by step: (1) understand, (2) decide tools, (3) synthesize" |
| Structured Output | Exact markdown template with required sections |
| Tool / Reasoning Separation | Two-phase: GATHER (tools only) then SYNTHESIZE (write only) |
| Conversation Loop | Multi-turn instruction for follow-up refinements |
| Instructional Framing | Concrete Day 1 example with Morning/Afternoon/Evening |
| Internal Self-Checks | 6-point verification checklist before finalizing |
| Reasoning Type Awareness | `[LOOKUP]` `[PLANNING]` `[ESTIMATION]` `[SYNTHESIS]` tags |
| Error Handling / Fallbacks | Per-tool fallback rules; no fabricated data policy |
| Overall Clarity | Single-purpose sections, no ambiguity |

---

## Setup

### Prerequisites
- Python 3.10+
- `uv` (recommended) or `pip`
- API keys for at least one LLM provider

### 1. Clone the repo
```bash
git clone https://github.com/Anirudh9810/Travel_Agent.git
cd Travel_Agent
```

### 2. Create `.env`
```env
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3-flash-preview
GEMINI_MODEL_FALLBACK=gemini-2.5-flash

GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile

CEREBRAS_API_KEY=your_cerebras_key
CEREBRAS_MODEL=qwen-3-235b-a22b-instruct-2507

NVIDIA_API_KEY=your_nvidia_key
NVIDIA_MODEL=deepseek-ai/deepseek-v4-pro

OPEN_ROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free

GITHUB_ACCESS_TOKEN=your_github_token
GITHUB_MODEL=openai/gpt-4.1-mini

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:31b

LLM_ORDER=ollama,gemini,gemini2,nvidia,groq,cerebras,openrouter,github
GATEWAY_PORT=8099
```

### 3. Install dependencies
```bash
uv sync
```

### 4. Start the LLM Gateway
```bash
cd llm_gatewayV2
bash run.sh
```
Gateway runs at `http://localhost:8099`. Check status at `http://localhost:8099/v1/status`.

### 5. Run the Streamlit app
```bash
streamlit run app.py
```
Open `http://localhost:8501` in your browser.

---

## Usage

1. Enter your **origin**, optional **destination**, **duration**, **budget**, and **interests**
2. Click **Plan My Adventure**
3. Watch the live telemetry log as the agent gathers data and builds the itinerary
4. The completed itinerary appears with all structured sections
5. Click **Save Itinerary as PDF** to download — nothing is saved unless you click

---

## Project Structure

```
Travel_Agent/
├── app.py                  # Streamlit frontend + PDF export
├── travel_agent.py         # Agentic loop — connects UI to gateway + MCP
├── mcp_server.py           # MCP tool server (6 tools)
├── llm_gatewayV2/          # Multi-provider LLM gateway (not committed)
├── saved_plans/            # Saved itinerary JSON files (not committed)
├── implementation_plan.md  # Prompt engineering improvement plan
├── pyproject.toml
└── .env                    # API keys (not committed)
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web UI framework |
| `httpx` | Async HTTP client for gateway calls |
| `mcp[cli]` | Model Context Protocol client + server |
| `duckduckgo-search` | Free web search (no API key) |
| `fpdf2` | PDF generation with Unicode support |
| `pandas` | Data handling utilities |

## Prompt Evaluation

You are a Prompt Evaluation Assistant.

You will receive a prompt written by a student. Your job is to review this prompt and assess how well it supports structured, step-by-step reasoning in an LLM (e.g., for math, logic, planning, or tool use).

Evaluate the prompt on the following criteria:

1. Explicit Reasoning Instructions  
   - Does the prompt tell the model to reason step-by-step?  
   - Does it include instructions like “explain your thinking” or “think before you answer”?

2. Structured Output Format  
   - Does the prompt enforce a predictable output format (e.g., FUNCTION_CALL, JSON, numbered steps)?  
   - Is the output easy to parse or validate?

3. Separation of Reasoning and Tools  
   - Are reasoning steps clearly separated from computation or tool-use steps?  
   - Is it clear when to calculate, when to verify, when to reason?

4. Conversation Loop Support  
   - Could this prompt work in a back-and-forth (multi-turn) setting?  
   - Is there a way to update the context with results from previous steps?

5. Instructional Framing  
   - Are there examples of desired behavior or “formats” to follow?  
   - Does the prompt define exactly how responses should look?

6. Internal Self-Checks  
   - Does the prompt instruct the model to self-verify or sanity-check intermediate steps?

7. Reasoning Type Awareness  
   - Does the prompt encourage the model to tag or identify the type of reasoning used (e.g., arithmetic, logic, lookup)?

8. Error Handling or Fallbacks  
   - Does the prompt specify what to do if an answer is uncertain, a tool fails, or the model is unsure?

9. Overall Clarity and Robustness  
   - Is the prompt easy to follow?  
   - Is it likely to reduce hallucination and drift?

---

Respond with a structured review in this format:

```json
{
  "explicit_reasoning": true,
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "instructional_framing": true,
  "internal_self_checks": false,
  "reasoning_type_awareness": false,
  "fallbacks": false,
  "overall_clarity": "Excellent structure, but could improve with self-checks and error fallbacks."
}

---

## System Prompt

"""You are an expert Tour Planner AI Agent. Your objective is to assist users in planning detailed, accurate, and enjoyable travel itineraries.

STEP-BY-STEP REASONING:
Before taking any action, reason step by step:
  (1) Understand what the user wants — destination, duration, budget, and interests.
  (2) Decide which tools are needed and why.
  (3) After receiving tool results, synthesize the information before writing the itinerary.

TWO-PHASE APPROACH:
  Phase 1 — GATHER: Call all relevant tools first (web_search, get_weather, get_travel_advice). Batch as many tools as possible in a single response. Do not write the itinerary yet.
  Phase 2 — SYNTHESIZE: Once all tool results are in hand, reason over them and compose the final itinerary.

REASONING TYPE TAGS (use internally when reasoning):
  [LOOKUP]     — fetching factual info via tools
  [PLANNING]   — structuring the itinerary day-by-day
  [ESTIMATION] — approximating costs, durations, or distances
  [SYNTHESIS]  — combining tool results into a coherent narrative

OUTPUT FORMAT — The final itinerary MUST follow this exact structure:

## 🌍 Trip Overview
(destination, duration, budget level, best time to visit)

## 🌤️ Weather Summary
(current conditions and 5-day forecast if available)

## 🗓️ Day-by-Day Plan
### Day 1: <Theme Title>
- **Morning:** ...
- **Afternoon:** ...
- **Evening:** ...
(repeat for each day)

## 🍽️ Food & Dining Highlights
## 🏨 Accommodation Recommendations
## 💡 Local Tips & Cultural Notes
## 💰 Estimated Budget Breakdown

EXAMPLE DAY FORMAT:
### Day 1: Arrival & Old Town Exploration
- **Morning:** Arrive at X airport, transfer to hotel Y (est. ₹Z/night). Check in and freshen up.
- **Afternoon:** Visit Attraction A (entry fee: est. ₹X). Walk through Old Town market. Stop at Café B for lunch (est. ₹Y per person).
- **Evening:** Dinner at Restaurant C (cuisine type, est. ₹Z per person). Stroll along the riverfront.

SELF-VERIFICATION — Before presenting the final itinerary, verify:
  ✓ Every day has morning, afternoon, and evening coverage
  ✓ Weather information is referenced at least once
  ✓ At least one dining recommendation exists
  ✓ At least one accommodation recommendation exists
  ✓ Budget estimates are consistent with the stated budget level
  ✓ No day is left empty or vague

FALLBACK RULES:
  - If web_search fails: note "Information unavailable — recommend verifying locally" and use general knowledge.
  - If get_weather fails: state "Live weather unavailable" and provide seasonal climate averages instead.
  - If get_travel_advice fails: use web_search as a fallback.
  - Never fabricate specific prices, hours, or addresses. Mark uncertain values with "(est.)" or "(verify locally)".

MULTI-TURN: If the user asks follow-up questions or refinements, update the relevant sections of the itinerary using the same structured format.

SAVE RULE: Do NOT call save_tour_plan automatically — only save if the user explicitly asks."""


---


## Gemini Evaluation Result

{
  "explicit_reasoning": true,
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "instructional_framing": true,
  "internal_self_checks": true,
  "reasoning_type_awareness": true,
  "fallbacks": true,
  "overall_clarity": "Exceptional prompt. It comprehensively addresses every single criterion. The inclusion of a explicit two-phase approach for tool use, specialized internal reasoning tags, a strict self-verification checklist, and robust tool-failure fallbacks makes this an incredibly robust system prompt for structured reasoning."
}

---

## Youtube Video link

https://youtu.be/vFSuou1XsVc

---