"""
Project Management Page
Complete project management interface with conversation history
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
import json
import sys
import os

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from ui.enhanced_project_manager import EnhancedProjectManager
from ui.file_handler import FileHandler
from ui.directory_upload import DirectoryUploader
from loguru import logger

# Page config
st.set_page_config(
    page_title="Projects - Hydra",
    page_icon="📁",
    layout="wide"
)

def initialize_project_manager():
    """Initialize project manager in session state"""
    if 'enhanced_project_manager' not in st.session_state:
        st.session_state.enhanced_project_manager = EnhancedProjectManager()
    return st.session_state.enhanced_project_manager

def render_project_list():
    """Render list of all projects"""
    pm = initialize_project_manager()
    projects = pm.list_projects()
    
    if not projects:
        st.info("📭 No projects yet. Create your first project to get started!")
        return None
    
    # Create project cards
    st.subheader(f"📚 All Projects ({len(projects)})")
    
    # Search and filter
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search = st.text_input("🔍 Search projects", placeholder="Search by name, description, or tags...")
    with col2:
        sort_by = st.selectbox("Sort by", ["Updated", "Created", "Name", "Size"])
    with col3:
        filter_active = st.checkbox("Active only", value=True)
    
    # Filter projects
    if search:
        projects = pm.search_projects(search)
    
    if filter_active:
        projects = [p for p in projects if p.active]
    
    # Sort projects
    if sort_by == "Updated":
        projects.sort(key=lambda x: x.updated_at, reverse=True)
    elif sort_by == "Created":
        projects.sort(key=lambda x: x.created_at, reverse=True)
    elif sort_by == "Name":
        projects.sort(key=lambda x: x.name)
    elif sort_by == "Size":
        projects.sort(key=lambda x: len(x.files), reverse=True)
    
    # Display projects in grid
    cols = st.columns(3)
    selected_project = None
    
    for idx, project in enumerate(projects):
        with cols[idx % 3]:
            with st.container():
                # Project card
                st.markdown(f"""
                <div style="
                    border: 2px solid #4CAF50;
                    border-radius: 10px;
                    padding: 15px;
                    margin: 10px 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                ">
                    <h3>📁 {project.name}</h3>
                    <p>{project.description or 'No description'}</p>
                    <small>Files: {len(project.files)} | Messages: {len(project.chat_history)}</small><br>
                    <small>Updated: {project.updated_at.strftime('%Y-%m-%d %H:%M')}</small>
                </div>
                """, unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("📂 Open", key=f"open_{project.id}", use_container_width=True):
                        st.session_state.current_project = project
                        selected_project = project
                        st.rerun()
                with col2:
                    if st.button("📥 Export", key=f"exp_{project.id}", use_container_width=True):
                        export_data = pm.export_project(project.id)
                        if export_data:
                            json_str = json.dumps(export_data, default=str, indent=2)
                            st.download_button(
                                "💾 Download",
                                json_str,
                                f"{project.name}.json",
                                "application/json",
                                key=f"dl_{project.id}"
                            )
                with col3:
                    if st.button("🗑️", key=f"del_{project.id}", use_container_width=True):
                        project.active = False
                        pm.save_project(project)
                        st.rerun()
    
    return selected_project

def render_project_details(project):
    """Render detailed project view"""
    pm = initialize_project_manager()
    
    # Project header
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.title(f"📁 {project.name}")
        if project.description:
            st.caption(project.description)
    with col2:
        if st.button("🔙 Back to Projects"):
            if 'current_project' in st.session_state:
                del st.session_state.current_project
            st.rerun()
    with col3:
        if st.button("⚙️ Settings"):
            st.session_state.show_project_settings = True
    
    # Project stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📄 Files", len(project.files))
    with col2:
        st.metric("💬 Messages", len(project.chat_history))
    with col3:
        total_size = sum(f.size for f in project.files.values())
        st.metric("💾 Size", f"{total_size / (1024*1024):.1f} MB")
    with col4:
        st.metric("🏷️ Tags", len(project.tags))
    
    # Tabs for different sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💬 Conversation History", 
        "📄 Files", 
        "📊 Analytics",
        "⚙️ Settings",
        "🔄 Activity"
    ])
    
    with tab1:
        render_conversation_history(project)
    
    with tab2:
        render_project_files(project)
    
    with tab3:
        render_project_analytics(project)
    
    with tab4:
        render_project_settings(project)
    
    with tab5:
        render_project_activity(project)

def render_conversation_history(project):
    """Render project conversation history"""
    st.subheader(f"💬 Conversation History ({len(project.chat_history)} messages)")
    
    if not project.chat_history:
        st.info("No conversations yet. Start chatting to build history!")
        return
    
    # Search and filter options
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_messages = st.text_input("🔍 Search messages", key="search_msgs")
    with col2:
        filter_role = st.selectbox("Filter by", ["All", "User", "Assistant"], key="filter_role")
    with col3:
        show_thinking = st.checkbox("Show thinking", value=False)
    
    # Filter messages
    filtered_messages = project.chat_history
    
    if search_messages:
        filtered_messages = [
            m for m in filtered_messages 
            if search_messages.lower() in m.get('content', '').lower()
        ]
    
    if filter_role != "All":
        filtered_messages = [
            m for m in filtered_messages 
            if m.get('role', '').lower() == filter_role.lower()
        ]
    
    # Display messages
    for idx, message in enumerate(filtered_messages):
        with st.chat_message(message.get('role', 'assistant')):
            # Show thinking if enabled
            if show_thinking and message.get('thinking'):
                with st.expander("🤔 Thinking", expanded=False):
                    st.markdown(message['thinking'])
            
            # Show message content
            st.markdown(message.get('content', ''))
            
            # Show attached files
            if message.get('attached_files'):
                total_lines = sum(f.get('lines', 0) for f in message['attached_files'])
                with st.expander(f"📎 {len(message['attached_files'])} files ({total_lines:,} lines)"):
                    for file in message['attached_files']:
                        if file.get('lines', 0) > 0:
                            st.text(f"📄 {file['name']}: {file['lines']:,} lines")
                        else:
                            st.text(f"📎 {file['name']}: {file['size'] / 1024:.1f} KB")
            
            # Show code if present
            if message.get('code'):
                st.code(message['code'], language=message.get('language', 'python'))
            
            # Message metadata
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                st.caption(f"Message #{idx + 1}")
            with col2:
                if message.get('metadata'):
                    st.caption(f"Task: {message['metadata'].get('task_id', 'N/A')}")
            with col3:
                # Export single message
                if st.button("📥", key=f"export_msg_{idx}", help="Export message"):
                    st.download_button(
                        "💾",
                        json.dumps(message, default=str, indent=2),
                        f"message_{idx}.json",
                        "application/json",
                        key=f"dl_msg_{idx}"
                    )

def render_project_files(project):
    """Render project files manager"""
    pm = initialize_project_manager()
    
    st.subheader(f"📄 Project Files ({len(project.files)})")
    
    # File upload section
    with st.expander("📤 Upload Files", expanded=False):
        tab1, tab2, tab3 = st.tabs(["📄 Files", "📁 Directory", "📂 Local Path"])
        
        with tab1:
            uploaded_files = st.file_uploader(
                "Choose files",
                accept_multiple_files=True,
                key="project_file_upload"
            )
            
            if uploaded_files:
                progress = st.progress(0)
                for idx, file in enumerate(uploaded_files):
                    pm.add_file_to_project(
                        project.id,
                        file.name,
                        file.getvalue(),
                        file.name
                    )
                    progress.progress((idx + 1) / len(uploaded_files))
                st.success(f"✅ Added {len(uploaded_files)} files")
                st.rerun()
        
        with tab2:
            st.info("📁 Select all files from a directory")
            dir_files = st.file_uploader(
                "Select all files (Ctrl/Cmd+A)",
                accept_multiple_files=True,
                key="project_dir_upload"
            )
            
            if dir_files:
                result = DirectoryUploader.process_uploaded_files(dir_files)
                if result:
                    for file_data in result['files']:
                        pm.add_file_to_project(
                            project.id,
                            file_data['name'],
                            file_data['content'],
                            file_data['path']
                        )
                    st.success(f"✅ Added {result['total_files']} files from directory")
                    st.rerun()
        
        with tab3:
            local_path = st.text_input("Enter directory path")
            if st.button("Load Directory"):
                if local_path and Path(local_path).exists():
                    count = pm.add_folder_to_project(project.id, local_path)
                    st.success(f"✅ Added {count} files")
                    st.rerun()
    
    # File search
    search_files = st.text_input("🔍 Search files", placeholder="Search by name or path...")
    
    # Display files
    if project.files:
        # Filter files
        filtered_files = project.files
        if search_files:
            filtered_files = {
                k: v for k, v in project.files.items()
                if search_files.lower() in k.lower()
            }
        
        # File tree
        st.markdown(f"**Showing {len(filtered_files)} files**")
        
        for file_path, file_obj in sorted(filtered_files.items()):
            col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
            
            with col1:
                icon = "📄" if not file_obj.is_binary else "🔒"
                st.write(f"{icon} {file_path}")
            
            with col2:
                st.caption(f"{file_obj.size / 1024:.1f} KB")
            
            with col3:
                st.caption(file_obj.modified.strftime('%Y-%m-%d'))
            
            with col4:
                if not file_obj.is_binary and st.button("👁️", key=f"view_{file_path}", help="View"):
                    st.session_state.viewing_file = file_path
            
            with col5:
                if st.button("🗑️", key=f"del_file_{file_path}", help="Delete"):
                    pm.remove_file_from_project(project.id, file_path)
                    st.rerun()
        
        # File viewer
        if hasattr(st.session_state, 'viewing_file'):
            file_path = st.session_state.viewing_file
            if file_path in project.files:
                file_obj = project.files[file_path]
                
                st.divider()
                st.subheader(f"📄 Viewing: {file_path}")
                
                if file_obj.content:
                    st.code(file_obj.content, language="python")
                
                if st.button("❌ Close", key="close_viewer"):
                    del st.session_state.viewing_file
                    st.rerun()
    else:
        st.info("No files in project yet. Upload files to get started!")

def render_project_analytics(project):
    """Render project analytics"""
    st.subheader("📊 Project Analytics")
    
    # Message analytics
    if project.chat_history:
        col1, col2 = st.columns(2)
        
        with col1:
            # Message distribution
            st.markdown("### Message Distribution")
            user_msgs = len([m for m in project.chat_history if m.get('role') == 'user'])
            assistant_msgs = len([m for m in project.chat_history if m.get('role') == 'assistant'])
            
            data = pd.DataFrame({
                'Role': ['User', 'Assistant'],
                'Count': [user_msgs, assistant_msgs]
            })
            st.bar_chart(data.set_index('Role'))
        
        with col2:
            # Code generation stats
            st.markdown("### Code Generation")
            code_messages = [m for m in project.chat_history if m.get('code')]
            st.metric("Code Snippets", len(code_messages))
            
            # Average response length
            response_lengths = [
                len(m.get('content', '')) 
                for m in project.chat_history 
                if m.get('role') == 'assistant'
            ]
            if response_lengths:
                st.metric("Avg Response Length", f"{sum(response_lengths) / len(response_lengths):.0f} chars")
    
    # File analytics
    if project.files:
        st.markdown("### File Statistics")
        
        # File type distribution
        file_types = {}
        for file_path in project.files:
            ext = Path(file_path).suffix.lower()
            file_types[ext] = file_types.get(ext, 0) + 1
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**File Types**")
            for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]:
                st.write(f"{ext or 'no extension'}: {count} files")
        
        with col2:
            st.markdown("**Largest Files**")
            sorted_files = sorted(
                project.files.items(), 
                key=lambda x: x[1].size, 
                reverse=True
            )[:5]
            for file_path, file_obj in sorted_files:
                st.write(f"📄 {Path(file_path).name}: {file_obj.size / 1024:.1f} KB")

def render_project_settings(project):
    """Render project settings"""
    pm = initialize_project_manager()
    
    st.subheader("⚙️ Project Settings")
    
    # Basic settings
    with st.form("project_settings"):
        new_name = st.text_input("Project Name", value=project.name)
        new_desc = st.text_area("Description", value=project.description)
        new_tags = st.text_input("Tags (comma-separated)", value=", ".join(project.tags))
        
        if st.form_submit_button("💾 Save Changes"):
            project.name = new_name
            project.description = new_desc
            project.tags = [t.strip() for t in new_tags.split(',') if t.strip()]
            project.updated_at = datetime.now()
            pm.save_project(project)
            st.success("✅ Settings updated!")
            st.rerun()
    
    # Danger zone
    st.divider()
    st.subheader("⚠️ Danger Zone")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear Chat History", type="secondary"):
            project.chat_history = []
            pm.save_project(project)
            st.success("Chat history cleared")
            st.rerun()
    
    with col2:
        if st.button("❌ Delete Project", type="secondary"):
            project.active = False
            pm.save_project(project)
            if 'current_project' in st.session_state:
                del st.session_state.current_project
            st.success("Project deleted")
            st.rerun()

def render_project_activity(project):
    """Render project activity timeline"""
    st.subheader("🔄 Recent Activity")
    
    # Create activity timeline
    activities = []
    
    # Add file activities
    for file_path, file_obj in project.files.items():
        activities.append({
            'time': file_obj.modified,
            'type': 'file',
            'action': f"📄 Added file: {Path(file_path).name}",
            'details': f"Size: {file_obj.size / 1024:.1f} KB"
        })
    
    # Add message activities
    for idx, message in enumerate(project.chat_history[-20:]):  # Last 20 messages
        activities.append({
            'time': datetime.now(),  # Would need timestamp in message
            'type': 'message',
            'action': f"💬 {message.get('role', 'Unknown')}: {message.get('content', '')[:50]}...",
            'details': f"Message #{idx + 1}"
        })
    
    # Sort by time
    activities.sort(key=lambda x: x['time'], reverse=True)
    
    # Display timeline
    for activity in activities[:20]:  # Show last 20 activities
        col1, col2 = st.columns([1, 3])
        with col1:
            st.caption(activity['time'].strftime('%H:%M'))
        with col2:
            st.write(activity['action'])
            if activity['details']:
                st.caption(activity['details'])

def create_new_project():
    """Create new project interface"""
    st.subheader("➕ Create New Project")
    
    with st.form("new_project"):
        name = st.text_input("Project Name", placeholder="My Awesome Project")
        description = st.text_area("Description", placeholder="Describe your project...")
        tags = st.text_input("Tags (comma-separated)", placeholder="python, api, web")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("✅ Create Project", use_container_width=True):
                if name:
                    pm = initialize_project_manager()
                    project = pm.create_project(name, description)
                    if tags:
                        project.tags = [t.strip() for t in tags.split(',')]
                        pm.save_project(project)
                    st.session_state.current_project = project
                    st.success(f"✅ Created project: {name}")
                    st.rerun()
                else:
                    st.error("Please enter a project name")
        with col2:
            if st.form_submit_button("❌ Cancel", use_container_width=True):
                st.rerun()

def main():
    st.title("📁 Project Management")
    st.caption("Manage your projects, files, and conversation history")
    
    # Initialize
    pm = initialize_project_manager()
    
    # Check if we have a current project
    if hasattr(st.session_state, 'current_project'):
        # Show project details
        render_project_details(st.session_state.current_project)
    else:
        # Show project list or create new
        tab1, tab2, tab3 = st.tabs(["📚 All Projects", "➕ New Project", "📥 Import"])
        
        with tab1:
            selected = render_project_list()
            if selected:
                st.session_state.current_project = selected
                st.rerun()
        
        with tab2:
            create_new_project()
        
        with tab3:
            st.subheader("📥 Import Project")
            
            import_type = st.radio("Import from:", ["JSON File", "Multiple Files"])
            
            if import_type == "JSON File":
                uploaded_json = st.file_uploader("Upload project JSON", type=['json'])
                if uploaded_json:
                    import_data = json.loads(uploaded_json.read())
                    project = pm.import_project(import_data)
                    if project:
                        st.success(f"✅ Imported: {project.name}")
                        st.session_state.current_project = project
                        st.rerun()
            else:
                imported_files = st.file_uploader(
                    "Choose files to import as new project",
                    accept_multiple_files=True
                )
                if imported_files:
                    project_name = st.text_input("Project name", f"Imported {datetime.now().strftime('%Y-%m-%d')}")
                    if st.button("Create Project from Files"):
                        new_proj = pm.create_project(project_name)
                        for file in imported_files:
                            pm.add_file_to_project(new_proj.id, file.name, file.getvalue(), file.name)
                        st.success(f"✅ Created project with {len(imported_files)} files")
                        st.session_state.current_project = new_proj
                        st.rerun()

if __name__ == "__main__":
    main()