import json
import re
from openai import OpenAI
from app.agents.prompts import SYSTEM_PROMPTS, UI_TEXTS
from app.tools.registry import run_tool_by_name
import os

OLLAMA_CLIENT = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.getenv("OLLAMA_API_KEY", "ollama")
)

ALLOWED_TOOLS = {
    "developer": ["read_file", "list_directory", "write_file", "write_tool", "execute_python_code", "delegate_to_agent", "search_web", "scrape_web_page", "merge_draft"],
    "evaluator": ["delegate_to_agent", "merge_draft"],
    "orchestrator": ["search_memory", "delegate_to_agent", "search_web", "scrape_web_page", "task_complete", "merge_draft"],
    "assistant": ["search_web", "scrape_web_page", "delegate_to_agent", "task_complete", "merge_draft"],
    "analyst": ["read_file", "list_directory", "search_memory", "execute_python_code", "delegate_to_agent"]
}

def get_best_agent(messages: list[dict]) -> str:
    """
    Uses a fast LLM call to determine which agent is best suited for the request.
    """
    router_system_prompt = SYSTEM_PROMPTS.get("router", "You are a routing assistant. Return exactly one word in JSON.")
    
    context_msgs = messages[-3:] if len(messages) >= 3 else messages
    formatted_messages = [{"role": "system", "content": router_system_prompt}]
    for msg in context_msgs:
        if msg.get("role") != "system":
            formatted_messages.append({"role": msg["role"], "content": msg.get("content", "")})
            
    try:
        response = OLLAMA_CLIENT.chat.completions.create(
            model="llama3.1:8b", 
            messages=formatted_messages,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content or ""
        data = json.loads(content)
        selected_agent = data.get("agent", "assistant")
        
        if selected_agent not in ALLOWED_TOOLS:
            return "assistant"
        return selected_agent
    except Exception as e:
        print(f"Router error: {e}")
        return "assistant"

def get_agent_response(
    agent_key: str,
    messages: list[dict],
    temperature: float = 0.0
) -> tuple[str, list[dict]]:
    system_prompt = SYSTEM_PROMPTS.get(agent_key, "You are a helpful assistant.")
    agent_meta = UI_TEXTS["agents"].get(agent_key, {})
    model_name = agent_meta.get("default_model", "qwen2.5-coder:7b-instruct")

    formatted_messages = [{"role": "system", "content": system_prompt}]
    active_messages = messages[-10:] if len(messages) > 10 else messages
    
    for msg in active_messages:
        if msg.get("role") != "system":
            formatted_messages.append({"role": msg["role"], "content": msg.get("content", "")})

    try:
        kwargs = {
            "model": model_name,
            "messages": formatted_messages,
            "temperature": temperature
        }
        
        response = OLLAMA_CLIENT.chat.completions.create(**kwargs)
        content_text = response.choices[0].message.content or ""
        
        print(f"DEBUG [{agent_key}]: Raw response -> {content_text}")

        answer_text = ""
        tool_calls = []
        
        tool_call_match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", content_text, re.DOTALL)
        
        if tool_call_match:
            json_str = tool_call_match.group(1).strip()
            answer_text = re.sub(r"<tool_call>.*?</tool_call>", "", content_text, flags=re.DOTALL).strip()
            
            try:
                parsed_tool = json.loads(json_str, strict=False)
                if isinstance(parsed_tool, dict):
                    tool_calls = [parsed_tool]
                elif isinstance(parsed_tool, list):
                    tool_calls = parsed_tool
            except json.JSONDecodeError:
                print("Error: Assistant's <tool_call> contained invalid JSON.")
                answer_text += "\n\n[System Error: Tool call JSON formatting failed.]"
        
        else:
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1).strip()
                try:
                    parsed_json = json.loads(json_str, strict=False)
                    if isinstance(parsed_json, dict):
                        answer_text = parsed_json.get("message", "")
                        if not answer_text:
                            answer_text = content_text.replace(json_match.group(0), "").strip()
                        tool_calls = parsed_json.get("tools", [])
                except json.JSONDecodeError:
                    print("Error: Agent's returned JSON inside markdown block was corrupted.")
                    answer_text = content_text.strip()
                    tool_calls = []
            else:
                try:
                    parsed_json = json.loads(content_text.strip(), strict=False)
                    if isinstance(parsed_json, dict):
                        answer_text = parsed_json.get("message", content_text)
                        tool_calls = parsed_json.get("tools", [])
                except json.JSONDecodeError:
                    start_idx = content_text.find('{')
                    end_idx = content_text.rfind('}')
                    
                    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                        try:
                            json_str = content_text[start_idx:end_idx+1]
                            parsed_json = json.loads(json_str, strict=False)
                            if isinstance(parsed_json, dict):
                                answer_text = parsed_json.get("message", content_text[:start_idx].strip())
                                tool_calls = parsed_json.get("tools", [])
                        except json.JSONDecodeError:
                            answer_text = content_text.strip()
                            tool_calls = []
                    else:
                        answer_text = content_text.strip()
                        tool_calls = []

        for tc in tool_calls:
            tc["_agent_key"] = agent_key
            
        return answer_text, tool_calls

    except Exception as e:
        print(f"DEBUG: get_agent_response error: {e}")
        return f"❌ **Error:** {str(e)}", []


