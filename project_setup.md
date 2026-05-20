# Tour Planner Project Specification

## Objective
Create a Tour Planner AI Agent. It should use an LLM to plan a tour for a user. The user can provide:
- **Destination**
- **Duration** (number of days)
- **Budget**
- **Interests** (e.g., adventure, nature, food, culture, history)
- **Travel Style** (e.g., budget, luxury, slow travel, solo, family)
- **Mode of Transport** (e.g., flight, train, self-drive, bus)
- **Accommodation Type** (e.g., hostel, 5-star hotel, homestay, camping)
- **Any other preferences**

The agent should process inputs dynamically:
1. **If a destination is given**: The agent should provide a brief overview of the destination, average temperature/climate, the best time to visit, major attractions, and things to do there.
2. **If a duration is given**: The agent should suggest the best destinations that can be reasonably covered in that time frame.
3. **If interests are given**: The agent should suggest destinations that align with those interests.

## Features
- **Real-time Context**: Use search and weather APIs to get up-to-date data for the travel advice.
- **Trip Persistence**: Save and reload generated itineraries.
- **Model Interactivity**: Run through LLM Gateway V2 to take advantage of model routing, fallback, and tool-calling capabilities.
- **Premium User Interface**: Modern web application layout.
