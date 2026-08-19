import os
import subprocess
import importlib.util
import inspect
from pathlib import Path
from app.core.vector_db import search_memory
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
import difflib

# Locate the directory of this file (registry.py)
CURRENT_FILE_DIR = Path(__file__).resolve().parent

# Go up two levels to the project root (app/tools -> app -> root)
BASE_DIR = CURRENT_FILE_DIR.parent.parent 

WORKSPACE_DIR = BASE_DIR / "data" / "workspace"
WORKSPACE_DIR.mkdir(exist_ok=True, parents=True)

def merge_draft(**kwargs) -> str:
    """
    Merges a proposed .draft file into the original existing file.
    Evaluator agent should use this after reviewing the developer's code.
    If user_approved=False, it blocks the action and shows a Diff to the user for approval.
    """
    # Cast a wider net for LLM hallucinations
    original_file = (
        kwargs.get("original_file") or 
        kwargs.get("file_path") or 
        kwargs.get("path") or 
        kwargs.get("main_file_path") or 
        kwargs.get("target_file")
    )
    
    if not original_file:
        return "[ERROR] Must provide a valid original_file or file_path."

    # ==========================================
    # IDIOOTTIVARMISTUS: Estetään .draft-päätteen tuplaus
    # ==========================================
    original_file = str(original_file).replace("\\", "/")
    if original_file.endswith(".draft"):
        original_file = original_file[:-6]  # Poistaa lopusta ".draft"

    draft_file = (
        kwargs.get("draft_file") or 
        kwargs.get("draft_file_path") or 
        kwargs.get("draft_path")
    )
    
    # If the agent only provided the main file, infer the draft file name automatically
    if not draft_file:
        draft_file = f"{original_file}.draft"
        
    # Handle user_approved passed as string or boolean
    user_approved_arg = kwargs.get("user_approved", False)
    user_approved = str(user_approved_arg).lower() == "true" if isinstance(user_approved_arg, str) else bool(user_approved_arg)

    # Clean up paths (Assume WORKSPACE_DIR is correctly defined above in the file)
    orig_path = (WORKSPACE_DIR / str(original_file).replace("data/workspace/", "").replace("workspace/", "")).resolve()
    draft_path = (WORKSPACE_DIR / str(draft_file).replace("data/workspace/", "").replace("workspace/", "")).resolve()

    if not orig_path.exists():
        return f"[ERROR] Original file not found: {original_file}"
    if not draft_path.exists():
        return f"[ERROR] Draft file not found: {draft_file}. The developer must create this file first using write_file."

    # Read contents for diff
    try:
        with open(orig_path, "r", encoding="utf-8") as f:
            old_content = f.read()
        with open(draft_path, "r", encoding="utf-8") as f:
            new_content = f.read()
    except Exception as e:
        return f"[ERROR] Could not read files: {str(e)}"

    # If the user hasn't approved yet, generate a Diff and halt execution (Fast-Fail)
    if not user_approved:
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            old_lines, new_lines, 
            fromfile='Current Code', 
            tofile='Proposed Code', 
            n=4
        ))
        
        diff_text = "".join(diff) if diff else "No changes detected."
        
        return (
            f"[REQUIRES USER CONFIRMATION]\n\n"
            f"**Code Review / Pull Request**\n\n"
            f"Target file: `{original_file}`\n\n"
            f"**🔍 PROPOSED CHANGES:**\n```diff\n{diff_text}\n```\n\n"
            f"*(System: Stop executing. Wait for the user to click the UI buttons to approve or reject.)*"
        )

    # If approved, perform "Merge" (overwrite original and delete draft)
    try:
        with open(orig_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        import os
        os.remove(draft_path)
        
        return f"[SUCCESS] The file {original_file} was successfully updated and the draft was cleaned up."
    except Exception as e:
        return f"[ERROR] Failed to merge files: {str(e)}"
# ==========================================
# AGENT-TO-AGENT COMMUNICATION
# ==========================================

def delegate_to_agent(target_agent: str, instruction: str) -> str:
    """
    Calls another agent in the system to help with a specific task.
    """
    return (
        f"[SYSTEM ERROR] Delegation to agent '{target_agent}' received in the tool registry. "
        f"The orchestrator (llm_client.py) should intercept the 'delegate_to_agent' call and handle it in the Auto-Loop!"
    )

# ==========================================
# CODER CORE TOOLS
# ==========================================

def write_file(**kwargs) -> str:
    """
    Writes content to a file.
    Accepts 'file_path', 'filepath', or 'path'.
    """
    # 1. Laajennettu haavi argumenteille
    file_path = kwargs.get("file_path") or kwargs.get("filepath") or kwargs.get("path")
    content = kwargs.get("content", "")
    
    if not file_path:
        return "[ERROR] Must provide a valid file_path."
        
    # 2. Estetään tiedostonimien hallusinaatiot (kuten .draft.draft)
    file_path = str(file_path).replace("\\", "/")
    if file_path.endswith(".draft.draft"):
        file_path = file_path.replace(".draft.draft", ".draft")
        
    # 3. Korjataan tekoälyn JSON-rivinvaihto-ongelmat
    # Jos LLM lähettää tupla-escapetetun rivinvaihdon (\n), muutetaan se oikeaksi rivinvaihdoksi.
    if "\\n" in content and "\\\\n" not in content:
        content = content.replace("\\n", "\n")
        
    # Puhdistetaan polku (Oletetaan että WORKSPACE_DIR on määritelty aiemmin tiedostossa)
    target_path = (WORKSPACE_DIR / file_path.replace("data/workspace/", "").replace("workspace/", "")).resolve()
    
    # ==========================================
    # UUSI SUOJAMUURI: Estetään olemassa olevien tiedostojen suora ylikirjoitus!
    # ==========================================
    if target_path.exists() and not str(file_path).endswith(".draft"):
        return (
            f"[ERROR] DIRECT OVERWRITE BLOCKED! You cannot modify '{file_path}' directly. "
            f"You MUST write your changes to a draft file instead (e.g., '{file_path}.draft')."
        )
        
    # Tietoturvatarkistus: Varmistetaan ettei tallenneta workspacen ulkopuolelle
    try:
        target_path.relative_to(WORKSPACE_DIR)
    except ValueError:
        return f"[ERROR] Access denied. Cannot write files outside the workspace directory."
        
    # Varmistetaan, että kansiorakenne on olemassa
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Kirjoitetaan tiedosto
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        # 4. HÄTÄJARRU: Pakotetaan agentti siirtymään eteenpäin!
        return (
            f"[SUCCESS] File successfully written to {file_path}. "
            f"CRITICAL INSTRUCTION: DO NOT call the 'write_file' tool again for this file. "
            f"You MUST proceed immediately to the next step (e.g., test the code with execute_python_code or create a PR with merge_draft)."
        )
    except Exception as e:
        return f"[ERROR] Failed to write file: {str(e)}"

def execute_python_code(**kwargs) -> str:
    """
    Safely tests a python file for syntax errors. 
    Accepts filepath, path, or file_path.
    """
    filepath = kwargs.get("filepath") or kwargs.get("path") or kwargs.get("file_path")
    
    if not filepath:
        return "❌ ERROR: Missing filepath argument."

    normalized_path = str(filepath).replace("\\", "/")
    
    if normalized_path.startswith("data/workspace/"):
        normalized_path = normalized_path[len("data/workspace/"):]
    elif normalized_path.startswith("workspace/"):
        normalized_path = normalized_path[len("workspace/"):]

    target_path = (WORKSPACE_DIR / normalized_path).resolve()

    if not str(target_path).endswith((".py", ".draft")):
        return "❌ SECURITY ERROR: Only .py or .draft files are allowed."
        
    if not target_path.exists():
        return f"❌ ERROR: File not found for syntax check: {normalized_path}"

    print(f"\n[SYSTEM] Running secure syntax check on: {normalized_path}")
    
    command = ["python", "-m", "py_compile", str(target_path)]
    
    try:
        result = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0:
            return "✅ SUCCESS: Code compiled successfully. No syntax errors detected."
        else:
            return f"❌ ERROR (Syntax):\n{result.stderr}\n{result.stdout}"
            
    except subprocess.TimeoutExpired:
        return "❌ CRITICAL ERROR: Execution timed out."
    except Exception as e:
        return f"❌ SYSTEM ERROR: {str(e)}"

# Assume WORKSPACE_DIR is defined somewhere, e.g., Path("data/workspace").resolve()
WORKSPACE_DIR = Path("data/workspace").resolve()

def read_file(**kwargs) -> str:
    """
    Reads the content of a file.
    """
    actual_path = kwargs.get("file_path") or kwargs.get("filename") or kwargs.get("path")
    if not actual_path:
         return "[ERROR] Agent failed to provide a valid file_path."
         
    target_path = (WORKSPACE_DIR / actual_path).resolve()
    
    # Safe boundary check using relative_to (Python 3.9+)
    try:
        target_path.relative_to(WORKSPACE_DIR)
    except ValueError:
        return f"[ERROR] Access denied. Path must be within {WORKSPACE_DIR}"
        
    if not target_path.exists():
        # Provide spatial awareness to the agent
        current_dirs = [d.name for d in WORKSPACE_DIR.iterdir() if d.is_dir()]
        return (
            f"[ERROR] File not found at '{target_path}'. "
            f"You are currently restricted to the workspace root. "
            f"Available directories here include: {', '.join(current_dirs)}. "
            f"Please use list_directory to explore further before guessing the path."
        )
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
         return f"[ERROR] Failed to read file: {str(e)}"

def list_directory(**kwargs) -> str:
    """
    Lists the contents of a directory.
    Accepts 'directory_path', 'path', 'dir', or 'folder'.
    """
    actual_path = (
        kwargs.get("directory_path") or 
        kwargs.get("path") or 
        kwargs.get("dir") or 
        kwargs.get("folder") or 
        ""
    )
    
    target_path = (WORKSPACE_DIR / str(actual_path)).resolve()
    
    try:
        target_path.relative_to(WORKSPACE_DIR)
    except ValueError:
        return f"[ERROR] Access denied. Cannot list directories outside the workspace: {WORKSPACE_DIR}"
        
    if not target_path.exists() or not target_path.is_dir():
        root_dirs = [d.name for d in WORKSPACE_DIR.iterdir() if d.is_dir()]
        return (
            f"[ERROR] Directory not found at '{target_path.name}'. "
            f"You are currently restricted to the workspace root. "
            f"Available directories here include: {', '.join(root_dirs)}. "
            f"Please ensure you are providing the correct relative path."
        )
        
    try:
        items = []
        for item in target_path.iterdir():
            item_type = "DIR" if item.is_dir() else "FILE"
            items.append(f"[{item_type}] {item.name}")
            
        if not items:
            return f"[RESULT] Directory '{target_path.relative_to(WORKSPACE_DIR)}' is empty."
            
        return f"[RESULT] Contents of '{target_path.relative_to(WORKSPACE_DIR)}':\n" + "\n".join(items)
    except Exception as e:
        return f"[ERROR] Failed to list directory: {str(e)}"

def search_web(query: str, max_results: int = 3) -> str:
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="wt-wt", max_results=max_results):
                results.append(r)
        if not results:
            return f"[INFO] No search results found for query: '{query}'."
            
        formatted_results = []
        for i, res in enumerate(results, 1):
            title = res.get('title', 'No title')
            href = res.get('href', '#')
            body = res.get('body', 'No description')
            formatted_results.append(f"{i}. **{title}**\n   URL: {href}\n   Description: {body}\n")
        return "\n".join(formatted_results)
    except Exception as e:
        return f"[ERROR] Web search failed: {str(e)}"

