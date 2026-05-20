import os
import json
import requests
from typing import Optional
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from duckduckgo_search import DDGS

# Create FastMCP server
mcp = FastMCP("Travel Planner MCP Server")

SAVED_PLANS_DIR = Path(__file__).parent / "saved_plans"
SAVED_PLANS_DIR.mkdir(exist_ok=True)

WEATHER_CODES = {
    0: "☀️ Clear sky",
    1: "🌤️ Mainly clear", 2: "🌤️ Partly cloudy", 3: "☁️ Overcast",
    45: "🌫️ Fog", 48: "🌫️ Depositing rime fog",
    51: "🌧️ Drizzle: Light", 53: "🌧️ Drizzle: Moderate", 55: "🌧️ Drizzle: Dense",
    56: "🌧️ Freezing Drizzle: Light", 57: "🌧️ Freezing Drizzle: Dense",
    61: "🌧️ Rain: Slight", 63: "🌧️ Rain: Moderate", 65: "🌧️ Rain: Heavy",
    66: "🌧️ Freezing Rain: Light", 67: "🌧️ Freezing Rain: Heavy",
    71: "❄️ Snow fall: Slight", 73: "❄️ Snow fall: Moderate", 75: "❄️ Snow fall: Heavy",
    77: "❄️ Snow grains",
    80: "🌦️ Rain showers: Slight", 81: "🌦️ Rain showers: Moderate", 82: "🌦️ Rain showers: Violent",
    85: "❄️ Snow showers: Slight", 86: "❄️ Snow showers: Heavy",
    95: "⛈️ Thunderstorm: Slight or moderate",
    96: "⛈️ Thunderstorm with slight hail", 99: "⛈️ Thunderstorm with heavy hail"
}

