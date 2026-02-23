"""Unit tests for SSH key management service."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from git.ssh_key_service import SSHKeyService, SSH_KEY_ID_PREFIX


class TestSSHKeyServiceInit:
    """Test SSHKeyService initialization."""

    def test_init_with_explicit_path(self, tmp_path):
        """Test service with explicit keys path."""
        service = SSHKeyService(ssh_keys_path=str(tmp_path))
        assert service._keys_path == tmp_path

    def test_init_with_config_default(self):
        """Test service falls back to config."""
        with patch("git.ssh_key_service.get_config") as mock_config:
            mock_config.return_value.git.ssh_keys_path = "/tmp/test_keys"
            service = SSHKeyService()
            assert service._keys_path == Path("/tmp/test_keys")


class TestSSHKeyGeneration:
    """Test SSH key generation."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create service with temp directory."""
        return SSHKeyService(ssh_keys_path=str(tmp_path))

    @pytest.fixture
    def keys_dir(self, tmp_path):
        return tmp_path

    def test_generate_key_creates_files(self, service, keys_dir):
        """Test that key generation creates private, public, and metadata files."""
        result = service.generate_key(description="test key")

        key_id = result["key_id"]
        assert key_id.startswith(SSH_KEY_ID_PREFIX)

        private_path = keys_dir / f"{key_id}_key"
        public_path = keys_dir / f"{key_id}_key.pub"
        meta_path = keys_dir / f"{key_id}_key.json"

        assert private_path.exists()
        assert public_path.exists()
        assert meta_path.exists()

    def test_generate_key_returns_public_key(self, service):
        """Test that result includes public key text."""
        result = service.generate_key()

        assert "public_key" in result
        assert result["public_key"].startswith("ssh-ed25519 ")

    def test_generate_key_returns_fingerprint(self, service):
        """Test that result includes a fingerprint."""
        result = service.generate_key()

        assert "fingerprint" in result
        assert len(result["fingerprint"]) > 0

    def test_generate_key_preserves_description(self, service):
        """Test that description is stored and returned."""
        result = service.generate_key(description="My GitHub deploy key")

        assert result["description"] == "My GitHub deploy key"

    def test_generate_key_private_permissions(self, service, keys_dir):
        """Test that private key has 0600 permissions."""
        result = service.generate_key()
        key_id = result["key_id"]

        private_path = keys_dir / f"{key_id}_key"
        mode = oct(private_path.stat().st_mode & 0o777)
        assert mode == "0o600"

    def test_generate_key_public_permissions(self, service, keys_dir):
        """Test that public key has 0644 permissions."""
        result = service.generate_key()
        key_id = result["key_id"]

        public_path = keys_dir / f"{key_id}_key.pub"
        mode = oct(public_path.stat().st_mode & 0o777)
        assert mode == "0o644"

    def test_generate_key_metadata_sidecar(self, service, keys_dir):
        """Test that metadata JSON sidecar is written correctly."""
        result = service.generate_key(description="test")
        key_id = result["key_id"]

        meta_path = keys_dir / f"{key_id}_key.json"
        metadata = json.loads(meta_path.read_text())

        assert metadata["key_id"] == key_id
        assert metadata["description"] == "test"
        assert "created_at" in metadata

    def test_generate_key_unique_ids(self, service):
        """Test that each key gets a unique ID."""
        result1 = service.generate_key()
        result2 = service.generate_key()

        assert result1["key_id"] != result2["key_id"]

    def test_generate_key_creates_directory(self, tmp_path):
        """Test that keys directory is created if it doesn't exist."""
        nested = tmp_path / "nested" / "keys"
        service = SSHKeyService(ssh_keys_path=str(nested))

        result = service.generate_key()
        assert nested.exists()
        assert (nested / f"{result['key_id']}_key").exists()


