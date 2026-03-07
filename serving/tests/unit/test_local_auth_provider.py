"""Tests for the local file-based authentication provider."""

import pytest
import tempfile
import os

from services.local_auth_provider import LocalAuthProvider


@pytest.fixture
def users_file(tmp_path):
    """Create a temporary users file."""
    f = tmp_path / "users.local"
    f.write_text(
        "# Comment line\n"
        "matt:password\n"
        "jason:secret123\n"
        "mom:hello\n"
        "\n"
        "# Another comment\n"
    )
    return str(f)


@pytest.fixture
def provider(users_file):
    """Create a local auth provider with test users."""
    return LocalAuthProvider(users_file)


class TestLocalAuthProvider:
    def test_loads_users(self, provider):
        assert provider.list_usernames() == ["matt", "jason", "mom"]

    def test_verify_correct_password(self, provider):
        assert provider.verify("matt", "password") is True

    def test_verify_wrong_password(self, provider):
        assert provider.verify("matt", "wrong") is False

    def test_verify_unknown_user(self, provider):
        assert provider.verify("unknown", "password") is False

    def test_verify_each_user(self, provider):
        assert provider.verify("matt", "password") is True
        assert provider.verify("jason", "secret123") is True
        assert provider.verify("mom", "hello") is True

    def test_skips_comments_and_blanks(self, provider):
        usernames = provider.list_usernames()
        assert len(usernames) == 3

    def test_missing_file(self, tmp_path):
        provider = LocalAuthProvider(str(tmp_path / "nonexistent"))
        assert provider.list_usernames() == []
        assert provider.verify("anyone", "pass") is False

    def test_malformed_line_skipped(self, tmp_path):
        f = tmp_path / "bad.local"
        f.write_text("good:password\nno-colon-here\n:empty-user\n")
        provider = LocalAuthProvider(str(f))
        assert provider.list_usernames() == ["good"]

    def test_password_with_colon(self, tmp_path):
        f = tmp_path / "colon.local"
        f.write_text("user:pass:word:with:colons\n")
        provider = LocalAuthProvider(str(f))
        assert provider.verify("user", "pass:word:with:colons") is True

    def test_reload(self, tmp_path):
        f = tmp_path / "reload.local"
        f.write_text("alice:pass1\n")
        provider = LocalAuthProvider(str(f))
        assert provider.list_usernames() == ["alice"]

        f.write_text("alice:pass1\nbob:pass2\n")
        provider.reload()
        assert provider.list_usernames() == ["alice", "bob"]
