# app/tools/code_runner.py
import subprocess
import sys
from pathlib import Path

# Workspace-kansion määrittely hiekkalaatikoksi
WORKSPACE_DIR = Path("data/workspace").resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def execute_python_code(code: str, timeout_seconds: int = 30) -> dict:
    """
    Ajaa Python-koodin lokaalissa ympäristössä ja palauttaa tuloksen.
    """
    script_path = WORKSPACE_DIR / "temp_script.py"
    
    # Kirjoitetaan suoritettava koodi väliaikaistiedostoon
    script_path.write_text(code, encoding="utf-8")
    
    try:
        # Käytetään absoluuttista polkua suorituksessa
        result = subprocess.run(
            [sys.executable, str(script_path.resolve())],
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds.",
            "exit_code": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution error: {str(e)}",
            "exit_code": -1
        }
    finally:
        # Siivotaan väliaikaistiedosto ajon jälkeen
        if script_path.exists():
            script_path.unlink()