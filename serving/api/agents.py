"""Agent proxy endpoints - proxy requests to marketplace(s)."""

import logging
import httpx
import hashlib
import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, status

from services.marketplace_registry import MarketplaceRegistry, get_marketplace_registry
from models.marketplace import MarketplaceStatus
from storage.cache_backend import get_cache_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


async def _get_primary_marketplace(
    registry: MarketplaceRegistry
) -> Optional[Dict[str, str]]:
    """Get the primary (healthy, highest priority) marketplace.
    
    Args:
        registry: Marketplace registry
        
    Returns:
        Dict with marketplace_id and endpoint, or None if no healthy marketplace
    """
    marketplaces = await registry.list_marketplaces(status=MarketplaceStatus.HEALTHY)
    
    if not marketplaces:
        logger.warning("No healthy marketplaces available")
        return None
    
    # Sort by priority (lower number = higher priority)
    marketplaces.sort(key=lambda m: m.priority)
    
    primary = marketplaces[0]
    return {
        "marketplace_id": primary.marketplace_id,
        "endpoint": primary.endpoint
    }


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Get agent definition by ID (proxied to marketplace).
    
    Args:
        agent_id: Agent ID
        registry: Marketplace registry (injected)
        
    Returns:
        Agent definition from marketplace
        
    Raises:
        HTTPException: If no marketplace available or agent not found
    """
    marketplace = await _get_primary_marketplace(registry)
    
    if not marketplace:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No marketplace available"
        )
    
    # Proxy request to marketplace
    url = f"{marketplace['endpoint']}/api/v1/agents/{agent_id}"
    
    logger.debug(f"Proxying GET agent {agent_id} to {marketplace['marketplace_id']}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            
            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent {agent_id} not found"
                )
            
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Marketplace returned error {e.response.status_code}: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Marketplace error: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Error connecting to marketplace: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach marketplace: {str(e)}"
        )


@router.post("/search")
async def search_agents(
    required_capabilities: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    search_text: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """Search for agents across all marketplaces (aggregated results).
    
    Args:
        required_capabilities: Required capabilities filter
        tags: Tags filter
        search_text: Text search in name/description
        limit: Maximum results per marketplace
        registry: Marketplace registry (injected)
        
    Returns:
        Aggregated agent search results from all marketplaces
        
    Raises:
        HTTPException: If no marketplace available
    """
    # Generate cache key from search parameters
    cache_key_data = {
        "capabilities": required_capabilities or [],
        "tags": tags or [],
        "search": search_text or "",
        "limit": limit
    }
    cache_key = f"agent_search:{hashlib.md5(json.dumps(cache_key_data, sort_keys=True).encode()).hexdigest()}"
    
    # Try cache first
    cache = get_cache_backend()
    cached_result = await cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"Returning cached agent search results")
        return cached_result
    
    marketplaces = await registry.list_marketplaces(status=MarketplaceStatus.HEALTHY)
    
    if not marketplaces:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No marketplace available"
        )
    
    # Build search request
    search_params = {}
    if required_capabilities:
        search_params["capabilities"] = ",".join(required_capabilities)
    if tags:
        search_params["tags"] = ",".join(tags)
    if search_text:
        search_params["search"] = search_text
    search_params["limit"] = limit
    
    all_agents = []
    errors = []
    
    # Query all healthy marketplaces
    async with httpx.AsyncClient(timeout=10.0) as client:
        for marketplace in marketplaces:
            try:
                url = f"{marketplace.endpoint}/api/v1/agents"
                
                logger.debug(f"Searching agents in {marketplace.marketplace_id}")
                
                response = await client.get(url, params=search_params)
                response.raise_for_status()
                
                result = response.json()
                
                # Handle paginated response format
                if isinstance(result, dict) and "items" in result:
                    agents = result["items"]
                else:
                    agents = result if isinstance(result, list) else []
                
                # Add marketplace source to each agent
                for agent in agents:
                    agent["_source_marketplace"] = marketplace.marketplace_id
                
                all_agents.extend(agents)
                
                logger.info(
                    f"Found {len(agents)} agents from {marketplace.marketplace_id}"
                )
                
            except Exception as e:
                logger.warning(
                    f"Error querying marketplace {marketplace.marketplace_id}: {e}"
                )
                errors.append({
                    "marketplace_id": marketplace.marketplace_id,
                    "error": str(e)
                })
                continue
    
    # Prepare result
    result = {
        "agents": all_agents,
        "total": len(all_agents),
        "marketplaces_queried": len(marketplaces),
        "marketplaces_succeeded": len(marketplaces) - len(errors),
        "errors": errors if errors else None
    }
    
    # Cache the result (5 minutes TTL)
    await cache.set(cache_key, result, ttl=300)
    
    return result


@router.get("")
async def list_agents(
    agent_type: Optional[str] = Query(None),
    capabilities: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    registry: MarketplaceRegistry = Depends(get_marketplace_registry)
):
    """List agents from all marketplaces with optional filters.
    
    This is a convenience endpoint that uses the same search mechanism
    but with GET instead of POST.
    
    Args:
        agent_type: Filter by agent type
        capabilities: Comma-separated capabilities
        tags: Comma-separated tags
        search: Text search
        limit: Results limit per marketplace
        registry: Marketplace registry (injected)
        
    Returns:
        Aggregated agent list
    """
    # Convert comma-separated strings to lists
    capability_list = capabilities.split(",") if capabilities else None
    tag_list = tags.split(",") if tags else None
    
    # Use the search endpoint
    return await search_agents(
        required_capabilities=capability_list,
        tags=tag_list,
        search_text=search,
        limit=limit,
        registry=registry
    )