def scrape_web_page(url: str) -> str:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            element.decompose()
            
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_text = "\n".join(lines)
        
        if len(cleaned_text) > 3000:
            cleaned_text = cleaned_text[:3000] + "\n\n[INFO] Content truncated."
            
        return f"[WEB PAGE CONTENT of {url}]\n\n{cleaned_text}"
    except Exception as e:
        return f"[ERROR] Web scraping failed ({str(e)})."

# ==========================================
# AUTONOMOUS TOOL CREATION
# ==========================================

def task_complete(summary: str = "") -> str:
    """
    Use this tool ONLY when the ENTIRE workflow is successfully finished.
    This tells the system that no more actions are needed.
    """
    return f"[WORKFLOW_COMPLETED] Task successfully marked as complete. Summary: {summary}"

def write_tool(filename: str, content: str) -> str:
    normalized_path = str(filename).replace("\\", "/")
    if normalized_path.startswith("app/tools/"):
        normalized_path = normalized_path[len("app/tools/"):]
    elif normalized_path.startswith("workspace/"):
        normalized_path = normalized_path[len("workspace/"):]
        
    if not normalized_path.endswith(".py"):
        normalized_path += ".py"
        
    target_path = (CURRENT_FILE_DIR / normalized_path).resolve()
    
    if not str(target_path).startswith(str(CURRENT_FILE_DIR)):
        return f"[ERROR] Access denied. Tools can only be written to app/tools/ directory."
        
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        global AVAILABLE_TOOLS
        AVAILABLE_TOOLS = load_all_tools()
        
        line_count = len(content.splitlines())
        return f"[SUCCESS] New tool '{normalized_path}' successfully written to app/tools/ and auto-registered! Verified {line_count} lines of code written."
    except Exception as e:
        return f"[ERROR] Failed to write tool: {str(e)}"
        
