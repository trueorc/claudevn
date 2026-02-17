"""Process map models for facilitated process orchestration."""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field


class ActivityStatus(str, Enum):
    """Status of an activity."""
    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    GOAL_MET = "goal_met"
    BLOCKED = "blocked"
    REVISIT = "revisit"


class ParticipantRole(str, Enum):
    """Role of a participant in an activity."""
    PRIMARY = "primary"
    BACKUP = "backup"
    OPTIONAL = "optional"
    CONSULTANT = "consultant"


class ExchangeIntent(str, Enum):
    """Intent of a facilitation exchange."""
    FRAME = "frame"
    QUESTION = "question"
    ANSWER = "answer"
    CLARIFY = "clarify"
    ASSESS = "assess"
    CONCLUDE = "conclude"
    IDENTIFY_BLOCKER = "identify_blocker"
    GOAL_CHECK = "goal_check"
    GOAL_MET = "goal_met"


class ConversationStatus(str, Enum):
    """Status of a facilitation conversation."""
    ACTIVE = "active"
    GOAL_MET = "goal_met"
    BLOCKED = "blocked"
    NEEDS_HELP = "needs_help"
    MAX_ITERATIONS = "max_iterations"


class ProcessMapStatus(str, Enum):
    """Status of a process map."""
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    GOAL_ACHIEVED = "goal_achieved"
    NEEDS_MORE_WORK = "needs_more_work"
    FAILED = "failed"


class ParticipantAssignment(BaseModel):
    """Assignment of an agent to an activity."""
    agent_id: str = Field(..., description="Agent identifier")
    agent_name: str = Field(..., description="Human-readable agent name")
    role: ParticipantRole = Field(..., description="Role in this activity")
    capabilities: List[str] = Field(default_factory=list, description="Agent capabilities")
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When assigned")
    added_by: str = Field(default="agent-selector-v1", description="Who made the assignment")
    reason: str = Field(..., description="Why this agent was selected")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class Exchange(BaseModel):
    """One interaction in activity facilitation."""
    exchange_id: str = Field(..., description="Unique exchange identifier")
    activity_id: str = Field(..., description="Parent activity ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When this exchange occurred")
    speaker: str = Field(..., description="Who spoke: 'facilitator' or agent_id")
    message: str = Field(..., description="The message content")
    intent: ExchangeIntent = Field(..., description="Intent of this exchange")
    
    # Outcomes
    outcome: Optional[str] = Field(None, description="Outcome of this exchange")
    new_understanding: Optional[str] = Field(None, description="New understanding gained")
    decision_made: Optional[str] = Field(None, description="Decision made in this exchange")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class Blocker(BaseModel):
    """Represents something blocking activity progress."""
    blocker_id: str = Field(..., description="Unique blocker identifier")
    activity_id: str = Field(..., description="Activity that is blocked")
    description: str = Field(..., description="What is blocking progress")
    identified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When identified")
    identified_by: str = Field(default="activity-facilitator-v1", description="Who identified it")
    resolution_activity_id: Optional[str] = Field(None, description="Activity created to resolve this")
    resolved_at: Optional[datetime] = Field(None, description="When resolved")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class FacilitationConversation(BaseModel):
    """Complete facilitation conversation for an activity."""
    activity_id: str = Field(..., description="Activity being facilitated")
    session_id: str = Field(..., description="Parent session ID")
    facilitator_id: str = Field(default="activity-facilitator-v1", description="Facilitator agent ID")
    participant_id: str = Field(..., description="Primary participant agent ID")
    goal: str = Field(..., description="Activity goal")
    exchanges: List[Exchange] = Field(default_factory=list, description="Conversation exchanges")
    status: ConversationStatus = Field(default=ConversationStatus.ACTIVE, description="Conversation status")
    blocker: Optional[Blocker] = Field(None, description="Blocker if detected")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When conversation started")
    completed_at: Optional[datetime] = Field(None, description="When conversation completed")
    iteration_count: int = Field(default=0, description="Number of conversation iterations")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class FacilitationResult(BaseModel):
    """Result of facilitating an activity."""
    activity_id: str = Field(..., description="Activity that was facilitated")
    status: ConversationStatus = Field(..., description="Final conversation status")
    exchanges: List[Exchange] = Field(default_factory=list, description="All exchanges")
    output: Optional[Dict[str, Any]] = Field(None, description="Output from the activity")
    blocker: Optional[Blocker] = Field(None, description="Blocker if detected")
    key_findings: List[str] = Field(default_factory=list, description="Key findings")
    iterations: int = Field(default=0, description="Number of iterations")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class Activity(BaseModel):
    """A goal-oriented work unit in a process map."""
    activity_id: str = Field(..., description="Unique activity identifier")
    goal: str = Field(..., description="What this activity aims to accomplish")
    description: Optional[str] = Field(None, description="Additional context about the activity")
    status: ActivityStatus = Field(default=ActivityStatus.PROPOSED, description="Current status")
    
    # Participants (evolves during facilitation)
    assigned_agents: List[ParticipantAssignment] = Field(
        default_factory=list,
        description="Agents assigned to this activity"
    )
    
    # Relationships (discovered dynamically)
    depends_on: List[str] = Field(
        default_factory=list,
        description="Activity IDs that must complete before this one"
    )
    enables: List[str] = Field(
        default_factory=list,
        description="Activity IDs that this activity enables"
    )
    parent_activity: Optional[str] = Field(
        None,
        description="Parent activity if this is a sub-activity"
    )
    sub_activities: List[str] = Field(
        default_factory=list,
        description="Sub-activities (hierarchies emerge)"
    )
    
    # Facilitation
    exchanges: List[Exchange] = Field(
        default_factory=list,
        description="Conversation history for this activity"
    )
    blockers: List[Blocker] = Field(
        default_factory=list,
        description="Blockers identified during facilitation"
    )
    facilitation_result: Optional['FacilitationResult'] = Field(
        None,
        description="Result of facilitation (status, outputs, iterations)"
    )
    
    # Outputs
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="What was produced by this activity"
    )
    key_findings: List[str] = Field(
        default_factory=list,
        description="Key findings from this activity"
    )
    
    # Tracking
    proposed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this activity was proposed"
    )
    started_at: Optional[datetime] = Field(None, description="When facilitation started")
    completed_at: Optional[datetime] = Field(None, description="When goal was met")
    revisit_count: int = Field(default=0, description="Times this activity was reevaluated")
    
    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional activity metadata"
    )

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })

    def get_primary_agent(self) -> Optional[ParticipantAssignment]:
        """Get the primary agent assigned to this activity."""
        for assignment in self.assigned_agents:
            if assignment.role == ParticipantRole.PRIMARY:
                return assignment
        return None
    
    def is_ready_to_start(self) -> bool:
        """Check if activity is ready to start (dependencies satisfied)."""
        # In Phase 1, we just check basic status
        return self.status == ActivityStatus.PROPOSED and len(self.assigned_agents) > 0


