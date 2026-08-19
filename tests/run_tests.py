# tests/run_tests.py
import os
import sys
import json
import argparse
from datetime import datetime

# Lisätään projektin juurikansio Pythonin etsintäpolkuun
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.llm_client import get_best_agent, get_agent_response
from app.core.vector_db import add_to_memory

CURRENT_DIR = os.path.dirname(__file__)

STATIC_TEST_CASES = [
    {
        "name": "Router Test: Basic Math (Chat)",
        "prompt": "What is 10 + 15?",
        "expected_behavior": "The response must contain the number 25. No tools should be requested."
    },
    {
        "name": "Coder Tool Usage: Write File",
        "prompt": "Write a Python script that prints 'Hello World' and save it as hello.py in the workspace.",
        "expected_behavior": "The agent MUST request to use the 'write_file' tool. If 'write_file' is present in the Requested Tools list, you MUST score this as PASS. Do NOT expect the file to actually exist or the agent to confirm the creation, as this test environment does not execute tools."
    },
    {
        "name": "Architect Logic: Project Planning",
        "prompt": "Plan a folder structure for a new web game. Do not write code yet.",
        "expected_behavior": "The agent should act as a planner and outline a structure. It should NOT execute python code."
    }
]

def load_dynamic_tests():
    """Loads dynamically generated tests if they exist and are valid."""
    dynamic_tests_path = os.path.join(CURRENT_DIR, "dynamic_tests.json")
    if os.path.exists(dynamic_tests_path):
        try:
            with open(dynamic_tests_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                tests = json.loads(content)
                return tests if isinstance(tests, list) else []
        except Exception as e:
            print(f"⚠️ Could not load dynamic tests (resetting to empty): {e}")
            return []
    return []

from pathlib import Path

def generate_dynamic_tests():
    """Uses Architect agent to generate new test cases with 100% bulletproof fallback and safe file handling."""
    print("🤖 Architect is generating new dynamic test cases...")
    prompt = """You are a Senior QA Architect for an autonomous multi-agent platform.
Your task is to generate 2 new, unique, and highly challenging test cases in a strict JSON array format.

To make the tests relevant, do NOT just ask for basic file writing. Instead, design tests that evaluate the agents' advanced capabilities. Choose two DIFFERENT focus areas from the list below:
1. Delegation: A complex task where an agent must use 'delegate_to_agent' to ask another agent for help.
2. Anti-Hallucination: A tricky prompt that tries to trick the agent into guessing information, forcing it to use 'search_memory' instead.
3. Web Research: A task requiring the agent to use 'search_web' or 'scrape_web_page' to find real-time information.
4. Tool Creation: Asking the coder to use 'write_tool' to build something highly specific (e.g., a tool that calculates Fibonacci sequences).

CRITICAL: Return ONLY a valid JSON array of objects. Do not include any explanations, markdown code blocks, or extra text. Start your response with '[' and end with ']'.
Example format:
[
  {
    "name": "Tricky Memory Search Test",
    "prompt": "What was the access code for the mainframe we discussed last week?",
    "expected_behavior": "The agent MUST request to use the 'search_memory' tool. If it attempts to use it, score PASS. Do NOT expect the agent to answer the question, as tools are not executed."
  }
]
"""
    try:
        response_text, _ = get_agent_response("architect", [{"role": "user", "content": prompt}])
    except Exception as e:
        response_text = ""
    
    new_tests = []
    if response_text and response_text.strip():
        try:
            cleaned = response_text.strip()
            # Poistetaan erikoismerkit ja markdown-koodiblokit
            cleaned = cleaned.replace('\xa0', ' ').replace('\r', '')
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1]
            if "```" in cleaned:
                cleaned = cleaned.split("```")[0]
            cleaned = cleaned.strip()
            
            start_idx = cleaned.find('[')
            end_idx = cleaned.rfind(']')
            
            if start_idx != -1 and end_idx != -1:
                json_str = cleaned[start_idx:end_idx+1]
                parsed = json.loads(json_str)
                if isinstance(parsed, list) and len(parsed) > 0:
                    new_tests = parsed
        except Exception as parse_err:
            print(f"⚠️ JSON parsing warning (using safe fallback): {parse_err}")

    # Jos LLM-vastaus tai parsiminen epäonnistui, käytetään aina varmaa fallback-testiä
    if not new_tests:
        new_tests = [
            {
                "name": "Self-Evolution: Dynamic Tool Generation",
                "prompt": "Create a new tool named dynamic_tool.py using write_tool with a sample function.",
                "expected_behavior": "The agent MUST request to use the 'write_tool' tool. If 'write_tool' is present in the Requested Tools list, you MUST score this as PASS. Do NOT expect the file to actually exist or the agent to confirm the creation, as this test environment does not execute tools."
            },
            {
                "name": "File Writing & Execution Test",
                "prompt": "Write a python script that outputs test results to a file.",
                "expected_behavior": "The agent MUST request to use the 'write_tool' or 'write_file' tool. If it is present in the Requested Tools list, you MUST score this as PASS. Do NOT expect the script to be executed or the output to exist, as this test environment does not execute tools."
            }
        ]

    # Turvallinen tallennus Pathlibillä (ei tiedostolukkoja Windowsilla)
    output_path = Path(CURRENT_DIR) / "dynamic_tests.json"
    existing = load_dynamic_tests()
    all_tests = existing + new_tests
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_tests, f, indent=4, ensure_ascii=False)
        print(f"✅ Successfully generated and saved {len(new_tests)} test cases.")
    except Exception as write_err:
        raise ValueError(f"Failed to write dynamic tests file: {write_err}")

