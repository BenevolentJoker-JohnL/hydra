import streamlit as st
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json
from pathlib import Path

@dataclass
class Artifact:
    id: str
    title: str
    type: str  # code, document, data, diagram
    content: str
    language: Optional[str] = "python"
    created_at: datetime = None
    updated_at: datetime = None
    version: int = 1
    metadata: Dict = None
    editable: bool = True
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}

class ArtifactManager:
    def __init__(self):
        if 'artifacts' not in st.session_state:
            st.session_state.artifacts = {}
        if 'current_artifact' not in st.session_state:
            st.session_state.current_artifact = None
            
    def create_artifact(self, title: str, content: str, artifact_type: str = "code", 
                        language: str = "python") -> Artifact:
        artifact_id = f"artifact_{uuid.uuid4().hex[:8]}"
        artifact = Artifact(
            id=artifact_id,
            title=title,
            type=artifact_type,
            content=content,
            language=language
        )
        
        st.session_state.artifacts[artifact_id] = artifact
        st.session_state.current_artifact = artifact_id
        
        return artifact
        
    def update_artifact(self, artifact_id: str, content: str = None, title: str = None):
        if artifact_id in st.session_state.artifacts:
            artifact = st.session_state.artifacts[artifact_id]
            
            if content is not None and content != artifact.content:
                artifact.content = content
                artifact.version += 1
                
            if title is not None:
                artifact.title = title
                
            artifact.updated_at = datetime.now()
            st.session_state.artifacts[artifact_id] = artifact
            
    def append_to_artifact(self, artifact_id: str, content: str):
        if artifact_id in st.session_state.artifacts:
            artifact = st.session_state.artifacts[artifact_id]
            artifact.content += "\n" + content
            artifact.version += 1
            artifact.updated_at = datetime.now()
            st.session_state.artifacts[artifact_id] = artifact
            
    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        return st.session_state.artifacts.get(artifact_id)
        
    def list_artifacts(self) -> List[Artifact]:
        return list(st.session_state.artifacts.values())
        
    def delete_artifact(self, artifact_id: str):
        if artifact_id in st.session_state.artifacts:
            del st.session_state.artifacts[artifact_id]
            if st.session_state.current_artifact == artifact_id:
                st.session_state.current_artifact = None
                
    def export_artifact(self, artifact_id: str) -> Dict:
        artifact = self.get_artifact(artifact_id)
        if artifact:
            data = asdict(artifact)
            data['created_at'] = artifact.created_at.isoformat()
            data['updated_at'] = artifact.updated_at.isoformat()
            return data
        return {}