def _run_delegation_loop(target_internal_key: str, instruction: str, source_agent: str, max_steps: int = 15, status_callback=None, caller_chain=None) -> str:
    print(f"🔄 Starting internal delegation: {source_agent} -> {target_internal_key}")
    
    if status_callback:
        status_callback(f"🔄 **{source_agent.capitalize()}** delegated task to **{target_internal_key.capitalize()}**")
        
    delegation_messages = [{
        "role": "user", 
        "content": f"Your colleague ({source_agent}) has delegated a task to you:\n\n{instruction}\n\nInvestigate using your tools. Do not stop until the task is complete."
    }]
    
    for step in range(max_steps):
        if status_callback:
            status_callback(f"💭 **{target_internal_key.capitalize()}** is thinking (Step {step+1}/{max_steps})...")
            
        ans_text, t_calls = get_agent_response(target_internal_key, delegation_messages)

        if status_callback and ans_text:
            status_callback(f"🗣️ **{target_internal_key.capitalize()}**: {ans_text}")
        
        if not t_calls:
            if status_callback:
                status_callback(f"✅ **{target_internal_key.capitalize()}** completed their current workflow.")
            return f"[DELEGATION RESULT from {target_internal_key}]\n{ans_text}"
            
        if status_callback:
            tool_names = ", ".join([t.get("name", "unknown") for t in t_calls])
            status_callback(f"⚙️ **{target_internal_key.capitalize()}** is calling tools: {tool_names}")
            
        # Pass the caller_chain down to the next tool execution
        tool_logs = execute_pending_tools(t_calls, status_callback=status_callback, caller_chain=caller_chain)
        
        for log in tool_logs:
            result_str = str(log.get("result", ""))
            
            # BUBBLE UP CRITICAL ERRORS AND PAUSES IMMEDIATELY
            if "⚠️" in result_str or "🛑" in result_str or "[REQUIRES USER CONFIRMATION]" in result_str or "[ERROR] Permission denied" in result_str:
                if status_callback:
                    status_callback("🛑 Task execution halted by circuit breaker.")
                return result_str # Immediately break this agent's loop and bubble the error up!
        
        import json
        logs_str = json.dumps(tool_logs, indent=2, ensure_ascii=False)
        delegation_messages.append({
            "role": "user",
            "content": f"Tool executions completed. Results:\n{logs_str}\n\nWhat is your next step? If the work is completely done, reply normally without tools."
        })
        
    return f"[DELEGATION RESULT from {target_internal_key}]\nMaximum steps reached ({max_steps}). Last message:\n{ans_text}"


def execute_pending_tools(tool_calls: list[dict], status_callback=None, caller_chain=None) -> list[dict]:
    print(f"DEBUG: execute_pending_tools started, tools count: {len(tool_calls)}")
    tool_logs = []
    
    if caller_chain is None:
        caller_chain = []
    
    AGENT_NAME_MAP = {
        "Developer": "developer",
        "Evaluator": "evaluator",
        "Orchestrator": "orchestrator",
        "Assistant": "assistant",
        "Analyst": "analyst",
        "developer": "developer",
        "evaluator": "evaluator",
        "orchestrator": "orchestrator",
        "assistant": "assistant",
        "analyst": "analyst"
    }

    sorted_tool_calls = sorted(
        tool_calls, 
        key=lambda x: 0 if x.get("name") in ["write_file", "execute_python_code"] else 1
    )

    for tc in sorted_tool_calls:
        func_name = tc.get("name")
        func_args = tc.get("arguments", {})
        agent_key = tc.get("_agent_key", "assistant") 
        
        if status_callback and func_name != "delegate_to_agent":
             status_callback(f"🔨 Running tool: `{func_name}`...")
             
        if isinstance(func_args, dict):
            func_args_str = json.dumps(func_args, ensure_ascii=False)
        else:
            func_args_str = str(func_args)
            if isinstance(func_args, str):
                try:
                    func_args = json.loads(func_args)
                except json.JSONDecodeError:
                    func_args = {}
            
        allowed_tools = ALLOWED_TOOLS.get(agent_key, [])
        
        if func_name not in allowed_tools:
            tool_result = f"[ERROR] Permission denied for agent '{agent_key}' to use tool '{func_name}'."
        elif func_name == "delegate_to_agent":
            target_ui_name = func_args.get("target_agent", "")
            instruction = func_args.get("instruction", "")
            target_internal_key = AGENT_NAME_MAP.get(target_ui_name, "evaluator")
            
            # 🛑 CIRCUIT BREAKER: Prevent infinite ping-pong loops
            new_chain = caller_chain + [agent_key]
            if target_internal_key in new_chain:
                tool_result = f"[REQUIRES USER CONFIRMATION] 🛑 Delegation loop detected ({' -> '.join(new_chain)} -> {target_internal_key}). The agents are stuck and cannot resolve this. Please intervene."
                print(f"⚠️ Ping-Pong loop detected and stopped: {new_chain} -> {target_internal_key}")
            else:
                try:
                    tool_result = _run_delegation_loop(target_internal_key, instruction, agent_key, status_callback=status_callback, caller_chain=new_chain)
                except Exception as e:
                    tool_result = f"[ERROR] {str(e)}"
        else:
            from app.tools.registry import run_tool_by_name
            tool_result = run_tool_by_name(func_name, func_args)
        
        tool_logs.append({
            "tool": func_name,
            "arguments": func_args_str,
            "result": tool_result
        })
        
    return tool_logs