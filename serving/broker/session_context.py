"""Session context management for the Serving Component."""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum


logger = logging.getLogger(__name__)

# Optional data provider for session persistence
_data_provider = None

def set_session_data_provider(provider):
    """Set the data provider for session persistence."""
    global _data_provider
    _data_provider = provider


class SessionStatus(str, Enum):
    """Session status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SessionContext:
    """Session context data structure.
    
    This object flows through all tasks in a session and maintains:
    - Execution plan
    - Task results
    - Data references (blobs, external URLs)
    - Metadata (user, timestamps, costs)
    """
    session_id: str
    status: SessionStatus
    execution_plan: Optional[Dict[str, Any]] = None
    task_results: Dict[str, Any] = None
    data_refs: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.task_results is None:
            self.task_results = {}
        if self.data_refs is None:
            self.data_refs = {}
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat() if self.created_at else None
        data["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            status=SessionStatus(data["status"]),
            execution_plan=data.get("execution_plan"),
            task_results=data.get("task_results", {}),
            data_refs=data.get("data_refs", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
        )
    
    def add_task_result(self, task_id: str, result: Dict[str, Any]):
        """Add or update a task result."""
        self.task_results[task_id] = result
        self.updated_at = datetime.now(timezone.utc)
    
    def add_data_ref(self, ref_name: str, ref_data: Dict[str, Any]):
        """Add a data reference (blob, external URL, etc.)."""
        self.data_refs[ref_name] = ref_data
        self.updated_at = datetime.now(timezone.utc)
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get result for a specific task."""
        return self.task_results.get(task_id)
    
    def get_data_ref(self, ref_name: str) -> Optional[Dict[str, Any]]:
        """Get a data reference by name."""
        return self.data_refs.get(ref_name)
    
    def update_metadata(self, key: str, value: Any):
        """Update a metadata field."""
        self.metadata[key] = value
        self.updated_at = datetime.now(timezone.utc)
    
    def set_execution_plan(self, plan: Dict[str, Any]):
        """Set the execution plan."""
        self.execution_plan = plan
        self.updated_at = datetime.now(timezone.utc)


class SessionContextManager:
    """Manages session contexts with optional persistence.
    
    Uses in-memory storage with optional data provider backup for persistence.
    """
    
    def __init__(self, enable_persistence: bool = True):
        """Initialize session context manager.
        
        Args:
            enable_persistence: If True, persist sessions to data provider
        """
        self._contexts: Dict[str, SessionContext] = {}
        self._enable_persistence = enable_persistence
        logger.info(f"Initialized SessionContextManager (persistence={'enabled' if enable_persistence else 'disabled'})")
    
    async def create_session(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionContext:
        """Create a new session context.
        
        Args:
            session_id: Unique session identifier
            metadata: Optional initial metadata
            
        Returns:
            Created SessionContext
        """
        if session_id in self._contexts:
            raise ValueError(f"Session {session_id} already exists")
        
        context = SessionContext(
            session_id=session_id,
            status=SessionStatus.PENDING,
            metadata=metadata or {}
        )
        
        self._contexts[session_id] = context
        
        # Persist if enabled
        if self._enable_persistence and _data_provider:
            await _data_provider.store(
                f"sessions:{session_id}",
                context.to_dict(),
                metadata={"created_at": datetime.now(timezone.utc).isoformat()}
            )
        
        logger.info(f"Created session {session_id}")
        return context
    
    async def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get session context by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionContext or None if not found
        """
        return self._contexts.get(session_id)
    
    async def update_session(self, context: SessionContext):
        """Update session context.
        
        Args:
            context: Updated SessionContext
        """
        context.updated_at = datetime.now(timezone.utc)
        self._contexts[context.session_id] = context
        
        # Persist if enabled
        if self._enable_persistence and _data_provider:
            await _data_provider.store(
                f"sessions:{context.session_id}",
                context.to_dict(),
                metadata={"updated_at": datetime.now(timezone.utc).isoformat()}
            )
        
        logger.debug(f"Updated session {context.session_id}")
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session context.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if deleted, False if not found
        """
        if session_id in self._contexts:
            del self._contexts[session_id]
            
            # Delete from persistence if enabled
            if self._enable_persistence and _data_provider:
                await _data_provider.delete(f"sessions:{session_id}")
            
            logger.info(f"Deleted session {session_id}")
            return True
        return False
    
    async def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        limit: int = 100
    ) -> list[SessionContext]:
        """List sessions, optionally filtered by status.
        
        Args:
            status: Optional status filter
            limit: Maximum number of sessions to return
            
        Returns:
            List of SessionContext objects
        """
        sessions = list(self._contexts.values())
        
        if status:
            sessions = [s for s in sessions if s.status == status]
        
        # Sort by created_at descending
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        
        return sessions[:limit]
    
    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus
    ):
        """Update session status.
        
        Args:
            session_id: Session identifier
            status: New status
        """
        context = await self.get_session(session_id)
        if context:
            context.status = status
            context.updated_at = datetime.now(timezone.utc)
            await self.update_session(context)
            logger.info(f"Session {session_id} status -> {status.value}")
    
    async def add_task_result(
        self,
        session_id: str,
        task_id: str,
        result: Dict[str, Any]
    ):
        """Add a task result to session context.
        
        Args:
            session_id: Session identifier
            task_id: Task identifier
            result: Task result data
        """
        context = await self.get_session(session_id)
        if context:
            context.add_task_result(task_id, result)
            await self.update_session(context)
            logger.debug(f"Added result for task {task_id} in session {session_id}")
    
    async def add_data_ref(
        self,
        session_id: str,
        ref_name: str,
        ref_data: Dict[str, Any]
    ):
        """Add a data reference to session context.
        
        Args:
            session_id: Session identifier
            ref_name: Reference name
            ref_data: Reference data (URL, type, size, etc.)
        """
        context = await self.get_session(session_id)
        if context:
            context.add_data_ref(ref_name, ref_data)
            await self.update_session(context)
            logger.debug(f"Added data ref '{ref_name}' to session {session_id}")
    
    async def set_execution_plan(
        self,
        session_id: str,
        plan: Dict[str, Any]
    ):
        """Set execution plan for session.
        
        Args:
            session_id: Session identifier
            plan: Execution plan data
        """
        context = await self.get_session(session_id)
        if context:
            context.set_execution_plan(plan)
            await self.update_session(context)
            logger.info(f"Set execution plan for session {session_id}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about sessions.
        
        Returns:
            Dict with session statistics
        """
        total = len(self._contexts)
        by_status = {}
        
        for context in self._contexts.values():
            status = context.status.value
            by_status[status] = by_status.get(status, 0) + 1
        
        return {
            "total_sessions": total,
            "by_status": by_status
        }


# Global instance (will be initialized by main app)
_session_manager: Optional[SessionContextManager] = None


def get_session_manager() -> SessionContextManager:
    """Get the global session context manager instance.
    
    Returns:
        SessionContextManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionContextManager()
    return _session_manager


def set_session_manager(manager: SessionContextManager):
    """Set the global session context manager instance.
    
    Args:
        manager: SessionContextManager instance
    """
    global _session_manager
    _session_manager = manager

