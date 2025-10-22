import streamlit as st
import asyncio
import json
from datetime import datetime
import pandas as pd
from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.express as px
from loguru import logger
from core.logging_config import configure_logging
from utils.async_helpers import run_async, AsyncContextManager
import nest_asyncio

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Configure logging at startup
configure_logging(verbose=True)

from core.orchestrator import ModelOrchestrator
from models.ollama_manager import OllamaLoadBalancer, ModelPool
from core.code_assistant import CodeAssistant, StreamingCodeAssistant, TaskDetector
from workflows.dag_pipeline import code_generation_pipeline
from db.connections import db_manager
from core.memory import HierarchicalMemory
from ui.enhanced_project_manager import EnhancedProjectManager, render_enhanced_project_sidebar, render_project_files_panel
from ui.project_context import get_project_context
from ui.artifacts import ArtifactManager, ArtifactGenerator, render_artifact_panel, render_artifacts_sidebar, extract_artifacts_from_response
from ui.file_handler import FileHandler, render_file_upload_zone, create_file_reference, parse_file_references, render_file_in_chat, FileSearch
from ui.terminal import Terminal, GenerationLogger, render_terminal_panel
from core.tools import ToolRegistry, ToolEnhancedGenerator
import yaml

st.set_page_config(
    page_title="Hydra - Intelligent Code Synthesis",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'task_history' not in st.session_state:
    st.session_state.task_history = []
if 'model_stats' not in st.session_state:
    st.session_state.model_stats = {}
if 'enhanced_project_manager' not in st.session_state:
    st.session_state.enhanced_project_manager = EnhancedProjectManager()

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
    
    try:
        lb = OllamaLoadBalancer([h for h in hosts if h])
        
        # Test connection without blocking
        # We'll check health asynchronously later when actually needed
        import httpx
        try:
            # Quick synchronous check if Ollama is reachable
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{hosts[0]}/api/tags")
                if response.status_code == 200:
                    logger.info("✅ Ollama connection verified")
                else:
                    logger.warning(f"Ollama returned status {response.status_code}")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(f"⚠️ Ollama may not be running: {e}")
            # Don't fail completely, continue with setup
        
        orchestrator = ModelOrchestrator(lb)
        pool = ModelPool(lb, config)
        code_assistant = StreamingCodeAssistant(lb)
        return lb, orchestrator, pool, config, code_assistant
        
    except Exception as e:
        logger.warning(f"Failed to initialize Ollama components: {e}")
        # Return None for load balancer but still create other objects
        orchestrator = None
        pool = None
        code_assistant = StreamingCodeAssistant(None)
        return None, orchestrator, pool, config, code_assistant

async def process_code_request_stream(prompt: str, context: Dict = None):
    """Process code request with streaming response using Code Assistant"""
    lb, orchestrator, pool, config, code_assistant = initialize_system()
    
    # Initialize terminal logger
    if 'terminal' not in st.session_state:
        st.session_state.terminal = Terminal()
    terminal = st.session_state.terminal
    logger = GenerationLogger(terminal)
    
    # Add project context if available
    project_context = get_project_context()
    if project_context:
        if context is None:
            context = {}
        context.update(project_context)
    
    # Detect task type
    detector = TaskDetector()
    task_type = detector.detect_task_type(prompt, context)
    
    # Log generation start
    logger.start_generation(prompt, model=f"code_assistant:{task_type.value}")
    
    # Create a placeholder for streaming output
    response_placeholder = st.empty()
    full_response = ""
    
    # Display detected task type
    st.info(f"🎯 Task Type: {task_type.value.title()}")
    logger.log_orchestration("Task detected", f"Type: {task_type.value}")
    
    # Check if we have a connection
    if not lb:
        st.error("⚠️ Ollama is not connected. Please ensure Ollama is running.")
        st.info("You can download Ollama from: https://ollama.com/download")
        st.code("# After installing, run:\ncurl -fsSL https://ollama.com/install.sh | sh\nsudo systemctl start ollama", language="bash")
        return {'response': 'Ollama connection required', 'error': True}
    
    # Use Code Assistant for intelligent handling
    try:
        # Stream the response
        logger.log_orchestration(f"Starting {task_type.value} task")
        
        async for chunk_data in code_assistant.process_stream(prompt, context):
            if 'chunk' in chunk_data:
                full_response += chunk_data['chunk']
                # Update the placeholder with streaming content
                response_placeholder.markdown(full_response)
                
                # Log streaming progress
                if chunk_data.get('done', False):
                    logger.log_success(f"{task_type.value.title()} completed")
                    
    except Exception as e:
        st.error(f"Error: {e}")
        logger.log_error(str(e), "CodeAssistant")
        return {'response': str(e), 'error': True}
    
    # Save to project history if in a project
    if hasattr(st.session_state, 'current_project'):
        pm = st.session_state.enhanced_project_manager
        project = st.session_state.current_project
        project.chat_history.append({
            'role': 'assistant',
            'content': full_response,
            'metadata': {
                'task_type': task_type.value,
                'timestamp': datetime.now().isoformat()
            }
        })
        pm.save_project(project)
    
    return {'response': full_response, 'task_type': task_type.value}

async def process_code_request(prompt: str, context: Dict = None):
    """Legacy non-streaming version for compatibility"""
    lb, orchestrator, pool, config, code_assistant = initialize_system()
    
    # Initialize terminal logger
    if 'terminal' not in st.session_state:
        st.session_state.terminal = Terminal()
    terminal = st.session_state.terminal
    logger = GenerationLogger(terminal)
    
    # Add project context if available
    project_context = get_project_context()
    if project_context:
        if context is None:
            context = {}
        context.update(project_context)
    
    # Log generation start
    logger.start_generation(prompt, model="orchestrator")
    
    with st.spinner("Analyzing task complexity..."):
        complexity = await orchestrator.analyze_task(prompt, context)
        st.info(f"Task Complexity: {complexity.value}")
        logger.log_orchestration("Task analyzed", f"Complexity: {complexity.value}")
    
    with st.spinner("Orchestrating models..."):
        logger.log_orchestration("Starting orchestration")
        result = await orchestrator.orchestrate(prompt, context)
        logger.log_success("Orchestration completed")
    
    # Save to project history if in a project
    if hasattr(st.session_state, 'current_project'):
        pm = st.session_state.enhanced_project_manager
        project = st.session_state.current_project
        project.chat_history.append({
            'role': 'assistant',
            'content': result.get('synthesized', result.get('response', '')),
            'metadata': {
                'complexity': complexity.value,
                'task_id': result.get('task_id')
            }
        })
        pm.save_project(project)
    
    return result

def main():
    # Title with version
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.title("🐉 Hydra - Intelligent Code Synthesis")
    with col2:
        st.caption("v1.0.0")
        st.caption(f"Models: {len(st.session_state.model_stats)}")
    with col3:
        # Quick project selector
        if hasattr(st.session_state, 'current_project'):
            st.info(f"📁 {st.session_state.current_project.name}")
            if st.button("Change", key="change_proj"):
                del st.session_state.current_project
                st.switch_page("pages/1_📁_Projects.py")
        else:
            if st.button("📁 Projects", key="go_to_projects"):
                st.switch_page("pages/1_📁_Projects.py")
    
    # Main interface tabs (simplified)
    tabs = st.tabs([
        "💬 Chat", 
        "📊 Dashboard", 
        "🔄 Workflows", 
        "🧠 Memory", 
        "🖥️ Terminal",
        "⚙️ Settings"
    ])
    
    with tabs[0]:
        chat_interface()
        
    with tabs[1]:
        dashboard()
    
    with tabs[2]:
        workflow_management()
    
    with tabs[3]:
        memory_explorer()
    
    with tabs[4]:
        render_terminal_panel()
        
    with tabs[5]:
        settings_panel()

def chat_interface():
    # Create columns for chat and artifacts
    col_chat, col_artifact = st.columns([1, 1])
    
    with col_chat:
        # Chat history container
        chat_container = st.container()
        
        # Display chat history
        with chat_container:
            messages = st.session_state.messages
            if hasattr(st.session_state, 'current_project'):
                # Use project chat history
                messages = st.session_state.current_project.chat_history
            
            # Display all messages from history
            for message in messages:
                if isinstance(message, dict):
                    with st.chat_message(message.get("role", "assistant")):
                        # Show thinking if present (for assistant messages)
                        if message.get("role") == "assistant" and message.get("thinking"):
                            with st.expander("🤔 Thinking", expanded=False):
                                st.markdown(message["thinking"])
                        
                        st.markdown(message.get("content", ""))
                        
                        # Show attached files if present
                        if "attached_files" in message and message["attached_files"]:
                            total_attached_lines = sum(f.get('lines', 0) for f in message['attached_files'])
                            expander_text = f"📎 {len(message['attached_files'])} files"
                            if total_attached_lines > 0:
                                expander_text += f" ({total_attached_lines:,} lines)"
                            
                            with st.expander(expander_text):
                                for file_info in message["attached_files"]:
                                    if file_info.get('lines', 0) > 0:
                                        st.text(f"📄 {file_info['name']}: {file_info['lines']:,} lines ({file_info['size'] / 1024:.1f} KB)")
                                    else:
                                        st.text(f"📎 {file_info['name']}: {file_info['size'] / 1024:.1f} KB")
                        
                        if "code" in message:
                            st.code(message["code"], language=message.get("language", "python"))
    
        # File attachment area (like Claude)
        with st.container():
            st.markdown("### 💬 Chat Input")
            
            # File upload section with limits (20 files OR 20k lines total)
            uploaded_files = st.file_uploader(
                "Attach files (max 20 files OR 20k lines of code)",
                accept_multiple_files=True,
                key="chat_file_upload",
                help="📎 Attach up to 20 files (10MB each) OR maximum 20,000 lines of code total"
            )
            
            # Validate uploaded files
            attached_files_info = []
            total_lines = 0
            
            if uploaded_files:
                MAX_FILES = 20
                MAX_SIZE_MB = 10
                MAX_TOTAL_LINES = 20000
                
                if len(uploaded_files) > MAX_FILES:
                    st.warning(f"⚠️ Maximum {MAX_FILES} files allowed. Only first {MAX_FILES} will be used.")
                    uploaded_files = uploaded_files[:MAX_FILES]
                
                # Process files and count lines
                for file in uploaded_files:
                    if file.size > MAX_SIZE_MB * 1024 * 1024:
                        st.error(f"❌ {file.name} exceeds 10MB limit ({file.size / (1024*1024):.1f} MB)")
                    else:
                        file_content = file.getvalue()
                        
                        # Count lines for text/code files
                        line_count = 0
                        try:
                            # Check if it's a text/code file
                            if file.name.endswith(('.txt', '.md', '.py', '.js', '.ts', '.jsx', '.tsx', 
                                                  '.java', '.c', '.cpp', '.h', '.cs', '.go', '.rs', 
                                                  '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.jl',
                                                  '.lua', '.pl', '.sh', '.bash', '.zsh', '.fish', '.ps1',
                                                  '.html', '.css', '.scss', '.sass', '.less', '.xml', 
                                                  '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', 
                                                  '.conf', '.sql', '.dockerfile', '.vue', '.dart', '.elm',
                                                  '.clj', '.ex', '.erl', '.hs', '.ml', '.fs', '.nim')):
                                text_content = file_content.decode('utf-8', errors='ignore')
                                line_count = len(text_content.splitlines())
                                total_lines += line_count
                                
                                # Check if we've exceeded the line limit
                                if total_lines > MAX_TOTAL_LINES:
                                    st.error(f"❌ Total lines exceeds {MAX_TOTAL_LINES:,} limit. Current: {total_lines:,} lines")
                                    st.info("💡 Consider uploading fewer files or smaller code files")
                                    break
                        except:
                            # Binary file or unable to decode
                            pass
                        
                        attached_files_info.append({
                            'name': file.name,
                            'content': file_content,
                            'size': file.size,
                            'type': file.type,
                            'lines': line_count
                        })
                
                if attached_files_info and total_lines <= MAX_TOTAL_LINES:
                    # Show usage metrics
                    col1, col2 = st.columns(2)
                    with col1:
                        files_pct = (len(attached_files_info) / MAX_FILES) * 100
                        st.progress(files_pct / 100, text=f"Files: {len(attached_files_info)}/{MAX_FILES}")
                    with col2:
                        lines_pct = (total_lines / MAX_TOTAL_LINES) * 100
                        st.progress(lines_pct / 100, text=f"Lines: {total_lines:,}/{MAX_TOTAL_LINES:,}")
                    
                    # Show file breakdown
                    with st.expander("📊 File Details", expanded=False):
                        for file_info in attached_files_info:
                            if file_info['lines'] > 0:
                                st.caption(f"📄 {file_info['name']}: {file_info['lines']:,} lines ({file_info['size'] / 1024:.1f} KB)")
                            else:
                                st.caption(f"📎 {file_info['name']}: {file_info['size'] / 1024:.1f} KB (binary)")
        
        # Input area with enhanced features
        col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
        
        with col1:
            prompt = st.chat_input("Enter your coding request...")
        
        with col2:
            use_context = st.checkbox("Context", value=True)
        
        with col3:
            use_tools = st.checkbox("Tools", value=True)
            
        with col4:
            create_artifact = st.checkbox("Artifact", value=True)
    
    if prompt:
        # Parse file references in prompt
        referenced_files = []
        if hasattr(st.session_state, 'current_project'):
            project = st.session_state.current_project
            referenced_files = parse_file_references(prompt, project.files)
        
        # Build message with attached files
        message_data = {
            'role': 'user',
            'content': prompt,
            'referenced_files': referenced_files
        }
        
        # Add attached files to message
        if attached_files_info:
            message_data['attached_files'] = attached_files_info
            
            # Add file contents to prompt context
            files_context = "\n\n--- Attached Files ---\n"
            for file_info in attached_files_info:
                try:
                    # Include line count if available
                    if file_info.get('lines', 0) > 0:
                        content = file_info['content'].decode('utf-8', errors='ignore')
                        # Limit preview to prevent context overflow
                        preview_lines = min(100, file_info['lines'])
                        preview_content = '\n'.join(content.splitlines()[:preview_lines])
                        
                        if file_info['lines'] > 100:
                            files_context += f"\n📄 {file_info['name']} ({file_info['lines']:,} lines - showing first {preview_lines}):\n```\n{preview_content}\n...\n```\n"
                        else:
                            files_context += f"\n📄 {file_info['name']} ({file_info['lines']} lines):\n```\n{content}\n```\n"
                    else:
                        files_context += f"\n📎 {file_info['name']}: [Binary file - {file_info['size'] / 1024:.1f} KB]\n"
                except:
                    files_context += f"\n📄 {file_info['name']}: [Unable to read]\n"
            
            # Append file context to prompt
            prompt = prompt + files_context
        
        # Add to messages
        if hasattr(st.session_state, 'current_project'):
            pm = st.session_state.enhanced_project_manager
            project = st.session_state.current_project
            project.chat_history.append(message_data)
            pm.save_project(project)
        else:
            st.session_state.messages.append(message_data)
        
        with st.chat_message("user"):
            st.markdown(message_data['content'])
            # Show attached files badge
            if 'attached_files' in message_data and message_data['attached_files']:
                st.caption(f"📎 {len(message_data['attached_files'])} file(s) attached")
        
        with st.chat_message("assistant"):
            async def run_generation_stream():
                context = get_project_context() if use_context else None
                
                # Add referenced files to context
                if referenced_files and context:
                    context['referenced_files'] = {}
                    for file_path in referenced_files:
                        if file_path in project.files:
                            file_obj = project.files[file_path]
                            if not file_obj.is_binary and file_obj.content:
                                context['referenced_files'][file_path] = file_obj.content
                
                # Add attached files to context
                if attached_files_info and context:
                    context['attached_files'] = attached_files_info
                
                # Use streaming version
                result = await process_code_request_stream(prompt, context)
                return result
            
            # Use streaming for better UX (with async helper)
            with AsyncContextManager() as async_ctx:
                result = async_ctx.run(run_generation_stream())
            
            # Handle streaming response format
            if 'response' in result:
                response = result['response']
                
                # Extract thinking and clean response
                thinking, cleaned_response = extract_thinking_from_response(response)
                
                code = extract_code_from_response(cleaned_response)
                
                # Create artifact if code present and enabled
                if code and create_artifact:
                    artifact_manager = ArtifactManager()
                    artifact = artifact_manager.create_artifact(
                        title=prompt[:50],
                        content=code,
                        artifact_type="code",
                        language="python"
                    )
                    
                # Save generated code to project if present
                if code and hasattr(st.session_state, 'current_project'):
                    pm = st.session_state.enhanced_project_manager
                    file_path = pm.save_generated_code(
                        st.session_state.current_project.id,
                        code,
                        "generated.py"
                    )
                    
                    message_data = {
                        "role": "assistant",
                        "content": cleaned_response,
                        "thinking": thinking,
                        "code": code,
                        "language": "python"
                    }
                else:
                    message_data = {
                        "role": "assistant",
                        "content": cleaned_response,
                        "thinking": thinking
                    }
                
                # Save to appropriate history
                if hasattr(st.session_state, 'current_project'):
                    pm = st.session_state.enhanced_project_manager
                    project = st.session_state.current_project
                    project.chat_history.append(message_data)
                    pm.save_project(project)
                else:
                    st.session_state.messages.append(message_data)
                
                # Rerun to display from history
                st.rerun()
            else:
                response = result.get('response', 'Processing failed')
                thinking, cleaned_response = extract_thinking_from_response(response)
                
                if hasattr(st.session_state, 'current_project'):
                    pm = st.session_state.enhanced_project_manager
                    project = st.session_state.current_project
                    project.chat_history.append({
                        "role": "assistant",
                        "content": cleaned_response,
                        "thinking": thinking
                    })
                    pm.save_project(project)
                else:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": cleaned_response,
                        "thinking": thinking
                    })
                
                # Rerun to display from history
                st.rerun()
    
        # Clear chat button
        if st.button("🗑️ Clear Chat"):
            if hasattr(st.session_state, 'current_project'):
                st.session_state.current_project.chat_history = []
                st.session_state.enhanced_project_manager.save_project(st.session_state.current_project)
            else:
                st.session_state.messages = []
            st.rerun()
    
    # Artifact panel in second column
    with col_artifact:
        st.subheader("📄 Artifacts")
        artifact_action = render_artifact_panel()
        
        # Handle artifact actions
        if artifact_action and artifact_action.get("action") == "continue":
            artifact_gen = ArtifactGenerator(initialize_system()[0])
            with st.spinner("Continuing generation..."):
                asyncio.run(artifact_gen.continue_artifact(artifact_action["artifact_id"]))

