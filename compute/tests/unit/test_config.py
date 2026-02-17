"""Unit tests for compute configuration module."""

import os
from unittest.mock import patch

import pytest

from config import ComputeConfig, load_config


class TestComputeConfig:
    """Tests for ComputeConfig model."""

    def test_default_values(self):
        """Test ComputeConfig has expected default values."""
        config = ComputeConfig()

        assert config.host == "0.0.0.0"
        assert config.port == 8003
        assert config.serving_url == "http://localhost:8002"
        assert config.sse_reconnect_delay == 5
        assert config.sse_max_reconnect_delay == 60

    def test_custom_sse_settings(self):
        """Test ComputeConfig with custom SSE settings."""
        config = ComputeConfig(
            sse_reconnect_delay=10,
            sse_max_reconnect_delay=120
        )

        assert config.sse_reconnect_delay == 10
        assert config.sse_max_reconnect_delay == 120


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_defaults(self):
        """Test load_config returns defaults when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()

            assert config.sse_reconnect_delay == 5
            assert config.sse_max_reconnect_delay == 60

    def test_load_config_sse_reconnect_delay_from_env(self):
        """Test load_config reads CLAUDEVN_SSE_RECONNECT_DELAY."""
        with patch.dict(os.environ, {"CLAUDEVN_SSE_RECONNECT_DELAY": "15"}, clear=True):
            config = load_config()

            assert config.sse_reconnect_delay == 15

    def test_load_config_sse_max_reconnect_delay_from_env(self):
        """Test load_config reads CLAUDEVN_SSE_MAX_RECONNECT_DELAY."""
        with patch.dict(os.environ, {"CLAUDEVN_SSE_MAX_RECONNECT_DELAY": "300"}, clear=True):
            config = load_config()

            assert config.sse_max_reconnect_delay == 300

    def test_load_config_both_sse_settings_from_env(self):
        """Test load_config reads both SSE settings from environment."""
        with patch.dict(os.environ, {
            "CLAUDEVN_SSE_RECONNECT_DELAY": "2",
            "CLAUDEVN_SSE_MAX_RECONNECT_DELAY": "30"
        }, clear=True):
            config = load_config()

            assert config.sse_reconnect_delay == 2
            assert config.sse_max_reconnect_delay == 30
