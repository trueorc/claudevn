"""SSH server manager for Git access.

Manages an SSH daemon that allows compute instances to push/pull
from Git repositories using key-based authentication.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from config import get_config, GitConfig

logger = logging.getLogger(__name__)


class SSHServer:
    """Manages SSH daemon for Git repository access.

    Uses system OpenSSH (sshd) with a custom configuration to:
    - Authenticate via SSHKeyManager's authorized_keys
    - Restrict to git-shell only
    - Run on a non-privileged port (default 2222)
    """

    def __init__(self, config: Optional[GitConfig] = None):
        """Initialize SSH server manager.

        Args:
            config: Git configuration (defaults to global config)
        """
        self._config = config or get_config().git
        self._process: Optional[asyncio.subprocess.Process] = None
        self._config_dir: Optional[Path] = None
        self._running = False

        # Configuration paths
        self._ssh_keys_path = Path(self._config.ssh_keys_path)
        self._repos_path = Path(self._config.repos_path)
        self._authorized_keys = self._ssh_keys_path / "authorized_keys"

        # SSH server settings
        self._port = int(os.getenv("SSH_GIT_PORT", "2222"))
        self._host_key_path = os.getenv(
            "SSH_HOST_KEY_PATH",
            str(self._ssh_keys_path / "ssh_host_ed25519_key")
        )

    async def start(self) -> bool:
        """Start the SSH daemon.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("SSH server already running")
            return True

        # Ensure prerequisites
        if not self._ensure_prerequisites():
            return False

        # Generate host key if needed
        if not self._ensure_host_key():
            return False

        # Create sshd config
        config_file = self._create_sshd_config()
        if not config_file:
            return False

        # Start sshd
        try:
            # Use sshd in non-daemon mode (-D) so we can manage it as a subprocess
            sshd_path = shutil.which("sshd")
            if not sshd_path:
                logger.error("sshd not found in PATH")
                return False

            logger.info(f"Starting SSH server on port {self._port}")

            self._process = await asyncio.create_subprocess_exec(
                sshd_path,
                "-D",  # Don't daemonize
                "-e",  # Log to stderr
                "-f", str(config_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Give it a moment to start and check if it's still running
            await asyncio.sleep(0.5)

            if self._process.returncode is not None:
                # Process already exited - read error
                _, stderr = await self._process.communicate()
                logger.error(f"SSH server failed to start: {stderr.decode()}")
                return False

            self._running = True
            logger.info(f"SSH server started on port {self._port}")

            # Start log reader task
            asyncio.create_task(self._read_logs())

            return True

        except Exception as e:
            logger.error(f"Failed to start SSH server: {e}")
            return False

    async def stop(self) -> bool:
        """Stop the SSH daemon.

        Returns:
            True if stopped successfully
        """
        if not self._running or not self._process:
            logger.debug("SSH server not running")
            return True

        try:
            logger.info("Stopping SSH server")

            # Terminate gracefully
            self._process.terminate()

            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Force kill if needed
                logger.warning("SSH server did not stop gracefully, killing")
                self._process.kill()
                await self._process.wait()

            self._running = False
            self._process = None

            # Cleanup config directory
            if self._config_dir and self._config_dir.exists():
                shutil.rmtree(self._config_dir, ignore_errors=True)
                self._config_dir = None

            logger.info("SSH server stopped")
            return True

        except Exception as e:
            logger.error(f"Failed to stop SSH server: {e}")
            return False

    def is_running(self) -> bool:
        """Check if SSH server is running.

        Returns:
            True if running
        """
        if not self._process:
            return False
        return self._process.returncode is None

    def get_status(self) -> dict:
        """Get SSH server status.

        Returns:
            Status dictionary
        """
        return {
            "running": self.is_running(),
            "port": self._port,
            "host_key": self._host_key_path,
            "authorized_keys": str(self._authorized_keys),
            "repos_path": str(self._repos_path),
            "pid": self._process.pid if self._process else None
        }

    def get_clone_url(self, project: str) -> str:
        """Get SSH clone URL for a project.

        Args:
            project: Project name

        Returns:
            SSH URL for cloning
        """
        git_user = self._config.git_user
        host = os.getenv("SSH_GIT_HOST", "localhost")
        return f"ssh://{git_user}@{host}:{self._port}{self._repos_path}/{project}.git"

    def _ensure_prerequisites(self) -> bool:
        """Ensure all prerequisites are met.

        Returns:
            True if all prerequisites are available
        """
        # Check for sshd
        if not shutil.which("sshd"):
            logger.error("sshd not found - install OpenSSH server")
            return False

        # Check for git-shell
        git_shell = shutil.which("git-shell")
        if not git_shell:
            logger.error("git-shell not found - install Git")
            return False

        # Ensure the git user exists — sshd rejects connections for
        # non-existent users before even checking authorized_keys.
        self._ensure_git_user(git_shell)

        # Ensure directories exist. ssh_keys needs 755 so the sshd privsep
        # child (uid 101) can traverse it to read authorized_keys.
        self._ssh_keys_path.mkdir(parents=True, exist_ok=True)
        self._ssh_keys_path.chmod(0o755)
        self._repos_path.mkdir(parents=True, exist_ok=True)

        # Ensure authorized_keys exists (even if empty).
        # Permissions: 644 — public keys are not secrets, and the sshd
        # privsep child (uid 101) must be able to read this file.
        if not self._authorized_keys.exists():
            self._authorized_keys.write_text("# ClaudeVN authorized keys\n")
            self._authorized_keys.chmod(0o644)

        return True

    def _ensure_git_user(self, git_shell_path: str) -> None:
        """Ensure the git user exists on the system.

        SSH authentication requires the connecting user (typically 'git')
        to exist in /etc/passwd. Without this, sshd immediately rejects
        the connection with "Permission denied (publickey)".

        Args:
            git_shell_path: Path to git-shell binary
        """
        import pwd

        git_user = self._config.git_user
        try:
            pwd.getpwnam(git_user)
            logger.debug(f"Git user '{git_user}' already exists")
        except KeyError:
            logger.info(f"Creating git user '{git_user}' for SSH access")
            try:
                subprocess.run(
                    [
                        "useradd",
                        "-m",
                        "-d", f"/home/{git_user}",
                        "-s", git_shell_path,
                        git_user
                    ],
                    check=True,
                    capture_output=True,
                    text=True
                )
                # Unlock account for SSH key auth (OpenSSH rejects locked accounts)
                subprocess.run(
                    ["usermod", "-p", "*", git_user],
                    check=True,
                    capture_output=True,
                    text=True
                )
                logger.info(f"Git user '{git_user}' created successfully")
            except subprocess.CalledProcessError as e:
                logger.warning(
                    f"Failed to create git user '{git_user}': {e.stderr}. "
                    "SSH Git access may not work."
                )
            except FileNotFoundError:
                logger.warning(
                    "useradd not found — cannot create git user. "
                    "Ensure the git user exists in the container image."
                )

    def _ensure_host_key(self) -> bool:
        """Ensure SSH host key exists, generate if needed.

        Returns:
            True if host key is available
        """
        host_key = Path(self._host_key_path)

        if host_key.exists():
            return True

        logger.info(f"Generating SSH host key: {host_key}")

        try:
            # Ensure parent directory exists
            host_key.parent.mkdir(parents=True, exist_ok=True)

            # Generate ed25519 host key
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-t", "ed25519",
                    "-f", str(host_key),
                    "-N", "",  # No passphrase
                    "-C", "claudevn-git-server"
                ],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"Failed to generate host key: {result.stderr}")
                return False

            # Set permissions
            host_key.chmod(0o600)
            Path(f"{host_key}.pub").chmod(0o644)

            logger.info("SSH host key generated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to generate host key: {e}")
            return False

    def _create_sshd_config(self) -> Optional[Path]:
        """Create sshd configuration file.

        Returns:
            Path to config file or None on failure
        """
        try:
            # Create temp directory for config
            self._config_dir = Path(tempfile.mkdtemp(prefix="claudevn-sshd-"))
            config_file = self._config_dir / "sshd_config"

            # PID file location
            pid_file = self._config_dir / "sshd.pid"

            # Get git-shell path
            git_shell = shutil.which("git-shell")

            config_content = f"""# ClaudeVN SSH Git Server Configuration
# Auto-generated - do not edit

# Network
Port {self._port}
ListenAddress 0.0.0.0
Protocol 2

# Host keys
HostKey {self._host_key_path}

# Authentication
AuthorizedKeysFile {self._authorized_keys}
PasswordAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitRootLogin no

# Restrict to git-shell
# Note: git-shell is already set as the user's login shell in _ensure_git_user()
# It will automatically process SSH_ORIGINAL_COMMAND when invoked as a login shell.
# ForceCommand is not needed and was causing command execution errors.
AllowAgentForwarding no
AllowTcpForwarding no
X11Forwarding no
PermitTTY no

# Logging
LogLevel INFO
SyslogFacility AUTH

# Misc
PrintMotd no
PrintLastLog no
UseDNS no
PidFile {pid_file}

# Accept new keys (for initial connections)
StrictModes no
"""

            config_file.write_text(config_content)
            config_file.chmod(0o600)

            logger.debug(f"Created sshd config: {config_file}")
            return config_file

        except Exception as e:
            logger.error(f"Failed to create sshd config: {e}")
            return None

    async def _read_logs(self) -> None:
        """Read and log SSH server output."""
        if not self._process or not self._process.stderr:
            return

        try:
            while self._running:
                line = await self._process.stderr.readline()
                if not line:
                    break
                log_line = line.decode().strip()
                if log_line:
                    logger.debug(f"[sshd] {log_line}")
        except Exception:
            pass  # Process may have ended


# Global SSH server instance
_ssh_server: Optional[SSHServer] = None


def get_ssh_server() -> Optional[SSHServer]:
    """Get the global SSH server instance.

    Returns:
        SSHServer instance or None
    """
    return _ssh_server


def set_ssh_server(server: SSHServer) -> None:
    """Set the global SSH server instance.

    Args:
        server: SSHServer instance
    """
    global _ssh_server
    _ssh_server = server


async def start_ssh_server() -> Optional[SSHServer]:
    """Start the SSH server.

    Returns:
        SSHServer instance or None on failure
    """
    global _ssh_server

    if _ssh_server and _ssh_server.is_running():
        return _ssh_server

    server = SSHServer()
    if await server.start():
        _ssh_server = server
        return server

    return None


async def stop_ssh_server() -> None:
    """Stop the SSH server."""
    global _ssh_server

    if _ssh_server:
        await _ssh_server.stop()
        _ssh_server = None