@mcp.tool()
def get_weather(city: str) -> str:
    """
    Fetches the current weather and 5-day forecast for a given city/destination using Open-Meteo.
    Returns a formatted markdown summary.
    """
    # 1. Geocode the city to get lat/lon
    geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
    try:
        geo_resp = requests.get(geocode_url, timeout=10)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        if not geo_data.get("results"):
            return f"Error: Could not find location coordinate details for '{city}'."
        
        result = geo_data["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        name = result.get("name", city)
        country = result.get("country", "")
        admin = result.get("admin1", "")
    except Exception as e:
        return f"Error resolving location coordinates for '{city}': {e}"

    # 2. Get the weather forecast
    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,rain_sum,showers_sum,snowfall_sum&timezone=auto"
    try:
        weather_resp = requests.get(weather_url, timeout=10)
        weather_resp.raise_for_status()
        w_data = weather_resp.json()
    except Exception as e:
        return f"Error fetching weather forecast for '{city}': {e}"

    current = w_data.get("current", {})
    daily = w_data.get("daily", {})
    
    current_temp = current.get("temperature_2m", "N/A")
    apparent_temp = current.get("apparent_temperature", "N/A")
    humidity = current.get("relative_humidity_2m", "N/A")
    wind_speed = current.get("wind_speed_10m", "N/A")
    w_code = current.get("weather_code", 0)
    w_desc = WEATHER_CODES.get(w_code, "Unknown weather condition")

    markdown = f"### Weather Report for {name}, {admin} ({country})\n"
    markdown += f"**Current Temperature:** {current_temp}°C (Feels like: {apparent_temp}°C)\n"
    markdown += f"**Condition:** {w_desc}\n"
    markdown += f"**Humidity:** {humidity}%\n"
    markdown += f"**Wind Speed:** {wind_speed} km/h\n\n"
    
    if daily:
        markdown += "#### 5-Day Forecast:\n"
        markdown += "| Date | Min Temp | Max Temp | Rain Sum | Showers |\n"
        markdown += "| --- | --- | --- | --- | --- |\n"
        dates = daily.get("time", [])
        min_temps = daily.get("temperature_2m_min", [])
        max_temps = daily.get("temperature_2m_max", [])
        rains = daily.get("rain_sum", [])
        showers = daily.get("showers_sum", [])
        
        for i in range(min(5, len(dates))):
            date_str = dates[i]
            t_min = min_temps[i] if i < len(min_temps) else "N/A"
            t_max = max_temps[i] if i < len(max_temps) else "N/A"
            r_sum = rains[i] if i < len(rains) else 0.0
            sh_sum = showers[i] if i < len(showers) else 0.0
            markdown += f"| {date_str} | {t_min}°C | {t_max}°C | {r_sum} mm | {sh_sum} mm |\n"
            
    return markdown

@mcp.tool()
def web_search(query: str) -> str:
    """
    Searches the web via DuckDuckGo and returns the top 5 search result snippets formatted in markdown.
    Use this for fetching current data, attractions, or details about places.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"No search results found for query: '{query}'."
        
        markdown = f"### Web Search Results for '{query}'\n\n"
        for idx, res in enumerate(results, 1):
            title = res.get("title", "No Title")
            href = res.get("href", "#")
            body = res.get("body", "")
            markdown += f"{idx}. **[{title}]({href})**\n   {body}\n\n"
        return markdown
    except Exception as e:
        return f"Error conducting web search: {e}"

@mcp.tool()
def get_travel_advice(destination: str, interest: Optional[str] = None) -> str:
    """
    Retrieves aggregated travel advice for a destination.
    Performs multiple queries: best time to visit, safety, local customs, and (optionally) recommendations for an interest.
    """
    queries = [
        f"best time to visit {destination} weather and crowds travel advice",
        f"{destination} travel safety tips and local customs"
    ]
    if interest:
        queries.append(f"{destination} top spots for {interest} activities")

    aggregated_results = []
    
    with DDGS() as ddgs:
        for q in queries:
            try:
                results = list(ddgs.text(q, max_results=3))
                if results:
                    aggregated_results.append((q, results))
            except Exception as e:
                aggregated_results.append((q, f"Error searching: {e}"))
                
    markdown = f"## Travel Advice & Expert Guide for {destination}\n\n"
    for query, res_list in aggregated_results:
        clean_q = query.replace(destination, "").strip().capitalize()
        markdown += f"### {clean_q}\n"
        if isinstance(res_list, str):
            markdown += f"*{res_list}*\n\n"
        else:
            for r in res_list:
                title = r.get("title", "Info")
                href = r.get("href", "#")
                body = r.get("body", "")
                markdown += f"- **[{title}]({href})**: {body}\n"
            markdown += "\n"
            
    return markdown

@mcp.tool()
def save_tour_plan(plan_name: str, itinerary_data: str) -> str:
    """
    Saves a generated itinerary plan to a JSON file.
    The itinerary_data should ideally be a structured JSON string containing destination, budget, itinerary days, etc.
    """
    # Clean the name to prevent directory traversal
    safe_name = "".join(c for c in plan_name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe_name:
        return "Error: Invalid plan name."
        
    file_path = SAVED_PLANS_DIR / f"{safe_name}.json"
    
    try:
        # Check if itinerary_data is valid JSON, otherwise save it as raw text wrap
        try:
            parsed = json.loads(itinerary_data)
        except Exception:
            parsed = {"raw_text": itinerary_data, "plan_name": plan_name}
            
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
            
        return f"Successfully saved tour plan as '{safe_name}'."
    except Exception as e:
        return f"Error saving tour plan: {e}"

@mcp.tool()
def load_tour_plan(plan_name: str) -> str:
    """
    Loads a saved tour plan JSON by name.
    """
    safe_name = "".join(c for c in plan_name if c.isalnum() or c in (" ", "-", "_")).strip()
    file_path = SAVED_PLANS_DIR / f"{safe_name}.json"
    
    if not file_path.exists():
        return f"Error: Plan '{safe_name}' does not exist."
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error loading tour plan: {e}"

@mcp.tool()
def list_saved_plans() -> str:
    """
    Lists all saved tour plans.
    """
    try:
        files = list(SAVED_PLANS_DIR.glob("*.json"))
        if not files:
            return "No saved tour plans found."
            
        names = [f.stem for f in files]
        return json.dumps(names)
    except Exception as e:
        return f"Error listing plans: {e}"

if __name__ == "__main__":
    mcp.run()