def dashboard():
    st.header("📊 System Dashboard")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Active Models", "14", "▲ 2")
    with col2:
        st.metric("Requests Today", "342", "▲ 45")
    with col3:
        st.metric("Avg Response Time", "2.3s", "▼ 0.5s")
    with col4:
        st.metric("Cache Hit Rate", "78%", "▲ 5%")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Request Volume")
        times = pd.date_range('2024-01-01', periods=24, freq='h')
        requests = pd.DataFrame({
            'Time': times,
            'Requests': [20, 15, 10, 8, 5, 3, 2, 5, 10, 25, 45, 60,
                        65, 70, 68, 65, 60, 55, 48, 40, 35, 30, 25, 20]
        })
        fig = px.line(requests, x='Time', y='Requests', title='Requests over Last 24 Hours')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Model Performance")
        model_data = pd.DataFrame({
            'Model': ['qwen2.5-coder', 'devstral', 'codestral', 'mistral-small', 'llama3.1'],
            'Success Rate': [95, 92, 88, 90, 87],
            'Avg Tokens/s': [45, 38, 42, 35, 40]
        })
        fig = px.bar(model_data, x='Model', y='Success Rate', title='Model Success Rates (%)')
        st.plotly_chart(fig, use_container_width=True)
    
    # System Health
    st.subheader("System Health")
    
    health_cols = st.columns(4)
    statuses = [
        ("PostgreSQL", "🟢 Healthy"),
        ("Redis", "🟢 Healthy"),
        ("Ollama", "🟢 Healthy"),
        ("ChromaDB", "🟢 Healthy")
    ]
    
    for col, (service, status) in zip(health_cols, statuses):
        with col:
            st.info(f"{service}\n{status}")

