"""Tests for pre-receive hook branch naming and protection logic.

Unit tests for the hook logic:
- Branch naming regex validation
- Main/master push protection
- Compute isolation enforcement
"""

import subprocess
import os
from pathlib import Path

# Path to the hook script (serving/git/hooks/pre-receive)
HOOK_PATH = Path(__file__).parent.parent.parent / "git" / "hooks" / "pre-receive"

# Updated regex matching the hook: {type}/{identifier}/{compute-id}
BRANCH_REGEX = r"^[fbrdt]/(issue|work)_[a-z0-9]+/compute-[a-z0-9-]+$"


def test_branch_regex_valid_branches():
    """Test that valid branch names pass the regex."""
    valid_branches = [
        "f/issue_ae655ba830a9/compute-001",
        "b/issue_abc123/compute-003",
        "r/work_def456789012/compute-002",
        "d/issue_789abc/compute-001",
        "t/issue_test12345678/compute-a",
        "f/work_a1b2c3d4e5f6/compute-1",
        "b/issue_0123456789ab/compute-abc",
        "f/issue_deadbeef1234/compute-long-id-01",
    ]

    for branch in valid_branches:
        result = subprocess.run(
            ["bash", "-c", f'[[ "{branch}" =~ {BRANCH_REGEX} ]]'],
            capture_output=True
        )
        assert result.returncode == 0, f"Branch '{branch}' should be valid"


def test_branch_regex_invalid_branches():
    """Test that invalid branch names are rejected by the regex."""
    invalid_branches = [
        # Wrong type prefix
        "feat/issue_abc123/compute-001",
        "feature/issue_abc123/compute-001",
        "fix/issue_abc123/compute-001",
        "x/issue_abc123/compute-001",

        # Wrong identifier format (must start with issue_ or work_)
        "f/task_abc123/compute-001",
        "f/implement-auth/compute-001",
        "f/issue-100/compute-001",  # old format with dash
        "f/abc123/compute-001",

        # Wrong compute ID format
        "f/issue_abc123/compute-",
        "f/issue_abc123/worker-001",
        "f/issue_abc123/compute_001",  # underscore instead of dash

        # Missing parts
        "f/issue_abc123",
        "f/compute-001",
        "issue_abc123/compute-001",

        # Old work/ prefix format (the bug this issue fixes)
        "work/work_abc123/compute-001",

        # Special branches (should use separate logic)
        "main",
        "master",
        "develop",
    ]

    for branch in invalid_branches:
        result = subprocess.run(
            ["bash", "-c", f'[[ "{branch}" =~ {BRANCH_REGEX} ]]'],
            capture_output=True
        )
        assert result.returncode != 0, f"Branch '{branch}' should be invalid"


