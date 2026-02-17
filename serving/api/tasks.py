"""Task submission and execution endpoints."""

import logging
import httpx
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.registry_service import get_compute_registry, ComputeRegistry


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskSubmissionRequest(BaseModel):
    """Request to submit a task to an agent."""
    agent_id: str
    prompt: str
    context: Optional[Dict[str, Any]] = None
    output_format: Optional[str] = "text"
    llm_config: Optional[Dict[str, Any]] = None
    target_instance_id: Optional[str] = None


class TaskSubmissionResponse(BaseModel):
    """Response from task submission."""
    task_id: str
    agent_id: str
    status: str
    compute_instance_id: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    agent_definition: Optional[Dict[str, Any]] = None


@router.post("/submit", response_model=TaskSubmissionResponse)
async def submit_task(
    request: TaskSubmissionRequest,
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Submit a task to be executed by a compute instance.
    
    This endpoint:
    1. Finds a suitable compute instance (by target_instance_id or agent capability)
    2. Routes the task to that instance
    3. Returns the execution result
    """
    try:
        # Find target compute instance
        if request.target_instance_id:
            # Use specified instance
            instance = registry.get_instance(request.target_instance_id)
            if not instance:
                raise HTTPException(
                    status_code=404,
                    detail=f"Compute instance not found: {request.target_instance_id}"
                )
            if instance.status != "online":
                raise HTTPException(
                    status_code=503,
                    detail=f"Compute instance is {instance.status}"
                )
        else:
            # Find instance with the required agent
            instances = await registry.list_instances()
            suitable_instances = [
                inst for inst in instances
                if inst.status == "online" and request.agent_id in inst.capabilities.agents
            ]
            
            if not suitable_instances:
                raise HTTPException(
                    status_code=404,
                    detail=f"No online compute instance found with agent: {request.agent_id}"
                )
            
            # Use the first suitable instance (could add load balancing here)
            instance = suitable_instances[0]
        
        logger.info(
            f"Routing task for agent {request.agent_id} to instance {instance.instance_id}"
        )
        
        # Build execution request
        execution_request = {
            "agent_id": request.agent_id,
            "prompt": request.prompt,
            "context": request.context,
            "output_format": request.output_format,
            "llm_config": request.llm_config
        }
        
        # Call compute instance
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{instance.endpoint}/api/v1/agents/execute",
                json=execution_request
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(
                    f"Compute instance execution failed: {response.status_code} - {error_detail}"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Task execution failed: {error_detail}"
                )
            
            result = response.json()
        
        # Add compute instance info to result
        result["compute_instance_id"] = instance.instance_id
        
        # Debug logging
        logger.info(f"Result from compute instance - output type: {type(result.get('output'))}")
        logger.info(f"Result from compute instance - output keys: {result.get('output', {}).keys() if result.get('output') else None}")
        logger.info(f"Result from compute instance - content length: {len(result.get('output', {}).get('content', '')) if result.get('output') else 0}")
        
        logger.info(
            f"Task {result.get('task_id')} completed on instance {instance.instance_id}"
        )
        
        return TaskSubmissionResponse(**result)
        
    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.error(f"Timeout calling compute instance {instance.instance_id}")
        raise HTTPException(
            status_code=504,
            detail="Task execution timed out"
        )
    except Exception as e:
        logger.error(f"Task submission failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Task submission failed: {str(e)}"
        )


@router.get("/{task_id}")
async def get_task_status(
    task_id: str,
    compute_instance_id: str,
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Get the status of a task from the compute instance.
    
    Note: This requires knowing which compute instance is executing the task.
    In a production system, we'd track this in a database.
    """
    try:
        # Get compute instance
        instance = registry.get_instance(compute_instance_id)
        if not instance:
            raise HTTPException(
                status_code=404,
                detail=f"Compute instance not found: {compute_instance_id}"
            )
        
        # Query task status from compute instance
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{instance.endpoint}/agents/tasks/{task_id}"
            )
            
            if response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Task not found: {task_id}"
                )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to get task status"
                )
            
            return response.json()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get task status: {str(e)}"
        )


