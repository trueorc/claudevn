"""Coherence analyzer — LLM-based cross-goal consistency checking.

Implements Planning System Specification Section 6:
- Detects contradictions, implicit requirements, scope drift, gaps,
  and unstated dependencies across the goal corpus.
- Uses Sonnet for analysis (cross-goal reasoning needs depth).
- Re-runs when decomposition changes or new goals are added.
"""

import json
import logging
import re
import uuid
from typing import Dict, List, Optional

from models.work_unit.coherence import (
    CoherenceAnalysis,
    CoherenceInsight,
    InsightSeverity,
    InsightSource,
    InsightType,
)

logger = logging.getLogger(__name__)

COHERENCE_SYSTEM_PROMPT = """You are analyzing a set of software project goals for consistency and completeness.

For each issue you find, classify it as one of:
- contradiction: Conflicting statements across goals (e.g., "lightweight" vs "rich 3D visualization")
- implicit_requirement: Something implied but not explicitly specified (e.g., "mobile" implies responsive design)
- scope_drift: Goals evolving in ways that change architecture (e.g., started as web app, now includes native mobile)
- gap: Combined goals imply something unstated (e.g., API layer needed but not mentioned)
- unstated_dependency: Infrastructure need that follows from goals (e.g., database needed but not specified)

For each issue, assign severity:
- high: Direct contradiction or critical gap that blocks execution
- medium: Implicit requirement or scope drift that should be addressed
- low: Minor gap or suggestion for improvement

Respond with JSON only:
{
  "insights": [
    {
      "type": "implicit_requirement",
      "severity": "medium",
      "title": "Brief title of the issue",
      "description": "Detailed explanation of what was detected and why it matters",
      "sources": [
        {"goal_id": "goal-123", "goal_title": "Build calculator", "excerpt": "relevant text from the goal"}
      ],
      "suggestion": "Suggested resolution or action",
      "affected_units": ["wu-abc123"]
    }
  ]
}

Rules:
- Only report genuine issues — do not invent problems
- Be specific about which goals and text triggered each insight
- Suggestions should be actionable
- If no issues are found, return {"insights": []}
- affected_units should reference work unit IDs when relevant, or be empty"""


class CoherenceAnalyzer:
    """Analyzes goal corpus for cross-goal consistency.

    Collects all goals and their work units for a project,
    sends them to Sonnet for inconsistency analysis, and
    returns structured CoherenceInsight objects.
    """

    async def analyze(
        self,
        project_id: str,
        goals: List[dict],
        work_units_by_goal: Dict[str, List[dict]],
    ) -> CoherenceAnalysis:
        """Run coherence analysis across all goals.

        Args:
            project_id: Project being analyzed.
            goals: List of goal dicts with goal_id, title, description.
            work_units_by_goal: Map of goal_id -> list of work unit dicts.

        Returns:
            CoherenceAnalysis with detected insights.
        """
        if len(goals) < 2:
            # Need at least 2 goals to find cross-goal issues
            return CoherenceAnalysis(
                project_id=project_id,
                insights=[],
                goals_analyzed=len(goals),
            )

        # Build the prompt corpus
        prompt = self._build_prompt(goals, work_units_by_goal)

        # Call LLM
        try:
            from services.claude_client import get_claude_client
            client = get_claude_client()
            response = await client.complete(
                prompt=prompt,
                system=COHERENCE_SYSTEM_PROMPT,
                model="sonnet",
            )
            insights = self._parse_response(response.content, goals)
        except Exception as e:
            logger.error(f"Coherence analysis LLM call failed: {e}")
            return CoherenceAnalysis(
                project_id=project_id,
                insights=[],
                goals_analyzed=len(goals),
            )

        return CoherenceAnalysis(
            project_id=project_id,
            insights=insights,
            goals_analyzed=len(goals),
        )

    def _build_prompt(
        self,
        goals: List[dict],
        work_units_by_goal: Dict[str, List[dict]],
    ) -> str:
        """Build the user prompt with goal corpus and work units."""
        parts = []
        for goal in goals:
            gid = goal.get("goal_id", "unknown")
            title = goal.get("title", goal.get("description", "Untitled")[:80])
            desc = goal.get("description", "")

            section = f"## Goal: {title}\nID: {gid}\n{desc}"

            # Add work units if available
            units = work_units_by_goal.get(gid, [])
            if units:
                unit_lines = []
                for u in units[:10]:  # Cap to avoid token overflow
                    uid = u.get("id", "?")
                    udesc = u.get("description", "")
                    files = ", ".join(u.get("formal_spec", {}).get("target_files", [])[:5])
                    criteria = u.get("acceptance_criteria", [])
                    criteria_str = "; ".join(criteria[:3]) if criteria else "none"
                    unit_lines.append(
                        f"  - [{uid}] {udesc}\n"
                        f"    Files: {files or 'none'}\n"
                        f"    Criteria: {criteria_str}"
                    )
                section += "\n\nWork Units:\n" + "\n".join(unit_lines)

            parts.append(section)

        return (
            "Analyze the following goals and their work units for consistency, "
            "completeness, and potential issues:\n\n"
            + "\n\n---\n\n".join(parts)
        )

    def _parse_response(
        self, content: str, goals: List[dict],
    ) -> List[CoherenceInsight]:
        """Parse LLM response into CoherenceInsight objects."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                data = json.loads(match.group())
            else:
                logger.warning(f"Unparseable coherence response: {content[:300]}")
                return []

        raw_insights = data.get("insights", [])
        insights = []

        # Build goal lookup for validation
        goal_ids = {g.get("goal_id") for g in goals}

        for raw in raw_insights:
            try:
                # Validate type
                insight_type = raw.get("type", "")
                if insight_type not in InsightType.__members__.values():
                    try:
                        insight_type = InsightType(insight_type)
                    except ValueError:
                        insight_type = InsightType.GAP

                # Validate severity
                severity = raw.get("severity", "medium")
                try:
                    severity = InsightSeverity(severity)
                except ValueError:
                    severity = InsightSeverity.MEDIUM

                # Parse sources
                sources = []
                for src in raw.get("sources", []):
                    sources.append(InsightSource(
                        goal_id=src.get("goal_id", ""),
                        goal_title=src.get("goal_title", ""),
                        excerpt=src.get("excerpt", ""),
                    ))

                insights.append(CoherenceInsight(
                    id=f"insight-{uuid.uuid4().hex[:12]}",
                    type=insight_type,
                    severity=severity,
                    title=raw.get("title", "Untitled insight"),
                    description=raw.get("description", ""),
                    sources=sources,
                    suggestion=raw.get("suggestion", ""),
                    affected_units=raw.get("affected_units", []),
                ))
            except Exception as e:
                logger.warning(f"Skipping malformed insight: {e}")
                continue

        return insights
