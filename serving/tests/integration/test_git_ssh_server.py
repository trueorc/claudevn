#!/usr/bin/env python3
"""
SSH Git Server Integration Tests
================================

Tests the SSH Git server infrastructure with a live server.

Prerequisites:
- Serving service running with SSH Git server enabled (port 2222)
- Redis running for PR queue management
- Docker services: docker compose up -d

Run with:
    ./scripts/run_integration_tests.sh -s serving/tests/integration/test_git_ssh_server.py

Test Categories:
1. SSH Key Management - Register, revoke, list keys via API
2. Repository Operations - Create, list, delete repos via API
3. SSH Connection Tests - Actual SSH connections (requires SSH client)
4. Git Hook Tests - Pre-receive and post-receive hook behavior
5. Error Scenarios - Invalid keys, auth failures, permission errors
"""

import asyncio
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx
import pytest

# Test configuration
SERVING_BASE_URL = os.getenv("SERVING_URL", "http://localhost:8002")
API_PREFIX = "/api/v1"
SSH_GIT_PORT = int(os.getenv("SSH_GIT_PORT", "2222"))
SSH_GIT_HOST = os.getenv("SSH_GIT_HOST", "localhost")


def generate_test_id() -> str:
    """Generate unique test ID."""
    return f"test-{uuid.uuid4().hex[:8]}"


def generate_compute_id() -> str:
    """Generate valid compute ID format."""
    return f"compute-{uuid.uuid4().hex[:8]}"


class TestSSHKeyManagementAPI:
    """Test SSH key management via REST API."""

    @pytest.mark.asyncio
    async def test_list_ssh_keys(self):
        """Test listing registered SSH keys."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys"
            )
            assert response.status_code == 200
            keys = response.json()
            assert isinstance(keys, list)

    @pytest.mark.asyncio
    async def test_generate_ssh_key_pair(self):
        """Test generating SSH key pair for compute instance."""
        compute_id = generate_compute_id()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}/generate"
            )
            assert response.status_code == 200
            key_pair = response.json()

            # Verify response contains key pair
            assert "public_key" in key_pair
            assert "private_key" in key_pair
            assert key_pair["compute_id"] == compute_id

            # Verify key format
            assert key_pair["public_key"].startswith("ssh-ed25519 ")
            assert "-----BEGIN OPENSSH PRIVATE KEY-----" in key_pair["private_key"]

            # Cleanup - revoke the key
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}"
            )

    @pytest.mark.asyncio
    async def test_register_ssh_key(self):
        """Test registering an external SSH key."""
        compute_id = generate_compute_id()

        # Generate a valid ed25519 key locally for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test_key"
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", "", "-C", compute_id],
                check=True,
                capture_output=True
            )
            public_key = (key_path.with_suffix(".pub")).read_text().strip()

        async with httpx.AsyncClient() as client:
            # Register the key
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys",
                json={"compute_id": compute_id, "public_key": public_key}
            )
            assert response.status_code in [200, 201]

            # Verify key is listed
            list_response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys"
            )
            keys = list_response.json()
            assert compute_id in keys

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}"
            )

    @pytest.mark.asyncio
    async def test_revoke_ssh_key(self):
        """Test revoking an SSH key."""
        compute_id = generate_compute_id()

        async with httpx.AsyncClient() as client:
            # First generate and register a key
            gen_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}/generate"
            )
            assert gen_response.status_code == 200

            # Verify it's registered
            list_response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys"
            )
            assert compute_id in list_response.json()

            # Revoke the key
            revoke_response = await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}"
            )
            assert revoke_response.status_code == 200

            # Verify it's no longer listed
            list_response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys"
            )
            assert compute_id not in list_response.json()

    @pytest.mark.asyncio
    async def test_register_invalid_key_format(self):
        """Test registering an invalid SSH key format."""
        compute_id = generate_compute_id()

        async with httpx.AsyncClient() as client:
            # Try to register an invalid key
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys",
                json={"compute_id": compute_id, "public_key": "invalid-key-data"}
            )
            # Should fail validation
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key(self):
        """Test revoking a key that doesn't exist."""
        compute_id = generate_compute_id()

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}"
            )
            # Should return 404 or success (idempotent)
            assert response.status_code in [200, 404]


