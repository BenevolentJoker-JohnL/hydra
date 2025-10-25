"""
Git Integration for Hydra
Provides Claude Code-style git workflow for file edits
"""

import os
import subprocess
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import difflib

@dataclass
class GitStatus:
    """Git repository status"""
    is_repo: bool
    current_branch: str
    is_clean: bool
    modified_files: List[str]
    untracked_files: List[str]
    staged_files: List[str]

@dataclass
class FileChange:
    """Represents a file change with diff"""
    path: str
    change_type: str  # 'modify', 'create', 'delete'
    old_content: Optional[str]
    new_content: Optional[str]
    diff: str
    approved: bool = False

class GitIntegration:
    """
    Git integration for safe, reviewable file edits.

    Workflow:
    1. Create feature branch (hydra/task-xxx)
    2. Make changes on branch
    3. Show diffs to user
    4. On approval → commit + optional merge
    5. On denial → discard branch
    """

    def __init__(self, project_dir: str = "."):
        self.project_dir = os.path.abspath(project_dir)
        self.hydra_branch_prefix = "hydra"
        self.current_hydra_branch: Optional[str] = None

    def is_git_repo(self) -> bool:
        """Check if directory is a git repository"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Not a git repo: {e}")
            return False

    def get_status(self) -> GitStatus:
        """Get current git status"""
        if not self.is_git_repo():
            return GitStatus(
                is_repo=False,
                current_branch="",
                is_clean=True,
                modified_files=[],
                untracked_files=[],
                staged_files=[]
            )

        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )
            current_branch = branch_result.stdout.strip()

            # Get status
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )

            modified = []
            untracked = []
            staged = []

            for line in status_result.stdout.split('\n'):
                if not line:
                    continue
                status = line[:2]
                filename = line[3:].strip()

                if status[0] in ['M', 'A', 'D', 'R', 'C']:
                    staged.append(filename)
                if status[1] == 'M':
                    modified.append(filename)
                elif status == '??':
                    untracked.append(filename)

            return GitStatus(
                is_repo=True,
                current_branch=current_branch,
                is_clean=len(modified) == 0 and len(untracked) == 0 and len(staged) == 0,
                modified_files=modified,
                untracked_files=untracked,
                staged_files=staged
            )

        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            return GitStatus(
                is_repo=True,
                current_branch="unknown",
                is_clean=False,
                modified_files=[],
                untracked_files=[],
                staged_files=[]
            )

    def create_hydra_branch(self, task_description: str = "") -> Tuple[bool, str]:
        """
        Create a new Hydra feature branch.
        Returns: (success, branch_name)
        """
        if not self.is_git_repo():
            return False, "Not a git repository"

        # Generate branch name
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_slug = task_description.lower().replace(' ', '-')[:30] if task_description else "changes"
        branch_name = f"{self.hydra_branch_prefix}/{task_slug}-{timestamp}"

        try:
            # Create and checkout new branch
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                self.current_hydra_branch = branch_name
                logger.success(f"✅ Created Hydra branch: {branch_name}")
                return True, branch_name
            else:
                logger.error(f"Failed to create branch: {result.stderr}")
                return False, result.stderr

        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            return False, str(e)

    def get_file_diff(self, filepath: str, new_content: str) -> str:
        """
        Generate unified diff for a file change.
        """
        abs_path = os.path.join(self.project_dir, filepath)

        # Read old content if file exists
        old_lines = []
        if os.path.exists(abs_path):
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    old_lines = f.readlines()
            except:
                old_lines = ["<binary file or read error>\n"]

        new_lines = new_content.splitlines(keepends=True)

        # Generate diff
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
            lineterm=''
        )

        return ''.join(diff)

    def create_file_change(self, filepath: str, new_content: str) -> FileChange:
        """Create a FileChange object with diff"""
        abs_path = os.path.join(self.project_dir, filepath)

        # Determine change type
        if os.path.exists(abs_path):
            change_type = 'modify'
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    old_content = f.read()
            except:
                old_content = "<binary file or read error>"
        else:
            change_type = 'create'
            old_content = None

        # Generate diff
        diff = self.get_file_diff(filepath, new_content)

        return FileChange(
            path=filepath,
            change_type=change_type,
            old_content=old_content,
            new_content=new_content,
            diff=diff,
            approved=False
        )

    def apply_file_change(self, change: FileChange) -> bool:
        """Apply a file change to disk"""
        abs_path = os.path.join(self.project_dir, change.path)

        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            # Write new content
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(change.new_content)

            logger.success(f"✅ Applied change to {change.path}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to apply change to {change.path}: {e}")
            return False

    def commit_changes(self, message: str, files: Optional[List[str]] = None) -> bool:
        """
        Commit changes to current branch.
        If files is None, commits all changes.
        """
        if not self.is_git_repo():
            logger.warning("Not in a git repository")
            return False

        try:
            # Add files
            if files:
                for file in files:
                    subprocess.run(
                        ["git", "add", file],
                        cwd=self.project_dir,
                        capture_output=True,
                        timeout=10
                    )
            else:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.project_dir,
                    capture_output=True,
                    timeout=10
                )

            # Commit
            commit_result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if commit_result.returncode == 0:
                logger.success(f"✅ Committed: {message[:50]}...")
                return True
            else:
                logger.error(f"❌ Commit failed: {commit_result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error committing: {e}")
            return False

    def merge_to_branch(self, target_branch: str = "main") -> Tuple[bool, str]:
        """
        Merge current Hydra branch to target branch.
        Returns: (success, message)
        """
        if not self.is_git_repo():
            return False, "Not in a git repository"

        if not self.current_hydra_branch:
            return False, "No active Hydra branch"

        try:
            # Switch to target branch
            checkout_result = subprocess.run(
                ["git", "checkout", target_branch],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if checkout_result.returncode != 0:
                return False, f"Failed to checkout {target_branch}: {checkout_result.stderr}"

            # Merge Hydra branch
            merge_result = subprocess.run(
                ["git", "merge", "--no-ff", self.current_hydra_branch, "-m",
                 f"Merge {self.current_hydra_branch}"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if merge_result.returncode == 0:
                logger.success(f"✅ Merged {self.current_hydra_branch} → {target_branch}")
                return True, f"Successfully merged to {target_branch}"
            else:
                # Merge conflict or error
                logger.error(f"❌ Merge failed: {merge_result.stderr}")
                return False, f"Merge failed: {merge_result.stderr}"

        except Exception as e:
            logger.error(f"Error during merge: {e}")
            return False, str(e)

    def discard_hydra_branch(self) -> bool:
        """
        Discard current Hydra branch and return to previous branch.
        """
        if not self.current_hydra_branch:
            return True

        try:
            # Get previous branch (usually main or master)
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "@{-1}"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )
            previous_branch = branch_result.stdout.strip() or "main"

            # Checkout previous branch
            subprocess.run(
                ["git", "checkout", previous_branch],
                cwd=self.project_dir,
                capture_output=True,
                timeout=10
            )

            # Delete Hydra branch
            delete_result = subprocess.run(
                ["git", "branch", "-D", self.current_hydra_branch],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if delete_result.returncode == 0:
                logger.success(f"✅ Discarded Hydra branch: {self.current_hydra_branch}")
                self.current_hydra_branch = None
                return True
            else:
                logger.error(f"Failed to delete branch: {delete_result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error discarding branch: {e}")
            return False

    def generate_commit_message(self, changes: List[FileChange]) -> str:
        """
        Generate an intelligent commit message based on changes.
        """
        if not changes:
            return "Update files"

        # Categorize changes
        creates = [c for c in changes if c.change_type == 'create']
        modifies = [c for c in changes if c.change_type == 'modify']
        deletes = [c for c in changes if c.change_type == 'delete']

        # Build message
        parts = []

        if creates:
            if len(creates) == 1:
                parts.append(f"Add {creates[0].path}")
            else:
                parts.append(f"Add {len(creates)} files")

        if modifies:
            if len(modifies) == 1:
                parts.append(f"Update {modifies[0].path}")
            else:
                parts.append(f"Update {len(modifies)} files")

        if deletes:
            if len(deletes) == 1:
                parts.append(f"Delete {deletes[0].path}")
            else:
                parts.append(f"Delete {len(deletes)} files")

        message = ", ".join(parts)

        # Add file list if multiple changes
        if len(changes) > 1:
            message += "\n\n"
            for change in changes:
                icon = "+" if change.change_type == 'create' else "~" if change.change_type == 'modify' else "-"
                message += f"{icon} {change.path}\n"

        message += "\n🤖 Generated by Hydra AI"

        return message

    def get_branch_diff(self, base_branch: str = "main") -> str:
        """Get full diff of current branch vs base branch"""
        try:
            result = subprocess.run(
                ["git", "diff", base_branch],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout
        except Exception as e:
            logger.error(f"Failed to get branch diff: {e}")
            return ""
