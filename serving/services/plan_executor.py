"""Plan Executor Service for Slim Claude Code.

Executes approved work plans by creating issues in dependency order,
mapping temporary IDs to real IDs, and maintaining audit trail.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from models.goal_decomposer import DecomposedIssue, GoalDecompositionResult
from models.issue import Issue, IssueArea, IssuePriority, IssueStatus, IssueType
from models.plan_executor import (
    ApprovalRecord,
    ExecutionError,
    ExecutionStatus,
    IssueBatchCreateResponse,
    IssueMapping,
    PlanExecutorConfig,
)
from models.work_planner import WorkPlan

logger = logging.getLogger(__name__)


class IssueServiceProtocol(Protocol):
    """Protocol for issue service operations."""

    async def create_issue(
        self,
        title: str,
        description: str,
        issue_type: IssueType,
        area: IssueArea,
        priority: IssuePriority,
        goal_id: Optional[str] = None,
        blocked_by: Optional[List[str]] = None,
        required_skills: Optional[List[str]] = None,
        required_tools: Optional[List[str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
    ) -> Issue:
        """Create a new issue."""
        ...

    async def delete_issue(self, issue_id: str) -> bool:
        """Delete an issue by ID."""
        ...


class StorageProtocol(Protocol):
    """Protocol for storing decompositions and plans."""

    async def get_decomposition(
        self, decomposition_id: str
    ) -> Optional[GoalDecompositionResult]:
        """Retrieve a stored decomposition."""
        ...

    async def get_plan(self, plan_id: str) -> Optional[WorkPlan]:
        """Retrieve a stored plan."""
        ...

    async def store_execution(
        self, goal_id: str, response: IssueBatchCreateResponse
    ) -> None:
        """Store execution result."""
        ...


class InMemoryStorage:
    """Simple in-memory storage for decompositions and plans.

    For testing and development. Production should use Redis or database.
    """

    def __init__(self):
        self._decompositions: Dict[str, GoalDecompositionResult] = {}
        self._plans: Dict[str, WorkPlan] = {}
        self._executions: Dict[str, IssueBatchCreateResponse] = {}

    async def store_decomposition(
        self, decomposition: GoalDecompositionResult
    ) -> None:
        """Store a decomposition result."""
        self._decompositions[decomposition.decomposition_id] = decomposition

    async def get_decomposition(
        self, decomposition_id: str
    ) -> Optional[GoalDecompositionResult]:
        """Retrieve a stored decomposition."""
        return self._decompositions.get(decomposition_id)

    async def store_plan(self, plan: WorkPlan) -> None:
        """Store a work plan."""
        self._plans[plan.plan_id] = plan

    async def get_plan(self, plan_id: str) -> Optional[WorkPlan]:
        """Retrieve a stored plan."""
        return self._plans.get(plan_id)

    async def store_execution(
        self, goal_id: str, response: IssueBatchCreateResponse
    ) -> None:
        """Store execution result."""
        self._executions[goal_id] = response

    async def get_execution(
        self, goal_id: str
    ) -> Optional[IssueBatchCreateResponse]:
        """Retrieve execution result."""
        return self._executions.get(goal_id)


class PlanExecutionError(Exception):
    """Raised when plan execution fails."""

    def __init__(
        self,
        message: str,
        errors: Optional[List[ExecutionError]] = None,
        created_issues: Optional[List[IssueMapping]] = None,
    ):
        self.message = message
        self.errors = errors or []
        self.created_issues = created_issues or []
        super().__init__(message)


class PlanNotFoundError(Exception):
    """Raised when a plan is not found."""
    pass


class DecompositionNotFoundError(Exception):
    """Raised when a decomposition is not found."""
    pass


class PlanExecutorService:
    """Service for executing approved work plans.

    Creates issues from decomposition in dependency order,
    maps temporary IDs to real IDs, and logs approval.
    """

    def __init__(
        self,
        issue_service: Optional[IssueServiceProtocol] = None,
        storage: Optional[StorageProtocol] = None,
        config: Optional[PlanExecutorConfig] = None,
    ):
        """Initialize the Plan Executor service.

        Args:
            issue_service: Service for creating issues
            storage: Storage for decompositions and plans
            config: Service configuration
        """
        self._issue_service = issue_service
        self._storage = storage or InMemoryStorage()
        self._config = config or PlanExecutorConfig()

    def set_issue_service(self, issue_service: IssueServiceProtocol) -> None:
        """Set the issue service (for dependency injection)."""
        self._issue_service = issue_service

    async def execute_plan(
        self,
        goal_id: str,
        plan_id: str,
        approved_by: str,
        approval_notes: Optional[str] = None,
        decomposition: Optional[GoalDecompositionResult] = None,
        plan: Optional[WorkPlan] = None,
    ) -> IssueBatchCreateResponse:
        """Execute an approved plan by creating issues.

        Args:
            goal_id: Goal ID to execute
            plan_id: Plan ID to execute
            approved_by: User ID approving execution
            approval_notes: Optional notes from approver
            decomposition: Optional decomposition (fetched from storage if not provided)
            plan: Optional plan (fetched from storage if not provided)

        Returns:
            IssueBatchCreateResponse with created issue mappings

        Raises:
            PlanNotFoundError: If plan is not found
            DecompositionNotFoundError: If decomposition is not found
            PlanExecutionError: If execution fails
        """
        if self._issue_service is None:
            raise ValueError("Issue service not configured")

        start_time = time.time()

        # Retrieve plan if not provided
        if plan is None:
            plan = await self._storage.get_plan(plan_id)
            if plan is None:
                raise PlanNotFoundError(f"Plan {plan_id} not found")

        # Retrieve decomposition if not provided
        if decomposition is None:
            decomposition = await self._storage.get_decomposition(
                plan.decomposition_id
            )
            if decomposition is None:
                raise DecompositionNotFoundError(
                    f"Decomposition {plan.decomposition_id} not found"
                )

        # Create approval record
        approval = ApprovalRecord(
            approved_by=approved_by,
            plan_id=plan_id,
            goal_id=goal_id,
            notes=approval_notes,
        )

        logger.info(
            f"Executing plan {plan_id} for goal {goal_id} "
            f"(approved by {approved_by})"
        )

        # Build issue lookup map
        issue_map = {issue.temp_id: issue for issue in decomposition.issues}

        # Track created issues and errors
        created_issues: List[IssueMapping] = []
        errors: List[ExecutionError] = []
        id_mapping: Dict[str, str] = {}  # temp_id -> real_id

        try:
            # Create issues in phase order
            for phase in plan.phases:
                for temp_id in phase.issues:
                    decomposed_issue = issue_map.get(temp_id)
                    if decomposed_issue is None:
                        error = ExecutionError(
                            temp_id=temp_id,
                            error_message=f"Issue {temp_id} not found in decomposition",
                            phase_number=phase.phase_number,
                        )
                        errors.append(error)
                        if not self._config.continue_on_error:
                            raise PlanExecutionError(
                                f"Issue {temp_id} not found",
                                errors=errors,
                                created_issues=created_issues,
                            )
                        continue

                    try:
                        # Create the issue
                        created = await self._create_issue(
                            decomposed_issue=decomposed_issue,
                            goal_id=goal_id,
                            id_mapping=id_mapping,
                        )

                        # Record mapping
                        mapping = IssueMapping(
                            temp_id=temp_id,
                            issue_id=created.id,
                            title=created.title,
                            phase_number=phase.phase_number,
                        )
                        created_issues.append(mapping)
                        id_mapping[temp_id] = created.id

                        logger.debug(
                            f"Created issue {created.id} from {temp_id} "
                            f"in phase {phase.phase_number}"
                        )

                    except Exception as e:
                        error = ExecutionError(
                            temp_id=temp_id,
                            error_message=str(e),
                            phase_number=phase.phase_number,
                        )
                        errors.append(error)
                        logger.error(f"Failed to create issue {temp_id}: {e}")

                        if not self._config.continue_on_error:
                            raise PlanExecutionError(
                                f"Failed to create issue {temp_id}",
                                errors=errors,
                                created_issues=created_issues,
                            )

        except PlanExecutionError:
            # Rollback if configured
            rolled_back = []
            if self._config.rollback_on_failure and created_issues:
                rolled_back = await self._rollback_issues(created_issues)

            execution_time = int((time.time() - start_time) * 1000)

            response = IssueBatchCreateResponse(
                success=False,
                goal_id=goal_id,
                plan_id=plan_id,
                decomposition_id=plan.decomposition_id,
                status=ExecutionStatus.ROLLED_BACK if rolled_back else ExecutionStatus.FAILED,
                created_issues=created_issues,
                approval=approval,
                errors=errors,
                rolled_back_issues=rolled_back,
                execution_duration_ms=execution_time,
            )

            await self._storage.store_execution(goal_id, response)
            return response

        execution_time = int((time.time() - start_time) * 1000)

        response = IssueBatchCreateResponse(
            success=len(errors) == 0,
            goal_id=goal_id,
            plan_id=plan_id,
            decomposition_id=plan.decomposition_id,
            status=ExecutionStatus.COMPLETED if len(errors) == 0 else ExecutionStatus.FAILED,
            created_issues=created_issues,
            approval=approval,
            errors=errors,
            execution_duration_ms=execution_time,
        )

        await self._storage.store_execution(goal_id, response)

        logger.info(
            f"Plan execution completed: {len(created_issues)} issues created, "
            f"{len(errors)} errors, {execution_time}ms"
        )

        return response

    async def _create_issue(
        self,
        decomposed_issue: DecomposedIssue,
        goal_id: str,
        id_mapping: Dict[str, str],
    ) -> Issue:
        """Create a single issue from a DecomposedIssue.

        Args:
            decomposed_issue: The decomposed issue to create
            goal_id: Parent goal ID
            id_mapping: Current temp_id to real_id mapping

        Returns:
            Created Issue
        """
        # Map string types to enums
        type_map = {
            "feature": IssueType.FEATURE,
            "bug": IssueType.BUG,
            "refactor": IssueType.REFACTOR,
            "test": IssueType.TEST,
            "docs": IssueType.DOCS,
        }
        issue_type = type_map.get(decomposed_issue.issue_type, IssueType.FEATURE)

        area_map = {
            "api": IssueArea.API,
            "database": IssueArea.DATABASE,
            "frontend": IssueArea.FRONTEND,
            "infra": IssueArea.INFRA,
        }
        area = area_map.get(decomposed_issue.area, IssueArea.API)

        priority_map = {
            "P0": IssuePriority.P0,
            "P1": IssuePriority.P1,
            "P2": IssuePriority.P2,
            "P3": IssuePriority.P3,
        }
        priority = priority_map.get(decomposed_issue.priority, IssuePriority.P2)

        # Resolve dependencies to real IDs
        real_blocked_by = [
            id_mapping[dep]
            for dep in decomposed_issue.blocked_by
            if dep in id_mapping
        ]

        return await self._issue_service.create_issue(
            title=decomposed_issue.title,
            description=decomposed_issue.description,
            issue_type=issue_type,
            area=area,
            priority=priority,
            goal_id=goal_id,
            blocked_by=real_blocked_by,
            required_skills=decomposed_issue.required_skills,
            required_tools=decomposed_issue.required_tools,
            acceptance_criteria=decomposed_issue.acceptance_criteria,
        )

    async def _rollback_issues(
        self,
        created_issues: List[IssueMapping],
    ) -> List[str]:
        """Rollback created issues on failure.

        Args:
            created_issues: List of created issue mappings

        Returns:
            List of successfully rolled back issue IDs
        """
        rolled_back = []

        # Rollback in reverse order
        for mapping in reversed(created_issues):
            try:
                await self._issue_service.delete_issue(mapping.issue_id)
                rolled_back.append(mapping.issue_id)
                logger.debug(f"Rolled back issue {mapping.issue_id}")
            except Exception as e:
                logger.error(
                    f"Failed to rollback issue {mapping.issue_id}: {e}"
                )

        logger.info(f"Rolled back {len(rolled_back)} issues")
        return rolled_back

    async def store_decomposition(
        self,
        decomposition: GoalDecompositionResult,
    ) -> None:
        """Store a decomposition for later execution.

        Args:
            decomposition: Decomposition result to store
        """
        await self._storage.store_decomposition(decomposition)

    async def store_plan(self, plan: WorkPlan) -> None:
        """Store a plan for later execution.

        Args:
            plan: Work plan to store
        """
        await self._storage.store_plan(plan)

    async def get_decomposition(
        self,
        decomposition_id: str,
    ) -> Optional[GoalDecompositionResult]:
        """Retrieve a stored decomposition.

        Args:
            decomposition_id: ID of the decomposition

        Returns:
            GoalDecompositionResult if found, None otherwise
        """
        return await self._storage.get_decomposition(decomposition_id)

    async def get_plan(self, plan_id: str) -> Optional[WorkPlan]:
        """Retrieve a stored plan.

        Args:
            plan_id: ID of the plan

        Returns:
            WorkPlan if found, None otherwise
        """
        return await self._storage.get_plan(plan_id)


# Global service instance
_plan_executor_service: Optional[PlanExecutorService] = None


def get_plan_executor_service() -> PlanExecutorService:
    """Get the global Plan Executor service instance."""
    global _plan_executor_service
    if _plan_executor_service is None:
        _plan_executor_service = PlanExecutorService()
    return _plan_executor_service


def set_plan_executor_service(service: Optional[PlanExecutorService]) -> None:
    """Set the global Plan Executor service instance."""
    global _plan_executor_service
    _plan_executor_service = service
