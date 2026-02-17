"""API endpoints for process maps."""

import logging
from fastapi import APIRouter, HTTPException, status
from typing import List

from models.process_map import (
    ProcessMap,
    Activity,
    ActivityStatus,
    ParticipantAssignment,
    ParticipantRole,
    CreateProcessMapRequest,
    AddActivityRequest,
    UpdateActivityStatusRequest,
    AssignParticipantRequest,
    Exchange,
    ExchangeIntent,
    FacilitationResult
)
from services.process_map_service import get_process_map_service
from services.coordinating_team_service import get_coordinating_team_service
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/process-maps", tags=["process-maps"])


@router.post("/sessions/{session_id}/map", response_model=ProcessMap)
async def create_process_map(
    session_id: str,
    request: CreateProcessMapRequest
):
    """Create a new process map for a session."""
    try:
        service = get_process_map_service()
        process_map = await service.create_map(
            session_id=session_id,
            business_goal=request.business_goal
        )
        return process_map
    
    except Exception as e:
        logger.error(f"Error creating process map: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create process map: {str(e)}"
        )


@router.get("/sessions/{session_id}/map", response_model=ProcessMap)
async def get_process_map(session_id: str):
    """Get current process map for a session."""
    service = get_process_map_service()
    process_map = await service.get_map(session_id)
    
    if not process_map:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process map not found for session {session_id}"
        )
    
    return process_map


@router.get("/sessions/{session_id}/map/history", response_model=List[ProcessMap])
async def get_process_map_history(session_id: str):
    """Get evolution history of a process map."""
    service = get_process_map_service()
    history = await service.get_map_history(session_id)
    return history


@router.get("/sessions/{session_id}/map/progress")
async def get_process_map_progress(session_id: str):
    """Get progress statistics for a process map."""
    service = get_process_map_service()
    progress = await service.get_progress(session_id)
    
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process map not found for session {session_id}"
        )
    
    return progress


@router.post("/sessions/{session_id}/map/activities", response_model=Activity)
async def add_activity(
    session_id: str,
    request: AddActivityRequest
):
    """Add an activity to a process map."""
    try:
        service = get_process_map_service()
        
        # Generate activity ID
        process_map = await service.get_map(session_id)
        if not process_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Process map not found for session {session_id}"
            )
        
        activity_num = len(process_map.activities) + 1
        activity_id = f"act-{activity_num}"
        
        # Create activity
        activity = Activity(
            activity_id=activity_id,
            goal=request.goal,
            description=request.description,
            depends_on=request.depends_on,
            status=ActivityStatus.PROPOSED
        )
        
        # Add to map
        added_activity = await service.add_activity(session_id, activity)
        return added_activity
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add activity: {str(e)}"
        )


@router.get("/sessions/{session_id}/activities/{activity_id}", response_model=Activity)
async def get_activity(session_id: str, activity_id: str):
    """Get activity details."""
    service = get_process_map_service()
    activity = await service.get_activity(session_id, activity_id)
    
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity {activity_id} not found"
        )
    
    return activity


class InsertActivityBeforeRequest(BaseModel):
    """Request to insert an activity before another (for blocker resolution)."""
    blocked_activity_id: str
    new_activity: dict  # Activity fields
    blocker_id: str = None


@router.post("/{session_id}/activities/insert-before", response_model=Activity)
async def insert_activity_before(
    session_id: str,
    request: InsertActivityBeforeRequest
):
    """
    Insert a new activity as prerequisite to a blocked activity.
    
    This is used for dynamic activity creation when blockers are detected.
    The new activity becomes a dependency of the blocked activity.
    """
    try:
        service = get_process_map_service()
        
        # Create new activity from request
        new_activity = Activity(
            activity_id=request.new_activity.get("activity_id"),
            goal=request.new_activity.get("goal"),
            description=request.new_activity.get("description", ""),
            status=ActivityStatus(request.new_activity.get("status", "proposed"))
        )
        
        # Insert activity
        inserted = await service.insert_activity_before(
            session_id=session_id,
            blocked_activity_id=request.blocked_activity_id,
            new_activity=new_activity,
            blocker_id=request.blocker_id
        )
        
        return inserted
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error inserting activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to insert activity: {str(e)}"
        )
    
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity {activity_id} not found"
        )
    
    return activity


