"""claudevn_get_skill tool - fetch skill definition."""

import logging
from typing import Optional

from ..models import GetSkillInput, SkillResponse, MCPError
from mcp.tools import emit_tool_error

logger = logging.getLogger(__name__)


async def get_skill(input: GetSkillInput) -> tuple[Optional[SkillResponse], Optional[MCPError]]:
    """Fetch skill definition from marketplace."""
    from services.marketplace_client import get_marketplace_client

    try:
        client = get_marketplace_client()
        skill = await client.get_skill(input.skill_id)

        return SkillResponse(
            skill_id=skill["id"],
            name=skill["name"],
            instructions=skill["instructions"],
            capabilities=skill.get("tags", []),
            specialized_tools=skill.get("specialized_tools", [])
        ), None

    except Exception as e:
        logger.error(f"Failed to get skill {input.skill_id}: {e}")
        await emit_tool_error(tool_name="get_skill", error_code="SKILL_NOT_FOUND", error_msg=str(e))
        return None, MCPError(
            code="SKILL_NOT_FOUND",
            message=f"Skill '{input.skill_id}' not found",
            details={"skill_id": input.skill_id}
        )
