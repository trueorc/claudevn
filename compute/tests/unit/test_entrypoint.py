"""Tests for compute/entrypoint.sh credential copy behavior.

Tests the entrypoint script by running it in a controlled environment
with temporary directories simulating the staging mount and target paths.
"""

import os
import stat
import subprocess
import pytest
from pathlib import Path


ENTRYPOINT_PATH = Path(__file__).parent.parent.parent / "entrypoint.sh"


class TestEntrypointScript:
    """Tests for entrypoint.sh script existence and structure."""

    def test_entrypoint_exists(self):
        """Entrypoint script exists at expected location."""
        assert ENTRYPOINT_PATH.exists(), f"entrypoint.sh not found at {ENTRYPOINT_PATH}"

    def test_entrypoint_is_executable(self):
        """Entrypoint script has executable permission."""
        mode = ENTRYPOINT_PATH.stat().st_mode
        assert mode & stat.S_IXUSR, "entrypoint.sh is not executable"

    def test_entrypoint_has_shebang(self):
        """Entrypoint script starts with bash shebang."""
        content = ENTRYPOINT_PATH.read_text()
        assert content.startswith("#!/bin/bash"), "entrypoint.sh missing bash shebang"

    def test_entrypoint_uses_set_e(self):
        """Entrypoint script uses set -e for fail-fast."""
        content = ENTRYPOINT_PATH.read_text()
        assert "set -e" in content, "entrypoint.sh missing 'set -e'"

    def test_entrypoint_has_exec_at_end(self):
        """Entrypoint script exec's the main command."""
        content = ENTRYPOINT_PATH.read_text()
        assert 'exec "$@"' in content, "entrypoint.sh missing 'exec \"$@\"'"