def evaluate_with_ai(prompt, expected, actual_response, requested_tools):
    """Uses AI as a judge to evaluate if the test succeeded."""
    tools_str = json.dumps([t["name"] for t in requested_tools]) if requested_tools else "No tools requested"
    judge_prompt = f"""You are an impartial AI judge evaluating an AI agent's performance.

USER PROMPT: {prompt}
EXPECTED BEHAVIOR: {expected}

AGENT TEXT RESPONSE: {actual_response}
AGENT REQUESTED TOOLS: {tools_str}

Did the agent successfully fulfill the expected behavior?
Analyze briefly, then on the VERY LAST LINE write exactly one word: PASS or FAIL.
"""
    evaluation_text, _ = get_agent_response("chat", [{"role": "user", "content": judge_prompt}])
    return evaluation_text

import uuid

# tests/run_tests.py (osio run_all_tests-funktiosta)
def run_all_tests(progress_callback=None, on_test_start=None, on_test_complete=None, stop_checker=None, start_index=0, existing_report=None, skip_first=False, run_mode="all", single_test_index=None):
    """Runs all static and dynamic tests, supporting real-time streaming, resuming, and skipping."""
    import uuid
    unique_code_name = f"Project-Aegis-{uuid.uuid4().hex[:6].upper()}"
    
    add_to_memory(
        message_id=888888, 
        session_id="test_evaluation_session", 
        role="user", 
        content=f"The secret project code name is {unique_code_name}."
    )
    
    dynamic_tests = load_dynamic_tests()
    
    # --- UUSI TILA-LOGIIKKA ---
    if run_mode == "dynamic":
        all_tests = dynamic_tests
    elif run_mode == "single" and single_test_index is not None:
        if 0 <= single_test_index < len(dynamic_tests):
            all_tests = [dynamic_tests[single_test_index]]
        else:
            all_tests = []
    else:
        rag_test = {
            "name": "Long-Term Memory (RAG) Validation Test",
            "prompt": "You are the Architect agent. I command you to explicitly use your search_memory tool to find out what we discussed earlier about project code names. What is the secret code name?",
            "expected_behavior": f"The agent MUST request the memory search tool and retrieve the exact code name '{unique_code_name}'."
        }
        all_tests = STATIC_TEST_CASES + [rag_test] + dynamic_tests
        
    total_tests = len(all_tests)
    
    # ... alkuperäinen koodi jatkuu tästä (If existing_report...)
    
    # Ladataan aiempi tila, jos testejä jatketaan napin painalluksen jälkeen
    if existing_report:
        report_data = existing_report
        passed = report_data.get("passed", 0)
    else:
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total_tests,
            "passed": 0,
            "failed": 0,
            "results": []
        }
        passed = 0
    
    for i in range(start_index, total_tests):
        test = all_tests[i]
        
        if stop_checker and stop_checker():
            print("🛑 Test execution stopped by user.")
            break
            
        # JOS KÄYTTÄJÄ PAINOI SKIP-NAPPIA:
        if skip_first and i == start_index:
            test_result = {
                "test_name": test.get('name', 'Unnamed Test'),
                "prompt": test.get('prompt', ''),
                "expected_behavior": test.get('expected_behavior', ''),
                "selected_agent": "-",
                "agent_response": "Test skipped by user to save time.",
                "requested_tools": [],
                "status": "SKIPPED",
                "judge_reasoning": "User manually skipped this test."
            }
            report_data["results"].append(test_result)
            if on_test_complete:
                on_test_complete(test_result, report_data)
            continue # Hypätään suoraan seuraavaan testiin
            
        if progress_callback:
            progress_callback(i + 1, total_tests, test.get('name', 'Test'))
            
        if on_test_start:
            on_test_start(test)
            
        messages = [{"role": "user", "content": test.get('prompt', '')}]
        best_agent = get_best_agent(messages)
        answer_text, tools = get_agent_response(best_agent, messages)
        
        eval_result = evaluate_with_ai(
            test.get('prompt', ''), 
            test.get('expected_behavior', ''), 
            answer_text, 
            tools
        )
        
        is_pass = "PASS" in eval_result.upper().split()[-5:]
        
        test_result = {
            "test_name": test.get('name', 'Unnamed Test'),
            "prompt": test.get('prompt', ''),
            "expected_behavior": test.get('expected_behavior', ''),
            "selected_agent": best_agent,
            "agent_response": answer_text,
            "requested_tools": [t["name"] for t in tools] if tools else [],
            "status": "PASS" if is_pass else "FAIL",
            "judge_reasoning": eval_result
        }
        
        report_data["results"].append(test_result)
        if is_pass:
            passed += 1
            
        report_data["passed"] = passed
        report_data["failed"] = len([r for r in report_data["results"] if r["status"] == "FAIL"])
        report_data["total_tests"] = len(all_tests) 
        
        if on_test_complete:
            on_test_complete(test_result, report_data)
            
    reports_dir = os.path.join(CURRENT_DIR, "test_reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_filename = os.path.join(reports_dir, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_filename, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=4, ensure_ascii=False)
        
    return report_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Test Runner")
    parser.add_argument("--generate", action="store_true", help="Generate new dynamic tests")
    args = parser.parse_args()
    
    if args.generate:
        generate_dynamic_tests()
    else:
        run_all_tests()

import os

import os

def request_ai_fix(test_name, prompt, expected, actual_response, judge_reasoning):
    """Asks Architect agent to inspect SPECIFIC files and suggest a precise fix."""
    import os
    
    code_context = ""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")) 
    
    # 🎯 WHITELIST: Vain nämä tiedostot annetaan Arkkitehdille luettavaksi ja korjattavaksi!
    # Voit myöhemmin lisätä tähän listaan tiedostoja, jos haluat sen korjaavan esim. työkaluja.
    allowed_files = [
        "tests/run_tests.py",
        "tests/dynamic_tests.json"
        # "app/tools/code_runner.py",  <- Esimerkki: ota kommentti pois jos haluat sen näkevän tämän
    ]
    
    for rel_path in allowed_files:
        # Korjataan polkujen vinoviivat Windows/Linux-yhteensopiviksi
        file_path = os.path.join(project_root, rel_path.replace("/", os.sep))
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code_context += f"\n\n--- FILE: {rel_path} ---\n{f.read()}"
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

    fix_prompt = f"""An automated test failed in our autonomous multi-agent platform.

TEST NAME: {test_name}
PROMPT: {prompt}
EXPECTED BEHAVIOR: {expected}
AGENT RESPONSE: {actual_response}
JUDGE REASONING: {judge_reasoning}

--- ALLOWED CODEBASE CONTEXT ---
{code_context}

CRITICAL INSTRUCTIONS FOR ARCHITECT:
You are an expert Senior QA Architect. You MUST follow this exact debugging checklist before suggesting ANY fixes. DO NOT SKIP STEPS.

Step 1. READ THE JUDGE REASONING CAREFULLY: Why exactly did the Judge fail the test?
Step 2. IDENTIFY THE FLAW: If the agent didn't use a tool when it should have, the test's `prompt` needs to be stronger, OR the agent didn't have access to the tool. 
Step 3. FIX ONLY WHAT YOU CAN SEE: You are only allowed to suggest fixes for the files provided in the ALLOWED CODEBASE CONTEXT above. Do not invent or fix files that are not explicitly listed there.

OUTPUT FORMAT RULES (CRITICAL):
If you suggest a code fix, you MUST provide the ENTIRE updated file content at the very end of your response using EXACTLY this format:

---FIX_START---
FILE: relative/path/to/file.py
CONTENT:
<put the ENTIRE fixed code here. DO NOT use markdown code blocks like ```python. DO NOT use placeholders like '# ... rest of code here ...'. You MUST write the exact, complete, and runnable file content from the first import to the last line.>
---FIX_END---

Based on the checklist above, analyze the root cause and provide:
1. Exact root cause (referencing the checklist).
2. Concrete corrections explained briefly.
3. The FIX_START block with the complete, updated file content.
"""
    # Kutsutaan AI arvioimaan (varmista, että get_agent_response on käytettävissä tässä tiedostossa)
    fix_response, _ = get_agent_response("architect", [{"role": "user", "content": fix_prompt}])
    return fix_response