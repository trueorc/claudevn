"""Manual test: validates the complete git flow used by the v2.0 engine.

Run inside the serving container:
    python3 -m tests.manual.test_git_flow

Tests:
1. Create a project with an internal repo
2. Clone the repo to a temp workspace
3. Create a feature branch (matching pre-receive hook format)
4. Create a file, commit, push
5. Create a PR
6. Approve the PR
7. Merge the PR
8. Verify the merge commit is on main
9. Create a second branch from main (chain continuity)
10. Verify the second branch has the first branch's work

This MUST all pass before execution can work.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        logger.info(f"  ✓ {name}")
    else:
        FAIL += 1
        logger.error(f"  ✗ {name} — {detail}")


def run_git(args, cwd, env=None):
    """Run a git command and return (returncode, stdout, stderr)."""
    safe_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, env=safe_env
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


async def main():
    global PASS, FAIL

    project_id = f"proj_test_{uuid.uuid4().hex[:8]}"
    compute_id = "test-compute-001"
    work_dir = tempfile.mkdtemp(prefix="git_flow_test_")

    logger.info(f"=== Git Flow Test ===")
    logger.info(f"Project: {project_id}")
    logger.info(f"Workdir: {work_dir}")
    logger.info("")

    try:
        # ============================================================
        # 1. Create project with internal repo
        # ============================================================
        logger.info("Step 1: Create project with internal repo")
        from services.project_service import get_project_service
        from models.project import ProjectCreateRequest, PendingRepoRequest

        ps = get_project_service()
        project = await ps.create_project(ProjectCreateRequest(
            name=f"git-flow-test-{uuid.uuid4().hex[:6]}",
            description="Automated git flow test",
            repos=[PendingRepoRequest(mode="create", name="test-repo", default_branch="main")],
        ))
        project_id = project.project_id
        check("Project created", project is not None, f"project_id={project_id}")
        check("Has repos", len(project.repos) > 0, f"repos={project.repos}")

        if not project.repos:
            logger.error("FATAL: No repo created. Cannot continue.")
            return

        repo = project.repos[0]
        repo_name = f"{project.project_id}_{repo.repo_id}"
        logger.info(f"  Repo: {repo_name}, URL: {repo.url}")

        # ============================================================
        # 2. Clone the repo
        # ============================================================
        logger.info("\nStep 2: Clone repo")
        clone_dir = os.path.join(work_dir, "repo")

        # Set up git token for HTTP auth
        git_token = ""
        try:
            from git.git_token_service import get_git_token_service
            token_svc = get_git_token_service()
            if token_svc:
                git_token = await token_svc.create_compute_token(compute_id)
            else:
                logger.warning("  Git token service not initialized — push will fail")
        except Exception as e:
            logger.warning(f"  Could not create git token: {e}")

        clone_env = {}
        if git_token:
            askpass = os.path.join(work_dir, "askpass.sh")
            with open(askpass, "w") as f:
                f.write(f"#!/bin/sh\necho '{git_token}'\n")
            os.chmod(askpass, 0o700)
            clone_env["GIT_ASKPASS"] = askpass
            clone_env["GIT_TERMINAL_PROMPT"] = "0"

        # Use URL-embedded credentials for git auth
        if git_token:
            internal_url = f"http://git:{git_token}@localhost:8002/git/{repo_name}.git"
        else:
            internal_url = f"http://localhost:8002/git/{repo_name}.git"
        clone_env = {"GIT_TERMINAL_PROMPT": "0"}

        rc, out, err = run_git(["clone", internal_url, clone_dir], cwd=work_dir, env=clone_env)
        check("Clone succeeded", rc == 0, f"stderr={err}")

        if rc != 0:
            logger.error("FATAL: Clone failed. Cannot continue.")
            return

        # Set git identity and ensure remote has credentials
        run_git(["config", "user.email", "test@claudevn.local"], cwd=clone_dir)
        run_git(["config", "user.name", "Git Flow Test"], cwd=clone_dir)
        # Re-set remote URL with embedded credentials (git strips them after clone)
        if git_token:
            auth_url = f"http://git:{git_token}@localhost:8002/git/{repo_name}.git"
            run_git(["remote", "set-url", "origin", auth_url], cwd=clone_dir)

        # ============================================================
        # 3. Create feature branch
        # ============================================================
        logger.info("\nStep 3: Create feature branch")
        branch_name = f"f/work_testunit001/{compute_id}"
        rc, _, err = run_git(["checkout", "-b", branch_name], cwd=clone_dir)
        check("Branch created", rc == 0, f"stderr={err}")

        # ============================================================
        # 4. Create file, commit, push
        # ============================================================
        logger.info("\nStep 4: Create file, commit, push")
        test_file = os.path.join(clone_dir, "hello.txt")
        with open(test_file, "w") as f:
            f.write("Hello from git flow test\n")

        run_git(["add", "hello.txt"], cwd=clone_dir)
        rc, _, err = run_git(["commit", "-m", "Add hello.txt"], cwd=clone_dir)
        check("Commit succeeded", rc == 0, f"stderr={err}")

        # Debug
        rc_dbg, remote_url, _ = run_git(["remote", "get-url", "origin"], cwd=clone_dir)
        logger.info(f"  Remote URL: {remote_url[:60]}...")
        logger.info(f"  Token: {git_token[:20]}...")

        rc, out, err = run_git(
            ["push", "--verbose", "origin", branch_name],
            cwd=clone_dir, env=clone_env
        )
        if rc != 0:
            logger.error(f"  Push stdout: {out}")
            logger.error(f"  Push stderr: {err}")
        check("Push succeeded", rc == 0, f"stderr={err}")

        # ============================================================
        # 5. Create PR
        # ============================================================
        logger.info("\nStep 5: Create PR")
        from git.pr_service import PRService
        pr_service = PRService()

        try:
            pr = await pr_service.create_pr(
                project=repo_name,
                branch=branch_name,
                compute_id=compute_id,
                task_id="wu-testunit001",
                title="Test PR",
                description="Automated git flow test",
            )
            check("PR created", pr is not None, f"pr={pr}")
        except Exception as e:
            check("PR created", False, str(e))
            logger.error("FATAL: PR creation failed. Cannot continue.")
            return

        # ============================================================
        # 6. Approve PR
        # ============================================================
        logger.info("\nStep 6: Approve PR")
        try:
            approved = await pr_service.approve(repo_name, branch_name, reviewed_by="test")
            check("PR approved", approved is not None)
        except Exception as e:
            check("PR approved", False, str(e))

        # ============================================================
        # 7. Merge PR
        # ============================================================
        logger.info("\nStep 7: Merge PR")
        try:
            result = await pr_service.merge(project=repo_name, branch=branch_name)
            check("Merge succeeded", result.get("success", False), f"result={result}")
        except Exception as e:
            check("Merge succeeded", False, str(e))

        # ============================================================
        # 8. Verify merge on main
        # ============================================================
        logger.info("\nStep 8: Verify merge on main")
        run_git(["fetch", "origin"], cwd=clone_dir, env=clone_env)
        run_git(["checkout", "main"], cwd=clone_dir)
        run_git(["pull", "origin", "main"], cwd=clone_dir, env=clone_env)

        file_exists = os.path.exists(os.path.join(clone_dir, "hello.txt"))
        check("File exists on main after merge", file_exists)

        rc, log_out, _ = run_git(["log", "--oneline", "-3"], cwd=clone_dir)
        logger.info(f"  Git log: {log_out}")

        # ============================================================
        # 9. Create second branch from main (chain continuity)
        # ============================================================
        logger.info("\nStep 9: Second branch from main (chain continuity)")
        branch2 = f"f/work_testunit002/{compute_id}"
        rc, _, err = run_git(["checkout", "-b", branch2], cwd=clone_dir)
        check("Second branch created", rc == 0, f"stderr={err}")

        # ============================================================
        # 10. Verify second branch has first branch's work
        # ============================================================
        logger.info("\nStep 10: Verify chain continuity")
        file_exists_on_branch2 = os.path.exists(os.path.join(clone_dir, "hello.txt"))
        check("First branch's file visible on second branch", file_exists_on_branch2)

    finally:
        # Cleanup
        shutil.rmtree(work_dir, ignore_errors=True)

        # Clean up test project
        try:
            ps = get_project_service()
            await ps.delete_project(project_id)
        except Exception:
            pass

    logger.info(f"\n{'='*40}")
    logger.info(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        logger.error("GIT FLOW TEST FAILED")
        sys.exit(1)
    else:
        logger.info("GIT FLOW TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
