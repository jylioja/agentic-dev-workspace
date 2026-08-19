# app/tools/file_tools.py
from pathlib import Path

# Käytetään .resolve() heti alussa, jotta saamme absoluuttisen, todellisen polun vertailuja varten
WORKSPACE_DIR = Path("data/workspace").resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def read_file(filename: str) -> dict:
    """
    Reads the content of a file from the data/workspace directory.
    """
    try:
        # .resolve() purkaa mahdolliset "../" yritykset
        file_path = (WORKSPACE_DIR / filename).resolve()
        
        # Tietoturvalukko: Estetään karkaaminen työtilasta
        if not file_path.is_relative_to(WORKSPACE_DIR):
             return {"success": False, "error": "Access denied. Path traversal attempt detected."}
             
        if not file_path.exists():
            return {"success": False, "error": f"File '{filename}' not found."}
        
        content = file_path.read_text(encoding="utf-8")
        return {"success": True, "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(filename: str, content: str) -> dict:
    """
    Writes or overwrites a file in the data/workspace directory.
    Automatically creates necessary subdirectories if they do not exist.
    """
    try:
        file_path = (WORKSPACE_DIR / filename).resolve()
        
        # Tietoturvalukko
        if not file_path.is_relative_to(WORKSPACE_DIR):
             return {"success": False, "error": "Access denied. Path traversal attempt detected."}
             
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"success": True, "message": f"File '{filename}' written successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(directory: str = "") -> dict:
    """
    Lists all files in the data/workspace directory or a specific subdirectory.
    Use the 'directory' argument to narrow down the search (e.g., 'discord_controller').
    """
    try:
        target_dir = (WORKSPACE_DIR / directory).resolve()
        
        # Tietoturvalukko
        if not target_dir.is_relative_to(WORKSPACE_DIR):
            return {"success": False, "error": "Access denied. Cannot access files outside the workspace."}
            
        if not target_dir.exists():
            return {"success": False, "error": f"Directory '{directory}' not found."}

        files = [str(p.relative_to(WORKSPACE_DIR)).replace('\\', '/') for p in target_dir.rglob('*') if p.is_file()]
        return {"success": True, "files": files}
    except Exception as e:
        return {"success": False, "error": str(e)}