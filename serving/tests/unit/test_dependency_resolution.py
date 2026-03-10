"""Tests for dependency resolution in WorkMapService.

Tests:
- Circular dependency detection on issue creation
- Circular dependency detection on batch creation
- Cascade unlock on issue completion
- AND logic for multiple dependencies
- Initial status calculation based on dependencies
- WorkItem completion → Issue completion → dependency cascade
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from services.work_map_service import WorkMapService
from models.work_map import (
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
    IssueCreateRequest, IssueBatchCreateRequest, IssueResult,
    WorkCreateRequest, WorkStatus,
    GoalCreateRequest
)


@pytest.fixture
def service():
    """Create service without Redis for in-memory testing."""
    return WorkMapService(redis_client=None)


# =============================================================================
# Circular Dependency Detection - Single Issue
# =============================================================================


class TestCircularDependencySingleIssue:
    """Tests for circular dependency detection on single issue creation."""

    @pytest.mark.asyncio
    async def test_no_circular_dependency_allowed(self, service):
        """Test that valid dependencies don't raise errors."""
        # Create A
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A",
            description="First issue"
        ))

        # Create B that depends on A - should work
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B",
            description="Depends on A",
            depends_on=[issue_a.issue_id]
        ))

        assert issue_b.depends_on == [issue_a.issue_id]

    @pytest.mark.asyncio
    async def test_missing_dependency_raises_error(self, service):
        """Test that missing dependencies raise ValueError."""
        with pytest.raises(ValueError, match="Dependencies not found"):
            await service.create_issue(IssueCreateRequest(
                title="Invalid Issue",
                description="Depends on nonexistent",
                depends_on=["nonexistent_id"]
            ))

    @pytest.mark.asyncio
    async def test_multiple_valid_dependencies(self, service):
        """Test that multiple valid dependencies work."""
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A",
            description="First"
        ))
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B",
            description="Second"
        ))

        # C depends on both A and B
        issue_c = await service.create_issue(IssueCreateRequest(
            title="Issue C",
            description="Depends on A and B",
            depends_on=[issue_a.issue_id, issue_b.issue_id]
        ))

        assert len(issue_c.depends_on) == 2


# =============================================================================
# Circular Dependency Detection - Batch Creation
# =============================================================================


class TestCircularDependencyBatch:
    """Tests for circular dependency detection in batch creation."""

    @pytest.fixture
    async def goal(self, service):
        """Create a goal for batch tests."""
        return await service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="For batch tests"
        ))

    @pytest.mark.asyncio
    async def test_batch_with_valid_internal_deps(self, service, goal):
        """Test batch creation with valid internal dependencies."""
        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Issue A",
                    description="First",
                    depends_on=[]
                ),
                IssueCreateRequest(
                    title="Issue B",
                    description="Depends on A",
                    depends_on=[0]  # Depends on index 0 (A)
                ),
                IssueCreateRequest(
                    title="Issue C",
                    description="Depends on B",
                    depends_on=[1]  # Depends on index 1 (B)
                )
            ]
        )

        response = await service.create_issues_batch(request)
        assert len(response.created_issues) == 3

    @pytest.mark.asyncio
    async def test_batch_circular_dependency_self(self, service, goal):
        """Test that self-referential dependency is detected."""
        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Issue A",
                    description="Depends on itself",
                    depends_on=[0]  # Self-reference
                )
            ]
        )

        with pytest.raises(ValueError, match="Circular dependency"):
            await service.create_issues_batch(request)

    @pytest.mark.asyncio
    async def test_batch_circular_dependency_two_items(self, service, goal):
        """Test that A→B→A cycle is detected."""
        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Issue A",
                    description="Depends on B",
                    depends_on=[1]  # A depends on B
                ),
                IssueCreateRequest(
                    title="Issue B",
                    description="Depends on A",
                    depends_on=[0]  # B depends on A - cycle!
                )
            ]
        )

        with pytest.raises(ValueError, match="Circular dependency"):
            await service.create_issues_batch(request)

    @pytest.mark.asyncio
    async def test_batch_circular_dependency_three_items(self, service, goal):
        """Test that A→B→C→A cycle is detected."""
        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Issue A",
                    description="Depends on C",
                    depends_on=[2]  # A depends on C
                ),
                IssueCreateRequest(
                    title="Issue B",
                    description="Depends on A",
                    depends_on=[0]  # B depends on A
                ),
                IssueCreateRequest(
                    title="Issue C",
                    description="Depends on B",
                    depends_on=[1]  # C depends on B - creates A→C→B→A
                )
            ]
        )

        with pytest.raises(ValueError, match="Circular dependency"):
            await service.create_issues_batch(request)

    @pytest.mark.asyncio
    async def test_batch_invalid_index(self, service, goal):
        """Test that invalid batch index raises error."""
        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Issue A",
                    description="Depends on invalid index",
                    depends_on=[5]  # Index out of range
                )
            ]
        )

        with pytest.raises(ValueError, match="Invalid batch index"):
            await service.create_issues_batch(request)

    @pytest.mark.asyncio
    async def test_batch_missing_external_dependency(self, service, goal):
        """Test that missing external dependency raises error."""
        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Issue A",
                    description="Depends on nonexistent",
                    depends_on=["nonexistent_external_id"]
                )
            ]
        )

        with pytest.raises(ValueError, match="External dependency not found"):
            await service.create_issues_batch(request)

    @pytest.mark.asyncio
    async def test_batch_with_valid_external_dependency(self, service, goal):
        """Test batch with valid external dependency."""
        # Create external issue first
        external = await service.create_issue(IssueCreateRequest(
            title="External Issue",
            description="Created separately"
        ))

        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Batch Issue",
                    description="Depends on external",
                    depends_on=[external.issue_id]
                )
            ]
        )

        response = await service.create_issues_batch(request)
        assert len(response.created_issues) == 1


