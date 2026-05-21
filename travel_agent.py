import os
import json
import httpx
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8099"))
GATEWAY_URL = f"http://localhost:{GATEWAY_PORT}/v1/chat"

class TravelAgent:
    def __init__(self, model: Optional[str] = None, provider: Optional[str] = None):
        self.model = model
        self.provider = provider
        self.server_params = StdioServerParameters(
            command="python",
            args=["mcp_server.py"],
        )

    async def run_agent_loop(self, user_query: str, chat_history: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Runs the agent loop. Yields progress/telemetry events and finally yields the final text response.
        """
        yield {"event": "agent_start", "query": user_query}
        
        # 1. Establish connection with the MCP Server
        yield {"event": "mcp_connect_start", "message": "Connecting to Travel MCP Server..."}
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield {"event": "mcp_connect_success", "message": "Successfully connected to MCP Server."}

                    # Fetch available tools from the MCP server
                    mcp_tools_resp = await session.list_tools()
                    # Convert to Gateway V2 ToolDef shape (name, description, input_schema)
                    gateway_tools = []
                    for t in mcp_tools_resp.tools:
                        gateway_tools.append({
                            "name": t.name,
                            "description": t.description,
                            "input_schema": t.inputSchema
                        })
                    
                    yield {"event": "mcp_tools_loaded", "tools": [t["name"] for t in gateway_tools]}

                    # Initialize messages list
                    messages = []
                    if chat_history:
                        # Translate chat history to API format
                        for h in chat_history:
                            messages.append({"role": h["role"], "content": h["content"]})
                    
                    # Add current user query
                    messages.append({"role": "user", "content": user_query})

                    loop_count = 0
                    max_loops = 20

                    # Define system prompt
                    system_prompt = (
                        "You are an expert Tour Planner AI Agent. Your objective is to assist users in planning trips. "
                        "You have access to a travel toolset to find information. "
                        "IMPORTANT: Always call multiple tools in a single response when possible — batch web_search, get_weather, and get_travel_advice together rather than one at a time. "
                        "When planning a tour, construct a detailed daily itinerary with rich descriptions, local tips, recommended restaurants, accommodation suggestions, and estimated costs where possible. "
                        "Include weather updates and the best time to visit the destination. "
                        "Present the final itinerary in a beautiful, structured markdown format with clear day-by-day sections, emojis, and highlights. "
                        "Do NOT call save_tour_plan automatically — only save if the user explicitly asks you to save the plan."
                    )

                    async with httpx.AsyncClient(timeout=180) as client:
                        while loop_count < max_loops:
                            loop_count += 1
                            yield {"event": "llm_start", "loop": loop_count, "message": "Querying LLM Gateway..."}
                            
                            payload = {
                                "messages": messages,
                                "system": system_prompt,
                                "tools": gateway_tools,
                                "temperature": 0.2
                            }
                            if self.model:
                                payload["model"] = self.model
                            if self.provider:
                                payload["provider"] = self.provider

                            try:
                                resp = await client.post(GATEWAY_URL, json=payload)
                                if resp.status_code != 200:
                                    yield {"event": "error", "message": f"LLM Gateway returned error {resp.status_code}: {resp.text}"}
                                    return
                                    
                                response_json = resp.json()
                            except Exception as e:
                                yield {"event": "error", "message": f"Error calling LLM Gateway: {e}"}
                                return

                            provider = response_json.get("provider", "unknown")
                            model_used = response_json.get("model", "unknown")
                            text_response = response_json.get("text", "")
                            tool_calls = response_json.get("tool_calls", [])
                            latency_ms = response_json.get("latency_ms", 0)

                            yield {
                                "event": "llm_end",
                                "provider": provider,
                                "model": model_used,
                                "latency_ms": latency_ms,
                                "text": text_response,
                                "tool_calls_count": len(tool_calls)
                            }

                            if not tool_calls:
                                # No tool calls, we are finished!
                                yield {"event": "agent_success", "response": text_response}
                                return

                            # We have tool calls to execute
                            # 1. Append assistant message containing the tool calls
                            assistant_msg = {
                                "role": "assistant",
                                "content": text_response,
                                "tool_calls": tool_calls
                            }
                            messages.append(assistant_msg)

                            # 2. Execute each tool call
                            for tc in tool_calls:
                                tc_id = tc.get("id")
                                tc_name = tc.get("name")
                                tc_args = tc.get("arguments", {})

                                yield {"event": "tool_start", "tool_name": tc_name, "arguments": tc_args}

                                try:
                                    # Call tool on MCP server session
                                    tool_result = await session.call_tool(tc_name, arguments=tc_args)
                                    # Get text content from tool response
                                    content_text = ""
                                    if hasattr(tool_result, "content") and tool_result.content:
                                        content_text = "".join(getattr(c, "text", "") for c in tool_result.content if hasattr(c, "text"))
                                    else:
                                        content_text = str(tool_result)

                                    yield {"event": "tool_end", "tool_name": tc_name, "result_preview": content_text[:300] + "..." if len(content_text) > 300 else content_text}
                                except Exception as e:
                                    content_text = f"Error executing tool: {e}"
                                    yield {"event": "tool_error", "tool_name": tc_name, "error": content_text}

                                # Append tool response back to conversation history
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "name": tc_name,
                                    "content": content_text
                                })

                        yield {"event": "error", "message": "Max agent loops exceeded."}

        except Exception as e:
            yield {"event": "error", "message": f"MCP connection/communication error: {e}"}
