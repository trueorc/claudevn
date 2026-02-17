#!/usr/bin/env python3
"""Manual test: branch verification inside serving container.

Run:  docker exec claudevn-serving python3 /app/tests/manual/test_branch_verification.py

Exercises the full chain:
  1. Filesystem-based project name resolution
  2. get_branches() with dubious-ownership bypass
  3. get_branch_head() with dubious-ownership bypass
  4. Full branch verification as used at work completion time
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/app")


def header(msg): print(f"\n{'='*60}\n  {msg}\n{'='*60}")
def ok(msg):     print(f"  ✅ {msg}")
def fail(msg):   print(f"  ❌ {msg}")
def info(msg):   print(f"     {msg}")


# ── Find a project with feature branches ────────────────────────────────

def find_test_project():
    repos_dir = Path("/app/data/repos")
    for repo_path in sorted(repos_dir.glob("*.git")):
        full_name = repo_path.name.replace(".git", "")
        project_id = full_name.split("_repo_")[0] if "_repo_" in full_name else full_name

        # Read branches directly from refs (no git command needed)
        refs_dir = repo_path / "refs" / "heads"
        if not refs_dir.exists():
            continue
        branches = []
        for p in refs_dir.rglob("*"):
            if p.is_file():
                branches.append(str(p.relative_to(refs_dir)))
        non_main = [b for b in branches if b != "main"]
        if non_main:
            return project_id, full_name, non_main[0]

    print("  ❌ No repos with feature branches found")
    sys.exit(1)


# ── Tests ───────────────────────────────────────────────────────────────

def test_resolve_git_project_name(project_id, expected_full_name):
    header("Test 1: _resolve_git_project_name (filesystem scan)")
    from api.compute import _resolve_git_project_name

    resolved = _resolve_git_project_name(project_id)
    info(f"_resolve_git_project_name('{project_id}') = '{resolved}'")

    if resolved == expected_full_name:
        ok("Resolved correctly via filesystem scan")
        return True
    else:
        fail(f"Expected '{expected_full_name}', got '{resolved}'")
        return False


def test_dubious_ownership_raw(full_repo_name, branch):
    header("Test 2: Raw git fails with dubious ownership")

    repo_path = Path(f"/app/data/repos/{full_repo_name}.git")
    owner = subprocess.run(["stat", "-c", "%U:%G", str(repo_path)],
                           capture_output=True, text=True).stdout.strip()
    whoami = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    info(f"Repo owner: {owner}, running as: {whoami}")

    # Raw git with NO safe.directory
    raw = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "--list", "--format=%(refname:short)"],
        capture_output=True, text=True,
        env={"HOME": "/tmp", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_SYSTEM": "/dev/null", "PATH": "/usr/local/bin:/usr/bin:/bin"}
    )
    info(f"Raw git exit code: {raw.returncode}")
    if raw.returncode != 0:
        info(f"stderr: {raw.stderr.strip()[:120]}")
        ok("Raw git correctly fails (dubious ownership)")
        return True
    else:
        info(f"stdout: {raw.stdout.strip()}")
        info("Raw git succeeded — safe.directory might be set globally already")
        return True  # Not a failure, just means safe.directory is already set


def test_get_branches_with_bypass(full_repo_name, branch):
    header("Test 3: RepoManager.get_branches() with ownership bypass")
    from git.repo_manager import RepoManager
    rm = RepoManager()

    branches = rm.get_branches(full_repo_name)
    info(f"get_branches('{full_repo_name}') = {branches}")

    if branch in branches:
        ok(f"Branch '{branch}' found")
        return True
    else:
        fail(f"Branch '{branch}' NOT found in {branches}")
        return False


def test_get_branch_head_with_bypass(full_repo_name, branch):
    header("Test 4: RepoManager.get_branch_head() with ownership bypass")
    from git.repo_manager import RepoManager
    rm = RepoManager()

    head = rm.get_branch_head(full_repo_name, branch)
    info(f"get_branch_head('{full_repo_name}', '{branch}') = {head}")

    if head:
        ok(f"Branch head: {head[:12]}...")
        return True
    else:
        fail("Branch head NOT found")
        return False


def test_git_cmd_bypass(full_repo_name, branch):
    header("Test 5: _git_cmd() directly (dubious ownership bypass)")
    from git.repo_manager import RepoManager
    rm = RepoManager()
    repo_path = rm._repo_path(full_repo_name)

    result = rm._git_cmd(repo_path, "branch", "--list", "--format=%(refname:short)")
    info(f"exit code: {result.returncode}")
    info(f"stdout: {result.stdout.strip()}")
    if result.stderr:
        info(f"stderr: {result.stderr.strip()[:120]}")

    branches = [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
    if result.returncode == 0 and branch in branches:
        ok("_git_cmd bypasses dubious ownership")
        return True
    else:
        fail("_git_cmd failed or branch missing")
        return False


def test_full_verification_chain(project_id, full_repo_name, branch):
    header("Test 6: Full branch verification chain")
    from api.compute import _resolve_git_project_name
    from git.repo_manager import RepoManager
    rm = RepoManager()

    # Step 1: resolve name
    resolved = _resolve_git_project_name(project_id)
    info(f"Step 1 - resolve: {project_id} -> {resolved}")

    # Step 2: get branches
    branches = rm.get_branches(resolved)
    info(f"Step 2 - branches: {branches}")

    # Step 3: check
    if branch in branches:
        ok(f"PASS: Branch '{branch}' verified — work would be marked COMPLETED")
        return True
    else:
        fail(f"FAIL: Branch '{branch}' not found — work would be marked FAILED")
        return False


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("\n" + " Branch Verification Diagnostic ".center(60, "="))

    project_id, full_name, branch = find_test_project()
    info(f"project_id:     {project_id}")
    info(f"full_repo_name: {full_name}")
    info(f"branch:         {branch}")

    results = {}
    results["resolve"] = test_resolve_git_project_name(project_id, full_name)
    results["dubious_raw"] = test_dubious_ownership_raw(full_name, branch)
    results["get_branches"] = test_get_branches_with_bypass(full_name, branch)
    results["get_branch_head"] = test_get_branch_head_with_bypass(full_name, branch)
    results["git_cmd_bypass"] = test_git_cmd_bypass(full_name, branch)
    results["full_chain"] = test_full_verification_chain(project_id, full_name, branch)

    header("SUMMARY")
    all_pass = True
    for name, passed in results.items():
        print(f"  {'✅' if passed else '❌'}  {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("  All tests passed — branch verification should work in production.")
    else:
        print("  Failures detected — see details above.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
