import streamlit as st
import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import base64
import mimetypes
from datetime import datetime
import shutil
import tempfile

class DirectoryUploader:
    """Handle directory uploads in Streamlit"""
    
    @staticmethod
    def render_directory_upload():
        """Render directory upload interface"""
        st.markdown("""
            <style>
            .directory-upload {
                border: 2px dashed #4CAF50;
                border-radius: 10px;
                padding: 30px;
                text-align: center;
                background: #f0f8f0;
                margin: 10px 0;
            }
            .directory-upload:hover {
                border-color: #45a049;
                background: #e8f5e8;
            }
            .file-tree {
                font-family: monospace;
                line-height: 1.6;
            }
            .tree-item {
                padding-left: 20px;
            }
            </style>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="directory-upload">', unsafe_allow_html=True)
        st.markdown("### 📁 Directory Upload")
        
        # Use Streamlit's file uploader with webkitdirectory attribute (via custom component)
        # For now, we'll use multiple file upload as a workaround
        st.info("**Option 1**: Select multiple files while preserving folder structure")
        
        uploaded_files = st.file_uploader(
            "Select all files from your directory (Ctrl/Cmd + A to select all)",
            accept_multiple_files=True,
            help="Upload all files from a directory. File paths will be preserved.",
            key="directory_files"
        )
        
        st.markdown("---")
        st.info("**Option 2**: Paste directory path (for local development)")
        
        local_path = st.text_input(
            "Enter local directory path",
            placeholder="/path/to/your/project",
            help="For local development: Enter the full path to your directory"
        )
        
        if st.button("📂 Load Directory", key="load_dir"):
            if local_path and os.path.exists(local_path):
                return DirectoryUploader.load_local_directory(local_path)
            else:
                st.error("Directory not found")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        if uploaded_files:
            return DirectoryUploader.process_uploaded_files(uploaded_files)
            
        return None
    
    @staticmethod
    def process_uploaded_files(uploaded_files) -> Dict:
        """Process multiple uploaded files and reconstruct directory structure"""
        
        # Try to detect common base path from file names
        file_structure = {}
        base_path = None
        
        for file in uploaded_files:
            # Check if filename contains path separators
            filename = file.name
            
            # Handle different path formats
            if '/' in filename or '\\' in filename:
                # File was uploaded with path information
                path_parts = filename.replace('\\', '/').split('/')
                base_path = path_parts[0] if not base_path else base_path
            else:
                # Single file, no path information
                path_parts = [filename]
            
            # Build nested structure
            current = file_structure
            for part in path_parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            
            # Add file
            current[path_parts[-1]] = {
                'content': file.getvalue(),
                'size': file.size,
                'type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            }
        
        # Create a flat list of files with paths
        flat_files = DirectoryUploader.flatten_structure(file_structure)
        
        return {
            'structure': file_structure,
            'files': flat_files,
            'total_files': len(flat_files),
            'base_name': base_path or 'uploaded_files'
        }
    
    @staticmethod
    def flatten_structure(structure: Dict, current_path: str = "") -> List[Dict]:
        """Flatten nested structure to list of files with paths"""
        files = []
        
        for name, content in structure.items():
            path = os.path.join(current_path, name) if current_path else name
            
            if isinstance(content, dict):
                if 'content' in content:
                    # It's a file
                    files.append({
                        'path': path,
                        'name': name,
                        'content': content['content'],
                        'size': content['size'],
                        'type': content['type']
                    })
                else:
                    # It's a directory
                    files.extend(DirectoryUploader.flatten_structure(content, path))
        
        return files
    
    @staticmethod
    def load_local_directory(directory_path: str) -> Dict:
        """Load a local directory (for development)"""
        if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
            return None
        
        base_name = os.path.basename(directory_path)
        files = []
        structure = {}
        
        # Walk through directory
        for root, dirs, filenames in os.walk(directory_path):
            # Skip hidden directories and common ignore patterns
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git']]
            
            rel_path = os.path.relpath(root, directory_path)
            
            for filename in filenames:
                # Skip hidden files and common ignore patterns
                if filename.startswith('.') or filename.endswith('.pyc'):
                    continue
                
                file_path = os.path.join(root, filename)
                rel_file_path = os.path.relpath(file_path, directory_path)
                
                try:
                    # Read file content
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    # Get file stats
                    stats = os.stat(file_path)
                    
                    files.append({
                        'path': rel_file_path,
                        'name': filename,
                        'content': content,
                        'size': stats.st_size,
                        'type': mimetypes.guess_type(filename)[0] or 'application/octet-stream',
                        'modified': datetime.fromtimestamp(stats.st_mtime)
                    })
                    
                    # Build structure
                    parts = rel_file_path.split(os.sep)
                    current = structure
                    for part in parts[:-1]:
                        if part not in current and part != '.':
                            current[part] = {}
                        if part != '.':
                            current = current[part]
                    
                    current[filename] = {
                        'content': content,
                        'size': stats.st_size,
                        'type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                    }
                    
                except Exception as e:
                    st.warning(f"Could not read {rel_file_path}: {e}")
        
        return {
            'structure': structure,
            'files': files,
            'total_files': len(files),
            'base_name': base_name,
            'source_path': directory_path
        }
    
    @staticmethod
    def render_file_tree(structure: Dict, level: int = 0):
        """Render a visual file tree"""
        for name, content in structure.items():
            indent = "  " * level
            
            if isinstance(content, dict):
                if 'content' in content:
                    # It's a file
                    icon = DirectoryUploader.get_file_icon(name)
                    size_kb = content['size'] / 1024
                    st.text(f"{indent}{icon} {name} ({size_kb:.1f} KB)")
                else:
                    # It's a directory
                    st.text(f"{indent}📁 {name}/")
                    DirectoryUploader.render_file_tree(content, level + 1)
    
    @staticmethod
    def get_file_icon(filename: str) -> str:
        """Get icon for file type"""
        ext = Path(filename).suffix.lower()
        
        icon_map = {
            # Code files
            '.py': '🐍', '.js': '📜', '.ts': '📘', '.java': '☕',
            '.cpp': '⚙️', '.c': '⚙️', '.h': '📄', '.go': '🐹',
            '.rs': '🦀', '.rb': '💎', '.php': '🐘', '.swift': '🦉',
            # Web files
            '.html': '🌐', '.css': '🎨', '.scss': '🎨', '.jsx': '⚛️',
            '.vue': '💚', '.tsx': '⚛️',
            # Data files
            '.json': '📊', '.yaml': '📋', '.yml': '📋', '.xml': '📄',
            '.csv': '📈', '.sql': '🗄️',
            # Doc files
            '.md': '📝', '.txt': '📄', '.pdf': '📕', '.doc': '📘',
            '.docx': '📘',
            # Image files
            '.png': '🖼️', '.jpg': '🖼️', '.jpeg': '🖼️', '.gif': '🎞️',
            '.svg': '🎨', '.ico': '🎨',
            # Config files
            '.env': '🔐', '.ini': '⚙️', '.conf': '⚙️', '.toml': '⚙️',
            # Other
            '.gitignore': '🚫', '.dockerfile': '🐳'
        }
        
        return icon_map.get(ext, '📄')

def render_directory_upload_interface():
    """Main interface for directory upload"""
    
    st.header("📁 Upload Directory")
    
    # Instructions
    with st.expander("ℹ️ How to upload directories"):
        st.markdown("""
        ### Option 1: File Selection
        1. Click 'Browse files'
        2. Navigate to your directory
        3. Select all files (Ctrl/Cmd + A)
        4. Click 'Open'
        
        ### Option 2: Local Path (Development)
        1. Enter the full path to your directory
        2. Click 'Load Directory'
        
        ### Supported Features:
        - ✅ Preserves folder structure
        - ✅ Handles nested directories
        - ✅ Skips hidden files and common ignore patterns
        - ✅ Shows file tree preview
        - ✅ Maintains file relationships
        """)
    
    # Upload interface
    result = DirectoryUploader.render_directory_upload()
    
    if result:
        st.success(f"✅ Loaded {result['total_files']} files from '{result['base_name']}'")
        
        # Show file tree
        with st.expander("📊 File Structure", expanded=True):
            DirectoryUploader.render_file_tree(result['structure'])
        
        # Show statistics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Files", result['total_files'])
        
        with col2:
            total_size = sum(f['size'] for f in result['files'])
            st.metric("Total Size", f"{total_size / (1024*1024):.2f} MB")
        
        with col3:
            file_types = set(Path(f['path']).suffix for f in result['files'])
            st.metric("File Types", len(file_types))
        
        # Return result for further processing
        return result
    
    return None

def add_directory_to_project(project_manager, project_id: str, directory_data: Dict) -> int:
    """Add uploaded directory to a project"""
    
    files_added = 0
    
    for file_data in directory_data['files']:
        try:
            # Preserve directory structure in project
            success = project_manager.add_file_to_project(
                project_id,
                file_data['name'],
                file_data['content'],
                file_data['path']  # Use full path to preserve structure
            )
            
            if success:
                files_added += 1
                
        except Exception as e:
            st.error(f"Failed to add {file_data['path']}: {e}")
    
    return files_added