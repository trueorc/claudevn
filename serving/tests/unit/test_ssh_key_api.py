"""Tests for SSH key management API endpoints.

Unit tests for:
- POST /git/ssh-keys — Generate SSH key pair
- GET /git/ssh-keys — List SSH keys
- GET /git/ssh-keys/{key_id} — Get specific key
- DELETE /git/ssh-keys/{key_id} — Delete key pair
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import app
import api.git as git_module

API_BASE = "/api/v1/git"


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_ssh_service():
    """Mock SSHKeyService by replacing the module-level getter."""
    mock_service = MagicMock()
    with patch.object(git_module, "get_ssh_key_service", return_value=mock_service):
        yield mock_service


class TestGenerateSSHKey:
    """Test POST /git/ssh-keys endpoint."""

    def test_generate_key_success(self, client, mock_ssh_service):
        """Test successful key generation."""
        mock_ssh_service.generate_key.return_value = {
            "key_id": "sshk_abc123def456",
            "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... claudevn-sshk_abc123def456",
            "fingerprint": "256 SHA256:abc123 claudevn-sshk_abc123def456 (ED25519)",
            "description": "My deploy key",
        }

        response = client.post(
            f"{API_BASE}/ssh-keys",
            json={"description": "My deploy key"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["key_id"] == "sshk_abc123def456"
        assert data["public_key"].startswith("ssh-ed25519 ")
        assert data["description"] == "My deploy key"
        assert "fingerprint" in data

    def test_generate_key_no_description(self, client, mock_ssh_service):
        """Test key generation with empty description."""
        mock_ssh_service.generate_key.return_value = {
            "key_id": "sshk_000000000000",
            "public_key": "ssh-ed25519 AAAA...",
            "fingerprint": "256 SHA256:xyz",
            "description": "",
        }

        response = client.post(f"{API_BASE}/ssh-keys", json={})

        assert response.status_code == 201
        mock_ssh_service.generate_key.assert_called_once_with(description="")

    def test_generate_key_ssh_keygen_missing(self, client, mock_ssh_service):
        """Test error when ssh-keygen is not found."""
        mock_ssh_service.generate_key.side_effect = FileNotFoundError("ssh-keygen")

        response = client.post(f"{API_BASE}/ssh-keys", json={})

        assert response.status_code == 500
        assert "ssh-keygen" in response.json()["detail"]

    def test_generate_key_internal_error(self, client, mock_ssh_service):
        """Test error during key generation."""
        mock_ssh_service.generate_key.side_effect = RuntimeError("disk full")

        response = client.post(f"{API_BASE}/ssh-keys", json={})

        assert response.status_code == 500


class TestListSSHKeys:
    """Test GET /git/ssh-keys endpoint."""

    def test_list_keys_success(self, client, mock_ssh_service):
        """Test listing keys returns metadata."""
        mock_ssh_service.list_keys.return_value = [
            {
                "key_id": "sshk_aaa111",
                "description": "GitHub key",
                "fingerprint": "256 SHA256:aaa",
                "created_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "key_id": "sshk_bbb222",
                "description": "GitLab key",
                "fingerprint": "256 SHA256:bbb",
                "created_at": "2024-01-02T00:00:00+00:00",
            },
        ]

        response = client.get(f"{API_BASE}/ssh-keys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["key_id"] == "sshk_aaa111"
        assert data[1]["description"] == "GitLab key"

    def test_list_keys_empty(self, client, mock_ssh_service):
        """Test listing when no keys exist."""
        mock_ssh_service.list_keys.return_value = []

        response = client.get(f"{API_BASE}/ssh-keys")

        assert response.status_code == 200
        assert response.json() == []


class TestGetSSHKey:
    """Test GET /git/ssh-keys/{key_id} endpoint."""

    def test_get_key_success(self, client, mock_ssh_service):
        """Test retrieving a specific key's public key."""
        mock_ssh_service.get_key.return_value = {
            "key_id": "sshk_abc123def456",
            "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...",
            "fingerprint": "256 SHA256:abc123",
            "description": "My key",
            "created_at": "2024-01-01T00:00:00+00:00",
        }

        response = client.get(f"{API_BASE}/ssh-keys/sshk_abc123def456")

        assert response.status_code == 200
        data = response.json()
        assert data["key_id"] == "sshk_abc123def456"
        assert data["public_key"].startswith("ssh-ed25519 ")

    def test_get_key_not_found(self, client, mock_ssh_service):
        """Test 404 for nonexistent key."""
        mock_ssh_service.get_key.return_value = None

        response = client.get(f"{API_BASE}/ssh-keys/sshk_nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDeleteSSHKey:
    """Test DELETE /git/ssh-keys/{key_id} endpoint."""

    def test_delete_key_success(self, client, mock_ssh_service):
        """Test successful key deletion."""
        mock_ssh_service.key_exists.return_value = True
        mock_ssh_service.delete_key.return_value = True

        response = client.delete(f"{API_BASE}/ssh-keys/sshk_abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["key_id"] == "sshk_abc123"
        assert data["deleted"] is True

    def test_delete_key_not_found(self, client, mock_ssh_service):
        """Test 404 for deleting nonexistent key."""
        mock_ssh_service.key_exists.return_value = False

        response = client.delete(f"{API_BASE}/ssh-keys/sshk_nonexistent")

        assert response.status_code == 404
