"""
Approval UI Handler for Tool Execution
Handles user approval dialogs and auto-approval rules
"""

import streamlit as st
import asyncio
from typing import Dict, Any
from core.tools import PermissionLevel
from loguru import logger

class ApprovalHandler:
    """Manages approval requests and UI for tool execution"""

    def __init__(self):
        # Initialize session state for pending approvals
        if 'pending_approvals' not in st.session_state:
            st.session_state.pending_approvals = []
        if 'approval_responses' not in st.session_state:
            st.session_state.approval_responses = {}

    async def request_approval(self, tool_name: str, arguments: Dict, permission_level: PermissionLevel) -> bool:
        """
        Request approval from user via Streamlit UI.
        This creates an approval request that will be displayed in the UI.
        """
        # Create unique ID for this approval request
        request_id = f"{tool_name}_{id(arguments)}"

        # Add to pending approvals
        st.session_state.pending_approvals.append({
            'id': request_id,
            'tool': tool_name,
            'arguments': arguments,
            'permission_level': permission_level.value,
            'timestamp': st.session_state.get('_approval_timestamp', 0)
        })

        logger.info(f"🔐 Approval request created: {request_id}")

        # Force Streamlit to rerun to display the approval dialog
        st.rerun()

        # Wait for user response (this will be set by the UI callback)
        # In practice, the UI will handle this through button callbacks
        # For now, return False to prevent execution until approved
        return False

    def render_pending_approvals(self):
        """Render pending approval requests in the UI"""
        if not st.session_state.pending_approvals:
            return

        st.divider()
        st.markdown("### 🔐 Pending Approval Requests")

        for idx, request in enumerate(st.session_state.pending_approvals):
            with st.expander(f"⚠️ Approve {request['tool']}? (Permission: {request['permission_level']})", expanded=True):
                st.markdown(f"**Tool**: `{request['tool']}`")
                st.markdown(f"**Permission Level**: `{request['permission_level']}`")
                st.markdown("**Arguments**:")
                st.json(request['arguments'])

                # Show warning for CRITICAL operations
                if request['permission_level'] == 'critical':
                    st.error("⚠️ **CRITICAL OPERATION** - This action can modify your system. Review carefully!")
                elif request['permission_level'] == 'approval':
                    st.warning("⚡ This operation requires approval but can be auto-approved with rules.")

                col1, col2, col3 = st.columns([1, 1, 2])

                with col1:
                    if st.button("✅ Approve", key=f"approve_{request['id']}", type="primary"):
                        self._approve_request(idx, request)

                with col2:
                    if st.button("❌ Deny", key=f"deny_{request['id']}"):
                        self._deny_request(idx, request)

                with col3:
                    if request['permission_level'] != 'critical':  # Can't auto-approve critical
                        if st.button("🔄 Approve Similar", key=f"approve_similar_{request['id']}"):
                            self._approve_and_remember(idx, request)

    def _approve_request(self, idx: int, request: Dict):
        """Approve a single request"""
        st.session_state.approval_responses[request['id']] = True
        st.session_state.pending_approvals.pop(idx)
        logger.info(f"✅ Request approved: {request['tool']}")
        st.success(f"✅ Approved {request['tool']}")
        st.rerun()

    def _deny_request(self, idx: int, request: Dict):
        """Deny a request"""
        st.session_state.approval_responses[request['id']] = False
        st.session_state.pending_approvals.pop(idx)
        logger.warning(f"⛔ Request denied: {request['tool']}")
        st.warning(f"⛔ Denied {request['tool']}")
        st.rerun()

    def _approve_and_remember(self, idx: int, request: Dict):
        """Approve request and add auto-approval pattern"""
        # Store the approval
        st.session_state.approval_responses[request['id']] = True

        # Add to auto-approval patterns (if code_assistant is available)
        if 'code_assistant' in st.session_state:
            approval_tracker = st.session_state.code_assistant.approval_tracker

            # Create a pattern based on the request
            pattern = {
                'name': f"Auto-approve {request['tool']}",
                'tool': request['tool'],
                'conditions': [
                    {
                        'type': 'session_limit',
                        'max_uses': 100  # Allow up to 100 similar operations
                    }
                ]
            }

            approval_tracker.add_auto_approval_pattern(pattern)
            logger.info(f"➕ Auto-approval pattern added for {request['tool']}")

        st.session_state.pending_approvals.pop(idx)
        st.success(f"✅ Approved {request['tool']} and similar operations")
        st.rerun()


def render_approval_stats():
    """Render approval statistics in the sidebar"""
    if 'code_assistant' not in st.session_state:
        return

    approval_tracker = st.session_state.code_assistant.approval_tracker
    stats = approval_tracker.get_approval_stats()

    with st.expander("📊 Approval Statistics", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.metric("Total Approvals", stats['total_approvals'])
            st.metric("Unique Operations", stats['unique_operations'])

        with col2:
            st.metric("Auto-Approval Rules", stats['auto_approval_patterns'])

        if stats['session_usage']:
            st.markdown("**Session Usage:**")
            for tool, count in stats['session_usage'].items():
                st.markdown(f"- `{tool}`: {count} uses")

        if stats['recent_approvals']:
            st.markdown("**Recent Approvals:**")
            for approval in stats['recent_approvals'][-5:]:  # Last 5
                auto_str = " (auto)" if approval['auto_approved'] else ""
                st.markdown(f"- `{approval['tool']}`{auto_str}")


def setup_auto_approval_rules(approval_tracker):
    """Setup common auto-approval rules"""

    # Auto-approve reading files in the project directory
    approval_tracker.add_auto_approval_pattern({
        'name': 'Read project files',
        'tool': 'read_file',
        'conditions': [
            {
                'type': 'path_prefix',
                'allowed_prefixes': ['./', '/home/joker/hydra']
            }
        ]
    })

    # Auto-approve listing directories
    approval_tracker.add_auto_approval_pattern({
        'name': 'List directories',
        'tool': 'list_directory',
        'conditions': []  # Always allow
    })

    # Auto-approve searching codebase
    approval_tracker.add_auto_approval_pattern({
        'name': 'Search codebase',
        'tool': 'search_codebase',
        'conditions': []  # Always allow
    })

    # Auto-approve code analysis
    approval_tracker.add_auto_approval_pattern({
        'name': 'Analyze code',
        'tool': 'analyze_code',
        'conditions': []  # Always allow
    })

    # Auto-approve executing simple Python (read-only operations)
    approval_tracker.add_auto_approval_pattern({
        'name': 'Execute safe Python',
        'tool': 'execute_python',
        'conditions': [
            {
                'type': 'session_limit',
                'max_uses': 10  # Limit to 10 per session
            }
        ]
    })

    logger.info("✅ Default auto-approval rules configured")
