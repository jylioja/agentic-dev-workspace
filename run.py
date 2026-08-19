import subprocess
import sys
import time

print("🚀 Starting Multi-Agent AI Workspace...")

try:
    # 1. Start the FastAPI backend
    print("Starting FastAPI Backend...")
    # sys.executable automatically uses the Python from your active venv
    backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api.server:app"])

    # Wait briefly to ensure the backend is listening on port 8000
    time.sleep(3)

    # 2. Start the Streamlit frontend
    print("Starting Streamlit UI...")
    frontend = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/ui/streamlit_app.py"])

    # Keep the main script alive to monitor both processes
    backend.wait()
    frontend.wait()

except KeyboardInterrupt:
    # Handle Ctrl+C gracefully and kill both servers
    print("\n🛑 Shutting down Workspace...")
    backend.terminate()
    frontend.terminate()
    print("✅ All processes stopped.")