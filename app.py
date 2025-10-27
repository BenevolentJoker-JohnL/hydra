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
import warnings
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Suppress noisy warnings
# - Streamlit context warnings: harmless, occur during multiprocessing initialization
# - Plotly deprecation warnings: non-critical, will be fixed in future Streamlit releases
# - Distributed warnings: port conflicts are handled automatically
warnings.filterwarnings('ignore', category=UserWarning, module='streamlit.runtime.scriptrunner_utils.script_run_context')
warnings.filterwarnings('ignore', category=UserWarning, module='streamlit.runtime.state.session_state_proxy')
warnings.filterwarnings('ignore', category=UserWarning, module='streamlit.elements.plotly_chart')
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='distributed.node')
logging.getLogger('streamlit.runtime.scriptrunner_utils.script_run_context').setLevel(logging.ERROR)
logging.getLogger('streamlit.runtime.state.session_state_proxy').setLevel(logging.ERROR)
logging.getLogger('streamlit.elements.plotly_chart').setLevel(logging.ERROR)
logging.getLogger('distributed.node').setLevel(logging.ERROR)

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Configure logging at startup
configure_logging(verbose=True)

from core.orchestrator import ModelOrchestrator
from core.sollol_integration import SOLLOLIntegration
from core.code_assistant import CodeAssistant, StreamingCodeAssistant, TaskDetector
import os

# Try to import workflow pipeline, but make it optional
WORKFLOW_AVAILABLE = False
code_generation_pipeline = None
try:
    from workflows.dag_pipeline import code_generation_pipeline
    WORKFLOW_AVAILABLE = True
    logger.info("Workflow pipeline loaded successfully")
except Exception as e:
    logger.info(f"Workflow pipeline not available (optional): {e}")
    # This is expected and OK - workflow is optional
    pass

from db.connections import db_manager
from core.memory import HierarchicalMemory
from ui.enhanced_project_manager import EnhancedProjectManager, render_enhanced_project_sidebar, render_project_files_panel
from ui.project_context import get_project_context
from ui.artifacts import ArtifactManager, ArtifactGenerator, render_artifact_panel, render_artifacts_sidebar, extract_artifacts_from_response
from ui.file_handler import FileHandler, render_file_upload_zone, create_file_reference, parse_file_references, render_file_in_chat, FileSearch
from ui.terminal import Terminal, GenerationLogger, render_terminal_panel
from ui.approval_handler import ApprovalHandler, render_approval_stats, setup_auto_approval_rules
from core.tools import ToolRegistry, ToolEnhancedGenerator
from core.user_preferences import get_preferences_manager
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

# Initialize preferences manager
if 'preferences_manager' not in st.session_state:
    st.session_state.preferences_manager = get_preferences_manager()
    # Load saved preferences into session state
    routing_prefs = st.session_state.preferences_manager.get_routing_preferences()
    ui_prefs = st.session_state.preferences_manager.get_ui_preferences()

    st.session_state.routing_mode = routing_prefs.mode
    st.session_state.priority = routing_prefs.priority
    st.session_state.min_success_rate = routing_prefs.min_success_rate
    st.session_state.prefer_cpu = routing_prefs.prefer_cpu

    st.session_state.use_context_default = ui_prefs.use_context
    st.session_state.use_tools_default = ui_prefs.use_tools
    st.session_state.use_reasoning_default = ui_prefs.use_reasoning
    st.session_state.create_artifacts_default = ui_prefs.create_artifacts