class ActivityGroup(BaseModel):
    """Semantic grouping of related activities for visualization."""
    group_id: str = Field(..., description="Unique group identifier")
    name: str = Field(..., description="Human-readable group name")
    description: Optional[str] = Field(None, description="Description of this group's purpose")
    activity_ids: List[str] = Field(default_factory=list, description="Activities in this group")
    parent_group_id: Optional[str] = Field(None, description="Parent group if hierarchical")
    status: str = Field(default="in_progress", description="Group status (in_progress, completed, blocked)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When group was created")
    created_by: str = Field(default="process-mapper-v1", description="Who created this group")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional group metadata")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ReevaluationEvent(BaseModel):
    """Records a reevaluation of the process map."""
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When reevaluation occurred")
    triggered_by: str = Field(..., description="What triggered this reevaluation")
    previous_version: int = Field(..., description="Map version before reevaluation")
    new_version: int = Field(..., description="Map version after reevaluation")
    changes: Dict[str, Any] = Field(
        default_factory=dict,
        description="What changed in this reevaluation"
    )
    reasoning: str = Field(..., description="Why the map was restructured")

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


class ProcessMap(BaseModel):
    """Living document that evolves (not a fixed pipeline)."""
    map_id: str = Field(..., description="Unique map identifier")
    session_id: str = Field(..., description="Parent session ID")
    business_goal: str = Field(..., description="High-level business objective")
    
    # Map evolution
    map_version: int = Field(default=1, description="Increments with restructuring")
    activities: Dict[str, Activity] = Field(
        default_factory=dict,
        description="All activities by ID"
    )
    activity_graph: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Dependency relationships (activity_id -> [depends_on_ids])"
    )
    
    # Current state
    proposed_activities: List[str] = Field(
        default_factory=list,
        description="Activity IDs in proposed state"
    )
    in_progress_activities: List[str] = Field(
        default_factory=list,
        description="Activity IDs currently being facilitated"
    )
    completed_activities: List[str] = Field(
        default_factory=list,
        description="Activity IDs that achieved their goals"
    )
    blocked_activities: List[str] = Field(
        default_factory=list,
        description="Activity IDs that are blocked"
    )
    
    # Evolution tracking
    reevaluations: List[ReevaluationEvent] = Field(
        default_factory=list,
        description="History of process map reevaluations"
    )
    
    # Activity grouping for visualization
    activity_groups: Dict[str, ActivityGroup] = Field(
        default_factory=dict,
        description="Semantic groupings of activities"
    )
    group_order: List[str] = Field(
        default_factory=list,
        description="Order in which groups should be displayed"
    )
    
    # Status
    status: ProcessMapStatus = Field(
        default=ProcessMapStatus.INITIATED,
        description="Overall process map status"
    )
    
    # Goal completion tracking (Week 5)
    synthesis_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Final synthesis of all activity results"
    )
    goal_achieved: bool = Field(
        default=False,
        description="Whether the business goal has been achieved"
    )
    completeness_percent: int = Field(
        default=0,
        description="Percentage of goal completion (0-100)"
    )
    gaps_identified: List[str] = Field(
        default_factory=list,
        description="Remaining gaps preventing goal completion"
    )
    
    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When map was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update time"
    )
    created_by: str = Field(
        default="process-mapper-v1",
        description="Who created this map"
    )

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })

    def get_activity(self, activity_id: str) -> Optional[Activity]:
        """Get an activity by ID."""
        return self.activities.get(activity_id)
    
    def add_activity(self, activity: Activity):
        """Add an activity to the map."""
        self.activities[activity.activity_id] = activity
        self.activity_graph[activity.activity_id] = activity.depends_on
        
        # Update status lists
        if activity.status == ActivityStatus.PROPOSED:
            if activity.activity_id not in self.proposed_activities:
                self.proposed_activities.append(activity.activity_id)
        
        self.updated_at = datetime.now(timezone.utc)
    
    def update_activity_status(self, activity_id: str, new_status: ActivityStatus):
        """Update activity status and maintain status lists."""
        activity = self.get_activity(activity_id)
        if not activity:
            return
        
        old_status = activity.status
        activity.status = new_status
        
        # Update status lists
        # Remove from old status list
        if old_status == ActivityStatus.PROPOSED and activity_id in self.proposed_activities:
            self.proposed_activities.remove(activity_id)
        elif old_status == ActivityStatus.IN_PROGRESS and activity_id in self.in_progress_activities:
            self.in_progress_activities.remove(activity_id)
        elif old_status == ActivityStatus.GOAL_MET and activity_id in self.completed_activities:
            self.completed_activities.remove(activity_id)
        elif old_status == ActivityStatus.BLOCKED and activity_id in self.blocked_activities:
            self.blocked_activities.remove(activity_id)
        
        # Add to new status list
        if new_status == ActivityStatus.PROPOSED and activity_id not in self.proposed_activities:
            self.proposed_activities.append(activity_id)
        elif new_status == ActivityStatus.IN_PROGRESS and activity_id not in self.in_progress_activities:
            self.in_progress_activities.append(activity_id)
        elif new_status == ActivityStatus.GOAL_MET and activity_id not in self.completed_activities:
            self.completed_activities.append(activity_id)
        elif new_status == ActivityStatus.BLOCKED and activity_id not in self.blocked_activities:
            self.blocked_activities.append(activity_id)
        
        # Update timestamps
        if new_status == ActivityStatus.IN_PROGRESS and not activity.started_at:
            activity.started_at = datetime.now(timezone.utc)
        elif new_status == ActivityStatus.GOAL_MET and not activity.completed_at:
            activity.completed_at = datetime.now(timezone.utc)
        
        self.updated_at = datetime.now(timezone.utc)
    
    def get_ready_activities(self) -> List[Activity]:
        """Get activities that are ready to start (dependencies satisfied)."""
        ready = []
        for activity_id in self.proposed_activities:
            activity = self.get_activity(activity_id)
            if not activity:
                continue
            
            # Check if all dependencies are completed
            deps_satisfied = all(
                dep_id in self.completed_activities
                for dep_id in activity.depends_on
            )
            
            if deps_satisfied and len(activity.assigned_agents) > 0:
                ready.append(activity)
        
        return ready
    
    def get_progress(self) -> Dict[str, Any]:
        """Get progress statistics."""
        total = len(self.activities)
        completed = len(self.completed_activities)
        in_progress = len(self.in_progress_activities)
        blocked = len(self.blocked_activities)
        proposed = len(self.proposed_activities)
        
        return {
            "total_activities": total,
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "proposed": proposed,
            "progress_percent": (completed / total * 100) if total > 0 else 0,
            "map_version": self.map_version,
            "reevaluations": len(self.reevaluations)
        }
    
    def evolve_map(
        self,
        triggered_by: str,
        changes: Dict[str, Any],
        reasoning: str
    ) -> ReevaluationEvent:
        """Record a reevaluation and increment version."""
        event = ReevaluationEvent(
            event_id=f"reeval-{self.map_id}-{len(self.reevaluations) + 1}",
            triggered_by=triggered_by,
            previous_version=self.map_version,
            new_version=self.map_version + 1,
            changes=changes,
            reasoning=reasoning
        )
        
        self.reevaluations.append(event)
        self.map_version += 1
        self.updated_at = datetime.now(timezone.utc)
        
        return event
    
    def add_activity_group(
        self,
        group_id: str,
        name: str,
        activity_ids: List[str],
        description: Optional[str] = None,
        parent_group_id: Optional[str] = None,
        created_by: str = "process-mapper-v1"
    ) -> ActivityGroup:
        """Add a new activity group."""
        group = ActivityGroup(
            group_id=group_id,
            name=name,
            description=description,
            activity_ids=activity_ids,
            parent_group_id=parent_group_id,
            created_by=created_by
        )
        
        self.activity_groups[group_id] = group
        if group_id not in self.group_order:
            self.group_order.append(group_id)
        
        self.updated_at = datetime.now(timezone.utc)
        return group
    
    def update_group_status(self, group_id: str, new_status: str):
        """Update the status of an activity group based on its activities."""
        group = self.activity_groups.get(group_id)
        if not group:
            return
        
        # Calculate status based on activities
        all_completed = all(
            aid in self.completed_activities
            for aid in group.activity_ids
            if aid in self.activities
        )
        any_blocked = any(
            aid in self.blocked_activities
            for aid in group.activity_ids
            if aid in self.activities
        )
        
        if all_completed:
            group.status = "completed"
        elif any_blocked:
            group.status = "blocked"
        else:
            group.status = "in_progress"
        
        self.updated_at = datetime.now(timezone.utc)
    
    def get_group_progress(self, group_id: str) -> Dict[str, Any]:
        """Get progress statistics for a specific group."""
        group = self.activity_groups.get(group_id)
        if not group:
            return {}
        
        total = len(group.activity_ids)
        completed = sum(
            1 for aid in group.activity_ids
            if aid in self.completed_activities
        )
        in_progress = sum(
            1 for aid in group.activity_ids
            if aid in self.in_progress_activities
        )
        blocked = sum(
            1 for aid in group.activity_ids
            if aid in self.blocked_activities
        )
        
        return {
            "group_id": group_id,
            "name": group.name,
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "progress_percent": (completed / total * 100) if total > 0 else 0,
            "status": group.status
        }


