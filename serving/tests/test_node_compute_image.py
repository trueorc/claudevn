"""Tests for Node.js compute image configuration and capability detection."""

import os
import subprocess
import pytest
from pathlib import Path


# Resolve repo root relative to this test file
REPO_ROOT = Path(__file__).resolve().parents[2]
NODE_IMAGE_DIR = REPO_ROOT / "compute" / "images" / "node"
DETECT_SCRIPT = NODE_IMAGE_DIR / "detect-capabilities.sh"
ENTRYPOINT = REPO_ROOT / "compute" / "entrypoint.sh"


class TestNodeImageFiles:
    def test_dockerfile_exists(self):
        assert (NODE_IMAGE_DIR / "Dockerfile").is_file()

    def test_detect_capabilities_exists(self):
        assert DETECT_SCRIPT.is_file()

    def test_detect_capabilities_is_executable(self):
        assert os.access(DETECT_SCRIPT, os.X_OK)


class TestDockerfileContent:
    @pytest.fixture(autouse=True)
    def _load_dockerfile(self):
        self.content = (NODE_IMAGE_DIR / "Dockerfile").read_text()

    def test_installs_nodejs(self):
        assert "nodesource" in self.content or "nodejs" in self.content

    def test_has_node22_reference(self):
        assert "setup_22.x" in self.content

    def test_sets_compute_capabilities(self):
        assert "COMPUTE_CAPABILITIES" in self.content

    def test_includes_javascript_capability(self):
        assert "javascript" in self.content

    def test_copies_detect_capabilities_script(self):
        assert "detect-capabilities.sh" in self.content

    def test_sets_managed_env_defaults(self):
        assert "COMPUTE_REGISTER_ON_STARTUP=true" in self.content
        assert "COMPUTE_AUTH_MODE=serving" in self.content


class TestDetectCapabilitiesScript:
    def test_script_has_shebang(self):
        content = DETECT_SCRIPT.read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_detects_node_section(self):
        content = DETECT_SCRIPT.read_text()
        assert "runtime:node" in content

    def test_detects_python_section(self):
        content = DETECT_SCRIPT.read_text()
        assert "runtime:python" in content

    def test_merges_with_existing_capabilities(self):
        content = DETECT_SCRIPT.read_text()
        assert "EXISTING" in content or "COMPUTE_CAPABILITIES" in content


class TestEntrypointIntegration:
    def test_sources_detect_capabilities(self):
        content = ENTRYPOINT.read_text()
        assert "detect-capabilities.sh" in content
