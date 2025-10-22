import streamlit as st
from typing import Dict, Optional

def get_project_context() -> Dict:
    """Get current project context including files"""
    if not hasattr(st.session_state, 'current_project'):
        return {}
        
    pm = st.session_state.enhanced_project_manager
    project = st.session_state.current_project
    
    # Get file contents
    files_content = {}
    for file_path, file_obj in project.files.items():
        if not file_obj.is_binary and file_obj.content:
            files_content[file_path] = file_obj.content
            
    return {
        'project_name': project.name,
        'project_description': project.description,
        'project_tags': project.tags,
        'files': files_content,
        'file_list': list(project.files.keys()),
        'chat_history': project.chat_history[-10:] if project.chat_history else []
    }