class TestRepositoryOperationsAPI:
    """Test Git repository operations via REST API."""

    @pytest.mark.asyncio
    async def test_list_repositories(self):
        """Test listing all repositories."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos"
            )
            assert response.status_code == 200
            repos = response.json()
            assert isinstance(repos, list)

    @pytest.mark.asyncio
    async def test_create_repository(self):
        """Test creating a new repository."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )
            assert response.status_code == 201
            repo = response.json()

            assert repo["project"] == project
            assert "ssh_url" in repo
            assert repo["hooks_installed"] is True

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )

    @pytest.mark.asyncio
    async def test_create_duplicate_repository(self):
        """Test creating a repository that already exists."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create first time
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            # Try to create again
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )
            assert response.status_code == 409  # Conflict

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )

    @pytest.mark.asyncio
    async def test_get_repository_details(self):
        """Test getting repository details."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create repository
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            # Get details
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )
            assert response.status_code == 200
            repo = response.json()

            assert repo["project"] == project
            assert "ssh_url" in repo
            assert "created_at" in repo or "path" in repo

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )

    @pytest.mark.asyncio
    async def test_get_nonexistent_repository(self):
        """Test getting a repository that doesn't exist."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/nonexistent-repo-xyz"
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_repository(self):
        """Test deleting a repository."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create repository
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            # Delete it
            response = await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )
            assert response.status_code == 200

            # Verify it's gone
            get_response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )
            assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_branches(self):
        """Test listing branches in a repository."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create repository
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            # List branches (empty repo may have no branches)
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}/branches"
            )
            assert response.status_code == 200
            branches = response.json()
            assert isinstance(branches, list)

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )


class TestGitHooksAPI:
    """Test Git hook management via REST API."""

    @pytest.mark.asyncio
    async def test_verify_hooks_installed(self):
        """Test verifying hooks are installed on repository creation."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create repository with hooks
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            # Verify hooks
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}/hooks"
            )
            assert response.status_code == 200
            hooks = response.json()

            assert hooks["hooks_installed"] is True
            assert hooks["pre_receive"]["exists"] is True
            assert hooks["pre_receive"]["executable"] is True
            assert hooks["post_receive"]["exists"] is True
            assert hooks["post_receive"]["executable"] is True

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )

    @pytest.mark.asyncio
    async def test_install_hooks_on_existing_repo(self):
        """Test installing hooks on existing repository."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create repository without hooks
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": False}
            )

            # Install hooks
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}/hooks"
            )
            assert response.status_code == 200

            # Verify hooks
            verify_response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}/hooks"
            )
            hooks = verify_response.json()
            assert hooks["hooks_installed"] is True

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )


class TestSSHConnectionIntegration:
    """Test actual SSH connections to the Git server.

    These tests require:
    - SSH Git server running on port 2222
    - Ability to create SSH keys and connect
    """

    @pytest.fixture
    async def ssh_key_pair(self):
        """Generate and register an SSH key pair for testing."""
        compute_id = generate_compute_id()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}/generate"
            )
            key_pair = response.json()
            key_pair["compute_id"] = compute_id

            yield key_pair

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}"
            )

    @pytest.fixture
    async def test_repo(self):
        """Create a test repository."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            yield project

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )

    @pytest.mark.asyncio
    async def test_ssh_connection_with_valid_key(self, ssh_key_pair, test_repo):
        """Test SSH connection succeeds with valid registered key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write private key to file
            key_path = Path(tmpdir) / "id_ed25519"
            key_path.write_text(ssh_key_pair["private_key"])
            key_path.chmod(0o600)

            # Configure SSH to use this key
            ssh_config = Path(tmpdir) / "ssh_config"
            ssh_config.write_text(f"""
Host {SSH_GIT_HOST}
    HostName {SSH_GIT_HOST}
    Port {SSH_GIT_PORT}
    User git
    IdentityFile {key_path}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