def test_compute_id_extraction():
    """Test that compute ID can be extracted correctly from branch name."""
    test_cases = [
        ("f/issue_abc123/compute-001", "compute-001"),
        ("b/issue_def456/compute-003", "compute-003"),
        ("r/work_aaa111/compute-a", "compute-a"),
        ("d/issue_bbb222/compute-long-id-01", "compute-long-id-01"),
    ]

    for branch, expected in test_cases:
        result = subprocess.run(
            ["bash", "-c", f"echo '{branch}' | grep -oP 'compute-[a-z0-9-]+$'"],
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() == expected, f"Expected {expected} from {branch}"


def test_compute_isolation_same_id_allowed():
    """Test that a compute instance can push to its own branch."""
    branch = "f/issue_abc123/compute-001"
    compute_id = "compute-001"

    # Simulates the check in the hook
    result = subprocess.run(
        ["bash", "-c", f'''
            branch="{branch}"
            compute_id=$(echo "$branch" | grep -oP 'compute-[a-z0-9-]+$')
            GIT_PUSH_COMPUTE_ID="{compute_id}"
            if [ -n "$GIT_PUSH_COMPUTE_ID" ] && [ "$compute_id" != "$GIT_PUSH_COMPUTE_ID" ]; then
                exit 1
            fi
            exit 0
        '''],
        capture_output=True
    )
    assert result.returncode == 0, "Same compute ID should be allowed"


def test_compute_isolation_different_id_rejected():
    """Test that a compute instance cannot push to another's branch."""
    branch = "f/issue_abc123/compute-001"
    pushing_compute = "compute-002"

    result = subprocess.run(
        ["bash", "-c", f'''
            branch="{branch}"
            compute_id=$(echo "$branch" | grep -oP 'compute-[a-z0-9-]+$')
            GIT_PUSH_COMPUTE_ID="{pushing_compute}"
            if [ -n "$GIT_PUSH_COMPUTE_ID" ] && [ "$compute_id" != "$GIT_PUSH_COMPUTE_ID" ]; then
                exit 1
            fi
            exit 0
        '''],
        capture_output=True
    )
    assert result.returncode == 1, "Different compute ID should be rejected"


def test_compute_isolation_no_env_var_allowed():
    """Test that pushes are allowed when GIT_PUSH_COMPUTE_ID is not set (local dev)."""
    branch = "f/issue_abc123/compute-001"

    result = subprocess.run(
        ["bash", "-c", f'''
            branch="{branch}"
            compute_id=$(echo "$branch" | grep -oP 'compute-[a-z0-9-]+$')
            GIT_PUSH_COMPUTE_ID=""
            if [ -n "$GIT_PUSH_COMPUTE_ID" ] && [ "$compute_id" != "$GIT_PUSH_COMPUTE_ID" ]; then
                exit 1
            fi
            exit 0
        '''],
        capture_output=True
    )
    assert result.returncode == 0, "Local dev (no env var) should be allowed"


def test_main_protection_blocks_main():
    """Test that pushes to main are blocked."""
    result = subprocess.run(
        ["bash", "-c", '''
            branch="main"
            CLAUDEVN_ALLOW_MAIN_PUSH="false"
            if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
                if [ "$CLAUDEVN_ALLOW_MAIN_PUSH" != "true" ]; then
                    exit 1
                fi
            fi
            exit 0
        '''],
        capture_output=True
    )
    assert result.returncode == 1, "Push to main should be blocked"


def test_main_protection_blocks_master():
    """Test that pushes to master are blocked."""
    result = subprocess.run(
        ["bash", "-c", '''
            branch="master"
            CLAUDEVN_ALLOW_MAIN_PUSH="false"
            if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
                if [ "$CLAUDEVN_ALLOW_MAIN_PUSH" != "true" ]; then
                    exit 1
                fi
            fi
            exit 0
        '''],
        capture_output=True
    )
    assert result.returncode == 1, "Push to master should be blocked"


def test_main_protection_env_override():
    """Test that CLAUDEVN_ALLOW_MAIN_PUSH=true allows main push."""
    result = subprocess.run(
        ["bash", "-c", '''
            branch="main"
            CLAUDEVN_ALLOW_MAIN_PUSH="true"
            if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
                if [ "$CLAUDEVN_ALLOW_MAIN_PUSH" != "true" ]; then
                    exit 1
                fi
            fi
            exit 0
        '''],
        capture_output=True
    )
    assert result.returncode == 0, "Main push should be allowed when env var is set"


def test_hook_file_exists():
    """Test that the pre-receive hook file exists."""
    assert HOOK_PATH.exists(), f"Hook file should exist at {HOOK_PATH}"


def test_hook_file_executable():
    """Test that the pre-receive hook has executable content (shebang)."""
    content = HOOK_PATH.read_text()
    assert content.startswith("#!/bin/bash"), "Hook should have bash shebang"


def test_hook_contains_branch_naming_regex():
    """Test that the hook uses the updated branch naming regex."""
    content = HOOK_PATH.read_text()
    assert "(issue|work)_[a-z0-9]+" in content, "Hook should validate issue_xxx/work_xxx format"
    assert "compute-[a-z0-9-]+" in content, "Hook should validate compute-{id} format"
    assert "[fbrdt]" in content, "Hook should restrict type prefixes to f, b, r, d, t"


def test_hook_contains_compute_isolation():
    """Test that the hook enforces compute isolation."""
    content = HOOK_PATH.read_text()
    assert "GIT_PUSH_COMPUTE_ID" in content, "Hook should check GIT_PUSH_COMPUTE_ID"


def test_hook_contains_main_protection():
    """Test that the hook blocks main/master pushes."""
    content = HOOK_PATH.read_text()
    assert "FORBIDDEN" in content or "not allowed" in content, "Hook should have main protection message"
    assert "Only Serving" in content, "Hook should mention that only Serving can merge to main"
