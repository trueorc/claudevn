"""Unit tests for compute configuration (#79).

Tests URL security warnings for insecure HTTP serving URLs.
"""

import logging

from config import _warn_insecure_url, _LOCAL_HOSTS


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
