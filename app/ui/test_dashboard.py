# app/ui/test_dashboard.py
import streamlit as st
import json
import os
import time
import re
from pathlib import Path
from tests.run_tests import run_all_tests, generate_dynamic_tests, load_dynamic_tests, request_ai_fix

def typewriter_user_prompt(container, prompt):
    """Animates user prompt slowly character by character right when the test starts."""
    with container:
        with st.chat_message("user"):
            user_placeholder = st.empty()
            typed_user = ""
            for char in prompt:
                typed_user += char
                user_placeholder.markdown(typed_user + "▌")
                time.sleep(0.02)
            user_placeholder.markdown(prompt)

def render_test_dashboard():
    if "is_running" not in st.session_state:
        st.session_state["is_running"] = False
    if "current_test_index" not in st.session_state:
        st.session_state["current_test_index"] = 0
    if "latest_test_report" not in st.session_state:
        st.session_state["latest_test_report"] = None
    if "skip_triggered" not in st.session_state:
        st.session_state["skip_triggered"] = False
    if "run_mode" not in st.session_state:
        st.session_state["run_mode"] = "all"
    if "single_test_index" not in st.session_state:
        st.session_state["single_test_index"] = None
        
    st.title("🧪 Agent Testing & Evaluation Dashboard")
    st.markdown("Run automated evaluation tests in real-time with live chat stream, inspect agent decisions, and manage test cases.")
    
    col1, col2, col3 = st.columns([1.5, 1, 1])
    
    with col1:
        if not st.session_state["is_running"]:
            subA, subB = st.columns(2)
            with subA:
                if st.button("🚀 Run All", type="primary", use_container_width=True):
                    st.session_state["is_running"] = True
                    st.session_state["run_mode"] = "all"
                    st.session_state["current_test_index"] = 0
                    st.session_state["latest_test_report"] = None
                    st.session_state["skip_triggered"] = False
                    st.rerun()
            with subB:
                if st.button("⚡ Run Dynamic", type="secondary", use_container_width=True):
                    st.session_state["is_running"] = True
                    st.session_state["run_mode"] = "dynamic"
                    st.session_state["current_test_index"] = 0
                    st.session_state["latest_test_report"] = None
                    st.session_state["skip_triggered"] = False
                    st.rerun()
        else:
            sub1, sub2 = st.columns(2)
            with sub1:
                if st.button("⏭️ Skip", use_container_width=True):
                    st.session_state["skip_triggered"] = True
                    st.rerun()
            with sub2:
                if st.button("🛑 Stop", type="secondary", use_container_width=True):
                    st.session_state["is_running"] = False
                    st.warning("Stop signal sent! Halting execution...")
                    st.rerun()
            
    with col2:
        if st.button("🤖 Generate Tests", use_container_width=True):
            try:
                with st.spinner("Architect is generating test cases..."):
                    generate_dynamic_tests()
                st.success("New dynamic tests generated successfully!")
            except Exception as e:
                st.error(f"❌ Error generating tests: {str(e)}")
            st.rerun()
            
    with col3:
        dynamic_tests = load_dynamic_tests()
        st.metric(label="Active Dynamic Tests", value=len(dynamic_tests))
        
    st.write("---")
    
    tab_results, tab_manage = st.tabs(["📊 Live Results", "⚙️ Manage Dynamic Tests"])
    
    with tab_results:
        if st.session_state["is_running"]:
            if st.session_state["run_mode"] == "all":
                mode_text = "All Tests"
            elif st.session_state["run_mode"] == "dynamic":
                mode_text = "Dynamic Tests Only"
            else:
                mode_text = f"Single Dynamic Test"
                
            st.subheader(f"🔴 Live Test Execution & Chat Stream ({mode_text})")
            progress_bar = st.progress(0)
            status_placeholder = st.empty()
            
            live_chat_placeholder = st.empty()
            results_container = st.container()
            
            if not st.session_state["latest_test_report"]:
                live_report = {
                    "total_tests": 0,
                    "passed": 0,
                    "failed": 0,
                    "results": []
                }
                st.session_state["latest_test_report"] = live_report

            def handle_test_start(test):
                with live_chat_placeholder.container():
                    st.info(f"🔄 **Running test:** {test.get('name')}")
                    typewriter_user_prompt(st.container(), test.get('prompt'))
                    with st.chat_message("assistant"):
                        with st.spinner("Agent is thinking and processing response..."):
                            time.sleep(0.3)
                            st.write("💭 *Analyzing prompt and executing tools...*")

            def handle_test_complete(test_result, current_report):
                st.session_state["latest_test_report"] = current_report
                st.session_state["current_test_index"] = len(current_report["results"])
                
                live_chat_placeholder.empty()
                
                with results_container:
                    res = test_result
                    status_icon = "✅" if res["status"] == "PASS" else "⏭️" if res["status"] == "SKIPPED" else "❌"
                    
                    with st.expander(f"{status_icon} [{res.get('selected_agent', '-').upper()}] {res['test_name']} - {res['status']}", expanded=(res["status"] == "FAIL")):
                        st.write(f"**Prompt:** {res['prompt']}")
                        st.write(f"**Expected:** {res['expected_behavior']}")
                        st.write(f"**Requested Tools:** `{res.get('requested_tools', [])}`")
                        st.code(res.get('agent_response', ''), language="markdown")
                        st.info(f"**AI Judge Reasoning:**\n{res.get('judge_reasoning', '')}")
                        
                        if res["status"] == "FAIL":
                            fix_key = f"live_fix_{res['test_name']}"
                            if st.button("🤖 Ask AI to Fix", key=fix_key):
                                with st.spinner("Architect is analyzing the failure and writing a fix..."):
                                    try:
                                        fix_suggestion = request_ai_fix(
                                            res['test_name'],
                                            res['prompt'],
                                            res['expected_behavior'],
                                            res['agent_response'],
                                            res['judge_reasoning']
                                        )
                                        st.markdown("### 🛠️ AI Fix Suggestion:")
                                        st.markdown(fix_suggestion)
                                        
                                        match = re.search(r"---FIX_START---\s*FILE:\s*(.*?)\s*CONTENT:\s*(.*?)\s*---FIX_END---", fix_suggestion, re.DOTALL)
                                        
                                        if match:
                                            target_file = match.group(1).strip()
                                            new_content = match.group(2).strip()
                                            
                                            st.warning(f"⚠️ Tekoäly on laatinut valmiin korjauksen tiedostoon: **{target_file}**")
                                            
                                            if st.button(f"✨ Hyväksy ja ylikirjoita {target_file}", type="primary", key=f"live_apply_{res['test_name']}"):
                                                project_root = Path(__file__).resolve().parent.parent.parent
                                                full_file_path = project_root / target_file
                                                
                                                try:
                                                    full_file_path.parent.mkdir(parents=True, exist_ok=True)
                                                    with open(full_file_path, "w", encoding="utf-8") as f:
                                                        f.write(new_content)
                                                    st.success(f"✅ Muutokset tallennettu tiedostoon {target_file}! Aja testit uudelleen.")
                                                except Exception as write_error:
                                                    st.error(f"❌ Virhe tiedoston tallennuksessa: {write_error}")

                                    except Exception as e:
                                        st.error(f"Failed to generate fix: {e}")

            def update_progress(current, total, name):
                progress_val = min(current / total, 1.0) if total > 0 else 0
                progress_bar.progress(progress_val)
                status_placeholder.text(f"Running test {current}/{total}: {name}")

            def check_stop():
                return not st.session_state.get("is_running", True)

            try:
                skip_now = st.session_state["skip_triggered"]
                st.session_state["skip_triggered"] = False
                
                final_report = run_all_tests(
                    progress_callback=update_progress, 
                    on_test_start=handle_test_start,
                    on_test_complete=handle_test_complete,
                    stop_checker=check_stop,
                    start_index=st.session_state["current_test_index"],
                    existing_report=st.session_state["latest_test_report"],
                    skip_first=skip_now,
                    run_mode=st.session_state["run_mode"],
                    single_test_index=st.session_state.get("single_test_index")
                )
                
                st.session_state["latest_test_report"] = final_report
                
                if check_stop():
                    status_placeholder.warning(f"Test run stopped by user. Completed: {final_report['passed']}/{final_report['total_tests']}")
                else:
                    status_placeholder.success(f"All tests completed! Passed: {final_report['passed']}/{final_report['total_tests']}")
            except Exception as e:
                st.error(f"❌ Error during test execution: {str(e)}")
            finally:
                progress_bar.empty()
                st.session_state["is_running"] = False
                st.rerun()
                
        elif "latest_test_report" in st.session_state and st.session_state["latest_test_report"]:
            report = st.session_state["latest_test_report"]
            st.subheader("📊 Latest Test Execution Results")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Tests", report.get("total_tests", 0))
            m2.metric("Passed", report.get("passed", 0), delta=f"+{report.get('passed', 0)}")
            failed_count = report.get("failed", 0)
            m3.metric("Failed", failed_count, delta=f"-{failed_count}" if failed_count > 0 else "0")
            
            for res in report.get("results", []):
                status_icon = "✅" if res["status"] == "PASS" else "⏭️" if res["status"] == "SKIPPED" else "❌"
                
                with st.expander(f"{status_icon} [{res.get('selected_agent', '-').upper()}] {res['test_name']} - {res['status']}"):
                    st.write(f"**Prompt:** {res['prompt']}")
                    st.write(f"**Expected:** {res['expected_behavior']}")
                    st.write(f"**Requested Tools:** `{res.get('requested_tools', [])}`")
                    st.code(res.get("agent_response", ""), language="markdown")
                    st.info(f"**AI Judge Reasoning:**\n{res.get('judge_reasoning', '')}")

                    if res["status"] == "FAIL":
                        fix_key = f"fix_{res['test_name']}"
                        if st.button("🤖 Ask AI to Fix", key=fix_key):
                            with st.spinner("Architect is analyzing the failure and writing a fix..."):
                                try:
                                    fix_suggestion = request_ai_fix(
                                        res['test_name'],
                                        res['prompt'],
                                        res['expected_behavior'],
                                        res['agent_response'],
                                        res['judge_reasoning']
                                    )
                                    st.markdown("### 🛠️ AI Fix Suggestion:")
                                    st.markdown(fix_suggestion)
                                    
                                    match = re.search(r"---FIX_START---\s*FILE:\s*(.*?)\s*CONTENT:\s*(.*?)\s*---FIX_END---", fix_suggestion, re.DOTALL)
                                    
                                    if match:
                                        target_file = match.group(1).strip()
                                        new_content = match.group(2).strip()
                                        
