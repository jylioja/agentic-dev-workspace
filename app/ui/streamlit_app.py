# app/ui/streamlit_app.py
import streamlit as st
import json
import os
import difflib
from pathlib import Path
import time
import sys
from app.agents.prompts import UI_TEXTS
from app.ui.api_client import stream_chat_from_api
import app.core.database as db
import subprocess
import shutil
import chromadb

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

st.set_page_config(
    page_title=UI_TEXTS["title"],
    page_icon="🤖",
    layout="wide"
)
ui = UI_TEXTS

CURRENT_FILE_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_FILE_DIR.parent.parent 
WORKSPACE_DIR = BASE_DIR / "data" / "workspace"
TOOLS_DIR = BASE_DIR / "app" / "tools"

# Initialize session state variables
if "history_limit" not in st.session_state:
    st.session_state.history_limit = 10

if "auto_continue" not in st.session_state:
    st.session_state.auto_continue = False

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

initial_sessions = db.get_all_sessions()

if "current_session_id" not in st.session_state:
    if initial_sessions:
        st.session_state.current_session_id = initial_sessions[0]["id"]
    else:
        st.session_state.current_session_id = db.create_session("orchestrator", "New Chat")

db.cleanup_empty_sessions(exclude_session_id=st.session_state.current_session_id)
all_sessions = db.get_all_sessions()
st.session_state.messages = db.get_messages(st.session_state.current_session_id)

# ==========================================
# HARDWARE MONITORING HELPERS
# ==========================================
def get_hardware_status():
    """Fetches current GPU VRAM and E: drive usage, returning both text and percentage (0.0 to 1.0)."""
    # 1. Get GPU VRAM using nvidia-smi
    try:
        gpu_out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,nounits,noheader"],
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        gpu_used_str, gpu_total_str = gpu_out.strip().split(', ')
        gpu_used = float(gpu_used_str)
        gpu_total = float(gpu_total_str)
        
        gpu_text = f"{int(gpu_used)} MB / {int(gpu_total)} MB"
        gpu_percent = min(gpu_used / gpu_total, 1.0) if gpu_total > 0 else 0.0
    except Exception:
        gpu_text = "Unavailable"
        gpu_percent = 0.0
    
    # 2. Get Disk Space for E: Drive
    try:
        total, used, free = shutil.disk_usage("E:\\")
        free_gb = free / (1024**3)
        total_gb = total / (1024**3)
        
        disk_text = f"{free_gb:.1f} GB free of {total_gb:.1f} GB"
        disk_percent = min(used / total, 1.0) if total > 0 else 0.0
    except Exception:
        disk_text = "Unavailable"
        disk_percent = 0.0
        
    return gpu_text, gpu_percent, disk_text, disk_percent


# ==========================================
# SIDEBAR & HISTORY MANAGEMENT
# ==========================================
st.sidebar.write("---")
app_mode = st.sidebar.radio("Navigation", ["💬 Chat Workspace", "🧪 Test Dashboard"])

if app_mode == "🧪 Test Dashboard":
    from app.ui.test_dashboard import render_test_dashboard
    render_test_dashboard()
    st.stop() # Stops rendering the normal chat and shows the test dashboard instead

with st.sidebar:
    # --- HARDWARE MONITORING UI (TOP LEFT) ---
    st.markdown("### 🖥️ Hardware Status")
    hw_placeholder = st.empty()
    
    def refresh_hardware_ui():
        """Updates the placeholder with fresh hardware metrics and visual progress bars."""
        gpu_text, gpu_percent, disk_text, disk_percent = get_hardware_status()
        
        # Use a container inside the empty placeholder to group elements
        with hw_placeholder.container():
            st.markdown("**🎮 GPU VRAM**")
            st.progress(gpu_percent, text=gpu_text)
            
            st.markdown("**💾 E: NVMe Space**")
            st.progress(disk_percent, text=disk_text)
            
    # Initial render
    refresh_hardware_ui()
    st.write("---")
    # ----------------------------------------

# --- MEMORY MANAGEMENT (DROPDOWN) ---
    with st.expander("⚙️ System Maintenance"):
        st.markdown("Clear agent long-term memory. This will permanently delete the ChromaDB vector database files.")
        
        if st.button("🗑️ Clear Vector Database", use_container_width=True, type="primary"):
            chroma_path = BASE_DIR / "chroma_data" 
            
            if chroma_path.exists():
                import shutil
                
                locked_files = []
                
                for item in chroma_path.iterdir():
                    try:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except PermissionError:
                        locked_files.append(item.name)
                
                if not locked_files:
                    try:
                        shutil.rmtree(chroma_path)
                    except Exception:
                        pass
                    st.success("✅ Memory cleared! All database files deleted physically.")
                else:
                    st.warning(f"⚠️ Memory cleared, but system could not physically delete: {', '.join(locked_files)}. \n\n*(This is normal: FastAPI is holding the file open. To fully delete it, restart the server).*")
                
                time.sleep(3)
                st.rerun()
            else:
                st.info("ℹ️ Database folder not found (already empty).")
                
    st.write("---")

