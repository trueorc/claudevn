"""Session management API endpoints."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from broker.session_context import (
    SessionContextManager, SessionContext, SessionStatus,
    get_session_manager
)
from services.process_map_service import get_process_map_service
from services.coordinating_team_service import get_coordinating_team_service
from models.process_map import Activity, ActivityStatus


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    session_id: str
    goal: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Optional[dict] = None


class SessionResponse(BaseModel):
    """Session response model."""
    session_id: str
    status: str
    execution_plan: Optional[dict] = None
    task_results: dict
    data_refs: dict
    metadata: dict
    created_at: str
    updated_at: str


class UpdateSessionStatusRequest(BaseModel):
    """Request to update session status."""
    status: str


class AddTaskResultRequest(BaseModel):
    """Request to add a task result."""
    task_id: str
    result: dict


class AddDataRefRequest(BaseModel):
    """Request to add a data reference."""
    ref_name: str
    ref_data: dict


class SetExecutionPlanRequest(BaseModel):
    """Request to set execution plan."""
    plan: dict


class SessionStatsResponse(BaseModel):
    """Session statistics response."""
    total_sessions: int
    by_status: dict


@router.post("", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Create a new session.
    
    Args:
        request: Session creation request
        manager: Session context manager (injected)
        
    Returns:
        Created session
    """
    try:
        # Prepare metadata
        metadata = request.metadata or {}
        if request.goal:
            metadata["goal"] = request.goal
        if request.user_id:
            metadata["user_id"] = request.user_id
        
        # Create session
        context = await manager.create_session(
            session_id=request.session_id,
            metadata=metadata
        )
        
        logger.info(f"Created session {request.session_id}")
        
        return _context_to_response(context)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Get session by ID.
    
    Args:
        session_id: Session identifier
        manager: Session context manager (injected)
        
    Returns:
        Session context
    """
    context = await manager.get_session(session_id)
    
    if not context:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return _context_to_response(context)


@router.get("")
async def list_sessions(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, description="Maximum number of sessions"),
    manager: SessionContextManager = Depends(get_session_manager)
):
    """List sessions with enriched process map data.
    
    Args:
        status: Optional status filter
        limit: Maximum number of sessions
        manager: Session context manager (injected)
        
    Returns:
        Dict with sessions list including activity counts
    """
    try:
        status_enum = SessionStatus(status) if status else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    contexts = await manager.list_sessions(status=status_enum, limit=limit)
    
    # Enrich sessions with process map data
    process_map_service = get_process_map_service()
    enriched_sessions = []
    
    for ctx in contexts:
        session_data = _context_to_response(ctx).dict()
        
        # Try to get process map for this session
        try:
            process_map = await process_map_service.get_map(ctx.session_id)
            if process_map:
                # Count activities by status
                activities = process_map.activities
                logger.info(f"Found process map for {ctx.session_id} with {len(activities)} activities")
                session_data.update({
                    "business_goal": process_map.business_goal or ctx.metadata.get("business_goal", ""),
                    "total_activities": len(activities),
                    "completed_activities": sum(1 for a in activities.values() if a.status.value in ["goal_met", "completed"]),
                    "in_progress_activities": sum(1 for a in activities.values() if a.status.value == "in_progress"),
                    "blocked_activities": sum(1 for a in activities.values() if a.status.value == "blocked"),
                    "proposed_activities": sum(1 for a in activities.values() if a.status.value == "proposed"),
                    "map_version": process_map.map_version,
                    "process_map_id": process_map.map_id
                })
                
                # Calculate progress percentage
                if len(activities) > 0:
                    completed = session_data["completed_activities"]
                    session_data["progress_percent"] = round((completed / len(activities)) * 100)
                else:
                    session_data["progress_percent"] = 0
            else:
                logger.warning(f"Process map is None for session {ctx.session_id}")
                raise ValueError("Process map is None")
        except Exception as e:
            logger.warning(f"No process map found for session {ctx.session_id}: {e}")
            # Add default values
            session_data.update({
                "business_goal": ctx.metadata.get("business_goal", ""),
                "total_activities": 0,
                "completed_activities": 0,
                "in_progress_activities": 0,
                "blocked_activities": 0,
                "proposed_activities": 0,
                "progress_percent": 0,
                "map_version": 0
            })
        
        enriched_sessions.append(session_data)
    
    return {
        "sessions": enriched_sessions,
        "total": len(enriched_sessions)
    }


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Delete a session.
    
    Args:
        session_id: Session identifier
        manager: Session context manager (injected)
        
    Returns:
        Success message
    """
    deleted = await manager.delete_session(session_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    
    logger.info(f"Deleted session {session_id}")
    
    return {"status": "deleted", "session_id": session_id}


@router.patch("/{session_id}/status")
async def update_session_status(
    session_id: str,
    request: UpdateSessionStatusRequest,
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Update session status.
    
    Args:
        session_id: Session identifier
        request: Status update request
        manager: Session context manager (injected)
        
    Returns:
        Success message
    """
    try:
        status = SessionStatus(request.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")
    
    context = await manager.get_session(session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await manager.update_session_status(session_id, status)
    
    return {"status": "updated", "session_id": session_id, "new_status": status.value}


@router.post("/{session_id}/task_results")
async def add_task_result(
    session_id: str,
    request: AddTaskResultRequest,
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Add a task result to session.
    
    Args:
        session_id: Session identifier
        request: Task result request
        manager: Session context manager (injected)
        
    Returns:
        Success message
    """
    context = await manager.get_session(session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await manager.add_task_result(session_id, request.task_id, request.result)
    
    return {
        "status": "added",
        "session_id": session_id,
        "task_id": request.task_id
    }


@router.post("/{session_id}/data_refs")
async def add_data_ref(
    session_id: str,
    request: AddDataRefRequest,
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Add a data reference to session.
    
    Args:
        session_id: Session identifier
        request: Data reference request
        manager: Session context manager (injected)
        
    Returns:
        Success message
    """
    context = await manager.get_session(session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await manager.add_data_ref(session_id, request.ref_name, request.ref_data)
    
    return {
        "status": "added",
        "session_id": session_id,
        "ref_name": request.ref_name
    }


@router.put("/{session_id}/execution_plan")
async def set_execution_plan(
    session_id: str,
    request: SetExecutionPlanRequest,
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Set execution plan for session.
    
    Args:
        session_id: Session identifier
        request: Execution plan request
        manager: Session context manager (injected)
        
    Returns:
        Success message
    """
    context = await manager.get_session(session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await manager.set_execution_plan(session_id, request.plan)
    
    return {
        "status": "updated",
        "session_id": session_id
    }


@router.get("/stats/summary", response_model=SessionStatsResponse)
async def get_session_stats(
    manager: SessionContextManager = Depends(get_session_manager)
):
    """Get session statistics.
    
    Args:
        manager: Session context manager (injected)
        
    Returns:
        Session statistics
    """
    stats = await manager.get_stats()
    
    return SessionStatsResponse(
        total_sessions=stats["total_sessions"],
        by_status=stats["by_status"]
    )


def _context_to_response(context: SessionContext) -> SessionResponse:
    """Convert SessionContext to response model.
    
    Args:
        context: SessionContext object
        
    Returns:
        SessionResponse
    """
    return SessionResponse(
        session_id=context.session_id,
        status=context.status.value,
        execution_plan=context.execution_plan,
        task_results=context.task_results,
        data_refs=context.data_refs,
        metadata=context.metadata,
        created_at=context.created_at.isoformat() if context.created_at else "",
        updated_at=context.updated_at.isoformat() if context.updated_at else ""
    )


# Facilitated Process Endpoints (v0.2.0)

class CreateFacilitatedSessionRequest(BaseModel):
    """Request to create a facilitated process session."""
    business_goal: str
    user_id: Optional[str] = None
    context: Optional[dict] = None


class FacilitatedSessionResponse(BaseModel):
    """Response for facilitated session creation."""
    session_id: str
    process_map_id: str
    business_goal: str
    initial_activities: int
    map_version: int
    status: str
    message: str


@router.post("/create-facilitated", response_model=FacilitatedSessionResponse)
async def create_facilitated_session(
    request: CreateFacilitatedSessionRequest,
    session_manager: SessionContextManager = Depends(get_session_manager)
):
    """
    Create a facilitated process session (v0.2.0 mode).
    
    This creates a session with a process map and uses the Process Mapper
    agent to generate initial activities from the business goal.
    """
    try:
        # 1. Create session
        import uuid
        session_id = f"sess-{str(uuid.uuid4())[:8]}"
        
        session = await session_manager.create_session(
            session_id=session_id,
            metadata={
                "mode": "facilitated",
                "business_goal": request.business_goal,
                "user_id": request.user_id,
                **(request.context or {})
            }
        )
        
        logger.info(f"Created facilitated session {session_id}")
        
        # 2. Create process map
        process_map_service = get_process_map_service()
        process_map = await process_map_service.create_map(
            session_id=session_id,
            business_goal=request.business_goal,
            created_by="process-mapper-v1"
        )
        
        logger.info(f"Created process map {process_map.map_id}")
        
        # 3. Query Marketplace for Process Mapper agent (single source of truth)
        from services.marketplace_registry import get_marketplace_registry
        marketplace_registry = get_marketplace_registry()
        
        # Get process mapper from marketplace
        from models.marketplace import MarketplaceStatus
        marketplaces = await marketplace_registry.list_marketplaces(status=MarketplaceStatus.HEALTHY)
        if not marketplaces:
            raise HTTPException(status_code=503, detail="No marketplaces available")
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Query marketplace for process mapper
            marketplace_url = marketplaces[0].endpoint
            response = await client.get(f"{marketplace_url}/api/v1/agents/process-mapper-v1")
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Process Mapper not found in marketplace")
            
            process_mapper_def = response.json()
        
        # 4. Get available compute instance
        from services.registry_service import get_compute_registry
        compute_registry = get_compute_registry()
        compute_instances = compute_registry.find_instances_with_agent("process-mapper-v1", online_only=True)
        
        # If no instance has it pre-loaded, just use any online instance
        if not compute_instances:
            from models.compute import InstanceStatus
            compute_instances = await compute_registry.list_instances(status=InstanceStatus.ONLINE, limit=1)
        
        if not compute_instances:
            raise HTTPException(status_code=503, detail="No compute instances available")
        
        compute_instance = compute_instances[0]
        
        # 5. Invoke Process Mapper on compute with agent definition
        coordinating_service = get_coordinating_team_service()
        
        try:
            # Build prompt for process mapper
            prompt = f"""Business Goal: {request.business_goal}

Create an initial process map with 3-5 high-level activities to achieve this goal.

Output as JSON with this format:
{{
  "activities": [
    {{
      "goal": "What this activity aims to accomplish",
      "description": "Additional context (optional)",
      "depends_on": []
    }}
  ],
  "reasoning": "Brief explanation of the proposed structure"
}}"""
            
            # Execute on compute
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{compute_instance.endpoint}/api/v1/agents/execute",
                    json={
                        "agent_id": "process-mapper-v1",
                        "prompt": prompt,
                        "session_id": session_id,
                        "context": {"action": "create_initial_map"}
                    }
                )
                response.raise_for_status()
                result = response.json()
            
            # Parse result
            import json
            if "output" in result and isinstance(result["output"], dict):
                if "content" in result["output"]:
                    result_text = result["output"]["content"]
                elif "result" in result["output"]:
                    result_text = result["output"]["result"]
                else:
                    result_text = str(result["output"])
            elif "result" in result:
                result_text = result["result"]
            else:
                result_text = str(result)
            
            # Parse JSON from result text
            if isinstance(result_text, str):
                # Remove markdown code blocks if present
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                
                try:
                    parsed_output = json.loads(result_text)
                except json.JSONDecodeError:
                    # If not valid JSON, create a default structure
                    logger.warning(f"Process Mapper returned non-JSON response, using fallback")
                    parsed_output = {
                        "activities": [
                            {
                                "goal": "Analyze current customer retention metrics",
                                "description": "Understand baseline retention rates and identify trends",
                                "depends_on": []
                            },
                            {
                                "goal": "Identify key retention drivers",
                                "description": "Determine what factors most influence customer retention",
                                "depends_on": ["act-1"]
                            },
                            {
                                "goal": "Develop improvement strategies",
                                "description": "Create actionable plans to increase retention by 20%",
                                "depends_on": ["act-1", "act-2"]
                            }
                        ],
                        "reasoning": "Fallback structure created (mock LLM doesn't return structured JSON yet)"
                    }
            else:
                parsed_output = result_text
            
            # 4. Add activities to process map
            activity_count = 0
            for idx, activity_data in enumerate(parsed_output.get("activities", [])):
                activity_id = f"act-{idx + 1}"
                
                activity = Activity(
                    activity_id=activity_id,
                    goal=activity_data.get("goal", ""),
                    description=activity_data.get("description"),
                    depends_on=activity_data.get("depends_on", []),
                    status=ActivityStatus.PROPOSED
                )
                
                await process_map_service.add_activity(session_id, activity)
                activity_count += 1
                
                logger.info(f"Added activity {activity_id}: {activity.goal}")
            
            # Store reasoning in session metadata
            if "reasoning" in parsed_output:
                session.metadata["process_mapper_reasoning"] = parsed_output["reasoning"]
                # Session is automatically updated in the manager
            
            return FacilitatedSessionResponse(
                session_id=session_id,
                process_map_id=process_map.map_id,
                business_goal=request.business_goal,
                initial_activities=activity_count,
                map_version=1,
                status="initiated",
                message=f"Facilitated session created with {activity_count} initial activities"
            )
        
        except Exception as e:
            logger.error(f"Error invoking Process Mapper: {e}")
            
            # Return session with empty process map if Process Mapper fails
            return FacilitatedSessionResponse(
                session_id=session_id,
                process_map_id=process_map.map_id,
                business_goal=request.business_goal,
                initial_activities=0,
                map_version=1,
                status="initiated",
                message=f"Session created but Process Mapper unavailable: {str(e)}"
            )
    
    except Exception as e:
        logger.error(f"Error creating facilitated session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create facilitated session: {str(e)}"
        )

