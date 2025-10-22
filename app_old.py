import streamlit as st
import asyncio
import json
from datetime import datetime
import pandas as pd
from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.express as px

from core.orchestrator import ModelOrchestrator
from models.ollama_manager import OllamaLoadBalancer, ModelPool
from workflows.dag_pipeline import code_generation_pipeline
from db.connections import db_manager
from core.memory import HierarchicalMemory
import yaml

st.set_page_config(
    page_title="Hydra - Intelligent Code Synthesis",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'task_history' not in st.session_state:
    st.session_state.task_history = []
if 'model_stats' not in st.session_state:
    st.session_state.model_stats = {}

@st.cache_resource
def initialize_system():
    with open('config/models.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    hosts = [
        "http://localhost:11434",
        "http://192.168.1.100:11434",
        "http://192.168.1.101:11434",
        "http://192.168.1.102:11434"
    ]
    
    lb = OllamaLoadBalancer([h for h in hosts if h])
    orchestrator = ModelOrchestrator(lb)
    pool = ModelPool(lb, config)
    
    return lb, orchestrator, pool, config

async def process_code_request(prompt: str, context: Dict = None):
    lb, orchestrator, pool, config = initialize_system()
    
    with st.spinner("Analyzing task complexity..."):
        complexity = await orchestrator.analyze_task(prompt, context)
        st.info(f"Task Complexity: {complexity.value}")
    
    with st.spinner("Orchestrating models..."):
        result = await orchestrator.orchestrate(prompt, context)
    
    return result

def main():
    st.title("🐉 Hydra - Intelligent Code Synthesis")
    
    with st.sidebar:
        st.header("Configuration")
        
        mode = st.selectbox(
            "Operation Mode",
            ["Chat Interface", "Workflow Management", "Model Statistics", "Memory Explorer"]
        )
        
        if mode == "Chat Interface":
            st.subheader("Model Selection")
            
            with open('config/models.yaml', 'r') as f:
                config = yaml.safe_load(f)
            
            use_custom = st.checkbox("Custom Model Selection")
            
            if use_custom:
                selected_models = st.multiselect(
                    "Select Models",
                    options=config['code_synthesis']['primary'],
                    default=config['code_synthesis']['primary'][:3]
                )
            else:
                selected_models = None
                
            temperature = st.slider("Temperature", 0.0, 1.0, 0.7)
            max_tokens = st.slider("Max Tokens", 512, 8192, 2048)
    
    if mode == "Chat Interface":
        chat_interface()
    elif mode == "Workflow Management":
        workflow_management()
    elif mode == "Model Statistics":
        model_statistics()
    elif mode == "Memory Explorer":
        memory_explorer()

def chat_interface():
    st.header("💬 Chat with Hydra")
    
    chat_container = st.container()
    
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "code" in message:
                    st.code(message["code"], language=message.get("language", "python"))
    
    prompt = st.chat_input("Enter your coding request...")
    
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            placeholder = st.empty()
            
            async def run_generation():
                result = await process_code_request(prompt)
                return result
            
            result = asyncio.run(run_generation())
            
            if 'synthesized' in result:
                response = result['synthesized']
                code = extract_code_from_response(response)
                
                placeholder.markdown(response)
                
                if code:
                    st.code(code, language="python")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response,
                        "code": code,
                        "language": "python"
                    })
                else:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response
                    })
                    
                with st.expander("Task Details"):
                    st.json({
                        "task_id": result.get("task_id"),
                        "complexity": result.get("complexity"),
                        "subtasks": len(result.get("subtasks", []))
                    })
            else:
                response = result.get('response', 'Processing failed')
                placeholder.markdown(response)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response
                })
    
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

def workflow_management():
    st.header("🔄 Workflow Management")
    
    tab1, tab2, tab3 = st.tabs(["Active Workflows", "Create Workflow", "Workflow History"])
    
    with tab1:
        st.subheader("Active Workflows")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Running", "3", "▲ 1")
        with col2:
            st.metric("Queued", "7", "▼ 2")
        with col3:
            st.metric("Completed Today", "42", "▲ 5")
        
        active_workflows = pd.DataFrame({
            "ID": ["wf_001", "wf_002", "wf_003"],
            "Name": ["Code Review", "API Generation", "Test Suite"],
            "Status": ["Running", "Running", "Queued"],
            "Progress": [67, 34, 0],
            "Started": ["10:23 AM", "10:45 AM", "Pending"]
        })
        
        st.dataframe(active_workflows, use_container_width=True)
    
    with tab2:
        st.subheader("Create New Workflow")
        
        workflow_name = st.text_input("Workflow Name")
        workflow_desc = st.text_area("Description")
        
        st.write("Tasks")
        num_tasks = st.number_input("Number of Tasks", 1, 10, 1)
        
        tasks = []
        for i in range(num_tasks):
            with st.expander(f"Task {i+1}"):
                task_name = st.text_input(f"Task Name", key=f"task_name_{i}")
                task_prompt = st.text_area(f"Prompt", key=f"task_prompt_{i}")
                task_deps = st.multiselect(
                    f"Dependencies",
                    options=[f"Task {j+1}" for j in range(i)],
                    key=f"task_deps_{i}"
                )
                tasks.append({
                    "name": task_name,
                    "prompt": task_prompt,
                    "dependencies": task_deps
                })
        
        if st.button("Create Workflow"):
            st.success(f"Workflow '{workflow_name}' created successfully!")
    
    with tab3:
        st.subheader("Workflow History")
        
        history_df = pd.DataFrame({
            "ID": ["wf_040", "wf_039", "wf_038", "wf_037"],
            "Name": ["Data Pipeline", "ML Training", "Code Refactor", "Bug Fix"],
            "Completed": ["2 hours ago", "4 hours ago", "Yesterday", "Yesterday"],
            "Duration": ["45 min", "2.3 hours", "1.5 hours", "23 min"],
            "Status": ["Success", "Success", "Failed", "Success"]
        })
        
        st.dataframe(history_df, use_container_width=True)