@router.post("/demo/business-process")
async def run_demo_business_process(
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """Demo endpoint: Run a complete business process end-to-end.
    
    This demonstrates:
    1. Task planning with the coordinator agent
    2. Data analysis with the data analyst agent
    3. Report generation with the content writer agent
    """
    results = {
        "process": "Q4 Sales Analysis and Reporting",
        "steps": []
    }
    
    try:
        # Step 1: Plan the task
        logger.info("Step 1: Planning task with coordinator agent")
        planning_request = TaskSubmissionRequest(
            agent_id="task-coordinator-v1",
            prompt="""Plan a comprehensive analysis and reporting workflow for Q4 2024 sales data.
            
The goal is to:
1. Analyze sales data from Q4 2024 (Oct-Dec)
2. Identify trends, patterns, and insights
3. Generate an executive report with recommendations

Please create a step-by-step execution plan.""",
            context={
                "available_agents": ["data-analyst-v1", "content-writer-v1"],
                "data_source": "sales_q4_2024.csv",
                "deadline": "End of week"
            }
        )
        
        planning_result = await submit_task(planning_request, registry)
        logger.info(f"Planning result output type: {type(planning_result.output)}")
        logger.info(f"Planning result output keys: {planning_result.output.keys() if planning_result.output else None}")
        logger.info(f"Planning result output content length: {len(planning_result.output.get('content', '')) if planning_result.output else 0}")
        results["steps"].append({
            "step": 1,
            "agent": "task-coordinator-v1",
            "task_id": planning_result.task_id,
            "status": planning_result.status,
            "output": planning_result.output
        })
        
        # Step 2: Analyze the data
        logger.info("Step 2: Analyzing data with data analyst agent")
        analysis_request = TaskSubmissionRequest(
            agent_id="data-analyst-v1",
            prompt="""Analyze the Q4 2024 sales data and provide comprehensive insights.

Please analyze:
- Summary statistics (total revenue, average transaction, etc.)
- Regional performance comparison
- Product category performance
- Time-based trends (monthly patterns)
- Key findings and anomalies

Provide actionable recommendations based on the data.""",
            context={
                "data_file": "sales_q4_2024.csv",
                "date_range": "October 1 - December 31, 2024",
                "data_summary": {
                    "total_records": 95,
                    "regions": ["West", "East", "Central", "South"],
                    "categories": ["Electronics", "Tools"],
                    "total_revenue": 24127.50
                },
                "business_context": "Year-end performance review for strategic planning"
            }
        )
        
        analysis_result = await submit_task(analysis_request, registry)
        results["steps"].append({
            "step": 2,
            "agent": "data-analyst-v1",
            "task_id": analysis_result.task_id,
            "status": analysis_result.status,
            "output": analysis_result.output
        })
        
        # Step 3: Generate executive report
        logger.info("Step 3: Generating report with content writer agent")
        report_request = TaskSubmissionRequest(
            agent_id="content-writer-v1",
            prompt="""Create a professional executive report for Q4 2024 sales performance.

The report should include:
1. Executive Summary (high-level overview)
2. Key Performance Indicators
3. Regional Analysis
4. Product Performance
5. Trends and Insights
6. Strategic Recommendations
7. Conclusion

Write in a professional, business-appropriate tone suitable for senior management.""",
            context={
                "topic": "Q4 2024 Sales Performance Analysis",
                "audience": "Executive Leadership Team",
                "tone": "professional",
                "length": "2-3 pages",
                "sources": {
                    "analysis_results": "Comprehensive Q4 analysis with regional breakdown, product performance, and trend analysis",
                    "key_findings": [
                        "West region leads with 35% of sales",
                        "Smart Watch Pro is top performer at $499",
                        "November showed peak sales (Black Friday effect)",
                        "+15% month-over-month growth trend"
                    ]
                }
            }
        )
        
        report_result = await submit_task(report_request, registry)
        results["steps"].append({
            "step": 3,
            "agent": "content-writer-v1",
            "task_id": report_result.task_id,
            "status": report_result.status,
            "output": report_result.output
        })
        
        # Summary
        results["status"] = "completed"
        results["summary"] = {
            "total_steps": 3,
            "successful_steps": len([s for s in results["steps"] if s["status"] == "completed"]),
            "total_agents_used": 3,
            "compute_instances_used": len(set(
                getattr(result, "compute_instance_id", None) 
                for result in [planning_result, analysis_result, report_result]
                if result and hasattr(result, "compute_instance_id")
            ))
        }
        
        logger.info("Demo business process completed successfully")
        return results
        
    except Exception as e:
        logger.error(f"Demo business process failed: {e}", exc_info=True)
        results["status"] = "failed"
        results["error"] = str(e)
        return results

