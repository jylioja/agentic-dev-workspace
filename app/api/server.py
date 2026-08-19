# app/api/server.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import time
import json
import threading
import queue

from app.core.llm_client import get_best_agent, get_agent_response, execute_pending_tools
from app.core.vector_db import search_memory, add_to_memory

app = FastAPI(
    title="Multi-Agent AI API",
    description="Backend for the autonomous agent workspace",
    version="1.0.0"
)

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    agent_override: Optional[str] = None
    session_id: str = "default_api_session"

@app.post("/api/v1/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    message_queue = queue.Queue()
    
    def status_callback(msg: str):
        """
        This callback can be passed deep into the delegation loop 
        to bubble up real-time status messages to the frontend UI.
        """
        message_queue.put({"type": "status", "content": msg})
        
    def background_worker():
        try:
            messages = req.messages.copy()
            session_id = req.session_id
            
            user_prompt = messages[-1]["content"] if messages and messages[-1]["role"] == "user" else ""
            
            if user_prompt:
                add_to_memory(int(time.time() * 1000), session_id, "user", user_prompt)
            
            status_callback("🔄 Routing request to the best agent...")
            target_agent = req.agent_override
            if not target_agent:
                target_agent = get_best_agent(messages)
                
            status_callback(f"🎯 Agent selected: **{target_agent.upper()}**")
                
            if user_prompt:
                status_callback("🧠 Searching long-term memory (RAG)...")
                memory_results = search_memory(user_prompt, n_results=10)
                if "[MEMORY SEARCH RESULTS" in memory_results:
                    memory_context = (
                        f"[BACKGROUND CONTEXT FROM PREVIOUS CONVERSATIONS - USE THIS IF RELEVANT]:\n"
                        f"{memory_results}\n\n"
                        f"---User's actual message starts here---\n"
                    )
                    messages[-1]["content"] = memory_context + user_prompt
                    status_callback("💡 Found relevant past memories!")
                    
            status_callback(f"💭 {target_agent.upper()} is thinking and planning...")
            answer_text, tool_calls = get_agent_response(target_agent, messages)
            
            final_answer = answer_text
            tool_logs = []
            
            if tool_calls:
                tool_names = ", ".join([t.get("name", "unknown") for t in tool_calls])
                status_callback(f"⚙️ Executing tools: {tool_names}...")
                
# Pass the callback into the tool execution engine
                tool_logs = execute_pending_tools(tool_calls, status_callback=status_callback)
                
                # --- HARD CIRCUIT BREAKERS ---
                interrupted = False
                workflow_done = False
                
                for log in tool_logs:
                    res_str = str(log.get("result", ""))
                    
                    # 1st Breaker: User confirmation (PR)
                    if "[REQUIRES USER CONFIRMATION]" in res_str:
                        final_answer = res_str
                        interrupted = True
                        break
                        
                    # 2nd Breaker: Forced tool termination
                    if "[WORKFLOW_COMPLETED]" in res_str:
                        workflow_done = True
                        # Store the summary
                        final_answer = res_str.replace("[WORKFLOW_COMPLETED]", "").strip()
                        break
                
                if interrupted:
                    status_callback("🛑 Workflow paused for user confirmation.")
                elif workflow_done:
                    status_callback("✅ Task completed successfully by tools.")
                    # Since the agent invoked task_complete, skip further LLM queries, 
                    # and output the provided summary directly to the UI.
                else:
                    # NORMAL CONTINUATION (If the loop needs to be controlled by code, 
                    # a 'for i in range(MAX_ITERATIONS):' loop should be built around this)
                    feedback_messages = messages.copy()
                    logs_str = json.dumps(tool_logs, ensure_ascii=False)
                    feedback_messages.append({
                        "role": "user",
                        "content": f"[SYSTEM TOOL RESULTS]:\n{logs_str}\n\nAnalyze results and decide next step."
                    })
                    # ... continue querying the LLM ...
                    
                    status_callback("📝 Analyzing tool results and generating final summary...")
                    summary_text, _ = get_agent_response("assistant", feedback_messages)
                    
                    if answer_text:
                        final_answer = f"{answer_text}\n\n{summary_text}"
                    else:
                        final_answer = summary_text

            # Send the final payload
            message_queue.put({
                "type": "final", 
                "agent": target_agent,
                "answer": final_answer,
                "tool_calls": tool_calls,
                "tool_logs": tool_logs
            })
            
        except Exception as e:
            print(f"❌ API Error: {str(e)}")
            message_queue.put({"type": "error", "content": str(e)})
        finally:
            # Poison pill to stop the generator
            message_queue.put(None) 

    # Start the processing in a separate background thread
    threading.Thread(target=background_worker, daemon=True).start()

    def event_generator():
        """Yields items from the queue over HTTP as soon as they are available."""
        while True:
            item = message_queue.get()
            if item is None:
                break
            yield json.dumps(item) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")