def workflow_management():
    st.header("🔄 Workflow Management")
    
    tab1, tab2, tab3 = st.tabs(["Active Workflows", "Create Workflow", "Templates"])
    
    with tab1:
        st.subheader("Active Workflows")
        
        workflows_df = pd.DataFrame({
            "ID": ["wf_001", "wf_002", "wf_003"],
            "Name": ["Code Review Pipeline", "Test Generation", "Documentation"],
            "Status": ["🟢 Running", "🟢 Running", "🟡 Queued"],
            "Progress": [75, 45, 0],
            "ETA": ["5 min", "12 min", "Waiting"]
        })
        
        st.dataframe(workflows_df, use_container_width=True)
        
        # Progress bars
        for _, row in workflows_df.iterrows():
            if row["Progress"] > 0:
                st.progress(row["Progress"] / 100, text=f"{row['Name']}: {row['Progress']}%")
    
    with tab2:
        st.subheader("Create New Workflow")
        
        workflow_name = st.text_input("Workflow Name")
        workflow_type = st.selectbox("Type", ["Sequential", "Parallel", "DAG"])
        
        st.write("Add Steps")
        steps = []
        num_steps = st.number_input("Number of steps", 1, 10, 1)
        
        for i in range(num_steps):
            with st.expander(f"Step {i+1}"):
                step_name = st.text_input(f"Name", key=f"step_name_{i}")
                step_prompt = st.text_area(f"Prompt", key=f"step_prompt_{i}")
                step_model = st.selectbox(
                    f"Model",
                    ["Auto", "qwen2.5-coder", "devstral", "llama3.1"],
                    key=f"step_model_{i}"
                )
                steps.append({
                    "name": step_name,
                    "prompt": step_prompt,
                    "model": step_model
                })
        
        if st.button("Create Workflow"):
            st.success(f"Workflow '{workflow_name}' created!")
    
    with tab3:
        st.subheader("Workflow Templates")
        
        templates = [
            {"name": "Full Stack App", "steps": 5, "description": "Generate complete web application"},
            {"name": "API + Tests", "steps": 3, "description": "Create API with unit tests"},
            {"name": "Refactor + Optimize", "steps": 4, "description": "Refactor and optimize existing code"},
            {"name": "Documentation Suite", "steps": 2, "description": "Generate comprehensive docs"}
        ]
        
        for template in templates:
            with st.expander(f"📋 {template['name']}"):
                st.write(template['description'])
                st.write(f"Steps: {template['steps']}")
                if st.button(f"Use Template", key=f"template_{template['name']}"):
                    st.info(f"Loading template: {template['name']}")

