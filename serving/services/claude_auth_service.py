"""Claude token-based authentication service.

Manages API token storage for serving-centric authentication. Users paste
tokens obtained via `claude setup-token` into the serving UI. Tokens are
stored in Redis and served to compute instances via the /auth/credentials
API endpoint.

When a token is stored for the 'serving' component, it is also applied
to the process environment as CLAUDE_CODE_OAUTH_TOKEN so that any Claude
Code subprocesses spawned by serving inherit the credential.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional

from models.auth import AuthStatus, TokenStatus

logger = logging.getLogger(__name__)

# Default token validity: ~1 year
TOKEN_VALIDITY_DAYS = 365


class ClaudeAuthService:
    """Manages Claude API tokens for the platform.

    Stores tokens in Redis keyed by component ID. Compute containers
    fetch tokens from this service instead of mounting host ~/.claude
    volumes.
    """

    # Default Claude config directory for serving's own Claude Code
    DEFAULT_CLAUDE_CONFIG_DIR = os.getenv(
        "CLAUDE_CONFIG_DIR",
        str(Path.home() / ".claude"),
    )

    def __init__(
        self,
        redis_client=None,
        check_interval: int = 60,
        claude_config_dir: Optional[str] = None,
    ):
        self._redis = redis_client
        self._check_interval = check_interval
        self._claude_config_dir = claude_config_dir or self.DEFAULT_CLAUDE_CONFIG_DIR

        # In-memory cache of tokens: {component_id: token_data}
        self._tokens: dict[str, dict[str, Any]] = {}

        self._status = AuthStatus.NOT_CONFIGURED
        self._expires_at: Optional[str] = None
        self._error_message: Optional[str] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._broadcast_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None
        self._send_event_callback: Optional[
            Callable[[str, str, dict], Awaitable[bool]]
        ] = None

    def _redis_key(self, component_id: str) -> str:
        """Build Redis key for a token."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}auth:{component_id}"

    async def initialize(self) -> None:
        """Load tokens from Redis and start monitoring.

        If a serving token is already stored, apply it to the process
        environment so Claude Code subprocesses can use it immediately.
        """
        await self._load_from_redis()

        # Determine initial status from cached tokens
        self._update_status()

        # Apply serving token to env if present
        serving_token = self._tokens.get("serving")
        if serving_token and serving_token.get("status") == TokenStatus.ACTIVE.value:
            self._apply_token_to_env(serving_token["token"])

        # Sync existing compute tokens with registry auth_status
        await self._sync_registry_auth_status()

        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def shutdown(self) -> None:
        """Stop monitoring."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("Claude auth service shut down")

    def _update_status(self) -> None:
        """Update service status based on cached tokens."""
        active_tokens = [
            t for t in self._tokens.values()
            if t.get("status") == TokenStatus.ACTIVE.value
        ]
        if active_tokens:
            self._status = AuthStatus.AUTHENTICATED
            # Use the first active token's expiry
            self._expires_at = active_tokens[0].get("expires_at")
        elif any(t.get("status") == TokenStatus.EXPIRED.value for t in self._tokens.values()):
            self._status = AuthStatus.EXPIRED
            self._expires_at = None
        else:
            self._status = AuthStatus.NOT_CONFIGURED
            self._expires_at = None

    def get_status(self) -> dict[str, Any]:
        """Get current authentication status."""
        return {
            "status": self._status.value,
            "authenticated": self._status == AuthStatus.AUTHENTICATED,
            "expires_at": self._expires_at,
            "message": self._error_message,
        }

    async def store_token(
        self,
        token: str,
        component_id: str = "serving",
        component_type: str = "serving",
    ) -> dict[str, Any]:
        """Store a new API token.

        Args:
            token: The API token (must start with 'sk-ant-oat01-').
            component_id: Identifier for the component.
            component_type: Type of component ('compute' or 'serving').

        Returns:
            Dict with status and message.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=TOKEN_VALIDITY_DAYS)

        token_data = {
            "token": token,
            "component_type": component_type,
            "authorized_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": TokenStatus.ACTIVE.value,
        }

        self._tokens[component_id] = token_data
        await self._save_to_redis(component_id, token_data)

        self._error_message = None
        self._update_status()
        logger.info(f"Token stored for component {component_id}")

        # Apply serving token to process environment
        if component_id == "serving":
            self._apply_token_to_env(token)
            self._write_onboarding_flag()

        await self._broadcast_credentials_refresh()

        # Push token directly to compute instance via SSE
        if component_type == "compute":
            await self.push_token_to_compute(component_id)

            # Update registry auth_status to keep it synchronized with AuthManager
            from services.registry_service import get_compute_registry
            from models.compute import ComputeAuthStatus
            registry = get_compute_registry()
            if registry:
                await registry.update_auth_status(
                    component_id,
                    ComputeAuthStatus.AUTHORIZED,
                    auth_expires_at=expires_at
                )
                logger.info(f"Updated registry auth_status for {component_id} to AUTHORIZED")

        return {
            "status": AuthStatus.AUTHENTICATED.value,
            "message": "Token stored successfully",
            "authorized_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    async def get_token(self, component_id: str = "serving") -> Optional[str]:
        """Get the raw token for a component.

        Returns:
            The token string, or None if not available or expired.
        """
        token_data = self._tokens.get(component_id)
        if not token_data:
            return None

        if token_data.get("status") != TokenStatus.ACTIVE.value:
            return None

        return token_data.get("token")

    async def get_credentials(self) -> Optional[dict]:
        """Get credentials dict for compute instances.

        Returns the first active token as a credentials dict.
        """
        for component_id, data in self._tokens.items():
            if data.get("status") == TokenStatus.ACTIVE.value:
                return {"token": data["token"]}
        return None

    def get_token_info(self, component_id: str) -> Optional[dict[str, Any]]:
        """Get token metadata for a component (no raw token).

        Returns:
            Dict with status, authorized_at, expires_at, component_type, or None.
        """
        token_data = self._tokens.get(component_id)
        if not token_data:
            return None

        return {
            "component_id": component_id,
            "status": token_data.get("status", "unknown"),
            "authorized_at": token_data.get("authorized_at"),
            "expires_at": token_data.get("expires_at"),
            "component_type": token_data.get("component_type", "serving"),
        }

    def list_tokens(self) -> list[dict[str, Any]]:
        """List all token metadata (no raw tokens exposed).

        Returns:
            List of token info dicts.
        """
        items = []
        for component_id, data in self._tokens.items():
            items.append({
                "component_id": component_id,
                "status": data.get("status", "unknown"),
                "authorized_at": data.get("authorized_at"),
                "expires_at": data.get("expires_at"),
                "component_type": data.get("component_type", "serving"),
            })
        return items

    def get_system_auth_status(self) -> dict[str, Any]:
        """Get system-level auth overview.

        Returns:
            Dict with serving_authorized, compute counts, expiring_soon.
        """
        serving_authorized = False
        compute_authorized = 0
        compute_unauthorized = 0
        tokens_expiring_soon = 0

        now = datetime.now(timezone.utc)
        expiry_threshold = now + timedelta(days=30)

        for component_id, data in self._tokens.items():
            is_active = data.get("status") == TokenStatus.ACTIVE.value
            comp_type = data.get("component_type", "serving")

            if comp_type == "serving" and is_active:
                serving_authorized = True
            elif comp_type == "compute":
                if is_active:
                    compute_authorized += 1
                else:
                    compute_unauthorized += 1

            if is_active:
                try:
                    expires_at = datetime.fromisoformat(data.get("expires_at", ""))
                    if expires_at <= expiry_threshold:
                        tokens_expiring_soon += 1
                except (ValueError, TypeError):
                    pass

        return {
            "serving_authorized": serving_authorized,
            "compute_authorized": compute_authorized,
            "compute_unauthorized": compute_unauthorized,
            "tokens_expiring_soon": tokens_expiring_soon,
        }

    async def clear_credentials(self, component_id: str = "serving") -> bool:
        """Revoke and remove a stored token.

        Returns:
            True if a token was cleared, False if none existed.
        """
        if component_id not in self._tokens:
            return False

        # Get component type before deleting
        component_type = self._tokens[component_id].get("component_type", "serving")

        # Mark as revoked before removing
        self._tokens[component_id]["status"] = TokenStatus.REVOKED.value
        await self._save_to_redis(component_id, self._tokens[component_id])

        del self._tokens[component_id]
        await self._delete_from_redis(component_id)

        self._error_message = None
        self._update_status()

        # Remove serving token from environment
        if component_id == "serving":
            self._remove_token_from_env()

        # Update registry auth_status when compute token is cleared
        if component_type == "compute":
            from services.registry_service import get_compute_registry
            from models.compute import ComputeAuthStatus
            registry = get_compute_registry()
            if registry:
                await registry.update_auth_status(
                    component_id,
                    ComputeAuthStatus.UNAUTHORIZED
                )
                logger.info(f"Updated registry auth_status for {component_id} to UNAUTHORIZED")

        logger.info(f"Token cleared for component {component_id}")
        return True

    def _apply_token_to_env(self, token: str) -> None:
        """Apply a token to the process environment for Claude Code inheritance.

        Sets CLAUDE_CODE_OAUTH_TOKEN so any subprocess spawned by serving
        (e.g. goal decomposer, issue evaluator) can authenticate.
        """
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token
        logger.info("Applied serving token to process environment (CLAUDE_CODE_OAUTH_TOKEN)")

    def _remove_token_from_env(self) -> None:
        """Remove the token from the process environment."""
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        logger.info("Removed serving token from process environment")

    def _write_onboarding_flag(self) -> None:
        """Write the Claude onboarding completion flag.

        Creates the .claude directory and writes the onboarding marker
        so Claude Code skips the interactive setup flow.
        """
        try:
            config_dir = Path(self._claude_config_dir)
            config_dir.mkdir(parents=True, exist_ok=True)

            onboarding_file = config_dir / ".onboarding_complete"
            onboarding_file.write_text(
                json.dumps({
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "source": "claudevn_serving",
                })
            )
            logger.info(f"Wrote onboarding flag to {onboarding_file}")
        except Exception as e:
            logger.warning(f"Failed to write onboarding flag: {e}")

    def set_broadcast_callback(
        self, callback: Callable[[str, dict], Awaitable[None]]
    ) -> None:
        """Set the SSE broadcast callback for notifying compute instances."""
        self._broadcast_callback = callback

    def set_send_event_callback(
        self, callback: Callable[[str, str, dict], Awaitable[bool]]
    ) -> None:
        """Set the SSE send_event callback for targeted token push.

        Callback signature: (compute_id, event_type, data) -> bool
        """
        self._send_event_callback = callback

    async def push_token_to_compute(self, component_id: str) -> bool:
        """Push a stored token to a specific compute instance via SSE.

        Sends an auth_token event with the raw token to the compute.
        Used on initial token submission and on compute reconnect.

        Args:
            component_id: The compute instance to push to.

        Returns:
            True if event was sent, False otherwise.
        """
        if not self._send_event_callback:
            return False

        token_data = self._tokens.get(component_id)
        if not token_data or token_data.get("status") != TokenStatus.ACTIVE.value:
            return False

        raw_token = token_data.get("token")
        if not raw_token:
            return False

        # Mask token in logs (show only last 8 chars)
        masked = f"...{raw_token[-8:]}" if len(raw_token) > 8 else "***"

        try:
            sent = await self._send_event_callback(
                component_id,
                "auth_token",
                {
                    "token": raw_token,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            if sent:
                logger.info(f"Pushed auth_token to {component_id} (token: {masked})")
            else:
                logger.warning(f"Compute {component_id} not connected for token push")
            return sent
        except Exception as e:
            logger.error(f"Failed to push token to {component_id}: {e}")
            return False

    async def _broadcast_credentials_refresh(self) -> None:
        """Notify compute instances that credentials have been refreshed."""
        if self._broadcast_callback:
            try:
                await self._broadcast_callback("credentials_refresh", {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                logger.info("Broadcasted credentials_refresh to compute instances")
            except Exception as e:
                logger.error(f"Failed to broadcast credentials_refresh: {e}")

    async def _load_from_redis(self) -> None:
        """Load all tokens from Redis."""
        if not self._redis:
            return

        try:
            prefix = getattr(self._redis, '_prefix', 'claudevn:')
            pattern = f"{prefix}auth:*"
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor, match=pattern, count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    component_id = key_str.split(":")[-1]
                    data = await self._redis._redis.hgetall(key)
                    if data:
                        token_data = {
                            (k.decode() if isinstance(k, bytes) else k):
                            (v.decode() if isinstance(v, bytes) else v)
                            for k, v in data.items()
                        }
                        self._tokens[component_id] = token_data
                if cursor == 0:
                    break

            if self._tokens:
                logger.info(f"Loaded {len(self._tokens)} token(s) from Redis")
        except Exception as e:
            logger.warning(f"Failed to load tokens from Redis: {e}")

    async def _save_to_redis(self, component_id: str, token_data: dict) -> None:
        """Save a token to Redis."""
        if not self._redis:
            return

        try:
            key = self._redis_key(component_id)
            mapping = {k: str(v) for k, v in token_data.items()}
            await self._redis._redis.hset(key, mapping=mapping)
        except Exception as e:
            logger.error(f"Failed to save token to Redis: {e}")

    async def _delete_from_redis(self, component_id: str) -> None:
        """Delete a token from Redis."""
        if not self._redis:
            return

        try:
            key = self._redis_key(component_id)
            await self._redis._redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete token from Redis: {e}")

    async def _sync_registry_auth_status(self) -> None:
        """Synchronize registry auth_status for all existing compute tokens.

        Called on startup to ensure registry is in sync with stored tokens.
        """
        from services.registry_service import get_compute_registry
        from models.compute import ComputeAuthStatus

        registry = get_compute_registry()
        if not registry:
            return

        for component_id, token_data in self._tokens.items():
            component_type = token_data.get("component_type", "serving")
            if component_type != "compute":
                continue

            status = token_data.get("status")
            if status == TokenStatus.ACTIVE.value:
                # Sync AUTHORIZED status
                expires_at_str = token_data.get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    await registry.update_auth_status(
                        component_id,
                        ComputeAuthStatus.AUTHORIZED,
                        auth_expires_at=expires_at
                    )
                    logger.info(f"Synced registry auth_status for {component_id} to AUTHORIZED")
            else:
                # Sync UNAUTHORIZED status for expired/revoked tokens
                await registry.update_auth_status(
                    component_id,
                    ComputeAuthStatus.UNAUTHORIZED
                )
                logger.info(f"Synced registry auth_status for {component_id} to UNAUTHORIZED")

    async def _monitor_loop(self) -> None:
        """Periodically check token expiry."""
        while True:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_expiry()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in token monitor: {e}")

    async def _check_expiry(self) -> None:
        """Check all tokens for expiration."""
        now = datetime.now(timezone.utc)
        changed = False

        for component_id, data in list(self._tokens.items()):
            if data.get("status") != TokenStatus.ACTIVE.value:
                continue

            expires_at_str = data.get("expires_at")
            if not expires_at_str:
                continue

            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if now >= expires_at:
                    data["status"] = TokenStatus.EXPIRED.value
                    await self._save_to_redis(component_id, data)
                    logger.warning(f"Token expired for component {component_id}")
                    changed = True
                    if component_id == "serving":
                        self._remove_token_from_env()
            except (ValueError, TypeError):
                continue

        if changed:
            self._update_status()


# Module-level singleton
_claude_auth_service: Optional[ClaudeAuthService] = None


def get_claude_auth_service() -> Optional[ClaudeAuthService]:
    """Get the global Claude auth service instance."""
    return _claude_auth_service


def set_claude_auth_service(service: Optional[ClaudeAuthService]) -> None:
    """Set the global Claude auth service instance."""
    global _claude_auth_service
    _claude_auth_service = service