class TestSSHKeyListing:
    """Test SSH key listing."""

    @pytest.fixture
    def service(self, tmp_path):
        return SSHKeyService(ssh_keys_path=str(tmp_path))

    def test_list_keys_empty(self, service):
        """Test listing when no keys exist."""
        assert service.list_keys() == []

    def test_list_keys_returns_metadata(self, service):
        """Test listing returns key metadata."""
        service.generate_key(description="key one")
        service.generate_key(description="key two")

        keys = service.list_keys()
        assert len(keys) == 2

        descriptions = {k["description"] for k in keys}
        assert "key one" in descriptions
        assert "key two" in descriptions

    def test_list_keys_no_private_material(self, service):
        """Test that list does not include private key content."""
        service.generate_key()
        keys = service.list_keys()

        for key in keys:
            assert "private_key" not in key
            assert "public_key" not in key

    def test_list_keys_nonexistent_directory(self, tmp_path):
        """Test listing when directory doesn't exist yet."""
        service = SSHKeyService(ssh_keys_path=str(tmp_path / "nonexistent"))
        assert service.list_keys() == []


class TestSSHKeyRetrieval:
    """Test SSH key retrieval."""

    @pytest.fixture
    def service(self, tmp_path):
        return SSHKeyService(ssh_keys_path=str(tmp_path))

    def test_get_key_returns_public_key(self, service):
        """Test getting a key returns public key text."""
        generated = service.generate_key(description="test")
        key_id = generated["key_id"]

        result = service.get_key(key_id)
        assert result is not None
        assert result["public_key"].startswith("ssh-ed25519 ")
        assert result["key_id"] == key_id
        assert result["description"] == "test"

    def test_get_key_not_found(self, service):
        """Test getting a nonexistent key returns None."""
        assert service.get_key("sshk_nonexistent") is None

    def test_get_key_fingerprint_matches(self, service):
        """Test that fingerprint matches between generate and get."""
        generated = service.generate_key()
        retrieved = service.get_key(generated["key_id"])

        assert retrieved["fingerprint"] == generated["fingerprint"]


class TestSSHKeyDeletion:
    """Test SSH key deletion."""

    @pytest.fixture
    def service(self, tmp_path):
        return SSHKeyService(ssh_keys_path=str(tmp_path))

    @pytest.fixture
    def keys_dir(self, tmp_path):
        return tmp_path

    def test_delete_key_removes_files(self, service, keys_dir):
        """Test that deletion removes all key files."""
        result = service.generate_key()
        key_id = result["key_id"]

        assert service.delete_key(key_id) is True

        assert not (keys_dir / f"{key_id}_key").exists()
        assert not (keys_dir / f"{key_id}_key.pub").exists()
        assert not (keys_dir / f"{key_id}_key.json").exists()

    def test_delete_key_not_found(self, service):
        """Test deleting a nonexistent key returns False."""
        assert service.delete_key("sshk_nonexistent") is False

    def test_delete_key_then_get_returns_none(self, service):
        """Test that a deleted key cannot be retrieved."""
        result = service.generate_key()
        service.delete_key(result["key_id"])

        assert service.get_key(result["key_id"]) is None

    def test_delete_key_then_list_excludes(self, service):
        """Test that a deleted key is excluded from listing."""
        r1 = service.generate_key(description="keep")
        r2 = service.generate_key(description="delete me")

        service.delete_key(r2["key_id"])

        keys = service.list_keys()
        assert len(keys) == 1
        assert keys[0]["key_id"] == r1["key_id"]


class TestSSHKeyExists:
    """Test key existence check."""

    @pytest.fixture
    def service(self, tmp_path):
        return SSHKeyService(ssh_keys_path=str(tmp_path))

    def test_key_exists_true(self, service):
        result = service.generate_key()
        assert service.key_exists(result["key_id"]) is True

    def test_key_exists_false(self, service):
        assert service.key_exists("sshk_nonexistent") is False

    def test_key_exists_after_delete(self, service):
        result = service.generate_key()
        service.delete_key(result["key_id"])
        assert service.key_exists(result["key_id"]) is False
