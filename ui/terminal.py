import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional
import json
from collections import deque
import time

class Terminal:
    """Terminal/Console component for showing logs and generation output"""
    
    def __init__(self, max_lines: int = 1000):
        if 'terminal_logs' not in st.session_state:
            st.session_state.terminal_logs = deque(maxlen=max_lines)
        if 'terminal_auto_scroll' not in st.session_state:
            st.session_state.terminal_auto_scroll = True
        if 'terminal_show_timestamps' not in st.session_state:
            st.session_state.terminal_show_timestamps = True
        if 'terminal_log_level' not in st.session_state:
            st.session_state.terminal_log_level = "INFO"
            
    def log(self, message: str, level: str = "INFO", source: str = "System"):
        """Add a log entry to the terminal"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        log_entry = {
            'timestamp': timestamp,
            'level': level,
            'source': source,
            'message': message
        }
        
        st.session_state.terminal_logs.append(log_entry)
        
    def clear(self):
        """Clear all terminal logs"""
        st.session_state.terminal_logs.clear()
        
    def get_logs(self, level_filter: Optional[str] = None) -> List[Dict]:
        """Get filtered logs"""
        if level_filter and level_filter != "ALL":
            return [log for log in st.session_state.terminal_logs 
                   if log['level'] == level_filter]
        return list(st.session_state.terminal_logs)
    
    def render(self, height: int = 400, key: str = "terminal"):
        """Render the terminal interface"""
        
        # Terminal header with controls
        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])
        
        with col1:
            level_filter = st.selectbox(
                "Log Level",
                ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"],
                index=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"].index(
                    st.session_state.terminal_log_level
                ),
                key=f"{key}_level",
                label_visibility="collapsed"
            )
            st.session_state.terminal_log_level = level_filter
            
        with col2:
            search = st.text_input(
                "Search logs",
                placeholder="Filter...",
                key=f"{key}_search",
                label_visibility="collapsed"
            )
            
        with col3:
            st.session_state.terminal_show_timestamps = st.checkbox(
                "Timestamps",
                value=st.session_state.terminal_show_timestamps,
                key=f"{key}_timestamps"
            )
            
        with col4:
            st.session_state.terminal_auto_scroll = st.checkbox(
                "Auto-scroll",
                value=st.session_state.terminal_auto_scroll,
                key=f"{key}_autoscroll"
            )
            
        with col5:
            if st.button("🗑️ Clear", key=f"{key}_clear"):
                self.clear()
                st.rerun()
        
        # Terminal content
        terminal_css = """
        <style>
        .terminal {
            background-color: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Consolas', 'Monaco', 'Lucida Console', monospace;
            font-size: 12px;
            padding: 10px;
            border-radius: 5px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .log-debug { color: #808080; }
        .log-info { color: #d4d4d4; }
        .log-warning { color: #ce9178; }
        .log-error { color: #f48771; }
        .log-success { color: #4ec9b0; }
        .log-timestamp { color: #608b4e; }
        .log-source { color: #569cd6; }
        .log-model { color: #c586c0; }
        .log-generation { color: #dcdcaa; }
        </style>
        """
        
        st.markdown(terminal_css, unsafe_allow_html=True)
        
        # Get filtered logs
        logs = self.get_logs(level_filter if level_filter != "ALL" else None)
        
        # Apply search filter
        if search:
            logs = [log for log in logs if search.lower() in log['message'].lower()]
        
        # Format logs for display
        log_html = '<div class="terminal" style="height: {}px;">'.format(height)
        
        for log in logs:
            level_class = f"log-{log['level'].lower()}"
            
            if st.session_state.terminal_show_timestamps:
                log_html += f'<span class="log-timestamp">[{log["timestamp"]}]</span> '
                
            log_html += f'<span class="{level_class}">[{log["level"]}]</span> '
            log_html += f'<span class="log-source">[{log["source"]}]</span> '
            log_html += f'<span class="{level_class}">{log["message"]}</span>\n'
        
        log_html += '</div>'
        
        # Auto-scroll JavaScript
        if st.session_state.terminal_auto_scroll:
            log_html += """
            <script>
            var terminal = document.querySelector('.terminal');
            if (terminal) {
                terminal.scrollTop = terminal.scrollHeight;
            }
            </script>
            """
        
        st.markdown(log_html, unsafe_allow_html=True)
        
        # Status bar
        st.caption(f"Showing {len(logs)} logs")

class GenerationLogger:
    """Logger specifically for model generation events"""
    
    def __init__(self, terminal: Terminal):
        self.terminal = terminal
        self.current_task = None
        self.start_time = None
        
    def start_generation(self, prompt: str, model: str = None, task_id: str = None):
        """Log start of generation"""
        self.current_task = task_id or f"gen_{int(time.time())}"
        self.start_time = time.time()
        
        self.terminal.log(
            f"Starting generation with {model or 'default model'}",
            "INFO",
            "Generator"
        )
        
        # Log prompt preview
        preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
        self.terminal.log(
            f"Prompt: {preview}",
            "DEBUG",
            "Generator"
        )
        
    def log_model_call(self, model: str, status: str = "calling"):
        """Log model API calls"""
        self.terminal.log(
            f"Model {model}: {status}",
            "INFO",
            "ModelAPI"
        )
        
    def log_token_generation(self, tokens: int, model: str):
        """Log token generation progress"""
        self.terminal.log(
            f"Generated {tokens} tokens from {model}",
            "DEBUG",
            "Tokenizer"
        )
        
    def log_orchestration(self, action: str, details: str = ""):
        """Log orchestration events"""
        self.terminal.log(
            f"Orchestration: {action} {details}",
            "INFO",
            "Orchestrator"
        )
        
    def log_synthesis(self, models: List[str], consensus: float = None):
        """Log code synthesis events"""
        msg = f"Synthesizing from {len(models)} models"
        if consensus:
            msg += f" (consensus: {consensus:.2%})"
        
        self.terminal.log(msg, "INFO", "Synthesizer")
        
    def log_tool_call(self, tool: str, params: Dict = None):
        """Log tool usage"""
        msg = f"Calling tool: {tool}"
        if params:
            msg += f" with params: {json.dumps(params, indent=0)[:100]}"
            
        self.terminal.log(msg, "INFO", "Tools")
        
    def log_memory_operation(self, operation: str, tier: str = None):
        """Log memory operations"""
        msg = f"Memory {operation}"
        if tier:
            msg += f" in {tier}"
            
        self.terminal.log(msg, "DEBUG", "Memory")
        
    def log_error(self, error: str, source: str = "System"):
        """Log errors"""
        self.terminal.log(
            f"Error: {error}",
            "ERROR",
            source
        )
        
    def log_success(self, message: str):
        """Log successful completion"""
        if self.start_time:
            elapsed = time.time() - self.start_time
            message += f" (took {elapsed:.2f}s)"
            
        self.terminal.log(message, "INFO", "Generator")
        self.current_task = None
        self.start_time = None
        
    def log_stream_chunk(self, chunk: str, model: str = None):
        """Log streaming chunks"""
        if model:
            self.terminal.log(
                f"Stream chunk from {model}: {len(chunk)} chars",
                "DEBUG",
                "Stream"
            )

def render_terminal_panel():
    """Render terminal as a panel in the UI"""
    st.subheader("🖥️ System Terminal")
    
    terminal = Terminal()
    
    # Add some controls
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("📝 Test Log"):
            terminal.log("Test log message", "INFO", "Test")
            terminal.log("Debug information", "DEBUG", "Test")
            terminal.log("Warning message", "WARNING", "Test")
            terminal.log("Error occurred", "ERROR", "Test")
            st.rerun()
    
    # Render terminal
    terminal.render(height=500)
    
    return terminal

def integrate_terminal_with_generation(terminal: Terminal):
    """Hook to integrate terminal with generation pipeline"""
    
    logger = GenerationLogger(terminal)
    
    # This would be called from your generation functions
    def log_generation_pipeline(func):
        """Decorator to log generation pipeline events"""
        async def wrapper(*args, **kwargs):
            prompt = args[0] if args else kwargs.get('prompt', '')
            
            logger.start_generation(prompt)
            
            try:
                result = await func(*args, **kwargs)
                logger.log_success("Generation completed successfully")
                return result
            except Exception as e:
                logger.log_error(str(e))
                raise
                
        return wrapper
    
    return log_generation_pipeline