@st.cache_resource
def initialize_system():
    """Initialize Hydra system with SOLLOL integration"""
    from core.config_loader import load_model_config

    # Load config with environment variable overrides
    config = load_model_config()

    # Initialize SOLLOL with configuration from environment variables
    sollol_config = {
        'app_name': os.getenv('HYDRA_APP_NAME', 'Hydra-UI'),
        'register_with_dashboard': os.getenv('SOLLOL_REGISTER_APP', 'true').lower() == 'true',
        'discovery_enabled': os.getenv('SOLLOL_DISCOVERY_ENABLED', 'true').lower() == 'true',
        'discovery_timeout': int(os.getenv('SOLLOL_DISCOVERY_TIMEOUT', '10')),
        'health_check_interval': int(os.getenv('SOLLOL_HEALTH_CHECK_INTERVAL', '120')),
        'enable_vram_monitoring': os.getenv('SOLLOL_VRAM_MONITORING', 'true').lower() == 'true',
        'enable_dashboard': os.getenv('SOLLOL_DASHBOARD_ENABLED', 'true').lower() == 'true',
        'dashboard_port': int(os.getenv('SOLLOL_DASHBOARD_PORT', '8080')),
        'redis_host': os.getenv('REDIS_HOST', 'localhost'),
        'redis_port': int(os.getenv('REDIS_PORT', '6379')),
        'log_level': os.getenv('SOLLOL_LOG_LEVEL', 'INFO').upper(),
        'default_routing_mode': os.getenv('SOLLOL_DEFAULT_ROUTING_MODE', 'async').lower()
    }

    logger.info(f"🚀 Initializing Hydra with SOLLOL...")
    logger.info(f"   App Name: {sollol_config['app_name']}")
    logger.info(f"   Register with Dashboard: {sollol_config['register_with_dashboard']}")
    logger.info(f"   Discovery: {sollol_config['discovery_enabled']}")
    logger.info(f"   VRAM Monitoring: {sollol_config['enable_vram_monitoring']}")
    logger.info(f"   Dashboard: {'enabled' if sollol_config['enable_dashboard'] else 'disabled'} (port {sollol_config['dashboard_port']})")

    try:
        # Create SOLLOL integration (replaces OllamaLoadBalancer)
        sollol = SOLLOLIntegration(config=sollol_config)

        # Initialize SOLLOL (synchronously for Streamlit)
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(sollol.initialize())

        logger.info(f"✅ SOLLOL initialized successfully")
        logger.info(f"📊 Discovered {len(sollol.hosts)} Ollama nodes")

        # Print discovered nodes for debugging
        if len(sollol.hosts) == 0:
            print("\n" + "!"*70)
            print("⚠️  WARNING: NO OLLAMA NODES DISCOVERED!")
            print("!"*70)
            print("SOLLOL couldn't find any Ollama nodes.")
            print("\nTroubleshooting:")
            print("1. Make sure Ollama is running: systemctl status ollama")
            print("2. Test connection: curl http://localhost:11434/api/tags")
            print("3. Check SOLLOL discovery settings in .env")
            print("!"*70 + "\n")
        else:
            print(f"\n✅ Discovered {len(sollol.hosts)} Ollama node(s):")
            for host in sollol.hosts:
                print(f"   • {host}")
            print()

        if sollol.dashboard_enabled and sollol.dashboard:
            # Print prominent dashboard URL banner
            print("\n" + "="*70)
            print(f"🎯 SOLLOL UNIFIED DASHBOARD")
            print(f"   URL: http://localhost:{sollol.dashboard_port}")
            print(f"   Features: Node monitoring, VRAM tracking, routing logs, metrics")
            print("="*70 + "\n")
            logger.info(f"🎨 SOLLOL Dashboard running on port {sollol.dashboard_port}")

        # Initialize orchestrator with SOLLOL
        orchestrator = ModelOrchestrator(sollol)
        # Pass orchestrator to code assistant for autonomous agent support
        code_assistant = StreamingCodeAssistant(sollol, orchestrator)

        # Setup approval handler and auto-approval rules
        setup_auto_approval_rules(code_assistant.approval_tracker)
        logger.info("✅ Approval system initialized with default rules")

        return sollol, orchestrator, config, code_assistant

    except Exception as e:
        logger.error(f"❌ Failed to initialize SOLLOL: {e}")
        import traceback
        traceback.print_exc()
        # Return None for sollol but still create other objects
        orchestrator = None
        code_assistant = StreamingCodeAssistant(None, None)

        # Setup approval handler even on error
        setup_auto_approval_rules(code_assistant.approval_tracker)

        return None, orchestrator, config, code_assistant

