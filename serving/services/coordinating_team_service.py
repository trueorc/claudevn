"""Coordinating team service for routing to coordinating agents."""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import httpx

from services.registry_service import get_compute_registry
from services.marketplace_registry import get_marketplace_registry

logger = logging.getLogger(__name__)


class CoordinatingTeamService:
    """
    Routes messages to coordinating agents on compute instances.
    
    Note: This service does NOT execute agents - it routes messages to compute
    instances where agents execute via the existing agent executor.
    """
    
    def __init__(self, events_path: str = "./data/serving/coordinating_events"):
        self.compute_registry = get_compute_registry()
        self.marketplace_registry = get_marketplace_registry()
        self.http_client = httpx.AsyncClient(timeout=60.0)
        
        # Event bus storage
        self.events_path = Path(events_path)
        self.events_path.mkdir(parents=True, exist_ok=True)
    
    async def _find_agent_location(self, agent_id: str) -> Optional[str]:
        """
        Find which compute instance has a specific agent.
        
        Args:
            agent_id: Agent ID to find
            
        Returns:
            Compute instance URL or None if not found
        """
        instances = self.compute_registry.find_instances_with_agent(agent_id)
        
        if not instances:
            logger.warning(f"No compute instances found with agent {agent_id}")
            return None
        
        # Return first available instance
        instance = instances[0]
        return instance.endpoint
    
    async def _execute_agent_on_compute(
        self,
        agent_id: str,
        compute_url: str,
        prompt: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute agent on compute instance.
        
        Args:
            agent_id: Agent ID to execute
            compute_url: Compute instance URL
            prompt: Prompt for the agent
            session_id: Optional session ID
            context: Optional execution context
            
        Returns:
            Agent execution result
        """
        url = f"{compute_url}/api/v1/agents/execute"
        
        payload = {
            "agent_id": agent_id,
            "prompt": prompt,
            "session_id": session_id,
            "context": context or {}
        }
        
        logger.info(f"Executing {agent_id} on {compute_url}")
        
        try:
            response = await self.http_client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            logger.error(f"Error executing agent {agent_id}: {e}")
            raise
    
    async def invoke_process_mapper(
        self,
        session_id: str,
        action: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Invoke Process Mapper agent to create or evolve process map.
        
        Args:
            session_id: Session ID
            action: Action to perform ("create_initial_map" or "evolve_map")
            data: Data for the action (business_goal, current_map, etc.)
            
        Returns:
            Process Mapper result
        """
        agent_id = "process-mapper-v1"
        
        # Find compute instance with Process Mapper
        compute_url = await self._find_agent_location(agent_id)
        if not compute_url:
            raise ValueError(f"Process Mapper agent not available on any compute instance")
        
        # Build prompt based on action
        if action == "create_initial_map":
            prompt = self._build_initial_map_prompt(data.get("business_goal", ""))
        elif action == "evolve_map":
            prompt = self._build_evolve_map_prompt(
                data.get("current_map", {}),
                data.get("new_information", "")
            )
        else:
            raise ValueError(f"Unknown action: {action}")
        
        # Execute agent
        result = await self._execute_agent_on_compute(
            agent_id=agent_id,
            compute_url=compute_url,
            prompt=prompt,
            session_id=session_id,
            context={"action": action}
        )
        
        return result
    
    def _build_initial_map_prompt(self, business_goal: str) -> str:
        """Build prompt for creating initial process map."""
        return f"""Business Goal: {business_goal}

Create an initial process map with 3-5 high-level activities to achieve this goal.

Remember:
- Activities should be GOALS (what to accomplish), not tasks (how to do it)
- Keep them high-level - they will be refined during facilitation
- Identify basic dependencies between activities
- Focus on WHAT needs to be accomplished

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
    
    def _build_evolve_map_prompt(
        self,
        current_map: Dict[str, Any],
        new_information: str
    ) -> str:
        """Build prompt for evolving process map."""
        return f"""Current Process Map:
{json.dumps(current_map, indent=2)}

New Information: {new_information}

Evolve the process map based on this new information. You can:
- Add new activities
- Split existing activities into sub-activities
- Update dependencies
- Restructure the map

Output the updated activities in the same JSON format:
{{
  "activities": [...],
  "reasoning": "Why the map was restructured"
}}"""
    
    def parse_process_mapper_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Process Mapper output into structured format.
        
        Args:
            result: Raw result from agent execution
            
        Returns:
            Parsed activities and reasoning
        """
        try:
            # Extract result from agent response
            if "result" in result:
                result_text = result["result"]
            elif "response" in result:
                result_text = result["response"]
            else:
                result_text = str(result)
            
            # Try to parse as JSON
            if isinstance(result_text, str):
                # Remove markdown code blocks if present
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                
                parsed = json.loads(result_text)
            else:
                parsed = result_text
            
            # Validate structure
            if "activities" not in parsed:
                raise ValueError("Process Mapper output missing 'activities' field")
            
            return parsed
        
        except Exception as e:
            logger.error(f"Error parsing Process Mapper output: {e}")
            logger.error(f"Raw output: {result}")
            raise ValueError(f"Failed to parse Process Mapper output: {e}")
    
    async def query_marketplace_for_agents(
        self,
        capabilities: List[str],
        domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query marketplace(s) for agents matching capabilities.
        
        Args:
            capabilities: Required capabilities
            domain: Optional domain expertise
            
        Returns:
            List of matching agents
        """
        all_candidates = []
        
        # Get all healthy/degraded marketplaces (degraded means slow heartbeat but still operational)
        healthy = await self.marketplace_registry.list_marketplaces(status="healthy")
        degraded = await self.marketplace_registry.list_marketplaces(status="degraded")
        marketplaces = healthy + degraded
        
        logger.info(f"Querying {len(marketplaces)} marketplace(s) for agents with capabilities: {capabilities}")
        
        for marketplace in marketplaces:
            try:
                # Query this marketplace
                url = f"{marketplace.endpoint}/api/v1/agents/search"
                
                payload = {
                    "required_capabilities": capabilities
                }
                if domain:
                    payload["tags"] = [domain]
                
                response = await self.http_client.post(url, json=payload, timeout=10.0)
                
                if response.status_code == 200:
                    results = response.json()
                    
                    # results might be a list or a dict with 'agents' key
                    if isinstance(results, list):
                        agents = results
                    elif isinstance(results, dict) and 'agents' in results:
                        agents = results['agents']
                    else:
                        agents = []
                    
                    all_candidates.extend(agents)
                    logger.info(f"Found {len(agents)} candidates from {marketplace.marketplace_id}")
            
            except Exception as e:
                logger.warning(f"Error querying marketplace {marketplace.marketplace_id}: {e}")
                continue
        
        return all_candidates
    
    async def invoke_agent_selector(
        self,
        session_id: str,
        activity: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Invoke Agent Selector to recommend participants for an activity.
        
        Args:
            session_id: Session ID
            activity: Activity details (goal, description)
            candidates: List of candidate agents from marketplace
            
        Returns:
            Agent Selector recommendations
        """
        agent_id = "agent-selector-v1"
        
        # Find compute instance with Agent Selector
        compute_url = await self._find_agent_location(agent_id)
        if not compute_url:
            raise ValueError(f"Agent Selector not available on any compute instance")
        
        # Build prompt for Agent Selector
        prompt = self._build_agent_selector_prompt(activity, candidates)
        
        # Execute agent
        result = await self._execute_agent_on_compute(
            agent_id=agent_id,
            compute_url=compute_url,
            prompt=prompt,
            session_id=session_id,
            context={"activity_id": activity.get("activity_id")}
        )
        
        return result
    
    def _build_agent_selector_prompt(
        self,
        activity: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for Agent Selector."""
        return f"""Activity Goal: {activity.get('goal', '')}
Activity Description: {activity.get('description', 'N/A')}

Candidate Agents:
{json.dumps(candidates, indent=2)}

Analyze the activity and recommend which agent(s) would be best suited to accomplish it.

Consider:
- Capability match (do they have the required skills?)
- Specialization depth (focused experts vs generalists)
- Domain expertise (relevant business knowledge)

Output as JSON:
{{
  "required_capabilities": ["cap1", "cap2"],
  "domain_expertise": "domain_name",
  "recommended_primary": "agent-id",
  "recommended_backup": "agent-id",
  "reasoning": "Why these agents (be specific)"
}}"""
    
    def parse_agent_selector_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Agent Selector output.
        
        Args:
            result: Raw result from agent execution
            
        Returns:
            Parsed recommendations
        """
        try:
            # Extract result from agent response
            if "output" in result and "content" in result["output"]:
                result_text = result["output"]["content"]
            elif "result" in result:
                result_text = result["result"]
            elif "response" in result:
                result_text = result["response"]
            else:
                result_text = str(result)
            
            # Try to parse as JSON
            if isinstance(result_text, str):
                # Remove markdown code blocks if present
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                
                parsed = json.loads(result_text)
            else:
                parsed = result_text
            
            return parsed
        
        except Exception as e:
            logger.error(f"Error parsing Agent Selector output: {e}")
            logger.error(f"Raw output: {result}")
            raise ValueError(f"Failed to parse Agent Selector output: {e}")
    
    async def invoke_activity_facilitator(
        self,
        session_id: str,
        activity: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        current_situation: str,
        assigned_agents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Invoke Activity Facilitator to orchestrate next exchange.
        
        Args:
            session_id: Session ID
            activity: Activity details
            conversation_history: Previous exchanges
            current_situation: Current state description
            assigned_agents: Agents assigned to this activity
            
        Returns:
            Facilitator's decision (intent, next_prompt, outcome assessment)
        """
        agent_id = "activity-facilitator-v1"
        
        # Find compute instance with Activity Facilitator
        compute_url = await self._find_agent_location(agent_id)
        if not compute_url:
            raise ValueError(f"Activity Facilitator not available on any compute instance")
        
        # Build prompt for Activity Facilitator
        prompt = self._build_facilitator_prompt(
            activity,
            conversation_history,
            current_situation,
            assigned_agents
        )
        
        # Execute agent
        result = await self._execute_agent_on_compute(
            agent_id=agent_id,
            compute_url=compute_url,
            prompt=prompt,
            session_id=session_id,
            context={"activity_id": activity.get("activity_id")}
        )
        
        return result
    
    def _build_facilitator_prompt(
        self,
        activity: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        current_situation: str,
        assigned_agents: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for Activity Facilitator."""
        return f"""Activity Goal: {activity.get('goal', '')}
Activity Description: {activity.get('description', 'N/A')}

Conversation History:
{json.dumps(conversation_history, indent=2) if conversation_history else "No previous exchanges"}

Current Situation:
{current_situation}

Assigned Agents:
{json.dumps(assigned_agents, indent=2)}

As the Activity Facilitator, determine the next exchange to move this activity forward.

Output as JSON:
{{
  "intent": "inform|request|clarify|assess|conclude",
  "next_prompt": "Message for the agent (or null if concluding)",
  "target_agent": "agent-id (or null)",
  "outcome_assessment": {{
    "goal_met": true|false,
    "blocker_detected": true|false,
    "blocker_description": "description if blocked",
    "progress_summary": "brief summary"
  }},
  "reasoning": "why this step"
}}"""
    
    def parse_facilitator_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Activity Facilitator output.
        
        Args:
            result: Raw result from agent execution
            
        Returns:
            Parsed facilitation decision
        """
        try:
            # Extract result from agent response
            # Check for output.content structure first (standard agent response)
            if "output" in result and isinstance(result["output"], dict):
                result_text = result["output"].get("content", "")
            elif "result" in result:
                result_text = result["result"]
            elif "response" in result:
                result_text = result["response"]
            else:
                result_text = str(result)
            
            # Try to parse as JSON
            if isinstance(result_text, str):
                # Remove markdown code blocks if present
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                
                parsed = json.loads(result_text)
            else:
                parsed = result_text
            
            return parsed
        
        except Exception as e:
            logger.error(f"Error parsing Activity Facilitator output: {e}")
            logger.error(f"Raw output: {result}")
            raise ValueError(f"Failed to parse Activity Facilitator output: {e}")
    
    async def record_event(
        self,
        session_id: str,
        event_type: str,
        agent_id: str,
        data: Dict[str, Any]
    ):
        """
        Record a coordinating event to the event bus.
        
        Args:
            session_id: Session ID
            event_type: Type of event (e.g., "consistency_check", "progress_report")
            agent_id: Which coordinating agent created this event
            data: Event data
        """
        event = {
            "event_id": f"evt-{datetime.now(timezone.utc).timestamp()}",
            "session_id": session_id,
            "event_type": event_type,
            "agent_id": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        
        # Append to session events file
        events_file = self.events_path / f"{session_id}_events.jsonl"
        with open(events_file, 'a') as f:
            f.write(json.dumps(event) + "\n")
        
        logger.info(f"Recorded event {event_type} from {agent_id} for session {session_id}")
    
    async def get_events(
        self,
        session_id: str,
        event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get events for a session.
        
        Args:
            session_id: Session ID
            event_type: Optional filter by event type
            
        Returns:
            List of events
        """
        events_file = self.events_path / f"{session_id}_events.jsonl"
        if not events_file.exists():
            return []
        
        events = []
        with open(events_file, 'r') as f:
            for line in f:
                event = json.loads(line.strip())
                if event_type is None or event.get("event_type") == event_type:
                    events.append(event)
        
        return events
    
    async def invoke_consistency_manager(
        self,
        session_id: str,
        activities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Invoke Consistency Manager to detect contradictions across activities.
        
        Args:
            session_id: Session ID
            activities: List of activities with their exchanges
            
        Returns:
            Consistency analysis
        """
        agent_id = "consistency-manager-v1"
        
        # Find compute instance
        compute_url = await self._find_agent_location(agent_id)
        if not compute_url:
            raise ValueError(f"Consistency Manager not available")
        
        # Build prompt
        prompt = f"""Analyze these activities for contradictions and inconsistencies:

{json.dumps(activities, indent=2)}

Output as JSON with detected inconsistencies."""
        
        # Execute agent
        result = await self._execute_agent_on_compute(
            agent_id=agent_id,
            compute_url=compute_url,
            prompt=prompt,
            session_id=session_id,
            context={}
        )
        
        # Record event
        parsed = self._parse_json_output(result)
        await self.record_event(
            session_id=session_id,
            event_type="consistency_check",
            agent_id=agent_id,
            data=parsed
        )
        
        return parsed
    
    async def invoke_progress_reporter(
        self,
        session_id: str,
        business_goal: str,
        activities: List[Dict[str, Any]],
        inconsistencies: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Invoke Progress Reporter to synthesize status.
        
        Args:
            session_id: Session ID
            business_goal: Original business goal
            activities: List of activities with status
            inconsistencies: Any detected inconsistencies
            
        Returns:
            Progress report
        """
        agent_id = "progress-reporter-v1"
        
        # Find compute instance
        compute_url = await self._find_agent_location(agent_id)
        if not compute_url:
            raise ValueError(f"Progress Reporter not available")
        
        # Build prompt
        prompt = f"""Generate a progress report for this session.

Business Goal: {business_goal}

Activities:
{json.dumps(activities, indent=2)}

{f"Inconsistencies: {json.dumps(inconsistencies, indent=2)}" if inconsistencies else "No inconsistencies detected."}

Output as JSON with executive_summary, progress_by_activity, blockers, risks, overall_health, completion_estimate."""
        
        # Execute agent
        result = await self._execute_agent_on_compute(
            agent_id=agent_id,
            compute_url=compute_url,
            prompt=prompt,
            session_id=session_id,
            context={}
        )
        
        # Record event
        parsed = self._parse_json_output(result)
        await self.record_event(
            session_id=session_id,
            event_type="progress_report",
            agent_id=agent_id,
            data=parsed
        )
        
        return parsed
    
    async def invoke_result_synthesizer(
        self,
        session_id: str,
        business_goal: str,
        activities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Invoke Result Synthesizer to create final deliverable.
        
        Args:
            session_id: Session ID
            business_goal: Original business goal
            activities: List of completed activities with results
            
        Returns:
            Final deliverable
        """
        agent_id = "result-synthesizer-v1"
        
        # Find compute instance
        compute_url = await self._find_agent_location(agent_id)
        if not compute_url:
            raise ValueError(f"Result Synthesizer not available")
        
        # Build prompt
        prompt = f"""Synthesize the final deliverable for this session.

Business Goal: {business_goal}

Activities with Results:
{json.dumps(activities, indent=2)}

Output as JSON with deliverable (title, executive_summary, key_findings, recommendations, detailed_results), quality_assessment, next_steps."""
        
        # Execute agent
        result = await self._execute_agent_on_compute(
            agent_id=agent_id,
            compute_url=compute_url,
            prompt=prompt,
            session_id=session_id,
            context={}
        )
        
        # Record event
        parsed = self._parse_json_output(result)
        await self.record_event(
            session_id=session_id,
            event_type="result_synthesis",
            agent_id=agent_id,
            data=parsed
        )
        
        return parsed
    
    def _parse_json_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON output from any coordinating agent."""
        try:
            # Check standard agent response format first
            if "output" in result and isinstance(result["output"], dict):
                if "content" in result["output"]:
                    result_text = result["output"]["content"]
                else:
                    result_text = str(result["output"])
            elif "result" in result:
                result_text = result["result"]
            elif "response" in result:
                result_text = result["response"]
            else:
                result_text = str(result)
            
            if isinstance(result_text, str):
                # Remove markdown code blocks
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                
                parsed = json.loads(result_text)
            else:
                parsed = result_text
            
            return parsed
        
        except Exception as e:
            logger.error(f"Error parsing agent output: {e}")
            logger.error(f"Raw output: {result}")
            return {"error": str(e), "raw_output": str(result)}
    
    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()


# Global instance
_coordinating_team_service: Optional[CoordinatingTeamService] = None


def get_coordinating_team_service() -> CoordinatingTeamService:
    """Get global coordinating team service instance."""
    global _coordinating_team_service
    if _coordinating_team_service is None:
        _coordinating_team_service = CoordinatingTeamService()
    return _coordinating_team_service


def set_coordinating_team_service(service: CoordinatingTeamService):
    """Set global coordinating team service instance."""
    global _coordinating_team_service
    _coordinating_team_service = service