def model_statistics():
    st.header("📊 Model Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Model Usage Distribution")
        
        usage_data = {
            "qwen2.5-coder:14b": 234,
            "devstral:latest": 189,
            "codestral:latest": 156,
            "llama3.1:latest": 142,
            "mistral-small:24b": 98
        }
        
        fig = px.pie(
            values=list(usage_data.values()),
            names=list(usage_data.keys()),
            title="Model Usage (Last 24h)"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Response Time by Model")
        
        models = list(usage_data.keys())
        response_times = [1.2, 1.5, 1.8, 0.9, 2.1]
        
        fig = go.Figure(data=[
            go.Bar(x=models, y=response_times)
        ])
        fig.update_layout(
            title="Average Response Time (seconds)",
            xaxis_title="Model",
            yaxis_title="Time (s)"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("Node Health Status")
    
    nodes_df = pd.DataFrame({
        "Node": ["GPU Node", "CPU Node 1", "CPU Node 2", "CPU Node 3"],
        "Status": ["🟢 Healthy", "🟢 Healthy", "🟡 Degraded", "🟢 Healthy"],
        "Load": ["67%", "45%", "89%", "23%"],
        "Memory": ["12.3 GB / 24 GB", "8.1 GB / 16 GB", "14.7 GB / 16 GB", "4.2 GB / 16 GB"],
        "Active Models": [3, 2, 2, 1]
    })
    
    st.dataframe(nodes_df, use_container_width=True)

def memory_explorer():
    st.header("🧠 Memory Explorer")
    
    tab1, tab2, tab3 = st.tabs(["Memory Tiers", "Search", "Analytics"])
    
    with tab1:
        st.subheader("Memory Tier Status")
        
        tiers_data = {
            "L1 Cache (Redis)": {"Items": 1234, "Size": "45 MB", "Hit Rate": "92%"},
            "L2 Cache (SQLite)": {"Items": 5678, "Size": "234 MB", "Hit Rate": "67%"},
            "L3 Storage (PostgreSQL)": {"Items": 45678, "Size": "2.3 GB", "Hit Rate": "34%"},
            "L4 Archive (ChromaDB)": {"Items": 234567, "Size": "12.4 GB", "Hit Rate": "12%"}
        }
        
        for tier, stats in tiers_data.items():
            with st.expander(tier):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Items", stats["Items"])
                with col2:
                    st.metric("Size", stats["Size"])
                with col3:
                    st.metric("Hit Rate", stats["Hit Rate"])
    
    with tab2:
        st.subheader("Semantic Search")
        
        search_query = st.text_input("Search Query")
        search_type = st.selectbox("Search Type", ["Semantic", "Keyword", "Hybrid"])
        
        if st.button("Search"):
            with st.spinner("Searching..."):
                st.success("Found 23 relevant results")
                
                results = [
                    {"Title": "API Authentication Implementation", "Similarity": 0.94, "Tier": "L2"},
                    {"Title": "Database Connection Handler", "Similarity": 0.89, "Tier": "L3"},
                    {"Title": "Error Handling Middleware", "Similarity": 0.85, "Tier": "L1"}
                ]
                
                for result in results:
                    with st.container():
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.write(f"**{result['Title']}**")
                        with col2:
                            st.write(f"Similarity: {result['Similarity']}")
                        with col3:
                            st.write(f"Tier: {result['Tier']}")
    
    with tab3:
        st.subheader("Memory Analytics")
        
        times = pd.date_range('2024-01-01', periods=7, freq='D')
        memory_usage = pd.DataFrame({
            'Date': times,
            'L1': [45, 48, 52, 49, 51, 53, 50],
            'L2': [234, 240, 245, 238, 242, 248, 244],
            'L3': [2300, 2350, 2400, 2380, 2420, 2450, 2430],
            'L4': [12400, 12500, 12600, 12550, 12650, 12700, 12680]
        })
        
        fig = go.Figure()
        for tier in ['L1', 'L2', 'L3', 'L4']:
            fig.add_trace(go.Scatter(
                x=memory_usage['Date'],
                y=memory_usage[tier],
                mode='lines',
                name=tier
            ))
        
        fig.update_layout(
            title="Memory Usage Over Time (MB)",
            xaxis_title="Date",
            yaxis_title="Memory (MB)",
            hovermode='x'
        )
        
        st.plotly_chart(fig, use_container_width=True)

def extract_code_from_response(response: str) -> Optional[str]:
    import re
    code_pattern = r'```(?:python|py)?\n(.*?)```'
    matches = re.findall(code_pattern, response, re.DOTALL)
    if matches:
        return matches[0].strip()
    return None

if __name__ == "__main__":
    main()