@router.put("/sessions/{session_id}/activities/{activity_id}/status")
async def update_activity_status(
    session_id: str,
    activity_id: str,
    request: UpdateActivityStatusRequest
):
    """Update activity status."""
    try:
        service = get_process_map_service()
        await service.update_activity_status(
            session_id=session_id,
            activity_id=activity_id,
            status=request.status
        )
        
        return {"message": f"Activity status updated to {request.status}"}
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating activity status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update activity status: {str(e)}"
        )


@router.post("/sessions/{session_id}/activities/{activity_id}/participants")
async def assign_participant(
    session_id: str,
    activity_id: str,
    request: AssignParticipantRequest
):
    """Assign a participant to an activity."""
    try:
        service = get_process_map_service()
        
        assignment = ParticipantAssignment(
            agent_id=request.agent_id,
            agent_name=request.agent_name,
            role=request.role,
            capabilities=request.capabilities,
            reason=request.reason
        )
        
        await service.assign_agent_to_activity(
            session_id=session_id,
            activity_id=activity_id,
            assignment=assignment
        )
        
        return {
            "message": f"Assigned {request.agent_name} to activity {activity_id}",
            "assignment": assignment.dict()
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error assigning participant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign participant: {str(e)}"
        )


@router.get("/sessions/{session_id}/activities/ready", response_model=List[Activity])
async def get_ready_activities(session_id: str):
    """Get activities that are ready to start."""
    service = get_process_map_service()
    ready_activities = await service.get_ready_activities(session_id)
    return ready_activities


class SelectParticipantsRequest(BaseModel):
    """Request to select participants for an activity."""
    capabilities: List[str] = []
    domain: str = None


@router.post("/sessions/{session_id}/activities/{activity_id}/select-participants")
async def select_participants(
    session_id: str,
    activity_id: str,
    request: SelectParticipantsRequest
):
    """
    Use Agent Selector to recommend participants for an activity.
    
    Queries marketplace(s) for available agents, then invokes Agent Selector
    to determine best matches based on capability and domain expertise.
    """
    try:
        map_service = get_process_map_service()
        team_service = get_coordinating_team_service()
        
        # Get activity
        activity = await map_service.get_activity(session_id, activity_id)
        if not activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Activity {activity_id} not found"
            )
        
        # Query marketplace for candidates
        candidates = await team_service.query_marketplace_for_agents(
            capabilities=request.capabilities,
            domain=request.domain
        )
        
        if not candidates:
            return {
                "message": "No matching agents found in marketplace",
                "candidates": [],
                "recommendations": None
            }
        
        # Invoke Agent Selector
        activity_data = {
            "activity_id": activity_id,
            "goal": activity.goal,
            "description": activity.description or ""
        }
        
        result = await team_service.invoke_agent_selector(
            session_id=session_id,
            activity=activity_data,
            candidates=candidates
        )
        
        # Parse recommendations
        recommendations = team_service.parse_agent_selector_output(result)
        
        return {
            "message": "Agent selection complete",
            "candidates": candidates,
            "recommendations": recommendations
        }
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error selecting participants: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to select participants: {str(e)}"
        )


class StartFacilitationRequest(BaseModel):
    """Request to start facilitation for an activity."""
    initial_prompt: str = "Let's begin working on this activity"


