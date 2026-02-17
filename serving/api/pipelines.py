"""Execution pipeline API endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional

from models.pipeline import PipelineRequest, ExecutionPipeline
from services.pipeline_service import PipelineService
from services.registry_service import ComputeRegistry, get_compute_registry


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def get_pipeline_service(registry: ComputeRegistry = Depends(get_compute_registry)) -> PipelineService:
    """Dependency injection for pipeline service."""
    return PipelineService(registry)


@router.post("/execute-from-goal", response_model=ExecutionPipeline)
async def execute_from_goal(
    request: PipelineRequest,
    service: PipelineService = Depends(get_pipeline_service)
):
    """
    Complete pipeline execution from business goal.
    
    This endpoint demonstrates the full execution pipeline concept:
    
    1. **Coordinating Team Phase**:
       - Queries available agents from compute registry
       - Invokes pipeline-builder agent to create execution plan
       - Parses response into structured pipeline
    
    2. **Execution Phase**:
       - Executes each step in order
       - Respects dependencies between steps
       - Routes to appropriate compute instances
       - Stores results in session context
    
    3. **Result Phase**:
       - Aggregates all step outputs
       - Returns complete pipeline with results
    
    **Example Request**:
    ```json
    {
      "goal": "Analyze Q4 2024 sales and create executive report",
      "context": {
        "data_source": "sales_q4_2024.csv",
        "target_audience": "Senior Leadership"
      }
    }
    ```
    
    **Returns**: Complete ExecutionPipeline with all steps and results
    """
    try:
        logger.info(f"Pipeline request received: {request.goal}")
        
        # Build and execute pipeline
        pipeline = await service.build_and_execute_pipeline(
            goal=request.goal,
            context=request.context
        )
        
        logger.info(
            f"Pipeline {pipeline.pipeline_id} completed with status: {pipeline.status}"
        )
        
        return pipeline
        
    except ValueError as e:
        logger.error(f"Pipeline validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution failed: {str(e)}"
        )


@router.get("/demo/business-process", response_model=ExecutionPipeline)
async def demo_business_process(
    service: PipelineService = Depends(get_pipeline_service)
):
    """
    Demo endpoint: Run complete business process with execution pipeline.
    
    This demonstrates the full concept with a realistic business scenario:
    - Business goal: Analyze Q4 sales and create executive report
    - Uses coordinating team to build pipeline
    - Executes data analysis then report generation
    - Returns structured results
    
    **No parameters needed** - uses demo data
    
    **Returns**: Complete ExecutionPipeline showing the full workflow
    """
    try:
        logger.info("Demo business process started")
        
        # Demo goal and context
        goal = "Analyze Q4 2024 sales performance and generate a comprehensive executive report"
        context = {
            "data_source": "sales_q4_2024.csv",
            "date_range": "October 1 - December 31, 2024",
            "data_summary": {
                "total_records": 95,
                "total_revenue": 24127.50,
                "regions": ["West", "East", "Central", "South"],
                "categories": ["Electronics", "Tools"]
            },
            "target_audience": "Senior Leadership Team",
            "report_requirements": {
                "format": "Executive Summary",
                "length": "3-4 pages",
                "tone": "Professional and data-driven"
            }
        }
        
        # Execute full pipeline
        pipeline = await service.build_and_execute_pipeline(
            goal=goal,
            context=context,
            session_id="demo-session-001"
        )
        
        logger.info(f"Demo pipeline completed: {pipeline.status}")
        
        return pipeline
        
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Demo execution failed: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Health check for pipeline service."""
    return {
        "status": "healthy",
        "service": "pipeline-orchestration",
        "features": [
            "coordinating_team",
            "pipeline_building",
            "pipeline_execution",
            "dependency_management"
        ]
    }

