"""Credential health monitor for compute instances.

Periodically checks Claude OAuth credential validity and reports
status to Serving. Supports runtime credential reload via SIGHUP.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class CredentialStatus(str, Enum):
    """Credential health status."""
    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    MISSING = "missing"
    UNREADABLE = "unreadable"


class CredentialMonitor:
    """Monitors Claude OAuth credential health.

    Periodically reads ~/.claude/.credentials.json, checks token validity
    and expiry, and reports status. Supports reload via reload_credentials().
    """

    def __init__(
        self,
        credentials_path: str,
        check_interval: int = 3600,
        expiry_warning_days: int = 7,
        event_callback: Optional[Any] = None,
        auth_mode: Optional[str] = None,
        serving_auth_url: Optional[str] = None,
    ):
        """Initialize the credential monitor.

        Args:
            credentials_path: Path to credentials.json (supports ~ expansion)
            check_interval: Seconds between periodic checks
            expiry_warning_days: Days before expiry to report 'expiring' status
            event_callback: Async callback(event_type, data) for sending events to Serving
            auth_mode: Auth mode ("serving" enables auto-refresh from serving)
            serving_auth_url: Serving auth API URL for auto-refresh
        """
        self._credentials_path = Path(os.path.expanduser(credentials_path))
        self._check_interval = check_interval
        self._expiry_warning_days = expiry_warning_days
        self._event_callback = event_callback
        self._auth_mode = auth_mode
        self._serving_auth_url = serving_auth_url

        self._status = CredentialStatus.MISSING
        self._expires_at: Optional[datetime] = None
        self._last_check: Optional[datetime] = None
        self._last_modified: Optional[float] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._refresh_failures: int = 0
        self._max_refresh_backoff: int = 3600  # cap at 1 hour

    async def start(self) -> None:
        """Start periodic credential monitoring."""
        if self._running:
            return
        self._running = True
        # Do an initial check immediately
        await self._check_credentials()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"Credential monitor started (interval={self._check_interval}s, "
            f"path={self._credentials_path})"
        )

    async def stop(self) -> None:
        """Stop the credential monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Credential monitor stopped")

    async def reload_credentials(self) -> CredentialStatus:
        """Reload credentials from disk (called on SIGHUP).

        Returns:
            The new credential status after reload.
        """
        logger.info("Reloading credentials from disk...")
        previous_status = self._status
        await self._check_credentials()
        logger.info(
            f"Credential reload complete: {previous_status.value} -> {self._status.value}"
        )
        return self._status

    async def _monitor_loop(self) -> None:
        """Periodic monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
                if not self._running:
                    break
                await self._check_credentials()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in credential monitor loop: {e}")

    async def _check_credentials(self) -> None:
        """Check credential file and update status."""
        self._last_check = datetime.now(timezone.utc)
        previous_status = self._status

        if not self._credentials_path.exists():
            self._status = CredentialStatus.MISSING
            self._expires_at = None
            self._last_modified = None
            logger.warning(f"Credentials file not found: {self._credentials_path}")
            if previous_status != self._status:
                await self._notify_status_change(previous_status)
            if (
                self._auth_mode == "serving"
                and self._serving_auth_url
            ):
                await self._auto_refresh()
            return

        try:
            stat = self._credentials_path.stat()
            self._last_modified = stat.st_mtime

            data = json.loads(self._credentials_path.read_text())
            self._update_status_from_data(data)

        except PermissionError:
            self._status = CredentialStatus.UNREADABLE
            self._expires_at = None
            logger.error(f"Permission denied reading credentials: {self._credentials_path}")
        except json.JSONDecodeError:
            self._status = CredentialStatus.UNREADABLE
            self._expires_at = None
            logger.error(f"Invalid JSON in credentials file: {self._credentials_path}")
        except Exception as e:
            self._status = CredentialStatus.UNREADABLE
            self._expires_at = None
            logger.error(f"Error reading credentials: {e}")

        if previous_status != self._status:
            await self._notify_status_change(previous_status)

        # Auto-refresh from serving when credentials are expired or missing
        if (
            self._auth_mode == "serving"
            and self._serving_auth_url
            and self._status in (CredentialStatus.EXPIRED, CredentialStatus.MISSING)
        ):
            await self._auto_refresh()

    async def _auto_refresh(self) -> None:
        """Attempt to auto-refresh credentials from serving with backoff."""
        backoff = min(
            2 ** self._refresh_failures * 10,
            self._max_refresh_backoff,
        )
        if self._refresh_failures > 0:
            logger.info(
                f"Auto-refresh backoff: waiting {backoff}s "
                f"(attempt {self._refresh_failures + 1})"
            )
            await asyncio.sleep(backoff)

        logger.info("Auto-refreshing credentials from serving")
        result = await self.fetch_from_serving(self._serving_auth_url)
        if result in (CredentialStatus.VALID, CredentialStatus.EXPIRING):
            self._refresh_failures = 0
            logger.info("Auto-refresh succeeded")
        else:
            self._refresh_failures += 1
            logger.warning(
                f"Auto-refresh failed (attempt {self._refresh_failures}), "
                f"status: {result.value}"
            )

    def _update_status_from_data(self, data: dict) -> None:
        """Update status based on parsed credential data.

        Args:
            data: Parsed credentials JSON
        """
        # Look for expiry information in various possible fields
        expires_at_str = (
            data.get("expires_at")
            or data.get("expiresAt")
            or data.get("expiry")
        )

        if expires_at_str:
            try:
                if isinstance(expires_at_str, (int, float)):
                    self._expires_at = datetime.fromtimestamp(
                        expires_at_str, tz=timezone.utc
                    )
                else:
                    # Try ISO format
                    self._expires_at = datetime.fromisoformat(
                        expires_at_str.replace("Z", "+00:00")
                    )
            except (ValueError, TypeError):
                self._expires_at = None

        now = datetime.now(timezone.utc)

        if self._expires_at:
            if self._expires_at <= now:
                self._status = CredentialStatus.EXPIRED
                logger.warning(
                    f"Credentials expired at {self._expires_at.isoformat()}"
                )
            elif self._expires_at <= now + timedelta(days=self._expiry_warning_days):
                self._status = CredentialStatus.EXPIRING
                days_left = (self._expires_at - now).days
                logger.warning(
                    f"Credentials expiring in {days_left} days "
                    f"(at {self._expires_at.isoformat()})"
                )
            else:
                self._status = CredentialStatus.VALID
        else:
            # No expiry info found — check for token presence as basic validity
            has_token = bool(
                data.get("accessToken")
                or data.get("access_token")
                or data.get("token")
                or data.get("claudeAiOauth")
            )
            self._status = CredentialStatus.VALID if has_token else CredentialStatus.MISSING

    async def _notify_status_change(self, previous_status: CredentialStatus) -> None:
        """Notify Serving of a credential status change.

        Args:
            previous_status: The status before the change
        """
        logger.info(
            f"Credential status changed: {previous_status.value} -> {self._status.value}"
        )

        if self._event_callback and self._status in (
            CredentialStatus.EXPIRING,
            CredentialStatus.EXPIRED,
        ):
            try:
                await self._event_callback("credentials_expiring", {
                    "status": self._status.value,
                    "expires_at": (
                        self._expires_at.isoformat() if self._expires_at else None
                    ),
                    "previous_status": previous_status.value,
                })
            except Exception as e:
                logger.error(f"Failed to send credential status event: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current credential status.

        Returns:
            Dictionary with credential health information.
        """
        return {
            "status": self._status.value,
            "credentials_valid": self._status == CredentialStatus.VALID,
            "credentials_path": str(self._credentials_path),
            "expires_at": (
                self._expires_at.isoformat() if self._expires_at else None
            ),
            "last_check": (
                self._last_check.isoformat() if self._last_check else None
            ),
            "last_modified": self._last_modified,
            "check_interval": self._check_interval,
            "expiry_warning_days": self._expiry_warning_days,
        }

    @property
    def status(self) -> CredentialStatus:
        """Current credential status."""
        return self._status

    @property
    def is_valid(self) -> bool:
        """Whether credentials are currently valid."""
        return self._status == CredentialStatus.VALID

    async def fetch_from_serving(self, serving_auth_url: str) -> CredentialStatus:
        """Fetch credentials from Serving's auth API and write to disk.

        Args:
            serving_auth_url: Base URL of Serving's auth API (e.g., http://serving:8002/api/v1/auth)

        Returns:
            The credential status after fetch attempt.
        """
        url = f"{serving_auth_url.rstrip('/')}/credentials"
        logger.info(f"Fetching credentials from {url}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)

            if response.status_code != 200:
                logger.warning(f"Failed to fetch credentials: HTTP {response.status_code}")
                return self._status

            data = response.json()
            creds = data.get("credentials", data)

            # Write credentials to disk
            self._credentials_path.parent.mkdir(parents=True, exist_ok=True)
            self._credentials_path.write_text(json.dumps(creds))
            self._credentials_path.chmod(0o600)

            logger.info(f"Credentials written to {self._credentials_path}")

            # Reload to update status
            return await self.reload_credentials()

        except Exception as e:
            logger.error(f"Error fetching credentials from serving: {e}")
            return self._status

    def apply_token(self, token: str, expires_at: Optional[str] = None) -> None:
        """Apply a token received via SSE auth_token event.

        Sets credential status based on the token and its expiry. This is used
        when tokens are pushed from Serving rather than read from disk.

        Args:
            token: The OAuth token string
            expires_at: ISO-format expiry timestamp, or None
        """
        previous_status = self._status
        now = datetime.now(timezone.utc)

        if expires_at:
            try:
                self._expires_at = datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                self._expires_at = None

        if self._expires_at and self._expires_at <= now:
            self._status = CredentialStatus.EXPIRED
        elif (
            self._expires_at
            and self._expires_at <= now + timedelta(days=self._expiry_warning_days)
        ):
            self._status = CredentialStatus.EXPIRING
        else:
            self._status = CredentialStatus.VALID

        self._last_check = now
        self._refresh_failures = 0

        if previous_status != self._status:
            logger.info(
                f"Token applied: {previous_status.value} -> {self._status.value}"
            )

    @property
    def is_usable(self) -> bool:
        """Whether credentials are usable (valid or expiring soon)."""
        return self._status in (CredentialStatus.VALID, CredentialStatus.EXPIRING)


# Global instance
_credential_monitor: Optional[CredentialMonitor] = None


def get_credential_monitor() -> Optional[CredentialMonitor]:
    """Get the global credential monitor."""
    return _credential_monitor


def set_credential_monitor(monitor: CredentialMonitor) -> None:
    """Set the global credential monitor."""
    global _credential_monitor
    _credential_monitor = monitor


async def initialize_credential_monitor(
    credentials_path: str,
    check_interval: int = 3600,
    expiry_warning_days: int = 7,
    event_callback: Optional[Any] = None,
    auth_mode: Optional[str] = None,
    serving_auth_url: Optional[str] = None,
) -> CredentialMonitor:
    """Initialize and start the global credential monitor.

    Args:
        credentials_path: Path to credentials.json
        check_interval: Seconds between checks
        expiry_warning_days: Days before expiry to warn
        event_callback: Async callback for status events
        auth_mode: Auth mode ("serving" enables auto-refresh)
        serving_auth_url: Serving auth API URL for auto-refresh

    Returns:
        The initialized credential monitor
    """
    monitor = CredentialMonitor(
        credentials_path=credentials_path,
        check_interval=check_interval,
        expiry_warning_days=expiry_warning_days,
        event_callback=event_callback,
        auth_mode=auth_mode,
        serving_auth_url=serving_auth_url,
    )
    set_credential_monitor(monitor)
    await monitor.start()
    return monitor