""")

            # Test SSH connection (git-info-refs is a valid Git protocol request)
            ssh_url = f"ssh://git@{SSH_GIT_HOST}:{SSH_GIT_PORT}/app/data/repos/{test_repo}.git"

            # Try git ls-remote (tests SSH auth)
            result = subprocess.run(
                [
                    "git", "ls-remote", ssh_url
                ],
                env={
                    **os.environ,
                    "GIT_SSH_COMMAND": f"ssh -F {ssh_config}"
                },
                capture_output=True,
                timeout=30
            )

            # Empty repo may return empty output but should not have auth errors
            # Connection success is indicated by exit code 0 or specific git error
            assert result.returncode in [0, 128]  # 0 = success, 128 = git error (not auth error)
            if result.returncode == 128:
                # Ensure it's not an auth error
                stderr = result.stderr.decode()
                assert "Permission denied" not in stderr
                assert "authentication" not in stderr.lower()

    @pytest.mark.asyncio
    async def test_ssh_connection_with_invalid_key(self, test_repo):
        """Test SSH connection fails with unregistered key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate an unregistered key
            key_path = Path(tmpdir) / "id_ed25519"
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", "", "-C", "unregistered"],
                check=True,
                capture_output=True
            )

            # Configure SSH
            ssh_config = Path(tmpdir) / "ssh_config"
            ssh_config.write_text(f"""
Host {SSH_GIT_HOST}
    HostName {SSH_GIT_HOST}
    Port {SSH_GIT_PORT}
    User git
    IdentityFile {key_path}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
""")

            ssh_url = f"ssh://git@{SSH_GIT_HOST}:{SSH_GIT_PORT}/app/data/repos/{test_repo}.git"

            # Try to connect - should fail
            result = subprocess.run(
                [
                    "git", "ls-remote", ssh_url
                ],
                env={
                    **os.environ,
                    "GIT_SSH_COMMAND": f"ssh -F {ssh_config}"
                },
                capture_output=True,
                timeout=30
            )

            # Should fail with permission denied
            assert result.returncode != 0
            stderr = result.stderr.decode()
            assert "Permission denied" in stderr or "publickey" in stderr.lower()


class TestGitCloneAndPushIntegration:
    """Test actual Git clone and push operations.

    These tests verify end-to-end Git workflow:
    - Clone from SSH Git server
    - Make commits
    - Push to branches
    """

    @pytest.fixture
    async def setup_compute_and_repo(self):
        """Set up compute instance with SSH key and test repository."""
        compute_id = generate_compute_id()
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Generate SSH key
            key_response = await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}/generate"
            )
            key_pair = key_response.json()

            # Create repository
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            yield {
                "compute_id": compute_id,
                "project": project,
                "private_key": key_pair["private_key"],
                "public_key": key_pair["public_key"],
                "ssh_url": f"ssh://git@{SSH_GIT_HOST}:{SSH_GIT_PORT}/app/data/repos/{project}.git"
            }

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}"
            )

    @pytest.mark.asyncio
    async def test_clone_empty_repository(self, setup_compute_and_repo):
        """Test cloning an empty repository."""
        setup = setup_compute_and_repo

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write SSH key
            key_path = Path(tmpdir) / "id_ed25519"
            key_path.write_text(setup["private_key"])
            key_path.chmod(0o600)

            ssh_config = Path(tmpdir) / "ssh_config"
            ssh_config.write_text(f"""
Host {SSH_GIT_HOST}
    HostName {SSH_GIT_HOST}
    Port {SSH_GIT_PORT}
    User git
    IdentityFile {key_path}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
""")

            clone_dir = Path(tmpdir) / "clone"

            result = subprocess.run(
                ["git", "clone", setup["ssh_url"], str(clone_dir)],
                env={
                    **os.environ,
                    "GIT_SSH_COMMAND": f"ssh -F {ssh_config}"
                },
                capture_output=True,
                timeout=60
            )

            # Clone of empty repo should succeed (with warning)
            assert result.returncode == 0 or "empty repository" in result.stderr.decode().lower()
            assert clone_dir.exists()

    @pytest.mark.asyncio
    async def test_push_to_feature_branch(self, setup_compute_and_repo):
        """Test pushing to a properly named feature branch."""
        setup = setup_compute_and_repo
        compute_id = setup["compute_id"]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup SSH
            key_path = Path(tmpdir) / "id_ed25519"
            key_path.write_text(setup["private_key"])
            key_path.chmod(0o600)

            ssh_config = Path(tmpdir) / "ssh_config"
            ssh_config.write_text(f"""
Host {SSH_GIT_HOST}
    HostName {SSH_GIT_HOST}
    Port {SSH_GIT_PORT}
    User git
    IdentityFile {key_path}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
""")

            clone_dir = Path(tmpdir) / "clone"

            # Clone
            subprocess.run(
                ["git", "clone", setup["ssh_url"], str(clone_dir)],
                env={
                    **os.environ,
                    "GIT_SSH_COMMAND": f"ssh -F {ssh_config}"
                },
                capture_output=True,
                timeout=60
            )

            # Configure git user
            subprocess.run(
                ["git", "-C", str(clone_dir), "config", "user.email", "test@test.com"],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(clone_dir), "config", "user.name", "Test User"],
                check=True,
                capture_output=True
            )

            # Create feature branch with proper naming
            branch_name = f"f/issue-123/{compute_id}"
            subprocess.run(
                ["git", "-C", str(clone_dir), "checkout", "-b", branch_name],
                check=True,
                capture_output=True
            )

            # Create a file and commit
            test_file = clone_dir / "test.txt"
            test_file.write_text("Test content")
            subprocess.run(
                ["git", "-C", str(clone_dir), "add", "."],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(clone_dir), "commit", "-m", "Test commit"],
                check=True,
                capture_output=True
            )

            # Push to feature branch
            result = subprocess.run(
                ["git", "-C", str(clone_dir), "push", "-u", "origin", branch_name],
                env={
                    **os.environ,
                    "GIT_SSH_COMMAND": f"ssh -F {ssh_config}"
                },
                capture_output=True,
                timeout=60
            )

            # Should succeed
            assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_push_to_main_blocked(self, setup_compute_and_repo):
        """Test that direct pushes to main are blocked by pre-receive hook."""
        setup = setup_compute_and_repo

        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup SSH
            key_path = Path(tmpdir) / "id_ed25519"
            key_path.write_text(setup["private_key"])
            key_path.chmod(0o600)

            ssh_config = Path(tmpdir) / "ssh_config"
            ssh_config.write_text(f"""
Host {SSH_GIT_HOST}
    HostName {SSH_GIT_HOST}
    Port {SSH_GIT_PORT}
    User git
    IdentityFile {key_path}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
""")

            clone_dir = Path(tmpdir) / "clone"

            # Clone
            subprocess.run(
                ["git", "clone", setup["ssh_url"], str(clone_dir)],
                env={
                    **os.environ,
                    "GIT_SSH_COMMAND": f"ssh -F {ssh_config}"
                },
                capture_output=True,
                timeout=60
            )

            # Configure git user
            subprocess.run(
                ["git", "-C", str(clone_dir), "config", "user.email", "test@test.com"],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(clone_dir), "config", "user.name", "Test User"],
                check=True,
                capture_output=True
            )

            # Create a file and commit on main
            test_file = clone_dir / "test.txt"
            test_file.write_text("Test content")
            subprocess.run(
                ["git", "-C", str(clone_dir), "add", "."],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(clone_dir), "commit", "-m", "Test commit"],
                check=True,
                capture_output=True
            )

            # Try to push to main - should be blocked
            result = subprocess.run(
                ["git", "-C", str(clone_dir), "push", "origin", "main"],
                env={
                    **os.environ,
                    "GIT_SSH_COMMAND": f"ssh -F {ssh_config}"
                },
                capture_output=True,
                timeout=60
            )

            # Should fail (pre-receive hook blocks direct push to main)
            assert result.returncode != 0
            stderr = result.stderr.decode()
            assert "main" in stderr.lower() or "rejected" in stderr.lower() or "denied" in stderr.lower()


