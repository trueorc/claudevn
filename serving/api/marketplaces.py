"""Marketplace registry API endpoints."""

import logging
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, status

from models.marketplace import (
    MarketplaceInstance,
    MarketplaceStatus,
    MarketplaceRegistrationRequest,
    MarketplaceRegistrationResponse,
    MarketplaceHeartbeatRequest,
    MarketplaceUpdateRequest,
    MarketplaceListResponse,
    AggregatedMarketplaceStats,
)
from services.marketplace_registry import MarketplaceRegistry, get_marketplace_registry


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplaces", tags=["marketplaces"])


@router.post("/register", response_model=MarketplaceRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_marketplace(
    request: MarketplaceRegistrationRequest,
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Register a new marketplace.
    
    Args:
        request: Registration request
        registry: Marketplace registry (injected)
        
    Returns:
        Registration response with heartbeat details
        
    Raises:
        HTTPException: If marketplace_id already exists or validation fails
    """
    try:
        # Generate marketplace_id if not provided
        marketplace_id = request.marketplace_id or f"marketplace-{uuid.uuid4().hex[:8]}"
        
        # Create MarketplaceInstance from request
        marketplace = MarketplaceInstance(
            marketplace_id=marketplace_id,
            name=request.name,
            endpoint=request.endpoint,
            public_endpoint=request.public_endpoint,
            tier=request.tier,
            capabilities=request.capabilities or {},
            metadata=request.metadata,
            version=request.version,
            heartbeat_interval=request.heartbeat_interval,
            priority=request.priority,
        )
        
        # Register marketplace
        registered = await registry.add_marketplace(marketplace)
        
        logger.info(
            f"Registered marketplace {marketplace_id} ({request.name}) "
            f"with {request.capabilities.agent_count if request.capabilities else 0} agents"
        )
        
        return MarketplaceRegistrationResponse(
            status="registered",
            marketplace_id=registered.marketplace_id,
            heartbeat_interval=registered.heartbeat_interval,
            heartbeat_endpoint=f"/api/v1/marketplaces/{registered.marketplace_id}/heartbeat",
            message=f"Successfully registered marketplace {registered.marketplace_id}"
        )
        
    except ValueError as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error registering marketplace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during registration"
        )


@router.delete("/{marketplace_id}", status_code=status.HTTP_200_OK)
async def deregister_marketplace(
    marketplace_id: str,
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Deregister a marketplace.
    
    Args:
        marketplace_id: Marketplace ID
        registry: Marketplace registry (injected)
        
    Returns:
        Confirmation message
        
    Raises:
        HTTPException: If marketplace not found
    """
    removed = await registry.remove_marketplace(marketplace_id)
    
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace {marketplace_id} not found"
        )
    
    logger.info(f"Deregistered marketplace {marketplace_id}")
    
    return {
        "status": "deregistered",
        "marketplace_id": marketplace_id,
        "message": f"Successfully deregistered marketplace {marketplace_id}"
    }


@router.get("", response_model=MarketplaceListResponse)
async def list_marketplaces(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of marketplaces"),
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """List registered marketplaces.
    
    Args:
        status: Optional status filter
        limit: Maximum number of marketplaces
        registry: Marketplace registry (injected)
        
    Returns:
        List of marketplaces with summary stats
        
    Raises:
        HTTPException: If status is invalid
    """
    # Validate status
    status_enum = None
    if status:
        try:
            status_enum = MarketplaceStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}. Must be one of: {[s.value for s in MarketplaceStatus]}"
            )
    
    # Get marketplaces
    marketplaces = await registry.list_marketplaces(status=status_enum, limit=limit)
    
    # Calculate stats
    total = len(marketplaces)
    healthy = sum(1 for m in marketplaces if m.status == MarketplaceStatus.HEALTHY)
    offline = sum(1 for m in marketplaces if m.status == MarketplaceStatus.OFFLINE)
    
    return MarketplaceListResponse(
        marketplaces=marketplaces,
        total=total,
        healthy=healthy,
        offline=offline
    )


@router.get("/{marketplace_id}", response_model=MarketplaceInstance)
async def get_marketplace(
    marketplace_id: str,
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Get details of a specific marketplace.
    
    Args:
        marketplace_id: Marketplace ID
        registry: Marketplace registry (injected)
        
    Returns:
        Marketplace instance
        
    Raises:
        HTTPException: If marketplace not found
    """
    marketplace = await registry.get_marketplace(marketplace_id)
    
    if not marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace {marketplace_id} not found"
        )
    
    return marketplace


@router.patch("/{marketplace_id}", response_model=MarketplaceInstance)
async def update_marketplace(
    marketplace_id: str,
    request: MarketplaceUpdateRequest,
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Update marketplace information.
    
    Args:
        marketplace_id: Marketplace ID
        request: Update request
        registry: Marketplace registry (injected)
        
    Returns:
        Updated marketplace instance
        
    Raises:
        HTTPException: If marketplace not found
    """
    # Build updates dict
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.endpoint is not None:
        updates["endpoint"] = request.endpoint
    if request.public_endpoint is not None:
        updates["public_endpoint"] = request.public_endpoint
    if request.capabilities is not None:
        updates["capabilities"] = request.capabilities
    if request.metadata is not None:
        updates["metadata"] = request.metadata
    if request.priority is not None:
        updates["priority"] = request.priority
    
    marketplace = await registry.update_marketplace(marketplace_id, **updates)
    
    if not marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace {marketplace_id} not found"
        )
    
    logger.info(f"Updated marketplace {marketplace_id}")
    
    return marketplace


@router.post("/{marketplace_id}/heartbeat", status_code=status.HTTP_200_OK)
async def heartbeat(
    marketplace_id: str,
    request: Optional[MarketplaceHeartbeatRequest] = None,
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Receive heartbeat from marketplace.
    
    This endpoint is called by marketplaces to indicate they are alive.
    
    Args:
        marketplace_id: Marketplace ID
        request: Optional heartbeat metadata
        registry: Marketplace registry (injected)
        
    Returns:
        Acknowledgment
        
    Raises:
        HTTPException: If marketplace not found
    """
    metadata = {}
    if request:
        if request.agent_count is not None:
            metadata["agent_count"] = request.agent_count
        if request.tool_count is not None:
            metadata["tool_count"] = request.tool_count
        if request.skill_count is not None:
            metadata["skill_count"] = request.skill_count
        if request.status is not None:
            metadata["status"] = request.status
        if request.metadata is not None:
            metadata["metadata"] = request.metadata
    
    updated = await registry.update_heartbeat(
        marketplace_id=marketplace_id,
        metadata=metadata if metadata else None
    )
    
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace {marketplace_id} not found. Please register first."
        )
    
    logger.debug(f"Received heartbeat from marketplace {marketplace_id}")
    
    return {
        "status": "acknowledged",
        "marketplace_id": marketplace_id,
        "message": "Heartbeat received"
    }


@router.get("/stats/aggregated", response_model=AggregatedMarketplaceStats)
async def get_aggregated_stats(
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Get aggregated statistics across all marketplaces.
    
    Args:
        registry: Marketplace registry (injected)
        
    Returns:
        Aggregated statistics including total agents/tools
    """
    stats = await registry.get_aggregated_stats()
    return stats


@router.get("/stats/summary")
async def get_stats_summary(
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Get summary statistics for the marketplace registry.
    
    Args:
        registry: Marketplace registry (injected)
        
    Returns:
        Summary statistics
    """
    return registry.get_stats()