@router.post("/sessions/{session_id}/activities/{activity_id}/start-facilitation")
async def start_facilitation(
    session_id: str,
    activity_id: str,
    request: StartFacilitationRequest
):
    """
    Start facilitated conversation for an activity.
    
    Invokes Activity Facilitator to begin orchestrating work with assigned agents.
    """
    try:
        map_service = get_process_map_service()
        team_service = get_coordinating_team_service()
        
        # Get activity
        activity = await map_service.get_activity(session_id, activity_id)
        if not activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Activity {activity_id} not found"
            )
        
        # Check if agents are assigned
        if not activity.assigned_agents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No agents assigned to this activity. Please assign participants first."
            )
        
        # Update activity status
        await map_service.update_activity_status(
            session_id=session_id,
            activity_id=activity_id,
            status=ActivityStatus.IN_PROGRESS
        )
        
        # Prepare data for facilitator
        activity_data = {
            "activity_id": activity_id,
            "goal": activity.goal,
            "description": activity.description or ""
        }
        
        assigned_agents = [
            {
                "agent_id": a.agent_id,
                "agent_name": a.agent_name,
                "capabilities": a.capabilities
            }
            for a in activity.assigned_agents
        ]
        
        # Invoke Activity Facilitator
        result = await team_service.invoke_activity_facilitator(
            session_id=session_id,
            activity=activity_data,
            conversation_history=[],
            current_situation=request.initial_prompt,
            assigned_agents=assigned_agents
        )
        
        # Parse facilitator decision
        decision = team_service.parse_facilitator_output(result)
        
        # Create initial exchange
        target_agent = decision.get("target_agent", "unknown")
        next_prompt = decision.get("next_prompt", "Let's begin")
        
        exchange = Exchange(
            exchange_id=f"ex-{uuid.uuid4().hex[:8]}",
            activity_id=activity_id,
            speaker="activity-facilitator-v1",
            message=f"To {target_agent}: {next_prompt}",
            intent=ExchangeIntent(decision.get("intent", "question")),
            outcome="pending",
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add exchange to activity
        await map_service.add_exchange(session_id, activity_id, exchange)
        
        return {
            "message": "Facilitation started",
            "exchange": exchange.dict(),
            "facilitator_decision": decision
        }
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error starting facilitation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start facilitation: {str(e)}"
        )


@router.get("/sessions/{session_id}/activities/{activity_id}/exchanges", response_model=List[Exchange])
async def get_activity_exchanges(session_id: str, activity_id: str):
    """Get all exchanges (conversation) for an activity."""
    map_service = get_process_map_service()
    exchanges = await map_service.get_exchanges(session_id, activity_id)
    return exchanges


@router.post("/sessions/{session_id}/check-consistency")
async def check_consistency(session_id: str):
    """
    Run Consistency Manager across all activities to detect contradictions.
    """
    try:
        map_service = get_process_map_service()
        team_service = get_coordinating_team_service()
        
        # Get process map
        process_map = await map_service.get_map(session_id)
        if not process_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Process map not found for session {session_id}"
            )
        
        # Prepare activities data (serialize timestamps)
        activities_data = []
        for act_id, act in process_map.activities.items():
            exchanges_list = []
            for ex in act.exchanges:
                ex_dict = ex.dict()
                # Convert timestamp to ISO string
                if 'timestamp' in ex_dict and ex_dict['timestamp']:
                    ex_dict['timestamp'] = ex_dict['timestamp'].isoformat()
                exchanges_list.append(ex_dict)
            
            blockers_list = []
            if act.blockers:
                for b in act.blockers:
                    b_dict = b.dict()
                    if 'discovered_at' in b_dict and b_dict['discovered_at']:
                        b_dict['discovered_at'] = b_dict['discovered_at'].isoformat()
                    blockers_list.append(b_dict)
            
            activities_data.append({
                "activity_id": act_id,
                "goal": act.goal,
                "exchanges": exchanges_list,
                "blockers": blockers_list
            })
        
        # Invoke Consistency Manager
        result = await team_service.invoke_consistency_manager(
            session_id=session_id,
            activities=activities_data
        )
        
        return {
            "message": "Consistency check complete",
            "result": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking consistency: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check consistency: {str(e)}"
        )


