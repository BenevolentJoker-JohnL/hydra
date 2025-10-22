import streamlit as st
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
import yaml
import pickle
import sqlite3

@dataclass
class ProjectFile:
    path: str  # Relative path within project
    name: str
    content: Optional[str] = None  # None for binary files
    is_binary: bool = False
    size: int = 0
    modified: datetime = None
    is_directory: bool = False
    children: List['ProjectFile'] = field(default_factory=list)
    
    def __post_init__(self):
        if self.modified is None:
            self.modified = datetime.now()

@dataclass 
class Project:
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    context: Dict
    files: Dict[str, ProjectFile]  # path -> ProjectFile mapping
    chat_history: List[Dict]
    active: bool = True
    tags: List[str] = field(default_factory=list)
    
class EnhancedProjectManager:
    def __init__(self, base_path: str = "./projects", db_path: str = "./projects/projects.db"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database for project metadata"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                active BOOLEAN,
                tags TEXT,
                metadata TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_files (
                project_id TEXT,
                file_path TEXT,
                file_name TEXT,
                is_binary BOOLEAN,
                size INTEGER,
                modified TIMESTAMP,
                content TEXT,
                PRIMARY KEY (project_id, file_path),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)
        
        conn.commit()
        conn.close()
        
    def create_project(self, name: str, description: str = "") -> Project:
        project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        project = Project(
            id=project_id,
            name=name,
            description=description,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            context={},
            files={},
            chat_history=[],
            active=True,
            tags=[]
        )
        
        # Create project directory structure
        project_dir = self.base_path / project_id
        project_dir.mkdir(exist_ok=True)
        (project_dir / "files").mkdir(exist_ok=True)
        (project_dir / "generated").mkdir(exist_ok=True)
        (project_dir / ".metadata").mkdir(exist_ok=True)
        
        self.save_project(project)
        return project
        
    def save_project(self, project: Project):
        """Save project to database and filesystem"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Save project metadata
        cursor.execute("""
            INSERT OR REPLACE INTO projects 
            (id, name, description, created_at, updated_at, active, tags, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project.id,
            project.name,
            project.description,
            project.created_at.isoformat(),
            project.updated_at.isoformat(),
            project.active,
            json.dumps(project.tags),
            json.dumps({"context": project.context})
        ))
        
        # Save files metadata
        for file_path, file_obj in project.files.items():
            cursor.execute("""
                INSERT OR REPLACE INTO project_files
                (project_id, file_path, file_name, is_binary, size, modified, content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                project.id,
                file_path,
                file_obj.name,
                file_obj.is_binary,
                file_obj.size,
                file_obj.modified.isoformat(),
                file_obj.content if not file_obj.is_binary else None
            ))
        
        conn.commit()
        conn.close()
        
        # Save project data to filesystem
        project_dir = self.base_path / project.id
        
        # Save chat history
        chat_file = project_dir / ".metadata" / "chat_history.json"
        with open(chat_file, 'w') as f:
            json.dump(project.chat_history, f, indent=2, default=str)
            
        # Save project manifest
        manifest = project_dir / ".metadata" / "manifest.json"
        with open(manifest, 'w') as f:
            project_data = {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat(),
                "tags": project.tags,
                "file_count": len(project.files)
            }
            json.dump(project_data, f, indent=2)
            
    def load_project(self, project_id: str) -> Optional[Project]:
        """Load project from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Load project metadata
        cursor.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
            
        # Load files
        cursor.execute(
            "SELECT * FROM project_files WHERE project_id = ?", (project_id,)
        )
        file_rows = cursor.fetchall()
        
        files = {}
        for file_row in file_rows:
            file_obj = ProjectFile(
                path=file_row[1],
                name=file_row[2],
                is_binary=file_row[3],
                size=file_row[4],
                modified=datetime.fromisoformat(file_row[5]),
                content=file_row[6]
            )
            files[file_row[1]] = file_obj
        
        conn.close()
        
        # Load chat history from filesystem
        chat_file = self.base_path / project_id / ".metadata" / "chat_history.json"
        chat_history = []
        if chat_file.exists():
            with open(chat_file, 'r') as f:
                chat_history = json.load(f)
        
        metadata = json.loads(row[7]) if row[7] else {}
        
        return Project(
            id=row[0],
            name=row[1],
            description=row[2],
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
            active=row[5],
            tags=json.loads(row[6]) if row[6] else [],
            context=metadata.get("context", {}),
            files=files,
            chat_history=chat_history
        )
        
    def add_file_to_project(self, project_id: str, file_path: str, content: bytes, 
                           relative_path: str = None) -> bool:
        """Add a file to project with support for folder structure"""
        project = self.load_project(project_id)
        if not project:
            return False
            
        file_name = Path(file_path).name
        
        # Determine relative path within project
        if relative_path:
            rel_path = relative_path
        else:
            rel_path = file_name
            
        # Create directory structure if needed
        project_file_path = self.base_path / project_id / "files" / rel_path
        project_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Determine if binary
        is_binary = False
        text_content = None
        try:
            text_content = content.decode('utf-8')
        except:
            is_binary = True
            
        # Write file
        with open(project_file_path, 'wb') as f:
            f.write(content)
            
        # Create ProjectFile object
        file_obj = ProjectFile(
            path=rel_path,
            name=file_name,
            content=text_content if not is_binary else None,
            is_binary=is_binary,
            size=len(content),
            modified=datetime.now()
        )
        
        # Update project
        project.files[rel_path] = file_obj
        project.updated_at = datetime.now()
        self.save_project(project)
        
        return True
        
    def add_folder_to_project(self, project_id: str, folder_path: str) -> int:
        """Add entire folder to project, returns number of files added"""
        project = self.load_project(project_id)
        if not project:
            return 0
            
        files_added = 0
        folder_path = Path(folder_path)
        
        for file_path in folder_path.rglob('*'):
            if file_path.is_file():
                # Skip hidden and system files
                if any(part.startswith('.') for part in file_path.parts):
                    continue
                    
                rel_path = file_path.relative_to(folder_path)
                
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    if self.add_file_to_project(project_id, str(file_path), content, str(rel_path)):
                        files_added += 1
                except Exception as e:
                    st.error(f"Failed to add {file_path}: {e}")
                    
        return files_added
        
    def save_generated_code(self, project_id: str, code: str, filename: str) -> Path:
        """Save generated code to project's generated folder"""
        project_dir = self.base_path / project_id / "generated"
        project_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = project_dir / f"{timestamp}_{filename}"
        
        with open(file_path, 'w') as f:
            f.write(code)
            
        return file_path
        
    def update_file_in_project(self, project_id: str, file_path: str, new_content: str) -> bool:
        """Update content of a file in project"""
        project = self.load_project(project_id)
        if not project or file_path not in project.files:
            return False
            
        file_obj = project.files[file_path]
        file_obj.content = new_content
        file_obj.modified = datetime.now()
        
        # Write to filesystem
        project_file_path = self.base_path / project_id / "files" / file_path
        with open(project_file_path, 'w') as f:
            f.write(new_content)
            
        project.updated_at = datetime.now()
        self.save_project(project)
        
        return True
        
    def remove_file_from_project(self, project_id: str, file_path: str) -> bool:
        """Remove file from project"""
        project = self.load_project(project_id)
        if not project or file_path not in project.files:
            return False
            
        # Remove from project
        del project.files[file_path]
        
        # Remove from filesystem
        project_file_path = self.base_path / project_id / "files" / file_path
        if project_file_path.exists():
            project_file_path.unlink()
            
        # Remove from database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM project_files WHERE project_id = ? AND file_path = ?",
            (project_id, file_path)
        )
        conn.commit()
        conn.close()
        
        project.updated_at = datetime.now()
        self.save_project(project)
        
        return True
        
    def get_file_tree(self, project_id: str) -> Dict:
        """Get hierarchical file tree structure"""
        project = self.load_project(project_id)
        if not project:
            return {}
            
        tree = {}
        
        for file_path, file_obj in project.files.items():
            parts = Path(file_path).parts
            current = tree
            
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
                
            current[file_obj.name] = file_obj
            
        return tree
        
    def list_projects(self) -> List[Project]:
        """List all projects from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM projects WHERE active = 1 ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        projects = []
        for row in rows:
            project = self.load_project(row[0])
            if project:
                projects.append(project)
                
        return projects
        
    def search_projects(self, query: str) -> List[Project]:
        """Search projects by name, description, or tags"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM projects 
            WHERE active = 1 AND (
                name LIKE ? OR 
                description LIKE ? OR 
                tags LIKE ?
            )
            ORDER BY updated_at DESC
        """, (f"%{query}%", f"%{query}%", f"%{query}%"))
        
        rows = cursor.fetchall()
        conn.close()
        
        projects = []
        for row in rows:
            project = self.load_project(row[0])
            if project:
                projects.append(project)
                
        return projects
        
    def export_project(self, project_id: str) -> Dict:
        """Export project as JSON including all files and metadata"""
        project = self.load_project(project_id)
        if not project:
            return {}
            
        # Collect all project files
        files_data = {}
        for file_path, file_obj in project.files.items():
            files_data[file_path] = {
                'content': file_obj.content,
                'is_binary': file_obj.is_binary,
                'size': file_obj.size,
                'modified': file_obj.modified.isoformat()
            }
            
        # Create export data
        export_data = {
            "project": asdict(project),
            "files_data": files_data,
            "exported_at": datetime.now().isoformat()
        }
        
        return export_data
        
    def import_project(self, import_data: Dict, new_name: str = None) -> Optional[Project]:
        """Import project from JSON data"""
        if 'project' not in import_data:
            return None
            
        project_data = import_data["project"]
        
        # Create new project
        project = self.create_project(
            name=new_name or project_data["name"] + " (imported)",
            description=project_data["description"]
        )
        
        # Add files if present
        if 'files_data' in import_data:
            for file_path, file_info in import_data['files_data'].items():
                content = file_info['content']
                if content:
                    # Convert text content to bytes
                    content_bytes = content.encode('utf-8') if isinstance(content, str) else content
                    self.add_file_to_project(project.id, file_path, content_bytes, file_path)
                    
        return project

def render_enhanced_project_sidebar():
    """Enhanced project sidebar with file management"""
    st.sidebar.header("📁 Projects")
    
    if 'enhanced_project_manager' not in st.session_state:
        st.session_state.enhanced_project_manager = EnhancedProjectManager()
        
    pm = st.session_state.enhanced_project_manager
    
    # Search projects
    search_query = st.sidebar.text_input("🔍 Search projects", key="project_search")
    
    # Create new project
    with st.sidebar.expander("➕ New Project"):
        new_name = st.text_input("Project Name", key="new_project_name")
        new_desc = st.text_area("Description", key="new_project_desc")
        tags = st.text_input("Tags (comma-separated)", key="new_project_tags")
        
        if st.button("Create", key="create_project"):
            if new_name:
                project = pm.create_project(new_name, new_desc)
                if tags:
                    project.tags = [t.strip() for t in tags.split(',')]
                    pm.save_project(project)
                st.session_state.current_project = project
                st.success(f"Created project: {new_name}")
                st.rerun()
                
    # Import project
    with st.sidebar.expander("📥 Import Project"):
        import_type = st.radio("Import from:", ["JSON File", "Multiple Files"], key="import_type")
        
        if import_type == "JSON File":
            uploaded_json = st.file_uploader("Upload project JSON", type=['json'])
            if uploaded_json:
                import_data = json.loads(uploaded_json.read())
                project = pm.import_project(import_data)
                if project:
                    st.success(f"Imported: {project.name}")
                    st.session_state.current_project = project
                    st.rerun()
        else:
            st.info("📁 Select multiple files to import as new project")
            imported_files = st.file_uploader(
                "Choose files (Ctrl/Cmd+Click for multiple)",
                accept_multiple_files=True,
                key="import_multi_files"
            )
            if imported_files:
                new_proj = pm.create_project(f"Imported {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                for file in imported_files:
                    pm.add_file_to_project(new_proj.id, file.name, file.getvalue(), file.name)
                st.success(f"Created project with {len(imported_files)} files")
                st.session_state.current_project = new_proj
                st.rerun()
                
    # List projects
    if search_query:
        projects = pm.search_projects(search_query)
    else:
        projects = pm.list_projects()
        
    if projects:
        st.sidebar.subheader("Your Projects")
        
        for project in projects[:10]:
            col1, col2, col3 = st.sidebar.columns([5, 1, 1])
            
            with col1:
                if st.button(
                    f"📂 {project.name}",
                    key=f"proj_{project.id}",
                    use_container_width=True,
                    help=f"{len(project.files)} files"
                ):
                    st.session_state.current_project = project
                    st.rerun()
                    
            with col2:
                if st.button("📥", key=f"exp_{project.id}", help="Export"):
                    export_data = pm.export_project(project.id)
                    if export_data:
                        json_str = json.dumps(export_data, default=str, indent=2)
                        st.sidebar.download_button(
                            "💾",
                            json_str,
                            f"{project.name}.json",
                            "application/json",
                            key=f"dl_{project.id}"
                        )
                    
            with col3:
                if st.button("🗑️", key=f"del_{project.id}", help="Delete"):
                    # Archive instead of delete
                    project.active = False
                    pm.save_project(project)
                    if hasattr(st.session_state, 'current_project') and \
                       st.session_state.current_project.id == project.id:
                        del st.session_state.current_project
                    st.rerun()
                    
    # Current project info
    if hasattr(st.session_state, 'current_project'):
        project = st.session_state.current_project
        st.sidebar.divider()
        st.sidebar.subheader(f"📂 {project.name}")
        
        if project.tags:
            st.sidebar.caption(f"🏷️ {', '.join(project.tags)}")
        st.sidebar.caption(f"📄 {len(project.files)} files")
        st.sidebar.caption(f"🕒 {project.updated_at.strftime('%Y-%m-%d %H:%M')}")
        
        # File upload section
        with st.sidebar.expander("📤 Add Files"):
            upload_type = st.radio("Upload type", ["Files", "Directory", "Local Path"], horizontal=True)
            
            if upload_type == "Files":
                uploaded_files = st.file_uploader(
                    "Choose files",
                    accept_multiple_files=True,
                    key=f"upload_{project.id}"
                )
                
                if uploaded_files:
                    for uploaded_file in uploaded_files:
                        pm.add_file_to_project(
                            project.id,
                            uploaded_file.name,
                            uploaded_file.getvalue()
                        )
                    st.success(f"Added {len(uploaded_files)} files")
                    st.rerun()
                    
            elif upload_type == "Directory":
                st.info("📁 Upload entire folders - No ZIP needed!")
                uploaded_files = st.file_uploader(
                    "Select all files from your folder (Ctrl/Cmd + A)",
                    accept_multiple_files=True,
                    key=f"dir_upload_{project.id}",
                    help="Select all files in your directory to upload with preserved folder structure"
                )
                
                if uploaded_files:
                    # Process as directory
                    from .directory_upload import DirectoryUploader
                    result = DirectoryUploader.process_uploaded_files(uploaded_files)
                    
                    if result:
                        for file_data in result['files']:
                            pm.add_file_to_project(
                                project.id,
                                file_data['name'],
                                file_data['content'],
                                file_data['path']
                            )
                        st.success(f"Added {result['total_files']} files")
                        st.rerun()
                    
            else:
                folder_path = st.text_input("Local directory path")
                if folder_path and st.button("Load Directory"):
                    if Path(folder_path).exists():
                        count = pm.add_folder_to_project(project.id, folder_path)
                        st.success(f"Added {count} files")
                        st.rerun()
                    else:
                        st.error("Directory not found")

def render_project_files_panel():
    """Render project files in a file explorer interface"""
    if not hasattr(st.session_state, 'current_project'):
        st.info("Select a project to view files")
        return
        
    from .file_handler import FileHandler, render_file_upload_zone, FileSearch
    
    pm = st.session_state.enhanced_project_manager
    project = st.session_state.current_project
    
    st.subheader(f"📁 {project.name} Files")
    
    # File upload zone with tabs for different upload methods
    with st.expander("📤 Upload Files & Directories", expanded=False):
        upload_tab1, upload_tab2, upload_tab3 = st.tabs(["📄 Files", "📁 Directory", "📂 Local Path"])
        
        with upload_tab1:
            uploaded_files = render_file_upload_zone()
            
            if uploaded_files:
                for file_info in uploaded_files:
                    if not file_info.get('error'):
                        # Add file to project
                        pm.add_file_to_project(
                            project.id,
                            file_info['name'],
                            file_info['content'],
                            file_info['name']
                        )
                st.success(f"Added {len(uploaded_files)} files to project")
                st.rerun()
                
        with upload_tab2:
            from .directory_upload import DirectoryUploader
            
            st.markdown("### 📁 Upload Entire Directory - No ZIP Required!")
            st.info("Select all files from your directory to preserve folder structure")
            uploaded_dir_files = st.file_uploader(
                "Choose all files from your folder",
                accept_multiple_files=True,
                key="dir_tab_upload",
                help="Ctrl/Cmd + A to select all files. Folder structure will be preserved automatically!"
            )
            
            if uploaded_dir_files:
                result = DirectoryUploader.process_uploaded_files(uploaded_dir_files)
                if result:
                    with st.spinner(f"Adding {result['total_files']} files..."):
                        for file_data in result['files']:
                            pm.add_file_to_project(
                                project.id,
                                file_data['name'],
                                file_data['content'],
                                file_data['path']
                            )
                    st.success(f"Added directory '{result['base_name']}' with {result['total_files']} files")
                    st.rerun()
                    
        with upload_tab3:
            from .directory_upload import DirectoryUploader
            
            local_path = st.text_input("Enter directory path", placeholder="/path/to/project")
            if st.button("Load Directory"):
                if local_path and Path(local_path).exists():
                    result = DirectoryUploader.load_local_directory(local_path)
                    if result:
                        with st.spinner(f"Loading {result['total_files']} files..."):
                            for file_data in result['files']:
                                pm.add_file_to_project(
                                    project.id,
                                    file_data['name'],
                                    file_data['content'],
                                    file_data['path']
                                )
                        st.success(f"Loaded {result['total_files']} files from {result['base_name']}")
                        st.rerun()
                else:
                    st.error("Directory not found")
    
    # File search and filter
    search_query, file_types = FileSearch.render_search_bar()
    
    # Filter files
    filtered_files = FileSearch.search_files(project.files, search_query, file_types) if (search_query or file_types) else project.files
    
    # File tree view
    tree = pm.get_file_tree(project.id)
    
    if not filtered_files:
        if search_query or file_types:
            st.caption("No files match your search criteria.")
        else:
            st.caption("No files in project. Upload files above or use the sidebar.")
        return
        
    st.caption(f"Showing {len(filtered_files)} of {len(project.files)} files")
    
    # Display files with actions
    for file_path, file_obj in sorted(filtered_files.items()):
        col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
        
        with col1:
            icon = "📄" if not file_obj.is_binary else "🔒"
            if st.button(f"{icon} {file_path}", key=f"file_{file_path}", use_container_width=True):
                st.session_state.selected_file = file_path
                
        with col2:
            st.caption(f"{file_obj.size:,} B")
            
        with col3:
            if not file_obj.is_binary and st.button("✏️", key=f"edit_{file_path}", help="Edit"):
                st.session_state.editing_file = file_path
                
        with col4:
            if st.button("🗑️", key=f"rm_{file_path}", help="Remove"):
                pm.remove_file_from_project(project.id, file_path)
                st.rerun()
                
    # File editor
    if hasattr(st.session_state, 'editing_file'):
        file_path = st.session_state.editing_file
        if file_path in project.files:
            file_obj = project.files[file_path]
            
            st.divider()
            st.subheader(f"✏️ Editing: {file_path}")
            
            new_content = st.text_area(
                "Content",
                value=file_obj.content,
                height=400,
                key=f"editor_{file_path}"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Save", key=f"save_edit_{file_path}"):
                    pm.update_file_in_project(project.id, file_path, new_content)
                    del st.session_state.editing_file
                    st.success("File saved")
                    st.rerun()
                    
            with col2:
                if st.button("❌ Cancel", key=f"cancel_edit_{file_path}"):
                    del st.session_state.editing_file
                    st.rerun()