# ==========================================
# DYNAMIC REGISTRY LOADER (PLUGIN SYSTEM)
# ==========================================

def load_all_tools():
    tools = {
        "merge_draft": merge_draft,
        "task_complete": task_complete,
        "write_file": write_file,
        "execute_python_code": execute_python_code,
        "read_file": read_file,
        "list_directory": list_directory,
        "search_memory": search_memory,
        "delegate_to_agent": delegate_to_agent,
        "search_web": search_web,
        "scrape_web_page": scrape_web_page,
        "write_tool": write_tool
    }
    
    for file_path in CURRENT_FILE_DIR.glob("*.py"):
        module_name = file_path.stem
        if module_name in ["__init__", "registry"]:
            continue
            
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                for name, obj in inspect.getmembers(module, inspect.isfunction):
                    if obj.__module__ == module.__name__ and not name.startswith("_"):
                        tools[name] = obj
        except Exception as e:
            print(f"[WARNING] Error loading dynamic tool from {file_path.name}: {e}")
            
    return tools

AVAILABLE_TOOLS = load_all_tools()

def run_tool_by_name(tool_name: str, arguments: dict) -> str:
    """
    Safely routes the tool execution and prevents unexpected keyword argument crashes.
    """
    # Map the tool names to their actual Python functions
    TOOL_MAP = {
        "read_file": read_file,
        "write_file": write_file,
        "list_directory": list_directory,
        "execute_python_code": execute_python_code,
        "merge_draft": merge_draft,
        "search_web": search_web,
        "scrape_web_page": scrape_web_page,
        "search_memory": search_memory
    }
    
    func = TOOL_MAP.get(tool_name)
    
    if not func:
        return f"[ERROR] Tool '{tool_name}' does not exist in the registry."
        
    try:
        # Pass the dictionary safely using ** unpacking
        return func(**arguments)
    except TypeError as te:
        return f"[ERROR] Tool execution failed due to argument mismatch. Make sure the tool function accepts **kwargs. Error: {str(te)}"
    except Exception as e:
        return f"[ERROR] Tool execution failed: {str(e)}"