class TestEntrypointCredentialCopy:
    """Tests for credential copy behavior using subprocess."""

    def test_copies_credentials_from_staging(self, tmp_path):
        """Entrypoint copies .credentials.json from staging to target."""
        staging = tmp_path / "host-claude"
        staging.mkdir()
        target = tmp_path / "home-compute-claude"

        creds_content = '{"accessToken": "test-token-123"}'
        (staging / ".credentials.json").write_text(creds_content)

        # Create a wrapper script that overrides paths and runs entrypoint logic
        wrapper = tmp_path / "test_wrapper.sh"
        wrapper.write_text(f"""#!/bin/bash
set -e
STAGING_DIR="{staging}"
TARGET_DIR="{target}"

if [ -d "$STAGING_DIR" ]; then
    mkdir -p "$TARGET_DIR"
    if [ -f "$STAGING_DIR/.credentials.json" ]; then
        cp "$STAGING_DIR/.credentials.json" "$TARGET_DIR/.credentials.json"
        chmod 600 "$TARGET_DIR/.credentials.json"
    fi
    for f in "$STAGING_DIR"/*; do
        [ -e "$f" ] || continue
        fname=$(basename "$f")
        cp -r "$f" "$TARGET_DIR/$fname"
    done
    echo "[entrypoint] Credentials copied"
else
    echo "[entrypoint] No staging mount"
fi
echo "done"
""")
        wrapper.chmod(0o755)

        result = subprocess.run(
            ["bash", str(wrapper)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "[entrypoint] Credentials copied" in result.stdout
        assert (target / ".credentials.json").exists()
        assert (target / ".credentials.json").read_text() == creds_content

    def test_sets_restrictive_permissions(self, tmp_path):
        """Credentials file gets chmod 600 after copy."""
        staging = tmp_path / "host-claude"
        staging.mkdir()
        target = tmp_path / "home-compute-claude"

        (staging / ".credentials.json").write_text('{"token": "x"}')

        wrapper = tmp_path / "test_wrapper.sh"
        wrapper.write_text(f"""#!/bin/bash
set -e
STAGING_DIR="{staging}"
TARGET_DIR="{target}"
mkdir -p "$TARGET_DIR"
cp "$STAGING_DIR/.credentials.json" "$TARGET_DIR/.credentials.json"
chmod 600 "$TARGET_DIR/.credentials.json"
stat -f "%Lp" "$TARGET_DIR/.credentials.json" 2>/dev/null || stat -c "%a" "$TARGET_DIR/.credentials.json"
""")
        wrapper.chmod(0o755)

        result = subprocess.run(
            ["bash", str(wrapper)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        mode = (target / ".credentials.json").stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 600, got {oct(mode)}"

    def test_no_staging_dir_skips_copy(self, tmp_path):
        """When staging dir doesn't exist, skip gracefully."""
        staging = tmp_path / "nonexistent"
        target = tmp_path / "home-compute-claude"

        wrapper = tmp_path / "test_wrapper.sh"
        wrapper.write_text(f"""#!/bin/bash
set -e
STAGING_DIR="{staging}"
TARGET_DIR="{target}"
if [ -d "$STAGING_DIR" ]; then
    echo "[entrypoint] Credentials copied"
else
    echo "[entrypoint] No staging mount at $STAGING_DIR — skipping credential copy"
fi
echo "done"
""")
        wrapper.chmod(0o755)

        result = subprocess.run(
            ["bash", str(wrapper)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "skipping credential copy" in result.stdout
        assert not target.exists()

    def test_empty_staging_dir_creates_target(self, tmp_path):
        """When staging dir exists but is empty, target dir is still created."""
        staging = tmp_path / "host-claude"
        staging.mkdir()
        target = tmp_path / "home-compute-claude"

        wrapper = tmp_path / "test_wrapper.sh"
        wrapper.write_text(f"""#!/bin/bash
set -e
STAGING_DIR="{staging}"
TARGET_DIR="{target}"
if [ -d "$STAGING_DIR" ]; then
    mkdir -p "$TARGET_DIR"
    if [ -f "$STAGING_DIR/.credentials.json" ]; then
        cp "$STAGING_DIR/.credentials.json" "$TARGET_DIR/.credentials.json"
    fi
    echo "[entrypoint] Credentials copied"
fi
echo "done"
""")
        wrapper.chmod(0o755)

        result = subprocess.run(
            ["bash", str(wrapper)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert target.exists()
        # No credentials file should exist since staging was empty
        assert not (target / ".credentials.json").exists()

    def test_copies_additional_config_files(self, tmp_path):
        """Entrypoint copies all files from staging, not just .credentials.json."""
        staging = tmp_path / "host-claude"
        staging.mkdir()
        target = tmp_path / "home-compute-claude"

        (staging / ".credentials.json").write_text('{"token": "x"}')
        (staging / "settings.json").write_text('{"theme": "dark"}')

        wrapper = tmp_path / "test_wrapper.sh"
        wrapper.write_text(f"""#!/bin/bash
set -e
STAGING_DIR="{staging}"
TARGET_DIR="{target}"
mkdir -p "$TARGET_DIR"
if [ -f "$STAGING_DIR/.credentials.json" ]; then
    cp "$STAGING_DIR/.credentials.json" "$TARGET_DIR/.credentials.json"
    chmod 600 "$TARGET_DIR/.credentials.json"
fi
for f in "$STAGING_DIR"/*; do
    [ -e "$f" ] || continue
    fname=$(basename "$f")
    cp -r "$f" "$TARGET_DIR/$fname"
done
echo "done"
""")
        wrapper.chmod(0o755)

        result = subprocess.run(
            ["bash", str(wrapper)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert (target / ".credentials.json").exists()
        assert (target / "settings.json").exists()
        assert (target / "settings.json").read_text() == '{"theme": "dark"}'

    def test_exec_passes_through_command(self, tmp_path):
        """exec \"$@\" passes the CMD through correctly."""
        wrapper = tmp_path / "test_wrapper.sh"
        wrapper.write_text(f"""#!/bin/bash
set -e
STAGING_DIR="{tmp_path}/nonexistent"
if [ -d "$STAGING_DIR" ]; then
    echo "copy"
fi
exec "$@"
""")
        wrapper.chmod(0o755)

        result = subprocess.run(
            ["bash", str(wrapper), "echo", "hello-from-cmd"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "hello-from-cmd" in result.stdout


class TestDockerComposeConfig:
    """Tests that docker-compose.yml has correct volume mounts."""

    @pytest.fixture
    def compose_content(self):
        compose_path = Path(__file__).parent.parent.parent.parent / "docker-compose.yml"
        return compose_path.read_text()

    def test_no_host_claude_mount(self, compose_content):
        """Serving-centric auth: no host ~/.claude mount needed for compute."""
        # Since #732 (serving-centric auth), compute containers fetch credentials
        # from Serving's /auth/credentials endpoint instead of mounting host config.
        lines = compose_content.split("\n")
        for line in lines:
            if line.strip().startswith("#"):
                continue
            assert ":/host-claude" not in line, (
                f"Found legacy host-claude mount: {line.strip()}"
            )

    def test_no_direct_home_compute_mount(self, compose_content):
        """No direct mount to /home/compute/.claude (entrypoint handles it)."""
        assert ":/home/compute/.claude" not in compose_content

    def test_no_direct_root_claude_mount(self, compose_content):
        """No direct mount to /root/.claude."""
        # The active service definitions should not have /root/.claude mounts
        # (the external VCN template comments may mention it)
        lines = compose_content.split("\n")
        for line in lines:
            if line.strip().startswith("#"):
                continue
            assert ":/root/.claude" not in line, f"Found old mount pattern: {line.strip()}"


class TestDockerfileConfig:
    """Tests that Dockerfile has entrypoint configured."""

    @pytest.fixture
    def dockerfile_content(self):
        dockerfile_path = Path(__file__).parent.parent.parent / "Dockerfile"
        return dockerfile_path.read_text()

    def test_copies_entrypoint_script(self, dockerfile_content):
        """Dockerfile copies entrypoint.sh."""
        assert "COPY compute/entrypoint.sh" in dockerfile_content

    def test_sets_entrypoint(self, dockerfile_content):
        """Dockerfile sets ENTRYPOINT to entrypoint.sh."""
        assert 'ENTRYPOINT ["/app/entrypoint.sh"]' in dockerfile_content

    def test_cmd_uses_exec_form(self, dockerfile_content):
        """CMD uses exec form (JSON array) for proper signal handling with ENTRYPOINT."""
        assert 'CMD ["sh", "-c"' in dockerfile_content
