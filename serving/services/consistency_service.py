"""
Consistency checking service for detecting contradictions across activities.

Week 3: Monitors activity outputs for contradictions, inconsistencies, and conflicts.
Creates reconciliation activities when issues are detected.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


class Contradiction:
    """Represents a detected contradiction between activities."""
    
    def __init__(
        self,
        contradiction_id: str,
        type: str,  # "contradiction", "inconsistency", "conflict", "duplication"
        severity: str,  # "critical", "moderate", "minor"
        activities_affected: List[str],
        description: str,
        evidence: List[str],
        recommendation: str,
        detected_at: datetime
    ):
        self.contradiction_id = contradiction_id
        self.type = type
        self.severity = severity
        self.activities_affected = activities_affected
        self.description = description
        self.evidence = evidence
        self.recommendation = recommendation
        self.detected_at = detected_at
        self.reconciliation_activity_id: Optional[str] = None
        self.resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "contradiction_id": self.contradiction_id,
            "type": self.type,
            "severity": self.severity,
            "activities_affected": self.activities_affected,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "detected_at": self.detected_at.isoformat(),
            "reconciliation_activity_id": self.reconciliation_activity_id,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


class ConsistencyService:
    """Service for checking consistency across activities."""
    
    def __init__(self, agent_executor=None):
        """
        Initialize consistency service.
        
        Args:
            agent_executor: Agent executor for running consistency manager agent
        """
        self.agent_executor = agent_executor
        self.consistency_agent_id = "consistency-manager-v1"
        logger.info("ConsistencyService initialized")
    
    async def check_consistency(
        self,
        session_id: str,
        activities: List[Dict[str, Any]],
        min_severity: str = "moderate"
    ) -> List[Contradiction]:
        """
        Check consistency across multiple activities.
        
        Args:
            session_id: Session ID
            activities: List of activity data with exchanges and outputs
            min_severity: Minimum severity to report ("critical", "moderate", "minor")
            
        Returns:
            List of detected contradictions
        """
        if not activities or len(activities) < 2:
            logger.debug("Not enough activities to check consistency")
            return []
        
        logger.info(f"Checking consistency across {len(activities)} activities in session {session_id}")
        
        try:
            # Prepare input for consistency manager agent
            agent_input = {
                "activities": self._prepare_activity_data(activities),
                "session_id": session_id
            }
            
            # Execute consistency manager agent
            if self.agent_executor:
                result = await self.agent_executor.execute_agent(
                    agent_id=self.consistency_agent_id,
                    task_input={
                        "prompt": json.dumps(agent_input, indent=2),
                        "context": {"session_id": session_id}
                    }
                )
                
                # Parse agent output
                output = result.get("output", {}).get("content", "{}")
                contradictions = self._parse_agent_output(output)
            else:
                # Fallback: Basic rule-based checking
                contradictions = self._basic_consistency_check(activities)
            
            # Filter by severity
            filtered = self._filter_by_severity(contradictions, min_severity)
            
            logger.info(f"Detected {len(filtered)} contradictions (severity >= {min_severity})")
            
            return filtered
        
        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return []
    
    def _prepare_activity_data(self, activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare activity data for consistency agent."""
        prepared = []
        
        for activity in activities:
            # Extract key information
            activity_data = {
                "activity_id": activity.get("activity_id"),
                "goal": activity.get("goal"),
                "status": activity.get("status"),
                "outputs": activity.get("outputs", {}),
                "key_findings": activity.get("key_findings", []),
                "exchanges": []
            }
            
            # Include relevant exchanges (last 5 for context)
            exchanges = activity.get("exchanges", [])
            if exchanges:
                activity_data["exchanges"] = [
                    {
                        "speaker": ex.get("speaker"),
                        "message": ex.get("message"),
                        "intent": ex.get("intent")
                    }
                    for ex in exchanges[-5:]  # Last 5 exchanges
                ]
            
            prepared.append(activity_data)
        
        return prepared
    
    def _parse_agent_output(self, output: str) -> List[Contradiction]:
        """Parse consistency manager agent output."""
        contradictions = []
        
        try:
            # Try to parse as JSON
            if isinstance(output, str):
                data = json.loads(output)
            else:
                data = output
            
            # Extract contradictions
            for item in data.get("inconsistencies_detected", []):
                contradiction = Contradiction(
                    contradiction_id=f"contra-{datetime.now(timezone.utc).timestamp()}",
                    type=item.get("type", "inconsistency"),
                    severity=item.get("severity", "moderate"),
                    activities_affected=item.get("activities_affected", []),
                    description=item.get("description", ""),
                    evidence=item.get("evidence", []),
                    recommendation=item.get("recommendation", ""),
                    detected_at=datetime.now(timezone.utc)
                )
                contradictions.append(contradiction)
        
        except json.JSONDecodeError:
            logger.warning("Failed to parse agent output as JSON, trying text extraction")
            # Fallback: Look for keywords in text
            if "contradiction" in output.lower() or "inconsisten" in output.lower():
                contradiction = Contradiction(
                    contradiction_id=f"contra-{datetime.now(timezone.utc).timestamp()}",
                    type="inconsistency",
                    severity="moderate",
                    activities_affected=[],
                    description=output[:200],  # First 200 chars
                    evidence=[],
                    recommendation="Review activity outputs",
                    detected_at=datetime.now(timezone.utc)
                )
                contradictions.append(contradiction)
        
        return contradictions
    
    def _basic_consistency_check(self, activities: List[Dict[str, Any]]) -> List[Contradiction]:
        """Basic rule-based consistency checking (fallback)."""
        contradictions = []
        
        # Check for numerical contradictions in outputs
        numerical_values = {}
        
        for activity in activities:
            activity_id = activity.get("activity_id")
            outputs = activity.get("outputs", {})
            
            # Extract numerical values
            for key, value in outputs.items():
                if isinstance(value, (int, float)):
                    if key not in numerical_values:
                        numerical_values[key] = []
                    numerical_values[key].append({
                        "activity_id": activity_id,
                        "value": value
                    })
        
        # Check for significant differences
        for key, values in numerical_values.items():
            if len(values) >= 2:
                vals = [v["value"] for v in values]
                max_val = max(vals)
                min_val = min(vals)
                
                # If difference > 20%, flag as contradiction
                if max_val > 0 and (max_val - min_val) / max_val > 0.2:
                    contradiction = Contradiction(
                        contradiction_id=f"contra-{key}-{datetime.now(timezone.utc).timestamp()}",
                        type="contradiction",
                        severity="moderate",
                        activities_affected=[v["activity_id"] for v in values],
                        description=f"Numerical contradiction in '{key}': values range from {min_val} to {max_val}",
                        evidence=[f"{v['activity_id']}: {v['value']}" for v in values],
                        recommendation=f"Reconcile {key} values across activities",
                        detected_at=datetime.now(timezone.utc)
                    )
                    contradictions.append(contradiction)
        
        return contradictions
    
    def _filter_by_severity(
        self,
        contradictions: List[Contradiction],
        min_severity: str
    ) -> List[Contradiction]:
        """Filter contradictions by minimum severity."""
        severity_order = {"minor": 1, "moderate": 2, "critical": 3}
        min_level = severity_order.get(min_severity, 2)
        
        return [
            c for c in contradictions
            if severity_order.get(c.severity, 0) >= min_level
        ]
    
    async def create_reconciliation_activity(
        self,
        session_id: str,
        contradiction: Contradiction,
        serving_url: str = "http://localhost:8002"
    ) -> Optional[str]:
        """
        Create a reconciliation activity to resolve a contradiction.
        
        Args:
            session_id: Session ID
            contradiction: Detected contradiction
            serving_url: Serving service URL
            
        Returns:
            Reconciliation activity ID if created
        """
        import httpx
        
        logger.info(f"Creating reconciliation activity for contradiction: {contradiction.description}")
        
        try:
            # Create reconciliation activity goal
            reconciliation_goal = f"Reconcile contradiction: {contradiction.description}"
            reconciliation_activity_id = f"reconcile-{contradiction.contradiction_id}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Add reconciliation activity
                response = await client.post(
                    f"{serving_url}/api/process-maps/sessions/{session_id}/map/activities",
                    json={
                        "goal": reconciliation_goal,
                        "description": f"Resolve {contradiction.type} affecting activities: {', '.join(contradiction.activities_affected)}",
                        "depends_on": contradiction.activities_affected  # Depends on conflicting activities
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to create reconciliation activity: {response.text}")
                    return None
                
                # Update contradiction with reconciliation activity ID
                contradiction.reconciliation_activity_id = reconciliation_activity_id
                
                logger.info(f"Created reconciliation activity {reconciliation_activity_id}")
                return reconciliation_activity_id
        
        except Exception as e:
            logger.error(f"Failed to create reconciliation activity: {e}")
            return None


# Global instance
_consistency_service: Optional[ConsistencyService] = None


def get_consistency_service() -> ConsistencyService:
    """Get global consistency service instance."""
    global _consistency_service
    if _consistency_service is None:
        _consistency_service = ConsistencyService()
    return _consistency_service


def set_consistency_service(service: ConsistencyService):
    """Set global consistency service instance."""
    global _consistency_service
    _consistency_service = service
