"""Unit tests for SSH key provisioning on compute connect/disconnect."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSSHKeyProvisioningOnConnect:
    """Tests for SSH key generation and delivery when compute connects."""

    @pytest.mark.asyncio
    async def test_connect_generates_and_sends_key(self):
        """Test that on_connect generates a key pair, registers it, and sends it via SSE."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()
        sse_manager.send_event = AsyncMock(return_value=True)

        mock_key_mgr = MagicMock()
        mock_key_mgr.generate_key_pair.return_value = ("PRIVATE_KEY", "PUBLIC_KEY")
        mock_key_mgr.register_key.return_value = True
        mock_key_mgr.sync_to_system.return_value = True

        with patch("git.ssh_key_manager.SSHKeyManager", return_value=mock_key_mgr):
            from git.ssh_key_manager import SSHKeyManager
            ssh_key_mgr = SSHKeyManager()

            async def _on_compute_connect(compute_id: str) -> None:
                try:
                    private_key, public_key = ssh_key_mgr.generate_key_pair(compute_id)
                    ssh_key_mgr.register_key(compute_id, public_key)
                    ssh_key_mgr.sync_to_system()
                    await sse_manager.send_event(compute_id, "ssh_key_provisioned", {
                        "private_key": private_key,
                        "compute_id": compute_id,
                    })
                except Exception:
                    pass

            sse_manager.on_connect(_on_compute_connect)

        # Simulate a compute connecting
        await sse_manager.register_connection(
            compute_id="compute-001",
            capabilities=["claude_code"],
            resources={"cpu": 4}
        )

        mock_key_mgr.generate_key_pair.assert_called_once_with("compute-001")
        mock_key_mgr.register_key.assert_called_once_with("compute-001", "PUBLIC_KEY")
        mock_key_mgr.sync_to_system.assert_called_once()
        sse_manager.send_event.assert_called_once_with(
            "compute-001",
            "ssh_key_provisioned",
            {"private_key": "PRIVATE_KEY", "compute_id": "compute-001"}
        )

    @pytest.mark.asyncio
    async def test_connect_handles_keygen_failure(self):
        """Test that keygen failure is handled gracefully without crashing."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()
        sse_manager.send_event = AsyncMock(return_value=True)

        mock_key_mgr = MagicMock()
        mock_key_mgr.generate_key_pair.side_effect = Exception("keygen failed")

        errors = []

        async def _on_compute_connect(compute_id: str) -> None:
            try:
                private_key, public_key = mock_key_mgr.generate_key_pair(compute_id)
                mock_key_mgr.register_key(compute_id, public_key)
                mock_key_mgr.sync_to_system()
                await sse_manager.send_event(compute_id, "ssh_key_provisioned", {
                    "private_key": private_key,
                    "compute_id": compute_id,
                })
            except Exception as e:
                errors.append(str(e))

        sse_manager.on_connect(_on_compute_connect)

        # Should not raise
        await sse_manager.register_connection(
            compute_id="compute-002",
            capabilities=[],
            resources={}
        )

        assert len(errors) == 1
        assert "keygen failed" in errors[0]
        sse_manager.send_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_handles_register_key_failure(self):
        """Test that register_key failure is caught without crashing."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()
        sse_manager.send_event = AsyncMock(return_value=True)

        mock_key_mgr = MagicMock()
        mock_key_mgr.generate_key_pair.return_value = ("PRIV", "PUB")
        mock_key_mgr.register_key.side_effect = ValueError("Invalid key format")

        errors = []

        async def _on_compute_connect(compute_id: str) -> None:
            try:
                private_key, public_key = mock_key_mgr.generate_key_pair(compute_id)
                mock_key_mgr.register_key(compute_id, public_key)
                mock_key_mgr.sync_to_system()
                await sse_manager.send_event(compute_id, "ssh_key_provisioned", {
                    "private_key": private_key,
                    "compute_id": compute_id,
                })
            except Exception as e:
                errors.append(str(e))

        sse_manager.on_connect(_on_compute_connect)

        await sse_manager.register_connection(
            compute_id="compute-003",
            capabilities=[],
            resources={}
        )

        assert len(errors) == 1
        assert "Invalid key format" in errors[0]
        sse_manager.send_event.assert_not_called()


