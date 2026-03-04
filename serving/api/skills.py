"""Skill registry API endpoints (proxy to Marketplace service)."""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Body, status
from pydantic import BaseModel, Field

from services.marketplace_client import MarketplaceClient, get_marketplace_client
from services.marketplace_registry import MarketplaceRegistry, get_marketplace_registry
from models.marketplace import MarketplaceStatus


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])


# ============ Request/Response Models ============

class SkillUpdateRequest(BaseModel):
    """Request to update a skill."""
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    specialized_tools: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    conflicts_with: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    version: Optional[str] = None
    changelog: Optional[str] = Field(None, description="Description of changes for version history")


class AggregatedSkill(BaseModel):
    """Skill with marketplace source information."""
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "system"
    instructions: str = ""
    specialized_tools: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    conflicts_with: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    marketplace_id: Optional[str] = None
    marketplace_name: Optional[str] = None
    marketplace_tier: Optional[str] = None
    namespace: Optional[str] = None


class AggregatedSkillsResponse(BaseModel):
    """Response for aggregated skills endpoint."""
    skills: List[AggregatedSkill]
    total: int
    by_marketplace: Dict[str, int]
    by_tier: Dict[str, int]
    by_author: Dict[str, int]


# ============ Stats Endpoint (must be before /{skill_id}) ============

@router.get("/stats/summary")
async def get_stats(
    client: MarketplaceClient = Depends(get_marketplace_client)
):
    """Get skill statistics.

    Args:
        client: Marketplace client (injected)

    Returns:
        Summary statistics

    Raises:
        HTTPException: If marketplace request fails
    """
    try:
        return await client.get_stats()
    except Exception as e:
        logger.error(f"Error getting skill stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get skill stats: {str(e)}"
        )


# ============ Aggregated Skills Endpoint ============

@router.get("/aggregated", response_model=AggregatedSkillsResponse)
async def get_aggregated_skills(
    marketplace_id: Optional[str] = Query(None, description="Filter by marketplace ID"),
    tier: Optional[str] = Query(None, description="Filter by marketplace tier"),
    include_sources: bool = Query(True, description="Include source marketplace metadata"),
    registry: MarketplaceRegistry = Depends(get_marketplace_registry),
    client: MarketplaceClient = Depends(get_marketplace_client)
):
    """Get skills aggregated from all registered marketplaces.

    Args:
        marketplace_id: Optional filter by specific marketplace
        tier: Optional filter by marketplace tier (root, enterprise, team, project, user)
        include_sources: Whether to include source marketplace metadata
        registry: Marketplace registry (injected)
        client: Default marketplace client (injected)

    Returns:
        Aggregated skills from all marketplaces with source metadata

    Raises:
        HTTPException: If fetching skills fails
    """
    try:
        all_skills: List[Dict[str, Any]] = []
        by_marketplace: Dict[str, int] = {}
        by_tier: Dict[str, int] = {}
        by_author: Dict[str, int] = {}

        # Get all healthy marketplaces
        marketplaces = await registry.list_marketplaces(status=MarketplaceStatus.HEALTHY)

        # Filter by marketplace_id if specified
        if marketplace_id:
            marketplaces = [m for m in marketplaces if m.marketplace_id == marketplace_id]

        # Filter by tier if specified
        if tier:
            marketplaces = [m for m in marketplaces if m.tier.value == tier]

        # If no marketplaces registered, fall back to default client
        if not marketplaces:
            logger.info("No marketplaces registered, using default marketplace client")
            result = await client.list_skills()
            skills = result.get("skills", [])
            for skill in skills:
                # Add source metadata from default marketplace
                skill["marketplace_id"] = "default"
                skill["marketplace_name"] = "Default Marketplace"
                skill["marketplace_tier"] = skill.get("marketplace_tier", "root")
                all_skills.append(skill)
        else:
            # Fetch skills from all marketplaces concurrently
            import httpx

            async def fetch_skills_from_marketplace(marketplace):
                """Fetch skills from a single marketplace."""
                try:
                    async with httpx.AsyncClient() as http_client:
                        response = await http_client.get(
                            f"{marketplace.endpoint}/api/v1/skills",
                            timeout=10.0
                        )
                        response.raise_for_status()
                        data = response.json()
                        skills = data.get("skills", [])

                        # Enrich with marketplace source info
                        for skill in skills:
                            skill["marketplace_id"] = marketplace.marketplace_id
                            skill["marketplace_name"] = marketplace.name
                            skill["marketplace_tier"] = marketplace.tier.value

                        return skills
                except Exception as e:
                    logger.warning(f"Failed to fetch skills from {marketplace.marketplace_id}: {e}")
                    return []

            # Fetch from all marketplaces concurrently
            tasks = [fetch_skills_from_marketplace(m) for m in marketplaces]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, list):
                    all_skills.extend(result)

        # Build aggregation stats
        seen_ids: Dict[str, Dict[str, Any]] = {}  # skill_id -> skill (for deduplication)

        for skill in all_skills:
            skill_id = skill.get("id", "")
            mp_id = skill.get("marketplace_id", "unknown")
            mp_tier = skill.get("marketplace_tier", "unknown")
            author = skill.get("author", "unknown")

            # Track by marketplace
            by_marketplace[mp_id] = by_marketplace.get(mp_id, 0) + 1

            # Track by tier
            by_tier[mp_tier] = by_tier.get(mp_tier, 0) + 1

            # Track by author
            author_type = "system" if author == "system" else "user"
            by_author[author_type] = by_author.get(author_type, 0) + 1

            # Deduplicate by skill ID, keeping highest priority (lowest tier)
            if skill_id not in seen_ids:
                seen_ids[skill_id] = skill
            else:
                # Extended (specialized) wins over root (core)
                tier_priority = {"extended": 0, "root": 1}
                existing_tier = seen_ids[skill_id].get("marketplace_tier", "root")
                new_tier = skill.get("marketplace_tier", "root")
                if tier_priority.get(new_tier, 2) < tier_priority.get(existing_tier, 2):
                    seen_ids[skill_id] = skill

        # Convert to response format
        aggregated_skills = [
            AggregatedSkill(
                id=s.get("id", ""),
                name=s.get("name", ""),
                description=s.get("description", ""),
                version=s.get("version", "1.0.0"),
                author=s.get("author", "system"),
                instructions=s.get("instructions", "") if include_sources else "",
                specialized_tools=s.get("specialized_tools", []),
                tags=s.get("tags", []),
                conflicts_with=s.get("conflicts_with", []),
                constraints=s.get("constraints", []),
                dependencies=s.get("dependencies", []),
                marketplace_id=s.get("marketplace_id") if include_sources else None,
                marketplace_name=s.get("marketplace_name") if include_sources else None,
                marketplace_tier=s.get("marketplace_tier") if include_sources else None,
                namespace=s.get("namespace") if include_sources else None
            )
            for s in seen_ids.values()
        ]

        return AggregatedSkillsResponse(
            skills=aggregated_skills,
            total=len(aggregated_skills),
            by_marketplace=by_marketplace,
            by_tier=by_tier,
            by_author=by_author
        )

    except Exception as e:
        logger.error(f"Error getting aggregated skills: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get aggregated skills: {str(e)}"
        )