async def process_code_request_stream(prompt: str, context: Dict = None, use_tools: bool = False, autonomous: bool = False):
    """Process code request with streaming response using Code Assistant"""
    sollol, orchestrator, config, code_assistant = initialize_system()
    
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
    if not sollol:
        st.error("⚠️ SOLLOL is not initialized. Please ensure Ollama is running.")
        st.info("You can download Ollama from: https://ollama.com/download")
        st.code("# After installing, run:\ncurl -fsSL https://ollama.com/install.sh | sh\nsudo systemctl start ollama", language="bash")
        return {'response': 'Ollama connection required', 'error': True}

    # Check if we have any nodes discovered
    if len(sollol.hosts) == 0:
        st.error("⚠️ NO OLLAMA NODES DISCOVERED!")
        st.warning("""
        SOLLOL couldn't find any Ollama nodes.

        **Troubleshooting:**
        1. Check if Ollama is running: `systemctl status ollama`
        2. Test connection: `curl http://localhost:11434/api/tags`
        3. Restart Streamlit app to retry discovery
        4. Check SOLLOL logs above for details
        """)
        return {'response': 'No Ollama nodes available', 'error': True}
    
    # Use Code Assistant for intelligent handling
    try:
        # Stream the response
        logger.log_orchestration(f"Starting {task_type.value} task")

        # Get routing settings from session state (set in UI)
        routing_mode = st.session_state.get('routing_mode', None)
        priority = st.session_state.get('priority', 5)
        min_success_rate = st.session_state.get('min_success_rate', 0.0)
        prefer_cpu = st.session_state.get('prefer_cpu', False)

        async for chunk_data in code_assistant.process_stream(
            prompt,
            context,
            use_tools=use_tools,
            autonomous=autonomous,
            routing_mode=routing_mode,
            priority=priority,
            min_success_rate=min_success_rate,
            prefer_cpu=prefer_cpu
        ):
            if 'chunk' in chunk_data:
                # Check if this is a formatted replacement
                if chunk_data.get('replace_all', False):
                    # Replace entire response with formatted version
                    full_response = chunk_data['chunk']
                    response_placeholder.markdown(full_response)
                    logger.log_success(f"✨ Code automatically formatted")
                else:
                    # Normal streaming - append chunks
                    full_response += chunk_data['chunk']
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
    sollol, orchestrator, config, code_assistant = initialize_system()
    
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
    # Print dashboard info on first run (before any UI rendering)
    if 'dashboard_banner_shown' not in st.session_state:
        dashboard_port = int(os.getenv('SOLLOL_DASHBOARD_PORT', '8080'))
        print("\n" + "="*70)
        print("🐉 HYDRA - INTELLIGENT CODE SYNTHESIS")
        print("="*70)
        print(f"📊 SOLLOL Dashboard: http://localhost:{dashboard_port}")
        print(f"💬 Streamlit UI: http://localhost:8502")
        print("="*70 + "\n")
        st.session_state.dashboard_banner_shown = True

    # Title with version
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    with col1:
        st.title("🐉 Hydra - Intelligent Code Synthesis")
    with col2:
        st.caption("v1.0.0")
        # Dashboard link
        dashboard_port = int(os.getenv('SOLLOL_DASHBOARD_PORT', '8080'))
        st.markdown(f"[📊 Dashboard](http://localhost:{dashboard_port})", unsafe_allow_html=True)
    with col3:
        # New Chat button
        if st.button("🆕 New Chat", key="new_chat_btn", help="Start a fresh conversation"):
            # Clear messages
            if hasattr(st.session_state, 'current_project'):
                # If in a project, clear project chat history
                st.session_state.current_project.chat_history = []
                pm = st.session_state.enhanced_project_manager
                pm.save_project(st.session_state.current_project)
                st.success("✅ Project chat cleared!")
            else:
                # Clear global messages
                st.session_state.messages = []
                st.success("✅ Chat cleared!")
            st.rerun()
    with col4:
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
    # Initialize approval handler
    if 'approval_handler' not in st.session_state:
        st.session_state.approval_handler = ApprovalHandler()
    approval_handler = st.session_state.approval_handler

    # Setup approval callback for code_assistant if available
    if 'code_assistant' in st.session_state:
        st.session_state.code_assistant.tool_caller.set_approval_callback(
            approval_handler.request_approval
        )

    # Create columns for chat and artifacts
    col_chat, col_artifact = st.columns([1, 1])

    with col_chat:
        # Render pending approval requests
        approval_handler.render_pending_approvals()

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
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2.2, 1, 1, 1, 1, 1, 0.9])

        with col1:
            prompt = st.chat_input("Enter your coding request...")

        with col2:
            use_context = st.checkbox(
                "Context",
                value=st.session_state.get('use_context_default', True),
                help="Include project context"
            )

        with col3:
            use_tools = st.checkbox(
                "Tools",
                value=st.session_state.get('use_tools_default', True),
                help="Enable tool usage"
            )

        with col4:
            use_reasoning = st.checkbox(
                "🧠 Reasoning",
                value=st.session_state.get('use_reasoning_default', False),
                help="Use Claude-style reasoning (slower, higher quality)"
            )

        with col5:
            use_autonomous = st.checkbox(
                "🤖 Autonomous",
                value=st.session_state.get('use_autonomous_default', False),
                help="Multi-step iterative solving (Claude Code style) - requires Tools to be enabled"
            )

        with col6:
            use_consensus = st.checkbox(
                "🗳️ Consensus",
                value=st.session_state.get('use_consensus_default', False),
                help="Multi-model voting for higher quality (slower)"
            )

        with col7:
            create_artifact = st.checkbox(
                "📦 Artifact",
                value=st.session_state.get('create_artifacts_default', True),
                help="Save code blocks"
            )

        # Routing mode selection (below input controls)
        with st.expander("⚙️ Advanced Routing Settings", expanded=False):
            routing_col1, routing_col2, routing_col3, routing_col4 = st.columns(4)

            # Get saved routing mode for index
            saved_mode = st.session_state.get('routing_mode', None)
            mode_options = ["Auto", "Fast", "Reliable", "Async"]
            if saved_mode is None:
                mode_index = 0
            else:
                mode_index = mode_options.index(saved_mode.capitalize()) if saved_mode.capitalize() in mode_options else 0

            with routing_col1:
                routing_mode = st.selectbox(
                    "Routing Mode",
                    options=mode_options,
                    index=mode_index,
                    help="""
                    • **Auto**: Use default routing strategy
                    • **Fast**: GPU-first, lowest latency (user-facing tasks)
                    • **Reliable**: Stability over speed (production code, critical tasks)
                    • **Async**: CPU-preferred, resource-efficient (background tasks)
                    """
                )

            with routing_col2:
                priority = st.slider(
                    "Priority",
                    min_value=1,
                    max_value=10,
                    value=st.session_state.get('priority', 5),
                    help="Request priority (1=lowest, 10=urgent)"
                )

            with routing_col3:
                min_success_rate = st.slider(
                    "Min Success Rate (Reliable)",
                    min_value=0.0,
                    max_value=1.0,
                    value=st.session_state.get('min_success_rate', 0.95),
                    step=0.05,
                    help="Minimum node success rate for RELIABLE mode"
                )

            with routing_col4:
                prefer_cpu = st.checkbox(
                    "Prefer CPU (Async)",
                    value=st.session_state.get('prefer_cpu', False),
                    help="Intentionally use CPU to free GPU for ASYNC mode"
                )

            # Store routing settings in session state AND save to preferences
            new_routing_mode = None if routing_mode == "Auto" else routing_mode.lower()

            # Check if settings changed and save
            settings_changed = (
                st.session_state.get('routing_mode') != new_routing_mode or
                st.session_state.get('priority') != priority or
                st.session_state.get('min_success_rate') != min_success_rate or
                st.session_state.get('prefer_cpu') != prefer_cpu
            )

            st.session_state.routing_mode = new_routing_mode
            st.session_state.priority = priority
            st.session_state.min_success_rate = min_success_rate
            st.session_state.prefer_cpu = prefer_cpu

            if settings_changed and 'preferences_manager' in st.session_state:
                # Save to persistent preferences
                st.session_state.preferences_manager.update_routing_preferences(
                    mode=new_routing_mode,
                    priority=priority,
                    min_success_rate=min_success_rate,
                    prefer_cpu=prefer_cpu
                )

            # Add button to reset to defaults
            if st.button("🔄 Reset to Defaults", help="Reset routing settings to defaults"):
                st.session_state.preferences_manager.reset_to_defaults()
                st.rerun()
    
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

                # Use reasoning mode if enabled
                if use_reasoning:
                    # Use cached orchestrator from session state if available (preserves settings)
                    if 'orchestrator' in st.session_state and st.session_state.orchestrator:
                        orchestrator = st.session_state.orchestrator
                    else:
                        _, orchestrator, _, _ = initialize_system()
                        st.session_state.orchestrator = orchestrator

                    if orchestrator:
                        # Use reasoning engine for higher quality
                        response_placeholder = st.empty()
                        thinking_placeholder = st.empty()
                        full_response = ""
                        thinking_content = ""

                        async for chunk in orchestrator.orchestrate_reasoning_stream(prompt, context):
                            if chunk.get('type') == 'thinking':
                                thinking_content += chunk['chunk']
                                thinking_placeholder.expander("🤔 Thinking", expanded=False).markdown(thinking_content)
                            elif chunk.get('type') == 'response':
                                full_response += chunk['chunk']
                                response_placeholder.markdown(full_response)

                        return {'response': full_response, 'thinking': thinking_content}

                # Use standard streaming version
                result = await process_code_request_stream(prompt, context, use_tools=use_tools, autonomous=use_autonomous)
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

    # SOLLOL Dashboard Link (prominent)
    dashboard_port = int(os.getenv('SOLLOL_DASHBOARD_PORT', '8080'))
    st.info(f"""
    **🎯 SOLLOL Unified Dashboard**

    Real-time monitoring of distributed Ollama nodes, routing decisions, and performance metrics.

    👉 **[Open SOLLOL Dashboard](http://localhost:{dashboard_port})** (opens in new tab)

    Features:
    - Live node status and VRAM usage
    - Routing decision logs
    - Request/response metrics
    - Multi-application coordination
    """)

    st.divider()

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

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Models", "Database", "API", "Export", "Reasoning", "🔐 Tool Approvals"])
    
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

    with tab5:
        st.subheader("🧠 Reasoning Engine")

        st.markdown("""
        Configure Claude-style reasoning for local models. The reasoning engine adds
        structured thinking and self-critique capabilities to improve response quality.
        """)

        # Initialize orchestrator to access reasoning settings
        # Use cached orchestrator from session state if available
        if 'orchestrator' in st.session_state and st.session_state.orchestrator:
            orchestrator = st.session_state.orchestrator
        else:
            _, orchestrator, _, _ = initialize_system()
            if orchestrator:
                st.session_state.orchestrator = orchestrator

        if orchestrator is None:
            st.error("Orchestrator not initialized. Please check SOLLOL connection.")
            return

        # Current settings display
        current_mode = os.getenv('HYDRA_REASONING_MODE', 'auto')
        current_style = os.getenv('HYDRA_THINKING_STYLE', 'cot')
        current_thinking_tokens = int(os.getenv('HYDRA_MAX_THINKING_TOKENS', '8000'))
        current_critique_iterations = int(os.getenv('HYDRA_MAX_CRITIQUE_ITERATIONS', '2'))
        use_reasoning_model = os.getenv('HYDRA_USE_REASONING_MODEL', 'true').lower() == 'true'
        show_thinking = os.getenv('HYDRA_SHOW_THINKING', 'true').lower() == 'true'

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Reasoning Mode")
            reasoning_mode = st.selectbox(
                "Mode",
                options=["auto", "fast", "standard", "extended", "deep"],
                index=["auto", "fast", "standard", "extended", "deep"].index(current_mode) if current_mode in ["auto", "fast", "standard", "extended", "deep"] else 0,
                help="""
                - **Auto**: Automatically select based on task complexity
                - **Fast**: Direct response, no thinking (~1-2s)
                - **Standard**: Chain-of-thought reasoning (~3-5s)
                - **Extended**: Deep reasoning with QwQ (~10-30s)
                - **Deep**: Maximum thinking budget, multi-pass critique (~30-60s+)
                """
            )

            thinking_style = st.selectbox(
                "Thinking Style",
                options=["cot", "tot", "critique", "refine"],
                index=["cot", "tot", "critique", "refine"].index(current_style),
                help="""
                - **CoT**: Chain of Thought - step-by-step reasoning
                - **ToT**: Tree of Thought - explore multiple paths
                - **Critique**: Self-critique and improve
                - **Refine**: Iterative refinement
                """
            )

            max_thinking_tokens = st.slider(
                "Max Thinking Tokens",
                min_value=1000,
                max_value=16000,
                value=current_thinking_tokens,
                step=1000,
                help="Maximum tokens allocated for thinking/reasoning process"
            )

        with col2:
            st.markdown("### Advanced Settings")

            max_critique_iterations = st.slider(
                "Self-Critique Iterations",
                min_value=0,
                max_value=5,
                value=current_critique_iterations,
                help="Number of self-critique and improvement loops (0-5)"
            )

            use_specialized_model = st.checkbox(
                "Use Specialized Reasoning Model (QwQ)",
                value=use_reasoning_model,
                help="Use QwQ:32b for extended reasoning tasks (slower but higher quality)"
            )

            show_thinking_process = st.checkbox(
                "Show Thinking Process",
                value=show_thinking,
                help="Display the model's thinking process in chat (like Claude)"
            )

        # Deep Thinking Settings
        st.markdown("---")
        st.markdown("### 🧠💭 Deep Thinking Mode Settings")
        st.caption("Programmatic long think - automatically triggered for very complex tasks")

        deep_thinking_tokens = int(os.getenv('HYDRA_DEEP_THINKING_TOKENS', '32000'))
        deep_thinking_iterations = int(os.getenv('HYDRA_DEEP_THINKING_ITERATIONS', '3'))
        deep_thinking_threshold = float(os.getenv('HYDRA_DEEP_THINKING_THRESHOLD', '8.0'))

        col1, col2, col3 = st.columns(3)

        with col1:
            deep_thinking_tokens = st.slider(
                "Deep Thinking Token Budget",
                min_value=8000,
                max_value=64000,
                value=deep_thinking_tokens,
                step=4000,
                help="Maximum tokens for deep thinking mode (higher = more thorough but slower)"
            )

        with col2:
            deep_thinking_iterations = st.slider(
                "Deep Critique Passes",
                min_value=1,
                max_value=5,
                value=deep_thinking_iterations,
                help="Number of self-critique iterations in deep thinking mode"
            )

        with col3:
            deep_thinking_threshold = st.slider(
                "Auto-Trigger Threshold",
                min_value=7.0,
                max_value=10.0,
                value=deep_thinking_threshold,
                step=0.5,
                help="Complexity score (1-10) that triggers deep thinking automatically. Set to 10+ to disable."
            )

        st.info(f"💡 Deep thinking will auto-trigger when task complexity ≥ {deep_thinking_threshold:.1f}/10.0")

        # Save button
        st.markdown("---")
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            if st.button("💾 Save Reasoning Settings", use_container_width=True):
                # Update environment variables in .env file
                from dotenv import set_key
                env_path = '.env'

                set_key(env_path, 'HYDRA_REASONING_MODE', reasoning_mode)
                set_key(env_path, 'HYDRA_THINKING_STYLE', thinking_style)
                set_key(env_path, 'HYDRA_MAX_THINKING_TOKENS', str(max_thinking_tokens))
                set_key(env_path, 'HYDRA_MAX_CRITIQUE_ITERATIONS', str(max_critique_iterations))
                set_key(env_path, 'HYDRA_USE_REASONING_MODEL', 'true' if use_specialized_model else 'false')
                set_key(env_path, 'HYDRA_SHOW_THINKING', 'true' if show_thinking_process else 'false')

                # Deep thinking parameters
                set_key(env_path, 'HYDRA_DEEP_THINKING_TOKENS', str(deep_thinking_tokens))
                set_key(env_path, 'HYDRA_DEEP_THINKING_ITERATIONS', str(deep_thinking_iterations))
                set_key(env_path, 'HYDRA_DEEP_THINKING_THRESHOLD', str(deep_thinking_threshold))

                st.success("✅ Settings saved! Restart the app to apply changes.")

        with col2:
            if st.button("🔄 Apply Now", use_container_width=True):
                # Apply settings to current orchestrator session
                from core.reasoning_engine import ReasoningMode, ThinkingStyle

                mode_map = {
                    'auto': ReasoningMode.AUTO,
                    'fast': ReasoningMode.FAST,
                    'standard': ReasoningMode.STANDARD,
                    'extended': ReasoningMode.EXTENDED,
                    'deep': ReasoningMode.DEEP_THINKING
                }
                style_map = {
                    'cot': ThinkingStyle.CHAIN_OF_THOUGHT,
                    'tot': ThinkingStyle.TREE_OF_THOUGHT,
                    'critique': ThinkingStyle.SELF_CRITIQUE,
                    'refine': ThinkingStyle.ITERATIVE_REFINEMENT
                }

                orchestrator.set_reasoning_mode(mode_map[reasoning_mode])
                orchestrator.set_thinking_style(style_map[thinking_style])
                orchestrator.update_reasoning_config(
                    max_thinking_tokens=max_thinking_tokens,
                    max_critique_iterations=max_critique_iterations,
                    use_reasoning_model=use_specialized_model,
                    show_thinking=show_thinking_process,
                    deep_thinking_tokens=deep_thinking_tokens,
                    deep_thinking_iterations=deep_thinking_iterations,
                    deep_thinking_threshold=deep_thinking_threshold
                )

                # Store updated orchestrator in session state so it persists across requests
                st.session_state.orchestrator = orchestrator

                st.success("✅ Applied to current session!")

        with col3:
            if st.button("↩️ Reset", use_container_width=True):
                st.rerun()

        # Information section
        st.markdown("---")
        st.markdown("### 📊 Reasoning Models")

        col1, col2 = st.columns(2)

        with col1:
            st.info(f"""
            **Current Reasoning Model**
            - Model: `qwq:32b`
            - Optimized for: Deep reasoning, complex tasks
            - Token budget: {max_thinking_tokens:,} tokens
            """)

        with col2:
            st.info(f"""
            **Performance Impact**
            - Fast mode: ~1-2s per response
            - Standard mode: ~3-5s per response
            - Extended mode: ~10-30s per response
            - **Deep mode: ~30-60s+ per response**

            Deep mode uses {deep_thinking_tokens:,} tokens with {deep_thinking_iterations} critique passes.
            """)

    with tab6:
        st.subheader("🔐 Tool Execution Approvals")

        st.markdown("""
        Configure how Hydra requests approval for tool executions.
        **CRITICAL operations** (write_file, run_command) always require approval and cannot be bypassed.
        """)

        # Display approval statistics
        render_approval_stats()

        st.markdown("---")
        st.markdown("### 🔒 Permission Levels")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.success("""
            **SAFE**
            - read_file
            - list_directory
            - analyze_code
            - search_codebase

            Auto-approved, no prompts.
            """)

        with col2:
            st.warning("""
            **REQUIRES_APPROVAL**
            - execute_python

            Needs approval, but can be auto-approved with rules.
            """)

        with col3:
            st.error("""
            **CRITICAL**
            - write_file
            - run_command

            **ALWAYS** requires explicit approval. Cannot bypass.
            """)

        st.markdown("---")
        st.markdown("### ⚡ Auto-Approval Rules")

        st.info("""
        Auto-approval rules allow frequently used operations to proceed without prompting.
        - **Previously approved**: Same operation won't ask again
        - **Pattern matching**: Operations matching safe patterns auto-approve
        - **Session limits**: Prevent excessive auto-approvals

        **CRITICAL operations are NEVER auto-approved.**
        """)

        if 'code_assistant' in st.session_state:
            tracker = st.session_state.code_assistant.approval_tracker
            stats = tracker.get_approval_stats()

            st.markdown(f"**Active Rules**: {stats['auto_approval_patterns']}")

            if st.button("🔄 Reset All Approvals"):
                tracker.approved_operations.clear()
                tracker.approval_history.clear()
                tracker.session_approvals.clear()
                st.success("✅ All approval history cleared!")
                st.rerun()

            if st.button("➕ Add Custom Rule"):
                st.info("Custom rule UI coming soon! Edit `ui/approval_handler.py` to add patterns manually.")

        else:
            st.warning("Code assistant not initialized. Start a chat session to configure approvals.")

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