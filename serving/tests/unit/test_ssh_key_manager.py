"""Tests for SSH key manager."""

import pytest
from unittest.mock import MagicMock, patch

from git.ssh_key_manager import SSHKeyManager


@pytest.fixture
def manager():
    """Create an SSHKeyManager with a mocked config."""
    mock_config = MagicMock()
    mock_config.ssh_keys_path = "/tmp/test_ssh_keys"
    with patch("git.ssh_key_manager.get_config"):
        mgr = SSHKeyManager(config=mock_config)
    return mgr


class TestFormatAuthorizedKey:
    """Test _format_authorized_key output."""

    def test_no_command_restriction(self, manager):
        """authorized_keys line must NOT contain command= (git-shell is the login shell)."""
        key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest compute@test"
        result = manager._format_authorized_key(key, "compute-001")

        assert "command=" not in result

    def test_has_security_restrictions(self, manager):
        """authorized_keys line should still restrict port-forwarding, X11, agent, pty."""
        key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest compute@test"
        result = manager._format_authorized_key(key, "compute-001")

        assert "no-port-forwarding" in result
        assert "no-X11-forwarding" in result
        assert "no-agent-forwarding" in result
        assert "no-pty" in result

    def test_contains_key_and_compute_id(self, manager):
        """authorized_keys line should contain the key data and compute ID."""
        key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest compute@test"
        result = manager._format_authorized_key(key, "compute-001")

        assert "ssh-ed25519" in result
        assert "AAAAC3NzaC1lZDI1NTE5AAAAITest" in result
        assert "compute-001" in result

    def test_invalid_key_raises(self, manager):
        """Invalid public key format should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid public key format"):
            manager._format_authorized_key("invalid-key", "compute-001")