# ============ Skill CRUD Endpoints ============

@router.get("")
async def list_skills(
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    author: Optional[str] = Query(None, description="Filter by author"),
    client: MarketplaceClient = Depends(get_marketplace_client)
):
    """List skills from marketplace.

    Args:
        tags: Optional comma-separated tags
        author: Optional author filter
        client: Marketplace client (injected)

    Returns:
        Skills list with stats

    Raises:
        HTTPException: If marketplace request fails
    """
    try:
        # Parse tags if provided
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',')]

        # Get skills from marketplace
        result = await client.list_skills(tags=tag_list)

        # Apply author filter if provided (client-side filtering)
        if author and "skills" in result:
            filtered_skills = [
                skill for skill in result["skills"]
                if skill.get("author") == author
            ]
            result["skills"] = filtered_skills
            result["total"] = len(filtered_skills)

        return result

    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list skills: {str(e)}"
        )


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    client: MarketplaceClient = Depends(get_marketplace_client)
):
    """Get a specific skill.

    Args:
        skill_id: Skill ID
        client: Marketplace client (injected)

    Returns:
        Skill details

    Raises:
        HTTPException: If skill not found or marketplace request fails
    """
    try:
        return await client.get_skill(skill_id)
    except Exception as e:
        logger.error(f"Error getting skill {skill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found"
        )


@router.post("")
async def create_skill(
    skill_data: Dict[str, Any] = Body(...),
    client: MarketplaceClient = Depends(get_marketplace_client)
):
    """Create a new skill.

    Args:
        skill_data: Skill data
        client: Marketplace client (injected)

    Returns:
        Created skill

    Raises:
        HTTPException: If creation fails
    """
    try:
        return await client.create_skill(skill_data)
    except Exception as e:
        logger.error(f"Error creating skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create skill: {str(e)}"
        )


@router.patch("/{skill_id}")
async def update_skill(
    skill_id: str,
    request: SkillUpdateRequest,
    client: MarketplaceClient = Depends(get_marketplace_client)
):
    """Update a skill.

    Args:
        skill_id: Skill ID
        request: Update data
        client: Marketplace client (injected)

    Returns:
        Updated skill

    Raises:
        HTTPException: If skill not found or update fails
    """
    try:
        # Only include fields that were provided
        update_data = request.model_dump(exclude_unset=True)
        return await client.update_skill(skill_id, update_data)
    except Exception as e:
        logger.error(f"Error updating skill {skill_id}: {e}")
        # Check if it's a 404
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_id}' not found"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update skill: {str(e)}"
        )


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    client: MarketplaceClient = Depends(get_marketplace_client)
):
    """Delete a skill.

    Args:
        skill_id: Skill ID
        client: Marketplace client (injected)

    Returns:
        Confirmation message

    Raises:
        HTTPException: If skill not found or deletion fails
    """
    try:
        await client.delete_skill(skill_id)
        return {
            "status": "deleted",
            "skill_id": skill_id,
            "message": f"Skill '{skill_id}' deleted successfully"
        }
    except Exception as e:
        logger.error(f"Error deleting skill {skill_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_id}' not found"
            )
        if "system skill" in str(e).lower() or "cannot delete" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete system skills"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete skill: {str(e)}"
        )
