"""Unit tests for compute configuration (#79, #83).

Tests URL security warnings and auth URL consistency validation.
"""

import logging
import os
from unittest.mock import patch

from config import _warn_insecure_url, _validate_auth_url_consistency, _LOCAL_HOSTS, load_config


class TestWarnInsecureUrl:
    """Tests for _warn_insecure_url."""

    def test_https_url_no_warning(self, caplog):
        """HTTPS URLs should not emit a warning."""
        with caplog.at_level(logging.WARNING):
            _warn_insecure_url("https://claudevn.example.com", "CLAUDEVN_SERVING_URL")
        assert "SECURITY" not in caplog.text

    def test_http_remote_host_warns(self, caplog):
        """HTTP to a non-local host should warn."""
        with caplog.at_level(logging.WARNING):
            _warn_insecure_url("http://192.168.1.100:8002", "CLAUDEVN_SERVING_URL")
        assert "SECURITY" in caplog.text
        assert "plain HTTP" in caplog.text

    def test_http_localhost_no_warning(self, caplog):
        """HTTP to localhost should not warn (local dev)."""
        with caplog.at_level(logging.WARNING):
            _warn_insecure_url("http://localhost:8002", "CLAUDEVN_SERVING_URL")
        assert "SECURITY" not in caplog.text

    def test_http_127_0_0_1_no_warning(self, caplog):
        """HTTP to 127.0.0.1 should not warn (local dev)."""
        with caplog.at_level(logging.WARNING):
            _warn_insecure_url("http://127.0.0.1:8002", "CLAUDEVN_SERVING_URL")
        assert "SECURITY" not in caplog.text

    def test_http_docker_serving_no_warning(self, caplog):
        """HTTP to 'serving' (docker-compose service name) should not warn."""
        with caplog.at_level(logging.WARNING):
            _warn_insecure_url("http://serving:8002", "CLAUDEVN_SERVING_URL")
        assert "SECURITY" not in caplog.text

    def test_http_public_domain_warns(self, caplog):
        """HTTP to a public domain should warn."""
        with caplog.at_level(logging.WARNING):
            _warn_insecure_url("http://claudevn.example.com", "CLAUDEVN_SERVING_AUTH_URL")
        assert "SECURITY" in caplog.text
        assert "CLAUDEVN_SERVING_AUTH_URL" in caplog.text

    def test_local_hosts_set_contents(self):
        """Verify the expected local hosts are in the allow-set."""
        assert "localhost" in _LOCAL_HOSTS
        assert "127.0.0.1" in _LOCAL_HOSTS
        assert "::1" in _LOCAL_HOSTS
        assert "serving" in _LOCAL_HOSTS


class TestValidateAuthUrlConsistency:
    """Tests for _validate_auth_url_consistency (#83)."""

    def test_matching_hosts_no_error(self, caplog):
        """No error when hosts match."""
        with caplog.at_level(logging.ERROR):
            _validate_auth_url_consistency(
                "https://claudevn.example.com",
                "https://claudevn.example.com/api/v1/auth",
            )
        assert "differs" not in caplog.text

    def test_mismatched_hosts_logs_error(self, caplog):
        """Error when auth URL points to different host than serving URL."""
        with caplog.at_level(logging.ERROR):
            _validate_auth_url_consistency(
                "https://claudevn.example.com",
                "http://serving:8002/api/v1/auth",
            )
        assert "differs" in caplog.text
        assert "serving" in caplog.text

    def test_auth_url_derived_from_serving_url(self):
        """When CLAUDEVN_SERVING_AUTH_URL is not set, auth_url is derived from serving_url."""
        env = {
            "CLAUDEVN_SERVING_URL": "https://claudevn.example.com",
        }
        # Clear CLAUDEVN_SERVING_AUTH_URL to test derivation
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
        assert config.serving_auth_url == "https://claudevn.example.com/api/v1/auth"

    def test_explicit_auth_url_preserved(self):
        """When CLAUDEVN_SERVING_AUTH_URL is set, it is used as-is."""
        env = {
            "CLAUDEVN_SERVING_URL": "https://claudevn.example.com",
            "CLAUDEVN_SERVING_AUTH_URL": "https://auth.example.com/api/v1/auth",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
        assert config.serving_auth_url == "https://auth.example.com/api/v1/auth"
