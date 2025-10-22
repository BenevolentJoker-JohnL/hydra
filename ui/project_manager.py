import streamlit as st
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import shutil
from dataclasses import dataclass, asdict
import yaml

@dataclass
class Project:
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    context: Dict
    files: List[str]
    chat_history: List[Dict]
    active: bool = True
    
class ProjectManager:
    def __init__(self, base_path: str = "./projects"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        
    def create_project(self, name: str, description: str = "") -> Project:
        project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        project = Project(
            id=project_id,
            name=name,
            description=description,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            context={},
            files=[],
            chat_history=[],
            active=True
        )
        
        project_dir = self.base_path / project_id
        project_dir.mkdir(exist_ok=True)
        (project_dir / "files").mkdir(exist_ok=True)
        (project_dir / "generated").mkdir(exist_ok=True)
        
        self.save_project(project)
        return project
        
    def save_project(self, project: Project):
        project_dir = self.base_path / project.id
        project_file = project_dir / "project.json"
        
        project_data = asdict(project)
        project_data['created_at'] = project.created_at.isoformat()
        project_data['updated_at'] = project.updated_at.isoformat()
        
        with open(project_file, 'w') as f:
            json.dump(project_data, f, indent=2)
            
    def load_project(self, project_id: str) -> Optional[Project]:
        project_file = self.base_path / project_id / "project.json"
        if not project_file.exists():
            return None
            
        with open(project_file, 'r') as f:
            data = json.load(f)
            
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        return Project(**data)
        
    def list_projects(self) -> List[Project]:
        projects = []
        for project_dir in self.base_path.iterdir():
            if project_dir.is_dir():
                project = self.load_project(project_dir.name)
                if project:
                    projects.append(project)
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)
        
    def add_file_to_project(self, project_id: str, file_path: str, content: bytes):
        project_dir = self.base_path / project_id / "files"
        file_name = Path(file_path).name
        target_path = project_dir / file_name
        
        with open(target_path, 'wb') as f:
            f.write(content)
            
        project = self.load_project(project_id)
        if project and file_name not in project.files:
            project.files.append(file_name)
            project.updated_at = datetime.now()
            self.save_project(project)
            
    def get_project_files(self, project_id: str) -> Dict[str, str]:
        files_dir = self.base_path / project_id / "files"
        files = {}
        
        if files_dir.exists():
            for file_path in files_dir.iterdir():
                if file_path.is_file():
                    try:
                        with open(file_path, 'r') as f:
                            files[file_path.name] = f.read()
                    except:
                        files[file_path.name] = "[Binary file]"
                        
        return files
        
    def save_generated_code(self, project_id: str, code: str, filename: str):
        gen_dir = self.base_path / project_id / "generated"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = gen_dir / f"{timestamp}_{filename}"
        
        with open(file_path, 'w') as f:
            f.write(code)
            
        return file_path
        
    def update_chat_history(self, project_id: str, message: Dict):
        project = self.load_project(project_id)
        if project:
            project.chat_history.append({
                **message,
                'timestamp': datetime.now().isoformat()
            })
            project.updated_at = datetime.now()
            self.save_project(project)
            
    def delete_project(self, project_id: str):
        project_dir = self.base_path / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)
            
    def export_project(self, project_id: str) -> Dict:
        import io
        
        project_dir = self.base_path / project_id
        project_data = self.load_project(project_id)
        
        if not project_data:
            return {}
            
        # Export as JSON with all files
        export_data = {
            'project': {
                'id': project_data.id,
                'name': project_data.name,
                'description': project_data.description,
                'created_at': project_data.created_at.isoformat(),
                'updated_at': project_data.updated_at.isoformat()
            },
            'files': {},
            'chat_history': project_data.chat_history
        }
        
        # Add file contents
        for file_name, file_content in project_data.files.items():
            export_data['files'][file_name] = file_content
            
        return export_data

def render_project_sidebar():
    st.sidebar.header("📁 Projects")
    
    if 'project_manager' not in st.session_state:
        st.session_state.project_manager = ProjectManager()
        
    pm = st.session_state.project_manager
    
    # Create new project
    with st.sidebar.expander("➕ New Project"):
        new_name = st.text_input("Project Name", key="new_project_name")
        new_desc = st.text_area("Description", key="new_project_desc")
        if st.button("Create", key="create_project"):
            if new_name:
                project = pm.create_project(new_name, new_desc)
                st.session_state.current_project = project
                st.success(f"Created project: {new_name}")
                st.rerun()
                
    # List projects
    projects = pm.list_projects()
    
    if projects:
        st.sidebar.subheader("Recent Projects")
        for project in projects[:10]:
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                if st.button(
                    f"📂 {project.name}",
                    key=f"proj_{project.id}",
                    use_container_width=True
                ):
                    st.session_state.current_project = project
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"del_{project.id}"):
                    pm.delete_project(project.id)
                    if hasattr(st.session_state, 'current_project') and \
                       st.session_state.current_project.id == project.id:
                        del st.session_state.current_project
                    st.rerun()
                    
    # Current project info
    if hasattr(st.session_state, 'current_project'):
        project = st.session_state.current_project
        st.sidebar.divider()
        st.sidebar.subheader(f"Current: {project.name}")
        st.sidebar.caption(project.description)
        st.sidebar.caption(f"Files: {len(project.files)}")
        st.sidebar.caption(f"Updated: {project.updated_at.strftime('%Y-%m-%d %H:%M')}")
        
        # File upload
        uploaded_file = st.sidebar.file_uploader(
            "Add files to project",
            key=f"upload_{project.id}"
        )
        if uploaded_file:
            pm.add_file_to_project(
                project.id,
                uploaded_file.name,
                uploaded_file.getvalue()
            )
            st.success(f"Added {uploaded_file.name}")
            st.rerun()
            
        # Export project
        if st.sidebar.button("📥 Export Project"):
            export_data = pm.export_project(project.id)
            if export_data:
                json_str = json.dumps(export_data, default=str, indent=2)
                st.sidebar.download_button(
                    "Download JSON",
                    json_str,
                    f"{project.name}.json",
                    "application/json"
                )

def get_project_context() -> Dict:
    if not hasattr(st.session_state, 'current_project'):
        return {}
        
    pm = st.session_state.project_manager
    project = st.session_state.current_project
    
    files = pm.get_project_files(project.id)
    
    return {
        'project_name': project.name,
        'project_description': project.description,
        'files': files,
        'chat_history': project.chat_history[-10:] if project.chat_history else []
    }