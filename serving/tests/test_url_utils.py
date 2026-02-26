"""Unit tests for HTTPS ↔ SSH URL conversion utilities."""

import pytest

from git.url_utils import (
    ensure_ssh_url,
    https_to_ssh,
    is_https_url,
    is_ssh_url,
    ssh_to_https,
)


class TestHttpsToSsh:
    """Test HTTPS → SSH conversion."""

    def test_github(self):
        assert https_to_ssh("https://github.com/org/repo.git") == "git@github.com:org/repo.git"

    def test_github_no_dotgit(self):
        assert https_to_ssh("https://github.com/org/repo") == "git@github.com:org/repo.git"

    def test_gitlab(self):
        assert https_to_ssh("https://gitlab.com/org/repo.git") == "git@gitlab.com:org/repo.git"

    def test_bitbucket(self):
        assert https_to_ssh("https://bitbucket.org/org/repo.git") == "git@bitbucket.org:org/repo.git"

    def test_nested_path(self):
        assert https_to_ssh("https://github.com/org/sub/repo.git") == "git@github.com:org/sub/repo.git"

    def test_http_scheme(self):
        assert https_to_ssh("http://github.com/org/repo.git") == "git@github.com:org/repo.git"

    def test_not_https(self):
        assert https_to_ssh("git@github.com:org/repo.git") is None

    def test_invalid(self):
        assert https_to_ssh("not-a-url") is None


class TestSshToHttps:
    """Test SSH → HTTPS conversion."""

    def test_github(self):
        assert ssh_to_https("git@github.com:org/repo.git") == "https://github.com/org/repo.git"

    def test_github_no_dotgit(self):
        assert ssh_to_https("git@github.com:org/repo") == "https://github.com/org/repo.git"

    def test_gitlab(self):
        assert ssh_to_https("git@gitlab.com:org/repo.git") == "https://gitlab.com/org/repo.git"

    def test_not_ssh(self):
        assert ssh_to_https("https://github.com/org/repo.git") is None

    def test_invalid(self):
        assert ssh_to_https("not-a-url") is None


class TestPredicates:
    """Test URL type detection."""

    def test_is_ssh_url(self):
        assert is_ssh_url("git@github.com:org/repo.git") is True
        assert is_ssh_url("https://github.com/org/repo.git") is False

    def test_is_https_url(self):
        assert is_https_url("https://github.com/org/repo.git") is True
        assert is_https_url("http://github.com/org/repo.git") is True
        assert is_https_url("git@github.com:org/repo.git") is False


class TestEnsureSshUrl:
    """Test ensure_ssh_url helper."""

    def test_already_ssh(self):
        assert ensure_ssh_url("git@github.com:org/repo.git") == "git@github.com:org/repo.git"

    def test_converts_https(self):
        assert ensure_ssh_url("https://github.com/org/repo.git") == "git@github.com:org/repo.git"

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            ensure_ssh_url("not-a-url")


class TestRoundTrip:
    """Test bidirectional conversion preserves URLs."""

    @pytest.mark.parametrize("https_url,ssh_url", [
        ("https://github.com/org/repo.git", "git@github.com:org/repo.git"),
        ("https://gitlab.com/group/project.git", "git@gitlab.com:group/project.git"),
        ("https://bitbucket.org/team/repo.git", "git@bitbucket.org:team/repo.git"),
    ])
    def test_round_trip(self, https_url, ssh_url):
        assert https_to_ssh(https_url) == ssh_url
        assert ssh_to_https(ssh_url) == https_url