class TestSSHKeyRevocationOnDisconnect:
    """Tests for SSH key revocation when compute disconnects."""

    @pytest.mark.asyncio
    async def test_disconnect_revokes_key(self):
        """Test that on_disconnect revokes the SSH key and syncs."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()

        mock_key_mgr = MagicMock()
        mock_key_mgr.revoke_key.return_value = True
        mock_key_mgr.sync_to_system.return_value = True

        async def _on_compute_disconnect(compute_id: str) -> None:
            try:
                mock_key_mgr.revoke_key(compute_id)
                mock_key_mgr.sync_to_system()
            except Exception:
                pass

        sse_manager.on_disconnect(_on_compute_disconnect)

        # Register then unregister
        await sse_manager.register_connection(
            compute_id="compute-010",
            capabilities=[],
            resources={}
        )
        await sse_manager.unregister_connection("compute-010")

        mock_key_mgr.revoke_key.assert_called_once_with("compute-010")
        mock_key_mgr.sync_to_system.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_handles_revoke_failure(self):
        """Test that revoke failure is handled gracefully."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()

        mock_key_mgr = MagicMock()
        mock_key_mgr.revoke_key.side_effect = Exception("revoke failed")

        warnings = []

        async def _on_compute_disconnect(compute_id: str) -> None:
            try:
                mock_key_mgr.revoke_key(compute_id)
                mock_key_mgr.sync_to_system()
            except Exception as e:
                warnings.append(str(e))

        sse_manager.on_disconnect(_on_compute_disconnect)

        await sse_manager.register_connection(
            compute_id="compute-011",
            capabilities=[],
            resources={}
        )

        # Should not raise
        await sse_manager.unregister_connection("compute-011")

        assert len(warnings) == 1
        assert "revoke failed" in warnings[0]

    @pytest.mark.asyncio
    async def test_disconnect_no_key_to_revoke(self):
        """Test disconnect when no key was registered (revoke returns False)."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()

        mock_key_mgr = MagicMock()
        mock_key_mgr.revoke_key.return_value = False
        mock_key_mgr.sync_to_system.return_value = True

        async def _on_compute_disconnect(compute_id: str) -> None:
            try:
                mock_key_mgr.revoke_key(compute_id)
                mock_key_mgr.sync_to_system()
            except Exception:
                pass

        sse_manager.on_disconnect(_on_compute_disconnect)

        await sse_manager.register_connection(
            compute_id="compute-012",
            capabilities=[],
            resources={}
        )
        await sse_manager.unregister_connection("compute-012")

        # Should still call both without error
        mock_key_mgr.revoke_key.assert_called_once_with("compute-012")
        mock_key_mgr.sync_to_system.assert_called_once()


class TestSSHKeyProvisioningErrors:
    """Tests for error resilience in SSH key provisioning handlers."""

    @pytest.mark.asyncio
    async def test_connect_handler_does_not_crash_sse_manager(self):
        """Test that a failing connect handler doesn't prevent connection registration."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()

        async def _failing_connect(compute_id: str) -> None:
            raise RuntimeError("Handler crash")

        sse_manager.on_connect(_failing_connect)

        # Connection should still be registered despite handler failure
        # (SSEConnectionManager catches handler exceptions)
        conn = await sse_manager.register_connection(
            compute_id="compute-020",
            capabilities=["claude_code"],
            resources={}
        )

        assert conn is not None
        assert sse_manager.get_connection("compute-020") is not None

    @pytest.mark.asyncio
    async def test_disconnect_handler_does_not_crash_sse_manager(self):
        """Test that a failing disconnect handler doesn't prevent unregistration."""
        from services.sse_connection_manager import SSEConnectionManager

        sse_manager = SSEConnectionManager()

        async def _failing_disconnect(compute_id: str) -> None:
            raise RuntimeError("Handler crash")

        sse_manager.on_disconnect(_failing_disconnect)

        await sse_manager.register_connection(
            compute_id="compute-021",
            capabilities=[],
            resources={}
        )

        # Unregistration should still succeed
        result = await sse_manager.unregister_connection("compute-021")
        assert result is True
        assert sse_manager.get_connection("compute-021") is None
