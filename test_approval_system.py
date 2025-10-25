#!/usr/bin/env python3
"""
Test the approval system for tool executions
"""

import asyncio
from core.tools import ToolRegistry, ToolCaller, ApprovalTracker, PermissionLevel
from loguru import logger

print("="*70)
print("APPROVAL SYSTEM TEST")
print("="*70)

async def main():
    # Initialize components
    print("\n[1/6] Initializing tool system...")
    registry = ToolRegistry()
    approval_tracker = ApprovalTracker()
    tool_caller = ToolCaller(registry, approval_tracker)

    print(f"   ✅ Tool registry initialized with {len(registry.tools)} tools")
    print(f"   ✅ Approval tracker initialized")

    # Test 1: Check permission levels
    print("\n[2/6] Testing permission levels...")
    permission_counts = {"safe": 0, "approval": 0, "critical": 0}

    for tool in registry.tools.values():
        permission_counts[tool.permission_level.value] += 1

    print(f"   ✅ SAFE tools: {permission_counts['safe']}")
    print(f"   ✅ REQUIRES_APPROVAL tools: {permission_counts['approval']}")
    print(f"   ✅ CRITICAL tools: {permission_counts['critical']}")

    # Verify specific tools have correct permissions
    assert registry.get('read_file').permission_level == PermissionLevel.SAFE, "read_file should be SAFE"
    assert registry.get('write_file').permission_level == PermissionLevel.CRITICAL, "write_file should be CRITICAL"
    assert registry.get('run_command').permission_level == PermissionLevel.CRITICAL, "run_command should be CRITICAL"
    assert registry.get('execute_python').permission_level == PermissionLevel.REQUIRES_APPROVAL, "execute_python should be REQUIRES_APPROVAL"
    print("   ✅ Tool permission levels are correct")

    # Test 2: Auto-approval for SAFE operations
    print("\n[3/6] Testing auto-approval for SAFE operations...")
    is_approved = approval_tracker.is_approved('read_file', {'path': 'test.txt'}, PermissionLevel.SAFE)
    assert is_approved, "SAFE operations should auto-approve"
    print("   ✅ SAFE operations auto-approve correctly")

    # Test 3: CRITICAL operations NEVER auto-approve
    print("\n[4/6] Testing CRITICAL operations cannot auto-approve...")
    is_approved = approval_tracker.is_approved('write_file', {'path': 'test.txt', 'content': 'test'}, PermissionLevel.CRITICAL)
    assert not is_approved, "CRITICAL operations should NEVER auto-approve"
    print("   ✅ CRITICAL operations correctly require approval")

    # Test 4: Auto-approval patterns
    print("\n[5/6] Testing auto-approval patterns...")

    # Add a pattern for Python execution
    approval_tracker.add_auto_approval_pattern({
        'name': 'Safe Python execution',
        'tool': 'execute_python',
        'conditions': [
            {
                'type': 'session_limit',
                'max_uses': 5
            }
        ]
    })

    # Test that it auto-approves within session limit
    for i in range(5):
        is_approved = approval_tracker.is_approved(
            'execute_python',
            {'code': f'print({i})'},
            PermissionLevel.REQUIRES_APPROVAL
        )
        if is_approved:
            approval_tracker.record_approval(
                'execute_python',
                {'code': f'print({i})'},
                PermissionLevel.REQUIRES_APPROVAL,
                auto_approved=True
            )

    # 6th should not auto-approve (exceeds session limit)
    is_approved = approval_tracker.is_approved(
        'execute_python',
        {'code': 'print(6)'},
        PermissionLevel.REQUIRES_APPROVAL
    )
    assert not is_approved, "Should not auto-approve after session limit"
    print("   ✅ Auto-approval patterns work with session limits")

    # Test 5: Operation hashing (same operation auto-approves)
    print("\n[6/6] Testing operation hashing and re-approval...")

    # Manually approve an operation
    approval_tracker.record_approval(
        'execute_python',
        {'code': 'print("hello")'},
        PermissionLevel.REQUIRES_APPROVAL,
        auto_approved=False
    )

    # Same operation should now auto-approve
    is_approved = approval_tracker.is_approved(
        'execute_python',
        {'code': 'print("hello")'},
        PermissionLevel.REQUIRES_APPROVAL
    )
    assert is_approved, "Previously approved operation should auto-approve"
    print("   ✅ Previously approved operations auto-approve correctly")

    # Get statistics
    stats = approval_tracker.get_approval_stats()
    print("\n" + "="*70)
    print("APPROVAL STATISTICS:")
    print("="*70)
    print(f"  Total approvals: {stats['total_approvals']}")
    print(f"  Unique operations: {stats['unique_operations']}")
    print(f"  Auto-approval patterns: {stats['auto_approval_patterns']}")
    print(f"  Session usage: {stats['session_usage']}")

    print("\n" + "="*70)
    print("✅ ALL APPROVAL TESTS PASSED!")
    print("="*70)
    print("\nApproval System Status:")
    print("  ✅ Permission levels enforced (SAFE, REQUIRES_APPROVAL, CRITICAL)")
    print("  ✅ CRITICAL operations NEVER auto-approve")
    print("  ✅ SAFE operations always auto-approve")
    print("  ✅ Auto-approval patterns work with conditions")
    print("  ✅ Session limits prevent excessive auto-approvals")
    print("  ✅ Previously approved operations remembered")
    print("\nSecurity Features:")
    print("  🔒 write_file - CRITICAL (always requires approval)")
    print("  🔒 run_command - CRITICAL (always requires approval)")
    print("  ⚡ execute_python - Requires approval (can be auto-approved)")
    print("  ✅ read_file, list_directory, search_codebase, analyze_code - SAFE")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