st.warning(f"⚠️ The AI has prepared a ready fix for the file: **{target_file}**")
                                        
if st.button(f"✨ Accept and overwrite {target_file}", type="primary", key=f"apply_{res['test_name']}"):
    project_root = Path(__file__).resolve().parent.parent.parent
    full_file_path = project_root / target_file
    
    try:
        full_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        st.success(f"✅ Changes saved to {target_file}! Run the tests again.")
    except Exception as write_error:
        st.error(f"❌ Error saving file: {write_error}")

                                except Exception as e:
                                    st.error(f"Failed to generate fix: {e}")
        else:
            st.info("Click **'Run All'** or **'Run Dynamic'** above to start evaluating agents in real-time with live chat stream.")

    with tab_manage:
        st.subheader("⚙️ Manage / Delete / Run Dynamic Tests")
        dynamic_tests = load_dynamic_tests()
        
        if not dynamic_tests:
            st.info("No dynamic tests found in `dynamic_tests.json`.")
        else:
            for idx, test in enumerate(dynamic_tests):
                col_info, col_run, col_del = st.columns([0.7, 0.15, 0.15])
                with col_info:
                    st.markdown(f"**{idx + 1}. {test.get('name', 'Unnamed Test')}**")
                    st.caption(f"Prompt: {test.get('prompt', '')}")
                    st.text(f"Expected: {test.get('expected_behavior', '')}")
                    
                with col_run:
                    if st.button("▶️ Run", key=f"run_test_{idx}", use_container_width=True):
                        st.session_state["is_running"] = True
                        st.session_state["run_mode"] = "single"
                        st.session_state["single_test_index"] = idx
                        st.session_state["current_test_index"] = 0
                        st.session_state["latest_test_report"] = None
                        st.session_state["skip_triggered"] = False
                        st.rerun()
                        
                with col_del:
                    if st.button("🗑️ Delete", key=f"del_test_{idx}", use_container_width=True):
                        dynamic_tests.pop(idx)
                        dynamic_tests_path = Path(__file__).resolve().parent.parent.parent / "tests" / "dynamic_tests.json"
                        with open(dynamic_tests_path, "w", encoding="utf-8") as f:
                            json.dump(dynamic_tests, f, indent=4, ensure_ascii=False)
                        st.success("Deleted test successfully!")
                        st.rerun()
                st.write("---")