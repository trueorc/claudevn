"""Logs proxy endpoints for retrieving logs from compute and marketplace instances."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
import httpx

from services.registry_service import ComputeRegistry, get_compute_registry
from services.marketplace_registry import MarketplaceRegistry, get_marketplace_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])


class LogsResponse(BaseModel):
    """Response model for logs."""
    lines: list[str]
    total_lines: int
    log_file: str
    source: str  # 'compute' or 'marketplace'
    instance_id: str


@router.get("/compute/{instance_id}", response_model=LogsResponse)
async def get_compute_logs(
    instance_id: str,
    lines: int = Query(default=100, ge=1, le=1000, description="Number of lines to retrieve"),
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Retrieve logs from a compute instance.
    
    Args:
        instance_id: Compute instance ID
        lines: Number of log lines to retrieve (default: 100, max: 1000)
        registry: Compute registry (injected)
        
    Returns:
        LogsResponse with log lines from the compute instance
        
    Raises:
        HTTPException: If instance not found or logs cannot be retrieved
    """
    # Get the instance
    instance = await registry.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Compute instance {instance_id} not found"
        )
    
    # Make request to the compute instance's logs endpoint
    logs_url = f"{instance.endpoint}/logs"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                logs_url,
                params={"lines": lines}
            )
            
            if response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Logs endpoint not available on compute instance {instance_id}. "
                           "The instance may need to be updated to support log retrieval."
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Add metadata about the source
            return LogsResponse(
                lines=data["lines"],
                total_lines=data["total_lines"],
                log_file=data["log_file"],
                source="compute",
                instance_id=instance_id
            )
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error retrieving logs from {instance_id}: {e}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Error retrieving logs from compute instance: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Request error retrieving logs from {instance_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to compute instance {instance_id}. Instance may be offline."
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving logs from {instance_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error retrieving logs: {str(e)}"
        )


@router.get("/marketplace/{marketplace_id}", response_model=LogsResponse)
async def get_marketplace_logs(
    marketplace_id: str,
    lines: int = Query(default=100, ge=1, le=1000, description="Number of lines to retrieve"),
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Retrieve logs from a marketplace instance.
    
    Args:
        marketplace_id: Marketplace instance ID
        lines: Number of log lines to retrieve (default: 100, max: 1000)
        registry: Marketplace registry (injected)
        
    Returns:
        LogsResponse with log lines from the marketplace instance
        
    Raises:
        HTTPException: If marketplace not found or logs cannot be retrieved
    """
    # Get the marketplace
    marketplace = await registry.get_marketplace(marketplace_id)
    if not marketplace:
        raise HTTPException(
            status_code=404,
            detail=f"Marketplace {marketplace_id} not found"
        )
    
    # Make request to the marketplace's logs endpoint
    logs_url = f"{marketplace.endpoint}/api/v1/logs"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                logs_url,
                params={"lines": lines}
            )
            
            if response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Logs endpoint not available on marketplace {marketplace_id}. "
                           "The marketplace may need to be updated to support log retrieval."
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Add metadata about the source
            return LogsResponse(
                lines=data["lines"],
                total_lines=data["total_lines"],
                log_file=data["log_file"],
                source="marketplace",
                instance_id=marketplace_id
            )
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error retrieving logs from marketplace {marketplace_id}: {e}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Error retrieving logs from marketplace: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Request error retrieving logs from marketplace {marketplace_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to marketplace {marketplace_id}. Marketplace may be offline."
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving logs from marketplace {marketplace_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error retrieving logs: {str(e)}"
        )