class FacilitationResult(BaseModel):
    """Outcome of facilitating an activity."""
    activity_id: str = Field(..., description="Activity that was facilitated")
    status: ActivityStatus = Field(..., description="Final status after facilitation")
    
    # What emerged
    exchanges: List[Exchange] = Field(
        default_factory=list,
        description="Conversation exchanges"
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Activity outputs"
    )
    key_findings: List[str] = Field(
        default_factory=list,
        description="Key findings"
    )
    
    # If blocked
    blocker: Optional[Blocker] = Field(None, description="Blocker if activity blocked")
    
    # Metadata
    duration: Optional[float] = Field(None, description="Duration in seconds")
    exchange_count: int = Field(default=0, description="Number of exchanges")
    participants_involved: List[str] = Field(
        default_factory=list,
        description="Agent IDs that participated"
    )

    model_config = ConfigDict(json_encoders={
        datetime: lambda v: v.isoformat() if v else None
    })


# Request/Response models for API

class CreateProcessMapRequest(BaseModel):
    """Request to create a process map."""
    session_id: str = Field(..., description="Session ID")
    business_goal: str = Field(..., description="Business goal")


class AddActivityRequest(BaseModel):
    """Request to add an activity to a process map."""
    goal: str = Field(..., description="Activity goal")
    description: Optional[str] = Field(None, description="Activity description")
    depends_on: List[str] = Field(default_factory=list, description="Dependencies")


class UpdateActivityStatusRequest(BaseModel):
    """Request to update activity status."""
    status: ActivityStatus = Field(..., description="New status")


class AssignParticipantRequest(BaseModel):
    """Request to assign a participant to an activity."""
    agent_id: str = Field(..., description="Agent ID")
    agent_name: str = Field(..., description="Agent name")
    role: ParticipantRole = Field(default=ParticipantRole.PRIMARY, description="Role")
    capabilities: List[str] = Field(default_factory=list, description="Capabilities")
    reason: str = Field(..., description="Why this agent was selected")