# The existing sidebar content continues here...
    st.title(ui["sidebar_title"])
    selected_agent = st.selectbox(
        "Select Agent",
        [
            "Team (Lead Assistant)", 
            "Developer", 
            "Orchestrator", 
            "Analyst", 
            "Evaluator"
        ]
    )
    st.write("---")
    
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.current_session_id = db.create_session("orchestrator", "New Chat")
        st.session_state.pending_action = None 
        st.rerun()
        
    # ... rest of the sidebar code ...
    
    st.write("---")

    st.markdown("### 🤖 Team:")
    for key, info in ui["agents"].items():
        st.info(f"**{info['name']}**\n\n_{info['description']}_")
    
    st.write("---")

    st.subheader("💬 Chat History")
    visible_sessions = all_sessions[:st.session_state.history_limit]
    
    for s in visible_sessions:
        is_active = (s["id"] == st.session_state.current_session_id)
        btn_type = "primary" if is_active else "secondary"
        title_text = f"{s['title'][:25]}..." if len(s['title']) > 25 else s['title']
        
        if st.button(f"{title_text}", key=f"btn_{s['id']}", type=btn_type, use_container_width=True):
            st.session_state.current_session_id = s["id"]
            st.session_state.pending_action = None
            st.rerun()

    if len(all_sessions) > st.session_state.history_limit:
        if st.button("🔽 Load more...", use_container_width=True):
            st.session_state.history_limit += 10
            st.rerun()

    # ... existing sidebar code ...
    st.write("---")
    if st.button("🗑️ Delete this chat", use_container_width=True):
        db.delete_session(st.session_state.current_session_id)
        del st.session_state.current_session_id 
        st.session_state.pending_action = None
        st.rerun()

# ==========================================
# MAIN VIEW (CHAT AREA)
# ==========================================
st.title("🤖 Multi-Agent Team (Auto-Router)")

# Render previous messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Display tool logs in history
        if message.get("tool_logs"):
           with st.expander("🛠️ Tool Logs"):
                for log in message["tool_logs"]:
                    st.markdown(f"🔧 `{log['tool']}`")
                    st.caption(f"Input: {log['arguments']}")
                    st.caption(f"Result: {str(log.get('result', ''))[:200]}...") 

        # Display raw JSON/Markdown output for assistant messages
        if message["role"] == "assistant" and message["content"]:
            with st.expander("📋 Raw"):
                st.code(message["content"], language="markdown")


# --- NEW API-BASED CHAT FLOW (STREAMING) ---
prompt = st.chat_input(ui["input_placeholder"])

if prompt:
    prompt_for_backend = prompt
    if selected_agent != "Team (Lead Assistant)":
        prompt_for_backend = f"{selected_agent}, {prompt}"

    if len(st.session_state.messages) == 0:
        new_title = prompt[:30] + "..." if len(prompt) > 30 else prompt
        db.update_session_title(st.session_state.current_session_id, new_title)
    
    db.add_message(st.session_state.current_session_id, "user", prompt_for_backend)
    st.session_state.messages.append({"role": "user", "content": prompt_for_backend})
    
    with st.chat_message("user"):
        if selected_agent != "Team (Lead Assistant)":
            st.markdown(f"**[{selected_agent}]** {prompt}")
        else:
            st.markdown(prompt)

    with st.chat_message("assistant"):
        
        status_box = st.status("Starting multi-agent workflow...", expanded=True)
        
        log_placeholder = status_box.empty()
        recent_logs = []
        max_logs = 5
        
        final_response_data = None

        for event in stream_chat_from_api(st.session_state.messages, session_id=st.session_state.current_session_id):
            
            # --- NEW: Update hardware stats real-time during generation ---
            refresh_hardware_ui()
            
            if event["type"] == "status":
                recent_logs.append(event["content"])
                
                if len(recent_logs) > max_logs:
                    recent_logs.pop(0)
                
                log_placeholder.markdown("\n\n".join(recent_logs))
                
            elif event["type"] == "final":
                final_response_data = event
                status_box.update(label="✅ Workflow completed!", state="complete", expanded=False)
                
            elif event["type"] == "error":
                status_box.update(label="❌ Error occurred", state="error", expanded=True)
                st.error(event["content"])
                st.stop()
        
        if final_response_data:
            answer = final_response_data.get("answer", "")
            agent_name = final_response_data.get("agent", "unknown")
            tool_logs = final_response_data.get("tool_logs", [])
            
            import re
            answer = re.sub(r"^(?:\*\*)*\[.*?\](?:\*\*)*\s*", "", answer.strip(), flags=re.IGNORECASE)
            
            formatted_answer = f"**[{agent_name.upper()}]**\n\n{answer}"
            st.markdown(formatted_answer)
            
            if tool_logs:
                with st.expander("🛠️ Background Execution Logs", expanded=False):
                    for log in tool_logs:
                        if log['tool'] == "delegate_to_agent":
                            st.info("🔄 **Chained Delegation Completed:**")
                            st.markdown(f"```text\n{log['result']}\n```")
                        else:
                            st.write(f"**Tool:** `{log['tool']}`")
                            st.caption(f"Input: {log['arguments']}")
                            st.code(log['result'])
                        
            db.add_message(
                session_id=st.session_state.current_session_id, 
                role="assistant", 
                content=formatted_answer, 
                tool_logs=tool_logs
            )
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": formatted_answer,
                "tool_logs": tool_logs
            })
            
            st.rerun()