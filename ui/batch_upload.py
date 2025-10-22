"""
Batch file upload handler for multiple files
Optimized for handling large numbers of files efficiently
"""

import streamlit as st
from pathlib import Path
import asyncio
from typing import List, Dict, Any
import concurrent.futures
from loguru import logger
import tempfile
import shutil

class BatchFileUploader:
    """Handle batch file uploads efficiently"""
    
    @staticmethod
    def render_batch_upload_interface():
        """Render batch upload interface with multiple options"""
        
        st.markdown("""
        <style>
        .batch-upload-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 15px;
            padding: 30px;
            margin: 20px 0;
            color: white;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .upload-method {
            background: white;
            color: #333;
            padding: 15px;
            border-radius: 10px;
            margin: 10px 0;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .upload-method:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        .file-stats {
            background: rgba(255,255,255,0.2);
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="batch-upload-card">', unsafe_allow_html=True)
        st.markdown("# 📦 Batch File Upload")
        st.markdown("Upload multiple files or entire project directories at once!")
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Upload method selection
        upload_method = st.radio(
            "Choose upload method:",
            ["📁 Multiple Files", "📂 Folder (Select All)", "📋 File List (Text)"],
            horizontal=True
        )
        
        uploaded_files = None
        
        if upload_method == "📁 Multiple Files":
            st.info("💡 **Pro Tip**: Hold Ctrl (Windows/Linux) or Cmd (Mac) while clicking to select multiple files!")
            
            uploaded_files = st.file_uploader(
                "Select multiple files",
                accept_multiple_files=True,
                key="batch_multi_files",
                help="Select as many files as you want. No limit!"
            )
            
            if uploaded_files:
                BatchFileUploader._show_file_statistics(uploaded_files)
                
        elif upload_method == "📂 Folder (Select All)":
            st.info("📁 **How to upload a folder**:")
            st.markdown("""
            1. Click 'Browse files' below
            2. Navigate to your folder
            3. Press **Ctrl+A** (Windows/Linux) or **Cmd+A** (Mac) to select all files
            4. Click 'Open' to upload all selected files
            """)
            
            uploaded_files = st.file_uploader(
                "Select all files from folder",
                accept_multiple_files=True,
                key="batch_folder_files",
                help="Select all files in your folder using Ctrl+A or Cmd+A"
            )
            
            if uploaded_files:
                BatchFileUploader._show_folder_structure(uploaded_files)
                
        elif upload_method == "📋 File List (Text)":
            st.info("📝 Paste a list of file paths to upload")
            
            file_paths_text = st.text_area(
                "Enter file paths (one per line):",
                height=200,
                placeholder="/path/to/file1.py\n/path/to/file2.js\n/path/to/data.csv",
                key="batch_file_paths"
            )
            
            if st.button("📤 Load Files from Paths"):
                file_paths = [p.strip() for p in file_paths_text.split('\n') if p.strip()]
                uploaded_files = BatchFileUploader._load_files_from_paths(file_paths)
                
        return uploaded_files
    
    @staticmethod
    def _show_file_statistics(files: List):
        """Show statistics about uploaded files"""
        if not files:
            return
            
        total_size = sum(f.size for f in files)
        file_types = {}
        
        for f in files:
            ext = Path(f.name).suffix.lower()
            file_types[ext] = file_types.get(ext, 0) + 1
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Files", len(files))
        
        with col2:
            st.metric("Total Size", f"{total_size / (1024*1024):.2f} MB")
        
        with col3:
            st.metric("File Types", len(file_types))
        
        # Show file type distribution
        if file_types:
            with st.expander("📊 File Type Distribution"):
                for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]:
                    st.write(f"{ext or 'no extension'}: {count} files")
    
    @staticmethod
    def _show_folder_structure(files: List):
        """Display folder structure from uploaded files"""
        if not files:
            return
            
        # Try to detect common path prefix
        file_paths = [f.name for f in files]
        common_prefix = Path(file_paths[0]).parent if file_paths else Path()
        
        for path in file_paths[1:]:
            current_parent = Path(path).parent
            while not str(current_parent).startswith(str(common_prefix)):
                common_prefix = common_prefix.parent
                if common_prefix == Path():
                    break
        
        st.markdown(f"**Detected folder structure** (common prefix: `{common_prefix or '/'}`)")
        
        # Show tree structure
        with st.expander("📂 File Tree", expanded=True):
            tree = {}
            for f in files:
                path_parts = Path(f.name).parts
                current = tree
                for part in path_parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[Path(f.name).name] = f.size
            
            BatchFileUploader._render_tree(tree)
    
    @staticmethod
    def _render_tree(tree: Dict, indent: int = 0):
        """Render file tree structure"""
        for key, value in tree.items():
            if isinstance(value, dict):
                st.write("  " * indent + f"📁 {key}/")
                BatchFileUploader._render_tree(value, indent + 1)
            else:
                size_kb = value / 1024
                st.write("  " * indent + f"📄 {key} ({size_kb:.1f} KB)")
    
    @staticmethod
    def _load_files_from_paths(file_paths: List[str]) -> List:
        """Load files from local file paths"""
        loaded_files = []
        
        for path_str in file_paths:
            try:
                path = Path(path_str)
                if path.exists() and path.is_file():
                    with open(path, 'rb') as f:
                        content = f.read()
                    
                    loaded_files.append({
                        'name': path.name,
                        'content': content,
                        'size': path.stat().st_size
                    })
                    st.success(f"✅ Loaded: {path.name}")
                else:
                    st.warning(f"⚠️ File not found: {path_str}")
                    
            except Exception as e:
                st.error(f"❌ Error loading {path_str}: {e}")
                
        return loaded_files

def process_files_parallel(files: List, max_workers: int = 4):
    """Process multiple files in parallel for better performance"""
    from .file_handler import FileHandler
    
    def process_single_file(file):
        """Process a single file"""
        try:
            return FileHandler.process_file(file)
        except Exception as e:
            logger.error(f"Error processing {file.name}: {e}")
            return {'error': str(e), 'name': file.name}
    
    # Use thread pool for I/O bound operations
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_file, f) for f in files]
        results = []
        
        # Show progress
        progress_bar = st.progress(0)
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()
            results.append(result)
            progress_bar.progress((i + 1) / len(files))
        
        progress_bar.empty()
        
    return results