@router.post("/sessions/{session_id}/generate-progress-report")
async def generate_progress_report(session_id: str):
    """
    Generate a comprehensive progress report using Progress Reporter.
    """
    try:
        map_service = get_process_map_service()
        team_service = get_coordinating_team_service()
        
        # Get process map
        process_map = await map_service.get_map(session_id)
        if not process_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Process map not found for session {session_id}"
            )
        
        # Prepare activities data (with datetime serialization)
        activities_data = []
        for act_id, act in process_map.activities.items():
            exchanges_list = []
            for ex in act.exchanges:
                ex_dict = ex.dict()
                if 'timestamp' in ex_dict and ex_dict['timestamp']:
                    ex_dict['timestamp'] = ex_dict['timestamp'].isoformat()
                exchanges_list.append(ex_dict)
            
            assigned_agents_list = []
            if act.assigned_agents:
                for a in act.assigned_agents:
                    a_dict = a.dict()
                    if 'added_at' in a_dict and a_dict['added_at']:
                        a_dict['added_at'] = a_dict['added_at'].isoformat()
                    if 'role' in a_dict and hasattr(a_dict['role'], 'value'):
                        a_dict['role'] = a_dict['role'].value
                    assigned_agents_list.append(a_dict)
            
            facilitation_result_dict = None
            if act.facilitation_result:
                facilitation_result_dict = json.loads(act.facilitation_result.json())
            
            activities_data.append({
                "activity_id": act_id,
                "goal": act.goal,
                "status": act.status.value,  # Convert Enum to string
                "assigned_agents": assigned_agents_list,
                "exchanges": exchanges_list,
                "facilitation_result": facilitation_result_dict
            })
        
        # Get recent consistency events
        consistency_events = await team_service.get_events(session_id, "consistency_check")
        if consistency_events:
            last_check = consistency_events[-1]["data"]
            # Support both inconsistencies_detected and contradictions fields
            inconsistencies = last_check.get("inconsistencies_detected") or last_check.get("contradictions", [])
        else:
            inconsistencies = []
        
        # Invoke Progress Reporter
        result = await team_service.invoke_progress_reporter(
            session_id=session_id,
            business_goal=process_map.business_goal,
            activities=activities_data,
            inconsistencies=inconsistencies
        )
        
        return {
            "message": "Progress report generated",
            "report": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating progress report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate progress report: {str(e)}"
        )


@router.post("/sessions/{session_id}/synthesize-results")
async def synthesize_results(session_id: str):
    """
    Create final deliverable using Result Synthesizer.
    """
    try:
        map_service = get_process_map_service()
        team_service = get_coordinating_team_service()
        
        # Get process map
        process_map = await map_service.get_map(session_id)
        if not process_map:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Process map not found for session {session_id}"
            )
        
        # Prepare completed activities data
        activities_data = [
            {
                "activity_id": act_id,
                "goal": act.goal,
                "facilitation_result": act.facilitation_result.dict() if act.facilitation_result else None
            }
            for act_id, act in process_map.activities.items()
            if act.status == ActivityStatus.GOAL_MET
        ]
        
        if not activities_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No completed activities to synthesize. Please complete some activities first."
            )
        
        # Invoke Result Synthesizer
        result = await team_service.invoke_result_synthesizer(
            session_id=session_id,
            business_goal=process_map.business_goal,
            activities=activities_data
        )
        
        return {
            "message": "Results synthesized",
            "deliverable": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error synthesizing results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synthesize results: {str(e)}"
        )


@router.get("/sessions/{session_id}/coordinating-events")
async def get_coordinating_events(session_id: str, event_type: str = None):
    """
    Get coordinating events (consistency checks, progress reports, etc).
    """
    try:
        team_service = get_coordinating_team_service()
        events = await team_service.get_events(session_id, event_type)
        
        return {
            "session_id": session_id,
            "event_type_filter": event_type,
            "events": events
        }
    
    except Exception as e:
        logger.error(f"Error fetching coordinating events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch events: {str(e)}"
        )