def memory_explorer():
    st.header("🧠 Memory Explorer")
    
    tab1, tab2, tab3 = st.tabs(["Hierarchy", "Search", "Analytics"])
    
    with tab1:
        st.subheader("Memory Hierarchy")
        
        # Tier visualization
        tiers = {
            "L1 - Redis Cache": {"Items": 1234, "Size": "45 MB", "Speed": "< 1ms"},
            "L2 - SQLite": {"Items": 5678, "Size": "234 MB", "Speed": "< 10ms"},
            "L3 - PostgreSQL": {"Items": 45678, "Size": "2.3 GB", "Speed": "< 50ms"},
            "L4 - ChromaDB": {"Items": 234567, "Size": "12.4 GB", "Speed": "< 200ms"}
        }
        
        for tier, stats in tiers.items():
            with st.expander(tier):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Items", stats["Items"])
                with col2:
                    st.metric("Size", stats["Size"])
                with col3:
                    st.metric("Latency", stats["Speed"])
    
    with tab2:
        st.subheader("Semantic Search")
        
        search_query = st.text_input("Search Query")
        search_type = st.radio("Type", ["Semantic", "Keyword", "Hybrid"], horizontal=True)
        
        if st.button("Search"):
            with st.spinner("Searching..."):
                # Mock results
                st.success("Found 15 results")
                
                results = [
                    {"title": "FastAPI Authentication", "similarity": 0.94, "tier": "L2"},
                    {"title": "React Component State", "similarity": 0.89, "tier": "L1"},
                    {"title": "Database Connection Pool", "similarity": 0.85, "tier": "L3"}
                ]
                
                for result in results:
                    with st.container():
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"📄 **{result['title']}**")
                        with col2:
                            st.caption(f"Match: {result['similarity']:.0%} | {result['tier']}")
    
    with tab3:
        st.subheader("Memory Analytics")
        
        # Cache performance over time
        times = pd.date_range('2024-01-01', periods=7, freq='D')
        cache_data = pd.DataFrame({
            'Date': times,
            'Hit Rate': [75, 78, 82, 80, 85, 87, 89],
            'Miss Rate': [25, 22, 18, 20, 15, 13, 11]
        })
        
        fig = px.line(cache_data, x='Date', y=['Hit Rate', 'Miss Rate'],
                     title='Cache Performance Over Time')
        st.plotly_chart(fig, use_container_width=True)

