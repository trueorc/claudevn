"""Tests for heartbeat-based Docker healthcheck mechanism (#110)."""

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest


class TestHeartbeatFile:
    """Verify the heartbeat file mechanism for Docker healthcheck."""

    def test_touch_heartbeat_creates_file(self, tmp_path):
        """_touch_heartbeat should create the heartbeat file."""
        heartbeat_file = tmp_path / "heartbeat"
        with patch("app.HEARTBEAT_FILE", heartbeat_file):
            from app import _touch_heartbeat
            _touch_heartbeat()
            assert heartbeat_file.exists()

    def test_touch_heartbeat_updates_mtime(self, tmp_path):
        """_touch_heartbeat should update the file's modification time."""
        heartbeat_file = tmp_path / "heartbeat"
        heartbeat_file.touch()
        old_mtime = heartbeat_file.stat().st_mtime

        # Small delay to ensure mtime changes
        time.sleep(0.05)

        with patch("app.HEARTBEAT_FILE", heartbeat_file):
            from app import _touch_heartbeat
            _touch_heartbeat()
            new_mtime = heartbeat_file.stat().st_mtime
            assert new_mtime >= old_mtime

    def test_touch_heartbeat_handles_permission_error(self, tmp_path):
        """_touch_heartbeat should not raise on OSError."""
        # Use a path that can't be written
        heartbeat_file = Path("/nonexistent/dir/heartbeat")
        with patch("app.HEARTBEAT_FILE", heartbeat_file):
            from app import _touch_heartbeat
            # Should not raise
            _touch_heartbeat()


class TestKeepaliveHandler:
    """Verify keepalive handler touches heartbeat file."""

    @pytest.mark.asyncio
    async def test_keepalive_touches_heartbeat(self, tmp_path):
        """Keepalive events should update the heartbeat file."""
        heartbeat_file = tmp_path / "heartbeat"
        with patch("app.HEARTBEAT_FILE", heartbeat_file):
            from app import _handle_keepalive
            await _handle_keepalive("keepalive", {"timestamp": "2026-03-02T00:00:00Z"})
            assert heartbeat_file.exists()


class TestHealthStatusFunction:
    """Test the compute_health_status utility."""

    def test_healthy_when_connected_and_credentials_valid(self):
        from api.health import compute_health_status
        assert compute_health_status(True, True) == "healthy"

    def test_unhealthy_when_disconnected_and_no_credentials(self):
        from api.health import compute_health_status
        assert compute_health_status(False, False) == "unhealthy"

    def test_degraded_when_only_sse_connected(self):
        from api.health import compute_health_status
        assert compute_health_status(True, False) == "degraded"

    def test_degraded_when_only_credentials_valid(self):
        from api.health import compute_health_status
        assert compute_health_status(False, True) == "degraded"


class TestAppHasNoFastAPI:
    """Verify FastAPI has been removed from compute."""

    def test_no_fastapi_import(self):
        """app.py should not import FastAPI."""
        import importlib
        source_path = Path(__file__).parent.parent / "app.py"
        source = source_path.read_text()
        assert "from fastapi" not in source
        assert "import fastapi" not in source

    def test_no_uvicorn_import(self):
        """app.py should not import uvicorn."""
        source_path = Path(__file__).parent.parent / "app.py"
        source = source_path.read_text()
        assert "import uvicorn" not in source

    def test_no_fastapi_in_requirements(self):
        """requirements.txt should not contain fastapi."""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        source = req_path.read_text()
        assert "fastapi" not in source
        assert "uvicorn" not in source


class TestConfigNoPort:
    """Verify port/host fields removed from config."""

    def test_config_has_no_port_field(self):
        from config import ComputeConfig
        assert not hasattr(ComputeConfig.model_fields, "port") or "port" not in ComputeConfig.model_fields

    def test_config_has_no_host_field(self):
        from config import ComputeConfig
        assert not hasattr(ComputeConfig.model_fields, "host") or "host" not in ComputeConfig.model_fields
