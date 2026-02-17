"""Process map service for storage and management."""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from models.process_map import (
    ProcessMap,
    Activity,
    ActivityStatus,
    ParticipantAssignment,
    ReevaluationEvent,
    ProcessMapStatus,
    Exchange,
    ExchangeIntent,
    FacilitationResult
)

logger = logging.getLogger(__name__)


class ProcessMapService:
    """Service for managing process maps (storage only - no agent execution)."""
    
    def __init__(self, storage_path: str = "./data/serving/process_maps"):
        """
        Initialize process map service.
        
        Args:
            storage_path: Base path for storing process maps
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"ProcessMapService initialized with storage: {self.storage_path}")
    
    def _get_map_path(self, session_id: str) -> Path:
        """Get file path for a session's process map."""
        return self.storage_path / f"{session_id}_map.json"
    
    def _get_history_path(self, session_id: str) -> Path:
        """Get directory path for process map history."""
        return self.storage_path / session_id / "history"
    
    async def create_map(
        self,
        session_id: str,
        business_goal: str,
        created_by: str = "process-mapper-v1"
    ) -> ProcessMap:
        """
        Create initial process map for a session.
        
        Args:
            session_id: Session ID
            business_goal: Business goal this map achieves
            created_by: Who created this map
            
        Returns:
            Created ProcessMap
        """
        map_id = f"map-{session_id}"
        
        process_map = ProcessMap(
            map_id=map_id,
            session_id=session_id,
            business_goal=business_goal,
            created_by=created_by,
            map_version=1,
            status=ProcessMapStatus.INITIATED
        )
        
        # Save to disk
        await self._save_map(process_map)
        
        logger.info(f"Created process map {map_id} for session {session_id}")
        return process_map
    
    async def get_map(self, session_id: str) -> Optional[ProcessMap]:
        """
        Get current process map for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            ProcessMap or None if not found
        """
        map_path = self._get_map_path(session_id)
        
        if not map_path.exists():
            logger.warning(f"Process map not found for session {session_id}")
            return None
        
        try:
            with open(map_path, 'r') as f:
                data = json.load(f)
            
            process_map = ProcessMap(**data)
            return process_map
        
        except Exception as e:
            logger.error(f"Error loading process map for session {session_id}: {e}")
            return None
    
    async def _save_map(self, process_map: ProcessMap):
        """Save process map to disk."""
        map_path = self._get_map_path(process_map.session_id)
        
        try:
            # Update timestamp
            process_map.updated_at = datetime.now(timezone.utc)
            
            # Save current version
            with open(map_path, 'w') as f:
                json.dump(process_map.dict(), f, indent=2, default=str)
            
            # Save to history
            history_dir = self._get_history_path(process_map.session_id)
            history_dir.mkdir(parents=True, exist_ok=True)
            
            history_file = history_dir / f"v{process_map.map_version}.json"
            with open(history_file, 'w') as f:
                json.dump(process_map.dict(), f, indent=2, default=str)
            
            logger.debug(f"Saved process map {process_map.map_id} version {process_map.map_version}")
        
        except Exception as e:
            logger.error(f"Error saving process map {process_map.map_id}: {e}")
            raise
    
    async def add_activity(
        self,
        session_id: str,
        activity: Activity
    ) -> Activity:
        """
        Add an activity to a process map.
        
        Args:
            session_id: Session ID
            activity: Activity to add
            
        Returns:
            Added activity
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        # Add activity to map
        process_map.add_activity(activity)
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Added activity {activity.activity_id} to map {process_map.map_id}")
        return activity
    
    async def get_activity(
        self,
        session_id: str,
        activity_id: str
    ) -> Optional[Activity]:
        """
        Get an activity from a process map.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            
        Returns:
            Activity or None if not found
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            return None
        
        return process_map.get_activity(activity_id)
    
    async def insert_activity_before(
        self,
        session_id: str,
        blocked_activity_id: str,
        new_activity: Activity,
        blocker_id: Optional[str] = None
    ) -> Activity:
        """
        Insert a new activity as a prerequisite to a blocked activity.
        
        This is used for dynamic activity creation when blockers are detected.
        The new activity will be inserted with a dependency relationship:
        blocked_activity depends_on new_activity.
        
        Args:
            session_id: Session ID
            blocked_activity_id: ID of the activity that's blocked
            new_activity: New activity to insert
            blocker_id: Optional blocker ID that triggered this
            
        Returns:
            Inserted activity
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        blocked_activity = process_map.get_activity(blocked_activity_id)
        if not blocked_activity:
            raise ValueError(f"Blocked activity {blocked_activity_id} not found")
        
        # Add the new activity
        process_map.add_activity(new_activity)
        
        # Create dependency: blocked_activity depends on new_activity
        if new_activity.activity_id not in blocked_activity.depends_on:
            blocked_activity.depends_on.append(new_activity.activity_id)
        
        # Add enables relationship: new_activity enables blocked_activity
        if blocked_activity.activity_id not in new_activity.enables:
            new_activity.enables.append(blocked_activity.activity_id)
        
        # Link blocker to resolution activity
        if blocker_id:
            for blocker in blocked_activity.blockers:
                if blocker.blocker_id == blocker_id:
                    blocker.resolution_activity_id = new_activity.activity_id
                    break
        
        # Evolve process map (increment version)
        process_map.evolve_map(
            triggered_by=f"blocker_detected_{blocked_activity_id}",
            changes=f"Inserted resolution activity {new_activity.activity_id} before {blocked_activity_id}",
            reasoning=f"Activity {blocked_activity_id} blocked, prerequisite needed"
        )
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(
            f"Inserted activity {new_activity.activity_id} before {blocked_activity_id} "
            f"(new version: v{process_map.version})"
        )
        
        return new_activity
    
    async def add_dependency(
        self,
        session_id: str,
        activity_id: str,
        depends_on_activity_id: str
    ):
        """
        Add a dependency between two activities.
        
        Args:
            session_id: Session ID
            activity_id: Activity that has the dependency
            depends_on_activity_id: Activity that must complete first
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        activity = process_map.get_activity(activity_id)
        depends_on = process_map.get_activity(depends_on_activity_id)
        
        if not activity:
            raise ValueError(f"Activity {activity_id} not found")
        if not depends_on:
            raise ValueError(f"Activity {depends_on_activity_id} not found")
        
        # Add dependency
        if depends_on_activity_id not in activity.depends_on:
            activity.depends_on.append(depends_on_activity_id)
        
        # Add enables relationship
        if activity_id not in depends_on.enables:
            depends_on.enables.append(activity_id)
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Added dependency: {activity_id} depends on {depends_on_activity_id}")
    
    async def mark_blocker_resolved(
        self,
        session_id: str,
        activity_id: str,
        blocker_id: str,
        resolved_by_activity_id: str
    ):
        """
        Mark a blocker as resolved.
        
        Args:
            session_id: Session ID
            activity_id: Activity that was blocked
            blocker_id: Blocker ID
            resolved_by_activity_id: Activity that resolved the blocker
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        activity = process_map.get_activity(activity_id)
        if not activity:
            raise ValueError(f"Activity {activity_id} not found")
        
        # Find and update blocker
        for blocker in activity.blockers:
            if blocker.blocker_id == blocker_id:
                blocker.resolved_at = datetime.now(timezone.utc)
                blocker.resolution_activity_id = resolved_by_activity_id
                break
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Marked blocker {blocker_id} as resolved by activity {resolved_by_activity_id}")
    
    async def update_activity_status(
        self,
        session_id: str,
        activity_id: str,
        status: ActivityStatus
    ):
        """
        Update activity status.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            status: New status
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        # Update status
        process_map.update_activity_status(activity_id, status)
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Updated activity {activity_id} status to {status}")
    
    async def assign_agent_to_activity(
        self,
        session_id: str,
        activity_id: str,
        assignment: ParticipantAssignment
    ):
        """
        Assign an agent to an activity.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            assignment: Participant assignment
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        activity = process_map.get_activity(activity_id)
        if not activity:
            raise ValueError(f"Activity {activity_id} not found")
        
        # Add assignment
        activity.assigned_agents.append(assignment)
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(
            f"Assigned {assignment.agent_id} ({assignment.role}) "
            f"to activity {activity_id}"
        )
    
    async def update_activity_outputs(
        self,
        session_id: str,
        activity_id: str,
        outputs: Dict[str, Any],
        key_findings: Optional[List[str]] = None
    ):
        """
        Update activity outputs.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            outputs: Activity outputs
            key_findings: Optional key findings
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        activity = process_map.get_activity(activity_id)
        if not activity:
            raise ValueError(f"Activity {activity_id} not found")
        
        # Update outputs
        activity.outputs.update(outputs)
        if key_findings:
            activity.key_findings.extend(key_findings)
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Updated outputs for activity {activity_id}")
    
    async def evolve_map(
        self,
        session_id: str,
        triggered_by: str,
        changes: Dict[str, Any],
        reasoning: str
    ) -> ReevaluationEvent:
        """
        Evolve process map (create new version).
        
        Args:
            session_id: Session ID
            triggered_by: What triggered this evolution
            changes: Description of changes
            reasoning: Why the map was restructured
            
        Returns:
            ReevaluationEvent
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        # Record evolution
        event = process_map.evolve_map(
            triggered_by=triggered_by,
            changes=changes,
            reasoning=reasoning
        )
        
        # Save updated map with new version
        await self._save_map(process_map)
        
        logger.info(
            f"Evolved process map {process_map.map_id} "
            f"from v{event.previous_version} to v{event.new_version}"
        )
        
        return event
    
    async def get_map_history(self, session_id: str) -> List[ProcessMap]:
        """
        Get evolution history of a process map.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of ProcessMap versions (oldest to newest)
        """
        history_dir = self._get_history_path(session_id)
        
        if not history_dir.exists():
            return []
        
        versions = []
        for version_file in sorted(history_dir.glob("v*.json")):
            try:
                with open(version_file, 'r') as f:
                    data = json.load(f)
                
                process_map = ProcessMap(**data)
                versions.append(process_map)
            
            except Exception as e:
                logger.error(f"Error loading version {version_file}: {e}")
        
        return versions
    
    async def get_ready_activities(self, session_id: str) -> List[Activity]:
        """
        Get activities that are ready to start.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of activities ready to start
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            return []
        
        return process_map.get_ready_activities()
    
    async def split_activity(
        self,
        session_id: str,
        activity_id: str,
        sub_activities: List[Activity],
        reasoning: str
    ) -> List[Activity]:
        """
        Split an activity into multiple sub-activities.
        
        This is used when an activity is too complex and should be broken down.
        
        Args:
            session_id: Session ID
            activity_id: Activity to split
            sub_activities: List of new sub-activities
            reasoning: Why the split was needed
            
        Returns:
            List of created sub-activities
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        parent_activity = process_map.get_activity(activity_id)
        if not parent_activity:
            raise ValueError(f"Activity {activity_id} not found")
        
        logger.info(f"Splitting activity {activity_id} into {len(sub_activities)} sub-activities")
        
        # Add sub-activities
        for sub_activity in sub_activities:
            # Set parent relationship
            sub_activity.parent_activity = activity_id
            
            # Inherit dependencies from parent
            sub_activity.depends_on = parent_activity.depends_on.copy()
            
            # Add to map
            process_map.add_activity(sub_activity)
            
            # Update parent
            if sub_activity.activity_id not in parent_activity.sub_activities:
                parent_activity.sub_activities.append(sub_activity.activity_id)
        
        # Evolve map
        process_map.evolve_map(
            triggered_by=f"activity_split_{activity_id}",
            changes=f"Split {activity_id} into {len(sub_activities)} sub-activities: {[s.activity_id for s in sub_activities]}",
            reasoning=reasoning
        )
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Split activity {activity_id} (new version: v{process_map.version})")
        
        return sub_activities
    
    async def reorder_activities(
        self,
        session_id: str,
        new_order: List[str],
        reasoning: str
    ):
        """
        Reorder activities based on new insights.
        
        This updates dependency relationships to match a new execution order.
        
        Args:
            session_id: Session ID
            new_order: List of activity IDs in new execution order
            reasoning: Why reordering was needed
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        logger.info(f"Reordering {len(new_order)} activities")
        
        # Clear existing sequential dependencies (keep only explicit ones)
        changes = []
        
        for i, current_id in enumerate(new_order):
            current = process_map.get_activity(current_id)
            if not current:
                continue
            
            # If there's a next activity, ensure it depends on current
            if i < len(new_order) - 1:
                next_id = new_order[i + 1]
                next_activity = process_map.get_activity(next_id)
                
                if next_activity and current_id not in next_activity.depends_on:
                    next_activity.depends_on.append(current_id)
                    current.enables.append(next_id)
                    changes.append(f"{next_id} now depends on {current_id}")
        
        # Evolve map
        process_map.evolve_map(
            triggered_by="dependency_reordering",
            changes=f"Reordered activities: {new_order}. Changes: {', '.join(changes)}",
            reasoning=reasoning
        )
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Reordered activities (new version: v{process_map.version})")
    
    async def reevaluate_process_map(
        self,
        session_id: str,
        trigger: str,
        trigger_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Reevaluate process map and potentially restructure it.
        
        This is called when significant events happen:
        - Blocker detected
        - Contradiction found
        - Insight discovered
        - Multiple activities completed
        
        Args:
            session_id: Session ID
            trigger: What triggered reevaluation
            trigger_data: Data about the trigger
            
        Returns:
            Dictionary with reevaluation results
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        logger.info(f"Reevaluating process map due to: {trigger}")
        
        result = {
            "trigger": trigger,
            "actions_taken": [],
            "map_evolved": False,
            "new_version": process_map.version
        }
        
        # Check if reevaluation is needed based on trigger type
        if trigger == "blocker_detected":
            # Blocker already creates resolution activity (Week 2)
            # No additional reevaluation needed
            result["actions_taken"].append("Resolution activity created by blocker handler")
        
        elif trigger == "contradiction_detected":
            # Contradiction already creates reconciliation activity (Week 3)
            # No additional reevaluation needed
            result["actions_taken"].append("Reconciliation activity created by consistency checker")
        
        elif trigger == "activity_too_complex":
            # Could trigger activity splitting
            activity_id = trigger_data.get("activity_id")
            if activity_id:
                result["actions_taken"].append(f"Activity {activity_id} flagged for splitting")
                # In a full implementation, would analyze and split here
        
        elif trigger == "dependency_conflict":
            # Could trigger reordering
            result["actions_taken"].append("Dependency conflict detected, consider reordering")
            # In a full implementation, would analyze and reorder here
        
        elif trigger == "milestone_reached":
            # Multiple activities complete, check for patterns
            completed_count = len(process_map.completed_activities)
            result["actions_taken"].append(f"{completed_count} activities completed")
        
        return result

    
    async def get_progress(self, session_id: str) -> Dict[str, Any]:
        """
        Get progress statistics for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Progress statistics
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            return {}
        
        return process_map.get_progress()
    
    async def update_map_status(
        self,
        session_id: str,
        status: ProcessMapStatus
    ):
        """
        Update process map status.
        
        Args:
            session_id: Session ID
            status: New status
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        process_map.status = status
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Updated process map {process_map.map_id} status to {status}")
    
    async def add_exchange(
        self,
        session_id: str,
        activity_id: str,
        exchange: Exchange
    ) -> Exchange:
        """
        Add an exchange to an activity's conversation.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            exchange: Exchange to add
            
        Returns:
            Added exchange
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        activity = process_map.activities.get(activity_id)
        if not activity:
            raise ValueError(f"Activity {activity_id} not found")
        
        # Add exchange
        activity.exchanges.append(exchange)
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Added exchange {exchange.exchange_id} to activity {activity_id}")
        return exchange
    
    async def get_exchanges(
        self,
        session_id: str,
        activity_id: str
    ) -> List[Exchange]:
        """
        Get all exchanges for an activity.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            
        Returns:
            List of exchanges
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            return []
        
        activity = process_map.activities.get(activity_id)
        if not activity:
            return []
        
        return activity.exchanges
    
    async def record_facilitation_result(
        self,
        session_id: str,
        activity_id: str,
        result: FacilitationResult
    ):
        """
        Record facilitation result for an activity.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            result: Facilitation result
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        activity = process_map.activities.get(activity_id)
        if not activity:
            raise ValueError(f"Activity {activity_id} not found")
        
        # Set result
        activity.facilitation_result = result
        
        # Update activity status based on result
        if result.goal_achieved:
            activity.status = ActivityStatus.GOAL_MET
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.info(f"Recorded facilitation result for activity {activity_id}")
    
    async def save_conversation_state(
        self,
        session_id: str,
        activity_id: str,
        exchanges: List[Exchange],
        status: str,
        blocker: Optional[Dict[str, Any]] = None,
        iteration_count: int = 0
    ):
        """
        Save conversation state for an activity.
        
        This is a convenience method for saving conversation progress during facilitation.
        
        Args:
            session_id: Session ID
            activity_id: Activity ID
            exchanges: List of exchanges to save
            status: Conversation status (active, goal_met, blocked, etc.)
            blocker: Optional blocker information
            iteration_count: Number of iterations completed
        """
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        activity = process_map.activities.get(activity_id)
        if not activity:
            raise ValueError(f"Activity {activity_id} not found")
        
        # Update exchanges (replace completely to ensure consistency)
        activity.exchanges = exchanges
        
        # Update blocker if present
        if blocker:
            blocker_obj = Blocker(
                blocker_id=blocker.get("blocker_id", f"blocker-{len(activity.blockers)}"),
                activity_id=activity_id,
                description=blocker.get("description", "Unknown blocker"),
                identified_at=blocker.get("identified_at", datetime.now(timezone.utc)),
                identified_by=blocker.get("identified_by", "activity-facilitator-v1")
            )
            # Only add if not already present
            if not any(b.blocker_id == blocker_obj.blocker_id for b in activity.blockers):
                activity.blockers.append(blocker_obj)
        
        # Update activity status
        if status == "goal_met":
            activity.status = ActivityStatus.GOAL_MET
            activity.completed_at = datetime.now(timezone.utc)
        elif status == "blocked":
            activity.status = ActivityStatus.BLOCKED
        elif status == "active" and activity.status == ActivityStatus.PROPOSED:
            activity.status = ActivityStatus.IN_PROGRESS
            if not activity.started_at:
                activity.started_at = datetime.now(timezone.utc)
        
        # Save updated map
        await self._save_map(process_map)
        
        logger.debug(
            f"Saved conversation state for activity {activity_id}: "
            f"{len(exchanges)} exchanges, status={status}, iterations={iteration_count}"
        )

    
    async def analyze_and_group_activities(
        self,
        session_id: str,
        emit_events: bool = True
    ) -> List[Any]:
        """
        Analyze activities and create semantic groups.
        
        Args:
            session_id: Session ID
            emit_events: Whether to emit observability events for new groups
            
        Returns:
            List of created activity groups
        """
        from services.activity_grouping_service import get_activity_grouping_service
        
        process_map = await self.get_map(session_id)
        if not process_map:
            raise ValueError(f"Process map not found for session {session_id}")
        
        # Get grouping service and analyze
        grouping_service = get_activity_grouping_service()
        groups = grouping_service.analyze_and_group(process_map)
        
        # Save updated map with groups
        await self._save_map(process_map)
        
        # Emit observability events if requested
        if emit_events and groups:
            try:
                from services.observability_event_bus import get_observability_event_bus
                from models.observability import ProcessMapGroupingEvent
                
                event_bus = get_observability_event_bus()
                for group in groups:
                    event = ProcessMapGroupingEvent(
                        session_id=session_id,
                        group_id=group.group_id,
                        group_name=group.name,
                        activity_ids=group.activity_ids,
                        parent_group_id=group.parent_group_id,
                        status=group.status
                    )
                    await event_bus.publish(event)
                    logger.debug(f"Emitted grouping event for group {group.group_id}")
            except Exception as e:
                logger.error(f"Failed to emit grouping events: {e}")
        
        logger.info(f"Created {len(groups)} activity groups for session {session_id}")
        return groups


# Global instance
_process_map_service: Optional[ProcessMapService] = None


def get_process_map_service() -> ProcessMapService:
    """Get global process map service instance."""
    global _process_map_service
    if _process_map_service is None:
        _process_map_service = ProcessMapService()
    return _process_map_service


def set_process_map_service(service: ProcessMapService):
    """Set global process map service instance."""
    global _process_map_service
    _process_map_service = service

