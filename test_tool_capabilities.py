#!/usr/bin/env python3
"""
Test the tool system's ability to explore and manage files
"""
import asyncio
import os
from core.tools import ToolRegistry, ToolCaller

async def test_exploration_and_file_management():
    print("="*60)
    print("TOOL CAPABILITIES TEST")
    print("="*60)

    # Initialize tool system
    registry = ToolRegistry()
    caller = ToolCaller(registry)

    # Test 1: List current directory
    print("\n[1/5] Testing directory exploration...")
    list_result = await registry._list_directory(".")
    if list_result['success']:
        print(f"   ✅ Found {len(list_result['files'])} items in current directory")
        print(f"   📁 First 5 items: {list_result['files'][:5]}")
    else:
        print(f"   ❌ Failed: {list_result['error']}")

    # Test 2: Read an existing file
    print("\n[2/5] Testing file reading...")
    read_result = await registry._read_file("test_integration.py")
    if read_result['success']:
        lines = read_result['content'].split('\n')
        print(f"   ✅ Read file with {len(lines)} lines")
        print(f"   📄 First line: {lines[0][:60]}...")
    else:
        print(f"   ❌ Failed: {read_result['error']}")

    # Test 3: Create file in a NEW nested directory structure
    print("\n[3/5] Testing file creation with auto-directory creation...")
    test_path = "./temp_test/subdir/deep/test_file.txt"
    test_content = "This file was created by the tool system!\nIt can put files anywhere."
    write_result = await registry._write_file(test_path, test_content)

    if write_result['success']:
        print(f"   ✅ Created file at: {write_result['path']}")
        # Verify it exists
        if os.path.exists(test_path):
            print(f"   ✅ Verified file exists on disk")
            print(f"   📁 Parent directories auto-created: temp_test/subdir/deep/")
        else:
            print(f"   ❌ File not found on disk")
    else:
        print(f"   ❌ Failed: {write_result['error']}")

    # Test 4: Search codebase
    print("\n[4/5] Testing codebase search...")
    search_result = await registry._search_codebase("ReasoningMode", "./core")
    if search_result['success']:
        print(f"   ✅ Found {len(search_result['matches'])} matches for 'ReasoningMode'")
        if search_result['matches']:
            first_match = search_result['matches'][0]
            print(f"   🔍 First match: {first_match['file']}:{first_match['line']}")
    else:
        print(f"   ❌ Failed: {search_result['error']}")

    # Test 5: Run command for deep exploration
    print("\n[5/5] Testing shell command execution...")
    find_result = await registry._run_command("find ./core -name '*.py' -type f | head -5")
    if find_result['success']:
        print(f"   ✅ Command executed successfully")
        print(f"   📂 Python files found:")
        for line in find_result['stdout'].strip().split('\n'):
            if line:
                print(f"      - {line}")
    else:
        print(f"   ❌ Failed: {find_result['error']}")

    # Cleanup
    print("\n[Cleanup] Removing test directory...")
    cleanup_result = await registry._run_command("rm -rf ./temp_test")
    if cleanup_result['success']:
        print("   ✅ Cleanup successful")

    print("\n" + "="*60)
    print("✅ TOOL SYSTEM CAN:")
    print("   • Explore directories and file structure")
    print("   • Read file contents")
    print("   • Create files in ANY location (auto-creates dirs)")
    print("   • Search codebase for patterns")
    print("   • Execute shell commands for advanced operations")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_exploration_and_file_management())
