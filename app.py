import os
import asyncio
import streamlit as st
import json
from travel_agent import TravelAgent
from mcp_server import list_saved_plans, load_tour_plan

# Set page configuration with a premium title and layout
st.set_page_config(
    page_title="Vagabond AI — Premium Agentic Tour Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Custom CSS with Google Fonts, Glassmorphism, and Gradients
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

/* Global Font & Theme override */
html, body, [class*="css"], .stApp {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    background-color: #0d0f14;
    color: #f1f3f9;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700;
}

/* Gradient text for app title */
.gradient-title {
    background: linear-gradient(135deg, #6366F1 0%, #A855F7 50%, #EC4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 3rem;
    font-weight: 800;
    margin-bottom: 0.5rem;
    text-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
}

.gradient-subtitle {
    color: #94a3b8;
    font-size: 1.2rem;
    font-weight: 400;
    margin-bottom: 2rem;
}

/* Glassmorphic Container */
.glass-container {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 24px;
    backdrop-filter: blur(12px);
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
}

/* Day Itinerary Card */
.itinerary-day-card {
    background: linear-gradient(145deg, rgba(30, 27, 75, 0.3) 0%, rgba(15, 23, 42, 0.3) 100%);
    border-left: 4px solid #8B5CF6;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
    border-top: 1px solid rgba(255, 255, 255, 0.03);
    border-right: 1px solid rgba(255, 255, 255, 0.03);
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

/* Custom buttons styling */
div.stButton > button:first-child {
    background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
    color: white;
    font-family: 'Outfit', sans-serif;
    font-weight: 600;
    border: none;
    padding: 12px 28px;
    border-radius: 8px;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
}

div.stButton > button:first-child:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
    background: linear-gradient(135deg, #4f46e5 0%, #9333ea 100%);
    color: white;
}

/* Telemetry Log Styling */
.telemetry-box {
    background: #090b0f;
    border: 1px solid #1e293b;
    border-radius: 8px;
    font-family: 'Courier New', Courier, monospace;
    padding: 12px;
    font-size: 0.85rem;
    color: #38bdf8;
    max-height: 250px;
    overflow-y: auto;
    margin-bottom: 16px;
}

.telemetry-line {
    margin-bottom: 4px;
}

.telemetry-time {
    color: #64748b;
}

/* Hide Streamlit branding */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Helper function to run the async agent
async def run_planner(agent: TravelAgent, query: str, history=None):
    progress_log = []
    telemetry_placeholder = st.empty()
    output_placeholder = st.empty()

    with st.spinner("Vagabond Agent is assembling your travel plan..."):
        async for event in agent.run_agent_loop(query, chat_history=history):
            e_type = event.get("event")
            
            if e_type == "agent_start":
                progress_log.append(f"🛫 Initiating travel query: \"{event['query']}\"")
            elif e_type == "mcp_connect_start":
                progress_log.append("🔗 Connecting to Travel MCP Server...")
            elif e_type == "mcp_connect_success":
                progress_log.append("✅ Connected to MCP Server successfully.")
            elif e_type == "mcp_tools_loaded":
                tools_str = ", ".join(event["tools"])
                progress_log.append(f"🛠️ MCP Tools loaded: [{tools_str}]")
            elif e_type == "llm_start":
                progress_log.append(f"🧠 Querying LLM Gateway V2 (Agent Loop #{event['loop']})...")
            elif e_type == "llm_end":
                progress_log.append(f"📡 Gateway Response: provider={event['provider']}, model={event['model']} (Latency: {event['latency_ms']}ms)")
                if event['tool_calls_count'] > 0:
                    progress_log.append(f"⚡ LLM generated {event['tool_calls_count']} tool calls.")
            elif e_type == "tool_start":
                progress_log.append(f"🏃 Executing tool '{event['tool_name']}' arguments={json.dumps(event['arguments'])}")
            elif e_type == "tool_end":
                progress_log.append(f"✔️ Tool '{event['tool_name']}' executed successfully.")
            elif e_type == "tool_error":
                progress_log.append(f"❌ Error in tool '{event['tool_name']}': {event['error']}")
            elif e_type == "agent_success":
                progress_log.append("🎉 Itinerary planning completed successfully!")
                
                # Render the final text response
                with output_placeholder.container():
                    st.markdown("### 🗺️ Generated Travel Itinerary")
                    st.markdown(event["response"])
            elif e_type == "error":
                progress_log.append(f"⚠️ Agent error: {event['message']}")
                st.error(event['message'])
                
            # Render updated progress log
            log_html = "<div class='telemetry-box'>"
            for line in progress_log:
                log_html += f"<div class='telemetry-line'>{line}</div>"
            log_html += "</div>"
            telemetry_placeholder.markdown(log_html, unsafe_allow_html=True)
            
            # Tiny sleep to ensure UI rendering is smooth
            await asyncio.sleep(0.05)

# Render main header
st.markdown("<div class='gradient-title'>Vagabond AI</div>", unsafe_allow_html=True)
st.markdown("<div class='gradient-subtitle'>Your Premium Agentic Tour Planner powered by LLM Gateway V2</div>", unsafe_allow_html=True)

# ----------------- SIDEBAR -----------------
st.sidebar.markdown("### ⚙️ Gateway & Model Configuration")

# Read LLM Order from env or set defaults
DEFAULT_MODELS = ["gemini", "groq", "nvidia", "ollama", "openrouter"]
model_options = ["Default Routing (Router Pick)"] + DEFAULT_MODELS
selected_provider = st.sidebar.selectbox("Force Model Provider", model_options)
forced_provider = None if selected_provider == "Default Routing (Router Pick)" else selected_provider

# Load saved itineraries
st.sidebar.markdown("---")
st.sidebar.markdown("### 📁 Saved Trip Itineraries")

saved_plans_raw = list_saved_plans()
try:
    saved_plans_list = json.loads(saved_plans_raw)
except Exception:
    saved_plans_list = []

if saved_plans_list:
    selected_plan = st.sidebar.selectbox("Choose a saved plan", ["Select a plan..."] + saved_plans_list)
    if selected_plan != "Select a plan...":
        load_btn = st.sidebar.button("Load Selected Plan")
        if load_btn:
            plan_content = load_tour_plan(selected_plan)
            try:
                plan_data = json.loads(plan_content)
                st.session_state["loaded_plan"] = plan_data
                st.session_state["loaded_plan_name"] = selected_plan
                st.success(f"Loaded plan: {selected_plan}")
            except Exception as e:
                st.sidebar.error(f"Error loading plan: {e}")
else:
    st.sidebar.info("No saved plans found. Build a plan to save it automatically!")

# ----------------- MAIN LAYOUT -----------------
tab1, tab2 = st.tabs(["✨ Plan New Adventure", "📖 View Loaded Plan"])

with tab1:
    st.markdown("<div class='glass-container'>", unsafe_allow_html=True)
    st.markdown("#### Define Your Trip Parameters")
    
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Starting Location / Origin", value="Rajahmundry", help="Where you are starting your trip from.")
        destination = st.text_input("Destination (Optional)", placeholder="e.g. Araku Valley, Goa, Paris", help="Leave blank to let the agent recommend a destination.")
        duration = st.slider("Duration (Days)", min_value=1, max_value=14, value=3)
        budget = st.selectbox("Budget Level", ["Budget", "Moderate", "Luxury"], index=1)
        
    with col2:
        interests = st.multiselect(
            "Interests & Activities",
            ["Nature & Landscapes", "Adventure & Trekking", "Historical & Heritage", "Culinary & Food Tour", "Relaxation & Spa", "Shopping & City Walk"],
            default=["Nature & Landscapes"]
        )
        transport = st.selectbox("Preferred Transport Mode", ["No Preference", "Flight", "Train", "Self-Drive / Car", "Bus"])
        accommodation = st.selectbox("Accommodation Style", ["No Preference", "Hostel / Backpacking", "Homestay / Eco-lodge", "Standard Hotel", "5-Star Luxury Resort"])
        custom_pref = st.text_area("Other Preferences / Travel Styles", placeholder="e.g., Vegetarian dining, travelling with senior citizens, pet-friendly...")

    # Form query construction
    interests_str = ", ".join(interests) if interests else "General sightseeing"
    query_parts = []
    
    if destination:
        query_parts.append(f"Create a detailed {duration}-day tour itinerary for {destination} starting from {origin}.")
    else:
        query_parts.append(f"I am living in {origin} and have {duration} days for a trip. Suggest the best destination and plan a detailed itinerary.")
        
    query_parts.append(f"Budget: {budget}.")
    query_parts.append(f"Interests: {interests_str}.")
    if transport != "No Preference":
        query_parts.append(f"Preferred Mode of Transport: {transport}.")
    if accommodation != "No Preference":
        query_parts.append(f"Accommodation Style: {accommodation}.")
    if custom_pref.strip():
        query_parts.append(f"Additional Preferences: {custom_pref.strip()}.")
        
    query_parts.append("Provide details on weather, average temperatures, best time to visit, major attractions, and things to do. Finally, save this plan under a descriptive name.")
    
    full_query = " ".join(query_parts)
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    plan_button = st.button("🚀 Plan My Adventure")
    
    if plan_button:
        # Instantiate Agent
        agent = TravelAgent(provider=forced_provider)
        
        # Run agent loop asynchronously
        asyncio.run(run_planner(agent, full_query))

with tab2:
    if "loaded_plan" in st.session_state:
        st.markdown(f"### 🗺️ Loaded Tour Plan: {st.session_state['loaded_plan_name']}")
        
        loaded_data = st.session_state["loaded_plan"]
        
        # Check if the saved plan is raw text or has structured keys
        if isinstance(loaded_data, dict) and "raw_text" in loaded_data:
            st.markdown(loaded_data["raw_text"])
        else:
            # Render structured JSON in code block
            st.json(loaded_data)
    else:
        st.info("No plan loaded. Load a plan from the sidebar, or generate a new one in the first tab!")
