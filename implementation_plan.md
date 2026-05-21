# Implementation Plan: Pass All 9 Prompt Evaluation Criteria

**Scope:** `travel_agent.py` only — the `system_prompt` string inside `run_agent_loop`.  
No changes to `app.py`, `mcp_server.py`, or the LLM gateway.

---

## Current State

```python
system_prompt = (
    "You are an expert Tour Planner AI Agent. Your objective is to assist users in planning trips. "
    "You have access to a travel toolset to find information. "
    "IMPORTANT: Always call multiple tools in a single response when possible — batch web_search, get_weather, and get_travel_advice together rather than one at a time. "
    "When planning a tour, construct a detailed daily itinerary with rich descriptions, local tips, recommended restaurants, accommodation suggestions, and estimated costs where possible. "
    "Include weather updates and the best time to visit the destination. "
    "Present the final itinerary in a beautiful, structured markdown format with clear day-by-day sections, emojis, and highlights. "
    "Do NOT call save_tour_plan automatically — only save if the user explicitly asks you to save the plan."
)
```

**Score against rubric: ~4/9**

---

## Criteria & Fixes

### Criterion 1 — Explicit Reasoning Instructions ❌ → ✅

**Problem:** No instruction to think step-by-step or explain reasoning before acting.

**Fix — Add to prompt:**
```
Before taking any action, reason step by step:
  (1) Understand what the user wants (destination, duration, budget, interests).
  (2) Decide which tools are needed and why.
  (3) After receiving tool results, synthesize the information before writing the itinerary.
```

---

### Criterion 2 — Structured Output Format ✅ → ✅ (strengthen)

**Problem:** "Beautiful structured markdown" is vague — no concrete template enforced.

**Fix — Add explicit output skeleton:**
```
The final itinerary MUST follow this exact structure:

## 🌍 Trip Overview
(destination, duration, budget level, best time to visit)

## 🌤️ Weather Summary
(current conditions + 5-day forecast if available)

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
```

---

### Criterion 3 — Separation of Reasoning & Tools ❌ → ✅

**Problem:** No explicit two-phase separation between tool use and writing.

**Fix — Add two-phase instruction:**
```
Phase 1 — GATHER: Call all relevant tools first (web_search, get_weather,
get_travel_advice). Do not write the itinerary yet.

Phase 2 — SYNTHESIZE: Once all tool results are available, reason over them
and compose the final itinerary using the structured format above.
```

---

### Criterion 4 — Conversation Loop Support ✅

**Status:** Already handled by the agentic loop in code (multi-turn with chat history).

**Minor prompt addition:**
```
If the user asks follow-up questions or refinements, update the relevant
sections of the itinerary accordingly using the same structured format.
```

---

### Criterion 5 — Instructional Framing ⚠️ → ✅

**Problem:** Desired output is described but no concrete example is given.

**Fix — Add a day format example:**
```
Example of a correctly formatted day:

### Day 1: Arrival & Old Town Exploration
- **Morning:** Arrive at X airport, transfer to hotel Y (est. ₹Z/night).
  Check in and freshen up.
- **Afternoon:** Visit Attraction A (entry fee: est. ₹X). Walk through
  Old Town market. Stop at Café B for lunch (est. ₹Y).
- **Evening:** Dinner at Restaurant C (cuisine type, est. ₹Z per person).
  Stroll along the riverfront.
```

---

### Criterion 6 — Internal Self-Checks ❌ → ✅

**Problem:** No instruction to verify the output before finalizing.

**Fix — Add a self-verification checklist:**
```
Before presenting the final itinerary, verify:
  ✓ Every day has morning, afternoon, and evening coverage
  ✓ Weather information is referenced at least once
  ✓ At least one dining recommendation exists
  ✓ At least one accommodation recommendation exists
  ✓ Budget estimates are consistent with the stated budget level
  ✓ No day is left empty or vague
```

---

### Criterion 7 — Reasoning Type Awareness ❌ → ✅

**Problem:** No instruction to identify or tag the type of reasoning being applied.

**Fix — Add reasoning type tags:**
```
When reasoning internally, tag each step with its type:
  [LOOKUP]     — fetching factual info via tools
  [PLANNING]   — structuring the itinerary day-by-day
  [ESTIMATION] — approximating costs, durations, or distances
  [SYNTHESIS]  — combining tool results into a coherent narrative
```

---

### Criterion 8 — Error Handling & Fallbacks ❌ → ✅

**Problem:** No instruction on what to do when a tool fails or data is uncertain.

**Fix — Add fallback rules:**
```
If a tool returns an error or no results:
  - web_search failure: note "Information unavailable — recommend verifying
    locally" and continue using general knowledge.
  - get_weather failure: state "Live weather unavailable" and provide
    seasonal climate averages instead.
  - get_travel_advice failure: use web_search as a fallback.

Never fabricate specific prices, hours, or addresses.
Mark uncertain values with "(est.)" or "(verify locally)".
```

---

### Criterion 9 — Overall Clarity & Robustness ✅

**Status:** Already clear. Maintained by the structured additions above.  
No additional changes needed beyond what criteria 1–8 add.

---

## Final Prompt Structure (after changes)

The new `system_prompt` will be organized into these sections in order:

1. **Role definition** — who the agent is
2. **Step-by-step reasoning instruction** (Criterion 1)
3. **Two-phase tool/synthesis separation** (Criterion 3)
4. **Tool batching instruction** (existing, keep)
5. **Reasoning type tags** (Criterion 7)
6. **Structured output template** (Criterion 2)
7. **Day format example** (Criterion 5)
8. **Self-verification checklist** (Criterion 6)
9. **Fallback rules** (Criterion 8)
10. **Multi-turn support note** (Criterion 4)
11. **Save plan restriction** (existing, keep)

---

## Change Summary

| File | Lines changed | Nature of change |
|---|---|---|
| `travel_agent.py` | ~5 lines → ~40 lines | Replace `system_prompt` string only |

No new files, no new tools, no structural changes to the agentic loop or gateway.
