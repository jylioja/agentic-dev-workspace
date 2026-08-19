import os
import sys
import json
import glob
import re
import shutil
from datetime import datetime

# Lisätään projektin juurikansio Pythonin etsintäpolkuun (sys.path)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.llm_client import get_agent_response

# Määritetään dynaamiset polut suhteessa tämän skriptin sijaintiin (tests/ -kansioon)
CURRENT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..'))

PROMPTS_FILE_PATH = os.path.join(ROOT_DIR, "app", "agents", "prompts.py")
REPORTS_DIR = os.path.join(CURRENT_DIR, "test_reports")

def get_latest_report():
    """Finds the most recent test report JSON file."""
    if not os.path.exists(REPORTS_DIR):
        return None
    
    list_of_files = glob.glob(os.path.join(REPORTS_DIR, "*.json"))
    if not list_of_files:
        return None
        
    latest_file = max(list_of_files, key=os.path.getctime)
    return latest_file

def extract_python_code(text):
    """Extracts python code from the LLM's markdown response."""
    match = re.search(r'```(?:python)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def run_optimizer():
    print("🧠 Starting Prompt Optimizer Agent...\n")
    
    # 1. Find the latest report
    latest_report_path = get_latest_report()
    if not latest_report_path:
        print(f"❌ ERROR: No test reports found in '{REPORTS_DIR}' directory.")
        return

    print(f"📄 Analyzing report: {latest_report_path}")
    
    with open(latest_report_path, "r", encoding="utf-8") as f:
        try:
            report_data = json.load(f)
        except json.JSONDecodeError:
            print("❌ ERROR: Could not read the report JSON.")
            return
            
    # 2. Check if there are any failures
    failed_tests = [test for test in report_data.get("results", []) if test.get("status") == "FAIL"]
    
    if not failed_tests:
        print("✅ No failed tests in the latest report. Prompts are optimal. Exiting.")
        return
        
    print(f"⚠️ Found {len(failed_tests)} failed test(s). Preparing optimization task...")
    
    # 3. Read current prompts.py
    if not os.path.exists(PROMPTS_FILE_PATH):
        print(f"❌ ERROR: Could not find {PROMPTS_FILE_PATH}")
        return
        
    with open(PROMPTS_FILE_PATH, "r", encoding="utf-8") as f:
        current_prompts_code = f.read()
        
    # 4. Prepare the failure data for the LLM
    failure_details = ""
    for fail in failed_tests:
        failure_details += f"--- TEST FAILURE ---\n"
        failure_details += f"Test Name: {fail.get('test_name')}\n"
        failure_details += f"User Prompt: {fail.get('prompt')}\n"
        failure_details += f"Assigned Agent: {fail.get('selected_agent')}\n"
        failure_details += f"Judge Reasoning (Why it failed): {fail.get('judge_reasoning')}\n\n"

    # 5. Build the prompt for the AI Prompt Engineer
    md_ticks = "```"
    
    optimization_prompt = f"""You are an Expert AI Prompt Engineer. Your job is to improve the instructions of other AI agents to fix their test failures.

    CURRENT `prompts.py` FILE:
    {md_ticks}python
    {current_prompts_code}
    {md_ticks}

    FAILED TESTS LOG:
    {failure_details}

    YOUR TASK:
    1. Analyze the "Judge Reasoning" to understand exactly why the agent failed.
    2. Rewrite the specific SYSTEM PROMPTS (e.g., CODER_PROMPT, ARCHITECT_PROMPT) in the code to strictly prevent these failures. Add new rules or constraints if necessary.
    3. Keep the UI_TEXTS and the SYSTEM_PROMPTS dictionary structure exactly as they are. Only change the text inside the prompt strings.
    4. Output the ENTIRE updated prompts.py python code.

    OUTPUT FORMAT:
    You MUST wrap the complete updated Python code inside a markdown block ({md_ticks}python ... {md_ticks}). Do not include any text outside the code block.
    """

    messages = [{"role": "user", "content": optimization_prompt}]

    # 6. Ask the Architect to act as the Prompt Engineer
    print("⏳ AI Prompt Engineer is rewriting the prompts to fix the failures... This may take a minute.")
    response_text, _ = get_agent_response("architect", messages)

    new_code = extract_python_code(response_text)

    if not new_code:
        print("❌ ERROR: Failed to extract Python code from the agent's response.")
        print("Raw response:")
        print(response_text)
        return
        
    # 7. Create a backup and overwrite the prompts.py file
    backup_path = f"{PROMPTS_FILE_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(PROMPTS_FILE_PATH, backup_path)
    print(f"💾 Created backup of current prompts: {backup_path}")
    
    with open(PROMPTS_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_code)
        
    print(f"✅ SUCCESS! The file '{PROMPTS_FILE_PATH}' has been successfully updated with new prompts.")
    print("🚀 Run the tests again to see if the optimization worked!")

if __name__ == "__main__":
    run_optimizer()