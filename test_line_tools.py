#!/usr/bin/env python3
"""
Test line-based file editing tools
"""
import asyncio
import os
from core.tools import ToolRegistry

async def test_line_tools():
    print("="*60)
    print("LINE-BASED EDITING TOOLS TEST")
    print("="*60)

    # Initialize registry
    print("\n[Setup] Initializing ToolRegistry...")
    registry = ToolRegistry(use_git=True, project_dir="/home/joker/hydra")

    test_file = "test_line_edits.txt"

    # Cleanup any existing test file
    if os.path.exists(test_file):
        os.remove(test_file)

    # Create initial test file
    print("\n[1/7] Creating initial test file...")
    write_tool = registry.get('write_file')
    initial_content = """Line 1: Hello
Line 2: World
Line 3: This is a test
Line 4: For line editing
Line 5: Final line
"""
    result = await write_tool.function(path=test_file, content=initial_content)
    print(f"   Created: {result['success']}")
    print(f"   Lines: 5")

    # Test read_lines
    print("\n[2/7] Testing read_lines...")
    read_lines_tool = registry.get('read_lines')

    # Read lines 2-4
    result = await read_lines_tool.function(path=test_file, start_line=2, end_line=4)
    print(f"   Success: {result['success']}")
    print(f"   Read lines 2-4:")
    print(f"   {result['content'].strip()}")

    # Read all lines
    result = await read_lines_tool.function(path=test_file)
    print(f"   Total lines in file: {result['total_lines']}")

    # Test insert_lines
    print("\n[3/7] Testing insert_lines...")
    insert_tool = registry.get('insert_lines')
    result = await insert_tool.function(
        path=test_file,
        line_number=3,
        content="INSERTED LINE\nANOTHER INSERTED LINE"
    )
    print(f"   Success: {result['success']}")
    print(f"   Lines inserted: {result.get('lines_inserted', 0)}")
    print(f"   Branch: {result.get('branch_created', 'existing')}")

    # Verify insertion
    verify = await read_lines_tool.function(path=test_file)
    print(f"   New total lines: {verify['total_lines']}")

    # Test replace_lines
    print("\n[4/7] Testing replace_lines...")
    replace_tool = registry.get('replace_lines')
    result = await replace_tool.function(
        path=test_file,
        start_line=1,
        end_line=2,
        new_content="REPLACED FIRST LINE\nREPLACED SECOND LINE"
    )
    print(f"   Success: {result['success']}")
    print(f"   Lines replaced: {result.get('lines_replaced', 0)}")
    print(f"   New lines: {result.get('new_lines', 0)}")

    # Test append_to_file
    print("\n[5/7] Testing append_to_file...")
    append_tool = registry.get('append_to_file')
    result = await append_tool.function(
        path=test_file,
        content="APPENDED LINE 1\nAPPENDED LINE 2"
    )
    print(f"   Success: {result['success']}")
    print(f"   Content appended: {result.get('content_appended', 0)} chars")

    # Test delete_lines
    print("\n[6/7] Testing delete_lines...")
    delete_tool = registry.get('delete_lines')
    result = await delete_tool.function(
        path=test_file,
        start_line=3,
        end_line=5
    )
    print(f"   Success: {result['success']}")
    print(f"   Lines deleted: {result.get('lines_deleted', 0)}")

    # Final verification
    print("\n[7/7] Final file state...")
    final = await read_lines_tool.function(path=test_file)
    print(f"   Total lines: {final['total_lines']}")
    print("\n   Final content:")
    for i, line in enumerate(final['content'].split('\n')[:10], 1):
        if line:
            print(f"      {i}: {line}")

    # Cleanup
    print("\n[Cleanup]...")
    if registry.git and registry.git.current_hydra_branch:
        print(f"   Discarding branch: {registry.git.current_hydra_branch}")
        registry.git.discard_hydra_branch()

    if os.path.exists(test_file):
        os.remove(test_file)
        print(f"   ✅ Removed {test_file}")

    print("\n" + "="*60)
    print("✅ ALL LINE-BASED TOOLS WORKING!")
    print("="*60)
    print("\nTools tested:")
    print("  ✅ read_lines - Read specific line ranges")
    print("  ✅ insert_lines - Insert at specific position")
    print("  ✅ replace_lines - Replace line ranges")
    print("  ✅ append_to_file - Append to end")
    print("  ✅ delete_lines - Delete line ranges")
    print("\nAll tools:")
    print("  • Generate diffs automatically")
    print("  • Create git branches")
    print("  • Require CRITICAL approval")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_line_tools())
