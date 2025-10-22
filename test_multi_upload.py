#!/usr/bin/env python3
"""
Test multiple file upload functionality
"""

import streamlit as st
from ui.file_handler import FileHandler, render_file_upload_zone
from ui.batch_upload import BatchFileUploader
from pathlib import Path

st.set_page_config(
    page_title="Multi-File Upload Test",
    page_icon="📁",
    layout="wide"
)

st.title("📁 Multiple File Upload Test")
st.markdown("Test the improved multiple file upload functionality")

# Test different upload methods
tab1, tab2, tab3 = st.tabs(["Standard Upload", "Batch Upload", "File Info"])

with tab1:
    st.header("Standard Multi-File Upload")
    st.info("✅ You can now upload multiple files at once!")
    
    # Render the improved file upload zone
    uploaded_files = render_file_upload_zone(key_suffix="test1")
    
    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} files successfully!")
        
        # Show file summary
        st.subheader("📊 File Summary")
        for file_info in uploaded_files:
            if not file_info.get('error'):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"📄 {file_info['name']}")
                with col2:
                    st.write(f"Type: {file_info['type']}")
                with col3:
                    st.write(f"Size: {file_info['size'] / 1024:.1f} KB")

with tab2:
    st.header("Batch Upload Interface")
    st.markdown("Advanced batch upload with multiple methods")
    
    # Use the batch uploader
    batch_files = BatchFileUploader.render_batch_upload_interface()
    
    if batch_files:
        st.success(f"Batch uploaded {len(batch_files)} files!")

with tab3:
    st.header("📋 File Type Support")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Supported File Types")
        
        for category, extensions in FileHandler.SUPPORTED_EXTENSIONS.items():
            if extensions:
                with st.expander(f"{category.title()} Files"):
                    st.write(", ".join(extensions[:20]))
                    if len(extensions) > 20:
                        st.write(f"... and {len(extensions) - 20} more")
    
    with col2:
        st.subheader("File Size Limits")
        
        for file_type, max_size in FileHandler.MAX_FILE_SIZES.items():
            size_mb = max_size / (1024 * 1024)
            st.metric(f"{file_type.title()}", f"{size_mb:.0f} MB")

# Instructions
st.sidebar.header("📚 How to Use")
st.sidebar.markdown("""
### Multiple File Selection:

**Windows/Linux:**
- Click first file
- Hold `Ctrl` and click additional files
- Or use `Ctrl+A` to select all

**Mac:**
- Click first file  
- Hold `Cmd` and click additional files
- Or use `Cmd+A` to select all

**Drag & Drop:**
- Select multiple files in your file manager
- Drag them all into the upload zone

### Folder Upload:
1. Navigate to folder
2. Press `Ctrl+A` (Win/Linux) or `Cmd+A` (Mac)
3. Click Open to upload all files

### Tips:
- ✅ No file type restrictions
- ✅ No ZIP required
- ✅ Preserves folder structure
- ✅ Progress bar for large uploads
- ✅ Parallel processing for speed
""")

if __name__ == "__main__":
    st.sidebar.info("Multiple file upload is now fully supported!")