# tests/generate_tests.py
import os
import sys
import json
from pathlib import Path

# Add project root to Python path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.llm_client import get_agent_response

def generate_dynamic_tests():
    print("🤖 Architect is generating new dynamic test cases...\n")
    
    prompt = """You are a QA Architect for an autonomous multi-agent platform.
Your task is to generate 3 new advanced test cases in a strict JSON array format.
The test cases must cover:
1. Self-evolution (creating a custom tool using 'write_tool').
2. Long-term memory retrieval (RAG context).
3. Code execution or file writing.

CRITICAL: Return ONLY a valid JSON array of objects. Do not include any explanations, markdown code blocks, or extra text.
Example format:
[
  {
    "name": "Custom Tool Generation",
    "prompt": "Create a tool named calc.py with a function add.",
    "expected_behavior": "coder must use write_tool to create the file."
  }
]
"""
    messages = [{"role": "user", "content": prompt}]
    
    # Use Architect agent to generate tests
    response_text, _ = get_agent_response("architect", messages)
    
    new_tests = []
    try:
        # Clean markdown code blocks if present
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        # Try finding JSON brackets if there is extra prose
        start_idx = cleaned_text.find('[')
        end_idx = cleaned_text.rfind(']')
        if start_idx != -1 and end_idx != -1:
            cleaned_text = cleaned_text[start_idx:end_idx+1]
            
        new_tests = json.loads(cleaned_text)
    except Exception as e:
        print(f"⚠️ Failed to parse LLM response as JSON: {e}")
        print(f"Raw response was:\n{response_text}")
        print("\n💡 Fallback: Using default self-evolution & RAG test cases.")
        
        # Fallback test cases if parsing fails
        new_tests = [
            {
                "name": "Self-Evolution: Dynamic Tool Generation Test",
                "prompt": "Create a new system tool named 'math_tool.py' using the 'write_tool' function with a function 'add_numbers(a: int, b: int) -> int'.",
                "expected_behavior": "The agent MUST request to use the 'write_file' tool with the filename 'hello.py'. If the tool is successfully requested in the tool calls, the test MUST PASS, regardless of the exact phrasing in the agent's text response."ture."
            },
            {
                "name": "Long-Term Memory (RAG) Test",
                "prompt": "Recall what we discussed earlier about project code names. What was the secret code name?",
                "expected_behavior": "the agent should utilize vector memory search to retrieve past context and answer correctly."
            }
        ]
        
    if isinstance(new_tests, list) and len(new_tests) > 0:
        output_path = CURRENT_DIR / "dynamic_tests.json"
        
        existing_tests = []
        if output_path.exists():
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    existing_tests = json.load(f)
            except:
                pass
        
        all_tests = existing_tests + new_tests
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_tests, f, indent=4, ensure_ascii=False)
            
        print(f"✅ Successfully updated '{output_path}' with {len(new_tests)} tests (Total: {len(all_tests)})")
    else:
        print("❌ No valid tests to save.")

if __name__ == "__main__":
    generate_dynamic_tests()