def render_artifact_panel():
    """Render the artifact panel in the UI"""
    manager = ArtifactManager()
    
    if st.session_state.current_artifact:
        artifact = manager.get_artifact(st.session_state.current_artifact)
        
        if artifact:
            # Artifact header
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            
            with col1:
                new_title = st.text_input(
                    "Title",
                    value=artifact.title,
                    key=f"title_{artifact.id}",
                    label_visibility="collapsed"
                )
                if new_title != artifact.title:
                    manager.update_artifact(artifact.id, title=new_title)
                    
            with col2:
                st.caption(f"v{artifact.version}")
                
            with col3:
                if st.button("📋", key=f"copy_{artifact.id}", help="Copy to clipboard"):
                    st.write("Copied!")  # Note: Real clipboard requires JS
                    
            with col4:
                if st.button("❌", key=f"close_{artifact.id}", help="Close"):
                    st.session_state.current_artifact = None
                    st.rerun()
            
            # Artifact content
            if artifact.editable:
                # Editable code editor
                new_content = st.text_area(
                    "Content",
                    value=artifact.content,
                    height=400,
                    key=f"content_{artifact.id}",
                    label_visibility="collapsed"
                )
                
                if new_content != artifact.content:
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("💾 Save Changes", key=f"save_{artifact.id}"):
                            manager.update_artifact(artifact.id, content=new_content)
                            st.success("Saved!")
                    with col2:
                        if st.button("↩️ Revert", key=f"revert_{artifact.id}"):
                            st.rerun()
            else:
                # Read-only display
                if artifact.type == "code":
                    st.code(artifact.content, language=artifact.language)
                elif artifact.type == "document":
                    st.markdown(artifact.content)
                elif artifact.type == "data":
                    try:
                        data = json.loads(artifact.content)
                        st.json(data)
                    except:
                        st.text(artifact.content)
                else:
                    st.text(artifact.content)
            
            # Artifact actions
            with st.expander("Actions"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("🔄 Continue Generation", key=f"continue_{artifact.id}"):
                        return {"action": "continue", "artifact_id": artifact.id}
                        
                with col2:
                    if st.button("📥 Download", key=f"download_{artifact.id}"):
                        file_ext = {
                            "code": ".py",
                            "document": ".md",
                            "data": ".json",
                            "diagram": ".svg"
                        }.get(artifact.type, ".txt")
                        
                        st.download_button(
                            "Download File",
                            artifact.content,
                            f"{artifact.title}{file_ext}",
                            key=f"dl_btn_{artifact.id}"
                        )
                        
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{artifact.id}"):
                        manager.delete_artifact(artifact.id)
                        st.rerun()
            
            # Version history
            with st.expander("Version History"):
                st.caption(f"Created: {artifact.created_at.strftime('%Y-%m-%d %H:%M')}")
                st.caption(f"Updated: {artifact.updated_at.strftime('%Y-%m-%d %H:%M')}")
                st.caption(f"Version: {artifact.version}")
                
    return None

def render_artifacts_sidebar():
    """Render artifacts list in sidebar"""
    manager = ArtifactManager()
    artifacts = manager.list_artifacts()
    
    if artifacts:
        st.sidebar.subheader("📄 Artifacts")
        
        for artifact in sorted(artifacts, key=lambda a: a.updated_at, reverse=True)[:5]:
            if st.sidebar.button(
                f"{artifact.title}",
                key=f"sidebar_{artifact.id}",
                use_container_width=True
            ):
                st.session_state.current_artifact = artifact.id
                st.rerun()

class ArtifactGenerator:
    """Generate artifacts from prompts and continue generation"""
    
    def __init__(self, load_balancer):
        self.lb = load_balancer
        self.manager = ArtifactManager()
        
    async def generate_artifact(self, prompt: str, artifact_type: str = None) -> Artifact:
        """Generate a new artifact from prompt"""
        
        # Detect artifact type from prompt if not specified
        if artifact_type is None:
            artifact_type = self._detect_artifact_type(prompt)
            
        # Create generation prompt
        if artifact_type == "code":
            enhanced_prompt = f"""Generate complete, production-ready code for: {prompt}

Include:
- Proper imports
- Error handling
- Documentation/comments
- Example usage if applicable

Return ONLY the code, no explanations."""
            
        elif artifact_type == "document":
            enhanced_prompt = f"""Create a comprehensive document for: {prompt}

Use markdown formatting with:
- Clear sections and headers
- Bullet points where appropriate
- Code examples in code blocks
- Professional tone

Return ONLY the document content."""
            
        else:
            enhanced_prompt = prompt
            
        # Generate content
        response = await self.lb.generate(
            model="qwen2.5-coder:7b",  # Use appropriate model
            prompt=enhanced_prompt,
            temperature=0.7
        )
        
        # Extract title from prompt
        title = prompt[:50] + "..." if len(prompt) > 50 else prompt
        
        # Create artifact
        artifact = self.manager.create_artifact(
            title=title,
            content=response['response'],
            artifact_type=artifact_type,
            language="python" if artifact_type == "code" else None
        )
        
        return artifact
        
    async def continue_artifact(self, artifact_id: str, instruction: str = None) -> Artifact:
        """Continue generating content for existing artifact"""
        
        artifact = self.manager.get_artifact(artifact_id)
        if not artifact:
            return None
            
        if instruction:
            prompt = f"""Continue the following {artifact.type} based on this instruction: {instruction}

Current content:
{artifact.content}

Continue from where it left off:"""
        else:
            prompt = f"""Continue the following {artifact.type}:

{artifact.content}

Continue from where it left off with more content:"""
            
        # Generate continuation
        response = await self.lb.generate(
            model="qwen2.5-coder:7b",
            prompt=prompt,
            temperature=0.7
        )
        
        # Append to artifact
        self.manager.append_to_artifact(artifact_id, response['response'])
        
        return self.manager.get_artifact(artifact_id)
        
    def _detect_artifact_type(self, prompt: str) -> str:
        """Detect artifact type from prompt"""
        prompt_lower = prompt.lower()
        
        code_keywords = ["function", "class", "code", "implement", "algorithm", "script", "program"]
        doc_keywords = ["document", "documentation", "explain", "guide", "tutorial", "readme"]
        data_keywords = ["json", "data", "schema", "structure", "format"]
        
        if any(keyword in prompt_lower for keyword in code_keywords):
            return "code"
        elif any(keyword in prompt_lower for keyword in doc_keywords):
            return "document"
        elif any(keyword in prompt_lower for keyword in data_keywords):
            return "data"
        else:
            return "code"  # Default to code

def extract_artifacts_from_response(response: str) -> List[Dict]:
    """Extract artifact markers from model response"""
    import re
    
    artifacts = []
    
    # Pattern for artifact blocks
    artifact_pattern = r'<artifact(?:\s+type="(\w+)")?\s+title="([^"]+)">\n(.*?)\n</artifact>'
    matches = re.findall(artifact_pattern, response, re.DOTALL)
    
    for artifact_type, title, content in matches:
        artifacts.append({
            "type": artifact_type or "code",
            "title": title,
            "content": content.strip()
        })
        
    # Also check for code blocks as implicit artifacts
    if not artifacts:
        code_pattern = r'```(\w+)?\n(.*?)```'
        code_matches = re.findall(code_pattern, response, re.DOTALL)
        
        for language, content in code_matches:
            if len(content) > 100:  # Only create artifact for substantial code
                artifacts.append({
                    "type": "code",
                    "title": "Generated Code",
                    "content": content.strip(),
                    "language": language or "python"
                })
                
    return artifacts