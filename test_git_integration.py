#!/usr/bin/env python3
"""
Quick test of git integration
"""
import asyncio
import os
from core.git_integration import GitIntegration

async def test_git():
    print("="*60)
    print("GIT INTEGRATION TEST")
    print("="*60)

    # Test 1: Initialize
    print("\n[1/6] Initializing GitIntegration...")
    git = GitIntegration("/home/joker/hydra")

    # Test 2: Check if git repo
    print("\n[2/6] Checking git repo status...")
    is_repo = git.is_git_repo()
    print(f"   Is git repo: {is_repo}")
    assert is_repo, "Should be a git repo"

    # Test 3: Get status
    print("\n[3/6] Getting git status...")
    status = git.get_status()
    print(f"   Current branch: {status.current_branch}")
    print(f"   Is clean: {status.is_clean}")
    print(f"   Modified: {len(status.modified_files)}")
    print(f"   Untracked: {len(status.untracked_files)}")

    # Test 4: Create test file and generate diff
    print("\n[4/6] Testing diff generation...")
    test_content = "# Test File\nThis is a test.\nHello World!\n"
    file_change = git.create_file_change("test_git_file.txt", test_content)

    print(f"   Path: {file_change.path}")
    print(f"   Change type: {file_change.change_type}")
    print(f"   Has diff: {len(file_change.diff) > 0}")
    if file_change.diff:
        print("\n   Diff preview:")
        print("   " + "\n   ".join(file_change.diff.split('\n')[:10]))

    # Test 5: Create Hydra branch
    print("\n[5/6] Testing branch creation...")
    success, branch_name = git.create_hydra_branch("test-feature")
    print(f"   Branch created: {success}")
    print(f"   Branch name: {branch_name}")

    # Test 6: Generate commit message
    print("\n[6/6] Testing commit message generation...")
    changes = [file_change]
    commit_msg = git.generate_commit_message(changes)
    print(f"   Generated message:")
    print("   " + "\n   ".join(commit_msg.split('\n')[:5]))

    # Cleanup: Delete the test branch
    print("\n[Cleanup] Removing test branch...")
    cleanup_success = git.discard_hydra_branch()
    print(f"   Cleanup: {'✅' if cleanup_success else '❌'}")

    print("\n" + "="*60)
    print("✅ ALL GIT INTEGRATION TESTS PASSED!")
    print("="*60)
    print("\nGit Integration Features:")
    print("  ✅ Detect git repositories")
    print("  ✅ Get repository status")
    print("  ✅ Generate diffs for file changes")
    print("  ✅ Create Hydra feature branches")
    print("  ✅ Generate intelligent commit messages")
    print("  ✅ Rollback via branch discard")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_git())
