"""Pipeline orchestration service - coordinating team + execution engine."""

import logging
import httpx
import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from models.pipeline import (
    ExecutionPipeline,
    PipelineStep,
    PipelineStatus,
    StepStatus
)
from services.registry_service import ComputeRegistry


logger = logging.getLogger(__name__)


class PipelineService:
    """
    Orchestrates the complete pipeline lifecycle:
    1. Coordinating Team - Build pipeline from goal
    2. Pipeline Executor - Execute steps in order
    """
    
    def __init__(self, registry: ComputeRegistry):
        """Initialize pipeline service.
        
        Args:
            registry: Compute registry for finding instances
        """
        self.registry = registry
    
    async def build_and_execute_pipeline(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> ExecutionPipeline:
        """Build pipeline from goal and execute it end-to-end.
        
        This is the main entry point that demonstrates the full concept:
        1. Coordinating team builds pipeline
        2. Pipeline executor runs it
        3. Results aggregated and returned
        
        Args:
            goal: Business goal to achieve
            context: Optional additional context
            session_id: Optional session ID
            
        Returns:
            Completed ExecutionPipeline with all results
        """
        logger.info(f"Starting pipeline for goal: {goal}")
        
        # Phase 1: Build Pipeline (Coordinating Team)
        pipeline = await self._build_pipeline(
            goal=goal,
            context=context or {},
            session_id=session_id
        )
        
        logger.info(f"Pipeline built with {len(pipeline.steps)} steps")
        
        # Phase 2: Execute Pipeline
        pipeline = await self._execute_pipeline(pipeline)
        
        logger.info(f"Pipeline execution complete: {pipeline.status}")
        
        return pipeline
    
    async def _build_pipeline(
        self,
        goal: str,
        context: Dict[str, Any],
        session_id: Optional[str]
    ) -> ExecutionPipeline:
        """Coordinating Team: Build execution pipeline from goal.
        
        This simulates the coordinating team:
        1. Query available agents
        2. Invoke pipeline-builder agent
        3. Parse response into ExecutionPipeline
        4. Validate structure
        
        Args:
            goal: Business goal
            context: Execution context
            session_id: Optional session ID
            
        Returns:
            ExecutionPipeline ready to execute
        """
        logger.info("Coordinating team: Building pipeline")
        
        # Step 1: Get available agents from registry
        available_agents = await self._get_available_agents()
        
        logger.debug(f"Found {len(available_agents)} available agents")
        
        # Step 2: Invoke pipeline-builder agent to create plan
        pipeline_json = await self._invoke_pipeline_builder(
            goal=goal,
            available_agents=available_agents,
            context=context
        )
        
        # Step 3: Parse into ExecutionPipeline
        pipeline = self._parse_pipeline_response(
            pipeline_json=pipeline_json,
            goal=goal,
            session_id=session_id or f"session-{uuid.uuid4().hex[:8]}"
        )
        
        logger.info(f"Pipeline created: {pipeline.pipeline_id}")
        
        return pipeline
    
    async def _get_available_agents(self) -> List[Dict[str, Any]]:
        """Query compute registry for available agents.
        
        Returns:
            List of available agents with metadata
        """
        instances = self.registry.list_instances()
        
        available_agents = []
        for instance in instances:
            if instance.status != "online":
                continue
            
            for agent_id in instance.capabilities.agents:
                available_agents.append({
                    "agent_id": agent_id,
                    "compute_instance": instance.instance_id,
                    "endpoint": instance.endpoint
                })
        
        return available_agents
    
    async def _invoke_pipeline_builder(
        self,
        goal: str,
        available_agents: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke pipeline-builder agent to create execution plan.
        
        Args:
            goal: Business goal
            available_agents: List of available agents
            context: Additional context
            
        Returns:
            Pipeline JSON from agent
        """
        logger.info("Invoking pipeline-builder agent")
        
        # Find compute instance with pipeline-builder
        instances = self.registry.list_instances()
        builder_instance = None
        
        for instance in instances:
            if instance.status == "online" and "pipeline-builder-v1" in instance.capabilities.agents:
                builder_instance = instance
                break
        
        if not builder_instance:
            raise ValueError("No online compute instance found with pipeline-builder-v1")
        
        # Build prompt for pipeline builder
        agent_list = "\n".join([f"- {a['agent_id']}" for a in available_agents])
        
        prompt = f"""Build an execution pipeline for this business goal:

GOAL: {goal}

AVAILABLE AGENTS:
{agent_list}

CONTEXT:
{json.dumps(context, indent=2)}

Please create a structured execution plan that:
1. Breaks down the goal into steps
2. Assigns the right agent to each step
3. Defines dependencies between steps
4. Provides clear prompts for each agent

Return your response as JSON following the expected format."""
        
        # Call pipeline-builder agent
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{builder_instance.endpoint}/agents/execute",
                json={
                    "agent_id": "pipeline-builder-v1",
                    "prompt": prompt,
                    "context": {
                        "available_agents": available_agents,
                        "goal": goal
                    },
                    "output_format": "json"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Pipeline builder failed: {response.text}")
            
            result = response.json()
            content = result.get("output", {}).get("content", "")
            
            # Parse JSON from content
            try:
                pipeline_data = json.loads(content)
                return pipeline_data.get("pipeline", pipeline_data)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse pipeline JSON: {content}")
                raise
    
    def _parse_pipeline_response(
        self,
        pipeline_json: Dict[str, Any],
        goal: str,
        session_id: str
    ) -> ExecutionPipeline:
        """Parse pipeline builder's JSON into ExecutionPipeline model.
        
        Args:
            pipeline_json: JSON from pipeline builder
            goal: Business goal
            session_id: Session ID
            
        Returns:
            ExecutionPipeline object
        """
        pipeline_id = f"pipeline-{uuid.uuid4().hex[:8]}"
        
        steps = []
        for step_data in pipeline_json.get("steps", []):
            step = PipelineStep(
                step_id=f"step-{step_data['order']}",
                order=step_data["order"],
                agent_id=step_data["agent_id"],
                agent_name=step_data.get("agent_name", step_data["agent_id"]),
                description=step_data.get("description", ""),
                prompt=step_data.get("prompt", ""),
                context={},
                output_key=step_data.get("output_key", f"step_{step_data['order']}_output"),
                dependencies=step_data.get("dependencies", []),
                target_compute=step_data.get("target_compute"),
                status=StepStatus.PENDING
            )
            steps.append(step)
        
        pipeline = ExecutionPipeline(
            pipeline_id=pipeline_id,
            session_id=session_id,
            goal=goal,
            steps=steps,
            status=PipelineStatus.PENDING,
            created_by="pipeline-builder-v1",
            metadata={
                "reasoning": pipeline_json.get("reasoning", ""),
                "original_goal": goal
            }
        )
        
        return pipeline
    
    async def _execute_pipeline(self, pipeline: ExecutionPipeline) -> ExecutionPipeline:
        """Execute all steps in the pipeline.
        
        Args:
            pipeline: Pipeline to execute
            
        Returns:
            Updated pipeline with results
        """
        logger.info(f"Executing pipeline {pipeline.pipeline_id}")
        
        pipeline.status = PipelineStatus.EXECUTING
        session_outputs = {}  # Store outputs for dependencies
        
        # Execute steps in order
        for step in sorted(pipeline.steps, key=lambda s: s.order):
            logger.info(f"Executing step {step.step_id}: {step.agent_id}")
            
            try:
                # Check dependencies
                if not self._check_dependencies(step, pipeline, session_outputs):
                    step.status = StepStatus.FAILED
                    step.error = "Dependencies not satisfied"
                    continue
                
                # Mark running
                pipeline.mark_step_running(step.step_id)
                
                # Build context with dependency outputs
                step_context = self._build_step_context(step, session_outputs)
                
                # Execute step
                result = await self._execute_step(step, step_context)
                
                # Mark completed
                pipeline.mark_step_completed(step.step_id, result)
                
                # Store output for future steps
                session_outputs[step.output_key] = result.get("output", {}).get("content", "")
                
                logger.info(f"Step {step.step_id} completed successfully")
                
            except Exception as e:
                logger.error(f"Step {step.step_id} failed: {e}")
                pipeline.mark_step_failed(step.step_id, str(e))
                
                # Should we continue or stop?
                # For now, continue but mark pipeline as partially failed
        
        # Finalize pipeline status
        if pipeline.is_complete():
            pipeline.status = PipelineStatus.COMPLETED
            pipeline.final_output = session_outputs
        elif pipeline.has_failures():
            pipeline.status = PipelineStatus.FAILED
        
        logger.info(f"Pipeline execution finished: {pipeline.status}")
        
        return pipeline
    
    def _check_dependencies(
        self,
        step: PipelineStep,
        pipeline: ExecutionPipeline,
        outputs: Dict[str, Any]
    ) -> bool:
        """Check if step dependencies are satisfied.
        
        Args:
            step: Step to check
            pipeline: Full pipeline
            outputs: Completed step outputs
            
        Returns:
            True if dependencies satisfied
        """
        for dep_id in step.dependencies:
            dep_step = pipeline.get_step(dep_id)
            if not dep_step or dep_step.status != StepStatus.COMPLETED:
                return False
        return True
    
    def _build_step_context(
        self,
        step: PipelineStep,
        outputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build context for step, including dependency outputs.
        
        Args:
            step: Step to build context for
            outputs: Previous step outputs
            
        Returns:
            Complete context dict
        """
        context = step.context.copy()
        
        # Add outputs from dependencies
        for dep_id in step.dependencies:
            dep_output_key = dep_id.replace("step-", "step_") + "_output"
            if dep_output_key in outputs:
                context[f"dependency_{dep_id}"] = outputs[dep_output_key]
        
        return context
    
    async def _execute_step(
        self,
        step: PipelineStep,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single pipeline step.
        
        Args:
            step: Step to execute
            context: Execution context
            
        Returns:
            Step result
        """
        # Find compute instance with this agent
        instances = self.registry.list_instances()
        target_instance = None
        
        if step.target_compute:
            target_instance = self.registry.get_instance(step.target_compute)
        else:
            # Find any online instance with this agent
            for instance in instances:
                if instance.status == "online" and step.agent_id in instance.capabilities.agents:
                    target_instance = instance
                    break
        
        if not target_instance:
            raise ValueError(f"No online compute instance found with agent {step.agent_id}")
        
        logger.debug(f"Routing step to {target_instance.instance_id}")
        
        # Execute on compute
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{target_instance.endpoint}/agents/execute",
                json={
                    "agent_id": step.agent_id,
                    "prompt": step.prompt,
                    "context": context,
                    "output_format": "markdown"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Compute execution failed: {response.text}")
            
            return response.json()