class TestPRQueueIntegration:
    """Test PR queue management integration."""

    @pytest.mark.asyncio
    async def test_get_pr_queue(self):
        """Test getting PR queue for a project."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create repository
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            # Get PR queue
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/queues/{project}/prs"
            )
            assert response.status_code == 200
            queue = response.json()
            assert isinstance(queue, (list, dict))

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )

    @pytest.mark.asyncio
    async def test_get_merge_queue(self):
        """Test getting merge queue for a project."""
        project = generate_test_id()

        async with httpx.AsyncClient() as client:
            # Create repository
            await client.post(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
                json={"project": project, "install_hooks": True}
            )

            # Get merge queue
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/queues/{project}/merges"
            )
            assert response.status_code == 200
            queue = response.json()
            assert isinstance(queue, (list, dict))

            # Cleanup
            await client.delete(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}"
            )


class TestSSHServerStatus:
    """Test SSH server status and health endpoints."""

    @pytest.mark.asyncio
    async def test_git_server_status(self):
        """Test getting Git server status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_BASE_URL}{API_PREFIX}/git/status"
            )
            # May not be implemented
            assert response.status_code in [200, 404]
            if response.status_code == 200:
                status = response.json()
                assert isinstance(status, dict)

    @pytest.mark.asyncio
    async def test_ssh_port_accessible(self):
        """Test that SSH port is accessible."""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            result = sock.connect_ex((SSH_GIT_HOST, SSH_GIT_PORT))
            # 0 means port is open
            assert result == 0, f"SSH port {SSH_GIT_PORT} is not accessible"
        finally:
            sock.close()


# Run tests
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("SSH Git Server Integration Tests")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print(f"  - Serving service running at {SERVING_BASE_URL}")
    print(f"  - SSH Git server running on port {SSH_GIT_PORT}")
    print("  - Redis running for queue management")
    print()
    print("Running tests...")
    print()

    sys.exit(pytest.main([__file__, "-v", "-s"]))
