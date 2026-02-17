"""Authorization audit logging service.

Provides in-memory audit trail for all tool authorization checks,
with configurable alert thresholds for failed attempts.
"""

import logging
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional, List

from models import AuthorizationAuditEntry, AuthorizationFailure

logger = logging.getLogger(__name__)

# Configurable via environment
MAX_AUDIT_ENTRIES = int(os.getenv("AUDIT_MAX_ENTRIES", "10000"))
ALERT_THRESHOLD = int(os.getenv("AUDIT_ALERT_THRESHOLD", "10"))
ALERT_WINDOW_SECONDS = int(os.getenv("AUDIT_ALERT_WINDOW_SECONDS", "300"))


class AuthorizationAuditService:
    """In-memory authorization audit log with alerting."""

    def __init__(
        self,
        max_entries: int = MAX_AUDIT_ENTRIES,
        alert_threshold: int = ALERT_THRESHOLD,
        alert_window_seconds: int = ALERT_WINDOW_SECONDS,
    ):
        self._entries: deque[AuthorizationAuditEntry] = deque(maxlen=max_entries)
        self._max_entries = max_entries
        self._alert_threshold = alert_threshold
        self._alert_window_seconds = alert_window_seconds
        self._total_checks = 0
        self._total_authorized = 0
        self._total_denied = 0

    def log_authorization(
        self,
        agent_id: str,
        tool_id: str,
        authorized: bool,
        reason: str,
        compute_id: Optional[str] = None,
        failure_type: Optional[AuthorizationFailure] = None,
        granted_by: Optional[List[str]] = None,
    ) -> AuthorizationAuditEntry:
        """Log an authorization check result.

        Args:
            agent_id: Agent requesting authorization
            tool_id: Tool being checked
            authorized: Whether access was granted
            reason: Human-readable explanation
            compute_id: Compute instance (if applicable)
            failure_type: Specific failure reason (if denied)
            granted_by: Skills that granted access

        Returns:
            The created audit entry
        """
        entry = AuthorizationAuditEntry(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            tool_id=tool_id,
            compute_id=compute_id,
            authorized=authorized,
            failure_type=failure_type,
            granted_by=granted_by or [],
            reason=reason,
        )

        self._entries.append(entry)
        self._total_checks += 1

        if authorized:
            self._total_authorized += 1
            logger.debug(
                f"Auth GRANTED: agent={agent_id} tool={tool_id} "
                f"compute={compute_id or 'N/A'}"
            )
        else:
            self._total_denied += 1
            logger.warning(
                f"Auth DENIED: agent={agent_id} tool={tool_id} "
                f"compute={compute_id or 'N/A'} reason={failure_type}"
            )
            self._check_alert_threshold(agent_id, tool_id)

        return entry

    def _check_alert_threshold(self, agent_id: str, tool_id: str) -> None:
        """Check if failed attempts exceed the alert threshold within the window."""
        now = datetime.now(timezone.utc)
        window_start = now.timestamp() - self._alert_window_seconds

        recent_failures = sum(
            1
            for e in self._entries
            if not e.authorized
            and e.timestamp.timestamp() >= window_start
        )

        if recent_failures >= self._alert_threshold:
            logger.error(
                f"ALERT: {recent_failures} failed authorization attempts in "
                f"last {self._alert_window_seconds}s (threshold: {self._alert_threshold}). "
                f"Latest: agent={agent_id} tool={tool_id}"
            )

    def query(
        self,
        agent_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        authorized: Optional[bool] = None,
        compute_id: Optional[str] = None,
        since: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[AuthorizationAuditEntry], int]:
        """Query audit entries with optional filters.

        Args:
            agent_id: Filter by agent ID
            tool_id: Filter by tool ID
            authorized: Filter by authorization result
            compute_id: Filter by compute ID
            since: Only entries after this timestamp
            skip: Number of records to skip
            limit: Max records to return

        Returns:
            Tuple of (matching entries, total matching count)
        """
        filtered = list(self._entries)

        if agent_id is not None:
            filtered = [e for e in filtered if e.agent_id == agent_id]
        if tool_id is not None:
            filtered = [e for e in filtered if e.tool_id == tool_id]
        if authorized is not None:
            filtered = [e for e in filtered if e.authorized == authorized]
        if compute_id is not None:
            filtered = [e for e in filtered if e.compute_id == compute_id]
        if since is not None:
            filtered = [e for e in filtered if e.timestamp >= since]

        # Newest first
        filtered.sort(key=lambda e: e.timestamp, reverse=True)

        total = len(filtered)
        paginated = filtered[skip : skip + limit]
        return paginated, total

    def get_stats(self) -> dict:
        """Get summary statistics for the audit log.

        Returns:
            Dictionary with total_checks, authorized/denied counts,
            denial_rate, top denied tools, and top denied agents.
        """
        denial_rate = (
            self._total_denied / self._total_checks
            if self._total_checks > 0
            else 0.0
        )

        # Compute top denied tools from current entries
        tool_denials: dict[str, int] = {}
        agent_denials: dict[str, int] = {}
        for entry in self._entries:
            if not entry.authorized:
                tool_denials[entry.tool_id] = tool_denials.get(entry.tool_id, 0) + 1
                agent_denials[entry.agent_id] = agent_denials.get(entry.agent_id, 0) + 1

        top_denied_tools = [
            {"tool_id": tid, "count": count}
            for tid, count in sorted(
                tool_denials.items(), key=lambda x: x[1], reverse=True
            )[:5]
        ]

        top_denied_agents = [
            {"agent_id": aid, "count": count}
            for aid, count in sorted(
                agent_denials.items(), key=lambda x: x[1], reverse=True
            )[:5]
        ]

        return {
            "total_checks": self._total_checks,
            "total_authorized": self._total_authorized,
            "total_denied": self._total_denied,
            "denial_rate": round(denial_rate, 4),
            "top_denied_tools": top_denied_tools,
            "top_denied_agents": top_denied_agents,
        }


# Module-level singleton
_audit_service: Optional[AuthorizationAuditService] = None


def get_authorization_audit_service() -> AuthorizationAuditService:
    """Get the global authorization audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuthorizationAuditService()
    return _audit_service
