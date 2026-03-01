"""Unit tests for SERVING_PUBLIC_URL startup validation (#82).

Tests that internal Docker hostnames in SERVING_PUBLIC_URL trigger warnings
when running outside Docker.
"""

import logging
import os
from unittest.mock import patch

from app import _validate_serving_public_url


class TestValidateServingPublicUrl:
    """Tests for _validate_serving_public_url."""

    def test_no_env_var_no_warning(self, caplog):
        """No warning when SERVING_PUBLIC_URL is not set."""
        with patch.dict(os.environ, {}, clear=True), \
             caplog.at_level(logging.WARNING):
            _validate_serving_public_url()
        assert "SERVING_PUBLIC_URL" not in caplog.text

    def test_external_url_no_warning(self, caplog):
        """No warning for externally reachable URLs."""
        with patch.dict(os.environ, {"SERVING_PUBLIC_URL": "https://claudevn.example.com"}), \
             patch("app.os.path.exists", return_value=False), \
             caplog.at_level(logging.WARNING):
            _validate_serving_public_url()
        assert "SERVING_PUBLIC_URL" not in caplog.text

    def test_internal_hostname_warns_outside_docker(self, caplog):
        """Warning when 'serving' hostname is used outside Docker."""
        with patch.dict(os.environ, {"SERVING_PUBLIC_URL": "http://serving:8002"}), \
             patch("app.os.path.exists", return_value=False), \
             patch("app.os.path.isfile", return_value=False), \
             caplog.at_level(logging.WARNING):
            _validate_serving_public_url()
        assert "internal hostname" in caplog.text
        assert "serving" in caplog.text

    def test_localhost_warns_outside_docker(self, caplog):
        """Warning when 'localhost' is used outside Docker."""
        with patch.dict(os.environ, {"SERVING_PUBLIC_URL": "http://localhost:8002"}), \
             patch("app.os.path.exists", return_value=False), \
             patch("app.os.path.isfile", return_value=False), \
             caplog.at_level(logging.WARNING):
            _validate_serving_public_url()
        assert "internal hostname" in caplog.text

    def test_internal_hostname_no_warning_inside_docker(self, caplog):
        """No warning for internal hostname when running inside Docker."""
        with patch.dict(os.environ, {"SERVING_PUBLIC_URL": "http://serving:8002"}), \
             patch("app.os.path.exists", return_value=True), \
             caplog.at_level(logging.WARNING):
            _validate_serving_public_url()
        assert "internal hostname" not in caplog.text

    def test_ip_address_no_warning(self, caplog):
        """No warning for a routable IP address."""
        with patch.dict(os.environ, {"SERVING_PUBLIC_URL": "http://192.168.1.100:8002"}), \
             patch("app.os.path.exists", return_value=False), \
             caplog.at_level(logging.WARNING):
            _validate_serving_public_url()
        assert "SERVING_PUBLIC_URL" not in caplog.text