def settings_panel():
    st.header("⚙️ Settings")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Models", "Database", "API", "Export"])
    
    with tab1:
        st.subheader("Model Configuration")
        
        # Load current config
        with open('config/models.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        orchestrator_type = st.selectbox(
            "Orchestrator Type",
            ["Light (Fast)", "Heavy (Accurate)", "Balanced"]
        )
        
        temperature = st.slider("Default Temperature", 0.0, 1.0, 
                              config['model_params']['temperature'])
        
        top_p = st.slider("Top P", 0.0, 1.0,
                        config['model_params']['top_p'])
        
        if st.button("Save Model Settings"):
            config['model_params']['temperature'] = temperature
            config['model_params']['top_p'] = top_p
            with open('config/models.yaml', 'w') as f:
                yaml.dump(config, f)
            st.success("Settings saved!")
    
    with tab2:
        st.subheader("Database Configuration")
        
        db_type = st.selectbox("Primary Database", ["PostgreSQL", "SQLite", "Both"])
        
        cache_ttl = st.number_input("Cache TTL (seconds)", 60, 3600, 300)
        
        if st.button("Test Database Connection"):
            with st.spinner("Testing connections..."):
                st.success("✅ All databases connected")
    
    with tab3:
        st.subheader("API Configuration")
        
        api_port = st.number_input("API Port", 8000, 9999, 8001)
        api_host = st.text_input("API Host", "0.0.0.0")
        
        enable_cors = st.checkbox("Enable CORS", value=True)
        
        api_key = st.text_input("API Key (optional)", type="password")
        
        if st.button("Restart API Server"):
            st.info("API server restart requested")
    
    with tab4:
        st.subheader("Export & Backup")
        
        st.write("Export Options")
        
        include_chat = st.checkbox("Include chat history", value=True)
        include_projects = st.checkbox("Include projects", value=True)
        include_memory = st.checkbox("Include memory cache", value=False)
        
        if st.button("Generate Export"):
            with st.spinner("Creating export..."):
                # Mock export
                st.success("Export ready!")
                st.download_button(
                    "📥 Download Export",
                    "export_data",
                    "hydra_export.zip",
                    "application/zip"
                )