# =============================================================================
# Cascade Unlock on Completion
# =============================================================================


class TestCascadeUnlock:
    """Tests for cascade unlock when issues complete."""

    @pytest.mark.asyncio
    async def test_dependent_moves_to_ready_on_completion(self, service):
        """Test that dependent issue moves to READY when dependency completes."""
        # Create A
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A",
            description="Dependency"
        ))

        # Create B that depends on A
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B",
            description="Depends on A",
            depends_on=[issue_a.issue_id]
        ))

        # B should start in BACKLOG
        assert issue_b.status == IssueStatus.BACKLOG

        # Complete A and finalize (merge → DONE + cascade)
        await service.update_issue_status(issue_a.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(issue_a.issue_id, IssueResult(
            output="Done",
            success=True
        ))
        await service._issue_service.finalize_issue(issue_a.issue_id)

        # B should now be READY
        updated_b = await service.get_issue(issue_b.issue_id)
        assert updated_b.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_and_logic_multiple_dependencies(self, service):
        """Test that issue only becomes READY when ALL dependencies complete."""
        # Create A and B
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A",
            description="Dep 1"
        ))
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B",
            description="Dep 2"
        ))

        # Create C that depends on both
        issue_c = await service.create_issue(IssueCreateRequest(
            title="Issue C",
            description="Depends on A and B",
            depends_on=[issue_a.issue_id, issue_b.issue_id]
        ))

        assert issue_c.status == IssueStatus.BACKLOG

        # Complete and finalize only A
        await service.update_issue_status(issue_a.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(issue_a.issue_id, IssueResult(
            output="Done",
            success=True
        ))
        await service._issue_service.finalize_issue(issue_a.issue_id)

        # C should still be BACKLOG (B not done yet)
        updated_c = await service.get_issue(issue_c.issue_id)
        assert updated_c.status == IssueStatus.BACKLOG

        # Complete and finalize B
        await service.update_issue_status(issue_b.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(issue_b.issue_id, IssueResult(
            output="Done",
            success=True
        ))
        await service._issue_service.finalize_issue(issue_b.issue_id)

        # Now C should be READY
        updated_c = await service.get_issue(issue_c.issue_id)
        assert updated_c.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_cascade_chain(self, service):
        """Test cascade unlock through a chain: A→B→C."""
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A",
            description="First"
        ))
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B",
            description="Depends on A",
            depends_on=[issue_a.issue_id]
        ))
        issue_c = await service.create_issue(IssueCreateRequest(
            title="Issue C",
            description="Depends on B",
            depends_on=[issue_b.issue_id]
        ))

        assert issue_b.status == IssueStatus.BACKLOG
        assert issue_c.status == IssueStatus.BACKLOG

        # Complete A and finalize → B should become READY
        await service.update_issue_status(issue_a.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(issue_a.issue_id, IssueResult(
            output="Done", success=True
        ))
        await service._issue_service.finalize_issue(issue_a.issue_id)

        updated_b = await service.get_issue(issue_b.issue_id)
        updated_c = await service.get_issue(issue_c.issue_id)
        assert updated_b.status == IssueStatus.READY
        assert updated_c.status == IssueStatus.BACKLOG  # Still waiting on B

        # Complete B and finalize → C should become READY
        await service.update_issue_status(issue_b.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(issue_b.issue_id, IssueResult(
            output="Done", success=True
        ))
        await service._issue_service.finalize_issue(issue_b.issue_id)

        updated_c = await service.get_issue(issue_c.issue_id)
        assert updated_c.status == IssueStatus.READY


# =============================================================================
# Initial Status Calculation
# =============================================================================


class TestInitialStatusCalculation:
    """Tests for initial status calculation on issue creation."""

    @pytest.mark.asyncio
    async def test_no_deps_starts_ready(self, service):
        """Test that issue with no dependencies starts as READY."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Independent Issue",
            description="No dependencies"
        ))

        assert issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_pending_deps_starts_backlog(self, service):
        """Test that issue with pending dependencies starts as BACKLOG."""
        dep = await service.create_issue(IssueCreateRequest(
            title="Dependency",
            description="Not done yet"
        ))

        issue = await service.create_issue(IssueCreateRequest(
            title="Dependent Issue",
            description="Depends on pending",
            depends_on=[dep.issue_id]
        ))

        assert issue.status == IssueStatus.BACKLOG

    @pytest.mark.asyncio
    async def test_completed_deps_starts_ready(self, service):
        """Test that issue with all completed dependencies starts as READY."""
        dep = await service.create_issue(IssueCreateRequest(
            title="Dependency",
            description="Will be completed"
        ))

        # Complete and finalize the dependency (merge → DONE)
        await service.update_issue_status(dep.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(dep.issue_id, IssueResult(
            output="Done", success=True
        ))
        await service._issue_service.finalize_issue(dep.issue_id)

        # Create new issue depending on finalized (DONE) dep
        issue = await service.create_issue(IssueCreateRequest(
            title="Dependent Issue",
            description="Depends on completed",
            depends_on=[dep.issue_id]
        ))

        assert issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_batch_initial_status(self, service):
        """Test initial status calculation in batch creation."""
        # Create a goal for the batch
        goal = await service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="For batch status test"
        ))

        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Independent",
                    description="No deps",
                    depends_on=[]
                ),
                IssueCreateRequest(
                    title="Dependent",
                    description="Depends on first",
                    depends_on=[0]
                )
            ]
        )

        response = await service.create_issues_batch(request)

        # Get the created issues
        independent_id = response.created_issues[0]["id"]
        dependent_id = response.created_issues[1]["id"]

        independent = await service.get_issue(independent_id)
        dependent = await service.get_issue(dependent_id)

        assert independent.status == IssueStatus.READY
        assert dependent.status == IssueStatus.BACKLOG


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in dependency resolution."""

    @pytest.mark.asyncio
    async def test_diamond_dependency(self, service):
        """Test diamond dependency pattern: A→B,C→D where B,C both depend on A and D depends on both."""
        # Create A (no deps)
        a = await service.create_issue(IssueCreateRequest(
            title="A", description="Root"
        ))

        # Create B and C (both depend on A)
        b = await service.create_issue(IssueCreateRequest(
            title="B", description="Branch 1", depends_on=[a.issue_id]
        ))
        c = await service.create_issue(IssueCreateRequest(
            title="C", description="Branch 2", depends_on=[a.issue_id]
        ))

        # Create D (depends on both B and C)
        d = await service.create_issue(IssueCreateRequest(
            title="D", description="Merge", depends_on=[b.issue_id, c.issue_id]
        ))

        # Initial states
        assert a.status == IssueStatus.READY
        assert b.status == IssueStatus.BACKLOG
        assert c.status == IssueStatus.BACKLOG
        assert d.status == IssueStatus.BACKLOG

        # Complete A and finalize → B and C should become READY
        await service.update_issue_status(a.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(a.issue_id, IssueResult(output="Done", success=True))
        await service._issue_service.finalize_issue(a.issue_id)

        b = await service.get_issue(b.issue_id)
        c = await service.get_issue(c.issue_id)
        d = await service.get_issue(d.issue_id)

        assert b.status == IssueStatus.READY
        assert c.status == IssueStatus.READY
        assert d.status == IssueStatus.BACKLOG  # Still waiting

        # Complete B and finalize → D still waiting on C
        await service.update_issue_status(b.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(b.issue_id, IssueResult(output="Done", success=True))
        await service._issue_service.finalize_issue(b.issue_id)

        d = await service.get_issue(d.issue_id)
        assert d.status == IssueStatus.BACKLOG

        # Complete C and finalize → D should become READY
        await service.update_issue_status(c.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(c.issue_id, IssueResult(output="Done", success=True))
        await service._issue_service.finalize_issue(c.issue_id)

        d = await service.get_issue(d.issue_id)
        assert d.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_batch_diamond_pattern(self, service):
        """Test diamond dependency pattern in batch creation."""
        # Create a goal for the batch
        goal = await service.create_goal(GoalCreateRequest(
            title="Diamond Goal",
            description="For diamond pattern test"
        ))

        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(title="A", description="Root", depends_on=[]),
                IssueCreateRequest(title="B", description="Branch 1", depends_on=[0]),
                IssueCreateRequest(title="C", description="Branch 2", depends_on=[0]),
                IssueCreateRequest(title="D", description="Merge", depends_on=[1, 2])
            ]
        )

        response = await service.create_issues_batch(request)
        assert len(response.created_issues) == 4

        # Verify structure
        a = await service.get_issue(response.created_issues[0]["id"])
        d = await service.get_issue(response.created_issues[3]["id"])

        assert a.status == IssueStatus.READY
        assert d.status == IssueStatus.BACKLOG
        assert len(d.depends_on) == 2

    @pytest.mark.asyncio
    async def test_already_ready_not_regressed(self, service):
        """Test that READY issues aren't moved back to BACKLOG."""
        # Create independent issue
        issue = await service.create_issue(IssueCreateRequest(
            title="Independent",
            description="Should stay READY"
        ))
        assert issue.status == IssueStatus.READY

        # Create and complete another issue
        other = await service.create_issue(IssueCreateRequest(
            title="Other",
            description="Unrelated"
        ))
        await service.update_issue_status(other.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(other.issue_id, IssueResult(output="Done", success=True))

        # First issue should still be READY
        issue = await service.get_issue(issue.issue_id)
        assert issue.status == IssueStatus.READY


# =============================================================================
# WorkItem → Issue Completion Cascade
# =============================================================================


class TestWorkItemIssueCompletionCascade:
    """Tests for WorkItem completion triggering Issue completion and cascade."""

    @pytest.mark.asyncio
    async def test_work_completion_completes_parent_issue(self, service):
        """Test that completing a WorkItem auto-completes its parent Issue."""
        # Create an issue
        issue = await service.create_issue(IssueCreateRequest(
            title="Parent Issue",
            description="Will be completed by work item"
        ))
        assert issue.status == IssueStatus.READY

        # Move to in_progress so it can transition to DONE
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)

        # Create a work item linked to this issue
        work = await service.create_work(WorkCreateRequest(
            title="Work for parent issue",
            description="Does the work",
            issue_id=issue.issue_id,
            project_id="test-project"
        ))

        # Assign and start work
        await service.assign_work(work.work_id, "compute-1", [])
        await service.update_status(work.work_id, "in_progress", "compute-1")

        # Complete the work and finalize (post-merge)
        await service.complete_work(
            work.work_id,
            result={"summary": "Done"},
            compute_id="compute-1"
        )
        await service.finalize_work(work.work_id)

        # Parent issue should now be DONE (after finalize)
        updated_issue = await service.get_issue(issue.issue_id)
        assert updated_issue.status == IssueStatus.DONE

    @pytest.mark.asyncio
    async def test_work_completion_cascades_to_dependent_issues(self, service):
        """Test full cascade: WorkItem completes → parent Issue DONE → dependent Issue READY."""
        # Create Issue A (dependency)
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A",
            description="Dependency"
        ))

        # Create Issue B (depends on A)
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B",
            description="Depends on A",
            depends_on=[issue_a.issue_id]
        ))
        assert issue_b.status == IssueStatus.BACKLOG

        # Move Issue A to in_progress
        await service.update_issue_status(issue_a.issue_id, IssueStatus.IN_PROGRESS)

        # Create WorkItem linked to Issue A
        work = await service.create_work(WorkCreateRequest(
            title="Work for Issue A",
            description="Does the work for A",
            issue_id=issue_a.issue_id,
            project_id="test-project"
        ))

        # Assign, start, complete, and finalize the work (post-merge)
        await service.assign_work(work.work_id, "compute-1", [])
        await service.update_status(work.work_id, "in_progress", "compute-1")
        await service.complete_work(
            work.work_id,
            result={"summary": "Completed A"},
            compute_id="compute-1"
        )
        await service.finalize_work(work.work_id)

        # Issue A should be DONE (after finalize)
        updated_a = await service.get_issue(issue_a.issue_id)
        assert updated_a.status == IssueStatus.DONE

        # Issue B should have cascaded from BACKLOG → READY
        updated_b = await service.get_issue(issue_b.issue_id)
        assert updated_b.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_work_completion_no_cascade_without_issue_id(self, service):
        """Test that WorkItem without issue_id doesn't trigger cascade."""
        # Create a work item with no issue_id
        work = await service.create_work(WorkCreateRequest(
            title="Standalone work",
            description="No parent issue",
            project_id="test-project"
        ))

        # Assign, start, and complete (sets IMPLEMENTED, pending merge)
        await service.assign_work(work.work_id, "compute-1", [])
        await service.update_status(work.work_id, "in_progress", "compute-1")
        completed = await service.complete_work(
            work.work_id,
            result={"summary": "Done"},
            compute_id="compute-1"
        )

        # Should complete without error (IMPLEMENTED, not yet COMPLETED)
        assert completed is not None
        assert completed.status == WorkStatus.IMPLEMENTED

    @pytest.mark.asyncio
    async def test_work_completion_cascade_and_logic(self, service):
        """Test cascade respects AND logic: all deps must be done."""
        # Create two dependency issues
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A", description="Dep 1"
        ))
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B", description="Dep 2"
        ))

        # Create Issue C depending on both A and B
        issue_c = await service.create_issue(IssueCreateRequest(
            title="Issue C",
            description="Depends on A and B",
            depends_on=[issue_a.issue_id, issue_b.issue_id]
        ))
        assert issue_c.status == IssueStatus.BACKLOG

        # Complete Issue A via work item
        await service.update_issue_status(issue_a.issue_id, IssueStatus.IN_PROGRESS)
        work_a = await service.create_work(WorkCreateRequest(
            title="Work A", description="Work for A",
            issue_id=issue_a.issue_id, project_id="test-project"
        ))
        await service.assign_work(work_a.work_id, "compute-1", [])
        await service.update_status(work_a.work_id, "in_progress", "compute-1")
        await service.complete_work(work_a.work_id, result={"summary": "Done A"}, compute_id="compute-1")
        await service.finalize_work(work_a.work_id)

        # C should still be BACKLOG (B not done)
        updated_c = await service.get_issue(issue_c.issue_id)
        assert updated_c.status == IssueStatus.BACKLOG

        # Complete Issue B via work item and finalize
        await service.update_issue_status(issue_b.issue_id, IssueStatus.IN_PROGRESS)
        work_b = await service.create_work(WorkCreateRequest(
            title="Work B", description="Work for B",
            issue_id=issue_b.issue_id, project_id="test-project"
        ))
        await service.assign_work(work_b.work_id, "compute-2", [])
        await service.update_status(work_b.work_id, "in_progress", "compute-2")
        await service.complete_work(work_b.work_id, result={"summary": "Done B"}, compute_id="compute-2")
        await service.finalize_work(work_b.work_id)

        # Now C should be READY (all deps satisfied)
        updated_c = await service.get_issue(issue_c.issue_id)
        assert updated_c.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_work_completion_already_done_issue_no_error(self, service):
        """Test that completing work for an already-done Issue doesn't error."""
        # Create and manually complete an issue
        issue = await service.create_issue(IssueCreateRequest(
            title="Already Done", description="Completed separately"
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(issue.issue_id, IssueResult(summary="Manual complete"))

        # Create work item pointing to the already-done issue
        work = await service.create_work(WorkCreateRequest(
            title="Late work", description="Issue already done",
            issue_id=issue.issue_id, project_id="test-project"
        ))
        await service.assign_work(work.work_id, "compute-1", [])
        await service.update_status(work.work_id, "in_progress", "compute-1")

        # Should complete without error (issue already DONE, skip)
        completed = await service.complete_work(
            work.work_id, result={"summary": "Done"}, compute_id="compute-1"
        )
        assert completed is not None

    @pytest.mark.asyncio
    async def test_cascade_unblock_returns_unblocked_ids(self, service):
        """Test that _check_unblock_issue_dependents returns unblocked issue IDs."""
        # Create A and B (B depends on A)
        issue_a = await service.create_issue(IssueCreateRequest(
            title="Issue A", description="Dep"
        ))
        issue_b = await service.create_issue(IssueCreateRequest(
            title="Issue B", description="Depends on A",
            depends_on=[issue_a.issue_id]
        ))

        # Complete A and finalize (merge → DONE + cascade)
        await service.update_issue_status(issue_a.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(issue_a.issue_id, IssueResult(summary="Done"))
        await service._issue_service.finalize_issue(issue_a.issue_id)

        # B should be READY
        updated_b = await service.get_issue(issue_b.issue_id)
        assert updated_b.status == IssueStatus.READY
