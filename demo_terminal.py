#!/usr/bin/env python3
"""
Demo script to show terminal logging in action
"""

import streamlit as st
from ui.terminal import Terminal, GenerationLogger
import time
import asyncio

def demo_terminal():
    st.set_page_config(page_title="Hydra Terminal Demo", layout="wide")
    st.title("🖥️ Hydra Terminal Logging Demo")
    
    # Initialize terminal
    terminal = Terminal()
    
    # Demo controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🚀 Simulate Model Generation"):
            logger = GenerationLogger(terminal)
            
            # Start generation
            logger.start_generation("Generate a Python function to calculate factorial", "llama3.1")
            
            # Simulate model calls
            logger.log_model_call("llama3.1", "calling")
            time.sleep(0.5)
            logger.log_model_call("llama3.1", "completed in 1.2s")
            
            # Simulate token generation
            logger.log_token_generation(250, "llama3.1")
            
            # Log success
            logger.log_success("Generation completed")
            st.rerun()
    
    with col2:
        if st.button("🔧 Simulate Tool Usage"):
            logger = GenerationLogger(terminal)
            
            # Simulate tool calls
            logger.log_tool_call("read_file", {"path": "/home/user/code.py"})
            time.sleep(0.3)
            
            logger.log_tool_call("execute_python", {"code": "print('Hello')"})
            time.sleep(0.3)
            
            logger.log_tool_call("search_codebase", {"pattern": "def.*main"})
            
            terminal.log("Tool execution completed", "INFO", "Tools")
            st.rerun()
    
    with col3:
        if st.button("🧠 Simulate Orchestration"):
            logger = GenerationLogger(terminal)
            
            # Simulate orchestration
            logger.log_orchestration("analyze_task", "complexity: COMPLEX")
            time.sleep(0.2)
            
            logger.log_orchestration("decompose_task", "5 subtasks")
            time.sleep(0.3)
            
            # Simulate synthesis
            logger.log_synthesis(["qwen2.5-coder", "devstral", "codestral"], 0.92)
            time.sleep(0.2)
            
            logger.log_orchestration("synthesis_complete", "task_123456")
            st.rerun()
    
    # Memory operations demo
    col4, col5, col6 = st.columns(3)
    
    with col4:
        if st.button("💾 Simulate Memory Ops"):
            logger = GenerationLogger(terminal)
            
            logger.log_memory_operation("store", "L1_CACHE")
            time.sleep(0.1)
            logger.log_memory_operation("persist", "L2_CACHE") 
            time.sleep(0.1)
            logger.log_memory_operation("retrieve", "L1_CACHE")
            st.rerun()
    
    with col5:
        if st.button("⚠️ Simulate Errors"):
            logger = GenerationLogger(terminal)
            
            logger.log_error("Connection timeout to model server", "ModelAPI")
            time.sleep(0.2)
            logger.log_error("Tool 'undefined_tool' not found", "Tools")
            time.sleep(0.2)
            logger.log_error("Memory tier migration failed", "Memory")
            st.rerun()
    
    with col6:
        if st.button("🔍 Mixed Operations"):
            logger = GenerationLogger(terminal)
            
            # Simulate a complete flow
            logger.start_generation("Create a REST API endpoint", "qwen2.5-coder")
            logger.log_orchestration("analyze_task", "complexity: MODERATE")
            logger.log_model_call("qwen2.5-coder", "on http://localhost:11434")
            logger.log_tool_call("write_file", {"path": "api.py", "content": "..."})
            logger.log_memory_operation("store", "L1_CACHE")
            logger.log_synthesis(["qwen2.5-coder", "devstral"], 0.88)
            logger.log_success("API endpoint created successfully")
            st.rerun()
    
    # Add manual log entry
    st.subheader("📝 Manual Log Entry")
    col7, col8, col9 = st.columns([2, 1, 1])
    
    with col7:
        message = st.text_input("Message", "Custom log message")
    with col8:
        level = st.selectbox("Level", ["INFO", "DEBUG", "WARNING", "ERROR"])
    with col9:
        source = st.text_input("Source", "Manual")
    
    if st.button("➕ Add Log"):
        terminal.log(message, level, source)
        st.rerun()
    
    # Render terminal
    st.subheader("🖥️ Terminal Output")
    terminal.render(height=600, key="demo_terminal")
    
    # Stats
    st.subheader("📊 Terminal Statistics")
    logs = terminal.get_logs()
    
    col10, col11, col12, col13 = st.columns(4)
    with col10:
        st.metric("Total Logs", len(logs))
    with col11:
        errors = len([l for l in logs if l['level'] == 'ERROR'])
        st.metric("Errors", errors)
    with col12:
        warnings = len([l for l in logs if l['level'] == 'WARNING'])
        st.metric("Warnings", warnings)
    with col13:
        sources = list(set(l['source'] for l in logs))
        st.metric("Sources", len(sources))

if __name__ == "__main__":
    demo_terminal()