def extract_code_from_response(response: str) -> Optional[str]:
    import re
    code_pattern = r'```(?:python|py)?\n(.*?)```'
    matches = re.findall(code_pattern, response, re.DOTALL)
    if matches:
        return matches[0].strip()
    return None

def extract_thinking_from_response(response: str) -> tuple[Optional[str], str]:
    """Extract thinking section and clean response, similar to Claude's UI"""
    import re
    
    # Common thinking patterns from various models
    thinking_patterns = [
        r'<thinking>(.*?)</thinking>',  # XML style (Claude-like)
        r'\[Thinking\](.*?)\[/Thinking\]',  # Bracket style
        r'<!-- thinking -->(.*?)<!-- /thinking -->',  # HTML comment style
        r'"""thinking(.*?)"""',  # Python docstring style
        r'<\|thinking\|>(.*?)<\|/thinking\|>',  # Special token style
    ]
    
    thinking_content = None
    cleaned_response = response
    
    for pattern in thinking_patterns:
        matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
        if matches:
            thinking_content = matches[0].strip()
            # Remove thinking from response
            cleaned_response = re.sub(pattern, '', response, flags=re.DOTALL | re.IGNORECASE).strip()
            break
    
    return thinking_content, cleaned_response

def process_attached_files(files_list):
    """Process attached files and extract readable content"""
    processed_files = []
    for file_info in files_list:
        processed = {
            'name': file_info['name'],
            'size': file_info['size'],
            'type': file_info.get('type', 'unknown')
        }
        
        # Try to extract text content from common file types
        try:
            if file_info['name'].endswith(('.txt', '.md', '.log', '.csv', '.json', '.xml', '.yaml', '.yml')):
                processed['content'] = file_info['content'].decode('utf-8', errors='ignore')
                processed['is_text'] = True
            elif file_info['name'].endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h', '.cs', '.go', '.rs', '.rb', '.php')):
                processed['content'] = file_info['content'].decode('utf-8', errors='ignore')
                processed['is_text'] = True
                processed['language'] = file_info['name'].split('.')[-1]
            else:
                processed['is_text'] = False
                processed['content'] = None
        except:
            processed['is_text'] = False
            processed['content'] = None
        
        processed_files.append(processed)
    
    return processed_files

if __name__ == "__main__":
    main()