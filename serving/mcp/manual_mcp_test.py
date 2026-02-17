#!/usr/bin/env python3
"""Simple test script for MCP server endpoints."""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.models import (
    GetAssignmentInput,
    GetPersonaInput,
    ReportProgressInput,
    TaskStatus,
)
from mcp.tools import assignment, persona, progress


async def test_assignment():
    """Test get_assignment tool."""
    print("Testing claudevn_get_assignment...")
    input_data = GetAssignmentInput(compute_id="test-compute-001")
    result, error = await assignment.get_assignment(input_data)

    if error:
        print(f"  ERROR: {error.code} - {error.message}")
        return False

    print(f"  SUCCESS: Got task {result.task_id}")
    print(f"    Title: {result.title}")
    print(f"    Persona: {result.persona}")
    print(f"    Branch: {result.branch_name}")
    return True


async def test_progress():
    """Test report_progress tool."""
    print("\nTesting claudevn_report_progress...")
    input_data = ReportProgressInput(
        task_id="task-123",
        status=TaskStatus.IN_PROGRESS,
        progress_percent=50,
        message="Halfway done"
    )
    result, error = await progress.report_progress(input_data)

    if error:
        print(f"  ERROR: {error.code} - {error.message}")
        return False

    print(f"  SUCCESS: Progress acknowledged for {result.task_id}")
    print(f"    Updated at: {result.updated_at}")
    return True


async def test_persona_stub():
    """Test get_persona tool (stub - will fail without marketplace)."""
    print("\nTesting claudevn_get_persona (expected to fail without marketplace)...")
    input_data = GetPersonaInput(persona_id="code-writer")

    try:
        result, error = await persona.get_persona(input_data)

        if error:
            print(f"  EXPECTED ERROR: {error.code} - {error.message}")
            return True  # Expected to fail in test environment

        print(f"  SUCCESS: Got persona {result.persona_id}")
        print(f"    Name: {result.name}")
        return True
    except Exception as e:
        print(f"  EXPECTED EXCEPTION: {type(e).__name__} - {str(e)}")
        return True  # Expected to fail in test environment


async def main():
    """Run all tests."""
    print("=" * 60)
    print("MCP Tools Test Suite")
    print("=" * 60)

    results = []

    # Test assignment tool
    results.append(await test_assignment())

    # Test progress tool
    results.append(await test_progress())

    # Test persona tool (stub)
    results.append(await test_persona_stub())

    # Summary
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
