"""Phase 2 - Execution: Event-Driven Dispatcher, Conflict Resolution.

Mostly completed work with a few items still in progress. This represents the
system's core execution engine being built out and stabilized.
"""

# ==============================================================================
# Goal: Event-Driven Work Dispatcher (done)
# ==============================================================================

GOAL_DISPATCHER = {
    "goal_id": "goal-demo-dispatcher",
    "title": "Event-Driven Work Dispatcher",
    "description": (
        "Replace polling-based work distribution with an event-driven dispatcher. "
        "Multi-bucket scheduling with reconciliation ensures work items are dispatched "
        "efficiently to available compute instances."
    ),
    "priority": "P0",
    "status": "done",
    "created_by": "demo-user",
}

ISSUES_DISPATCHER = [
    {
        "issue_id": "issue-demo-016",
        "title": "Refactor: Event-driven work dispatcher with multi-bucket scheduling",
        "description": "Replace the polling loop with an event-driven architecture. Work items queue into priority buckets (critical, high, normal, low) and dispatch on compute-available events.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["code-writer", "refactor-specialist"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-017",
        "title": "Premature idle reset causes misrouted tasks to busy compute",
        "description": "When a compute rejects a task, its idle flag resets too early, causing the dispatcher to immediately route another task to it before it's actually ready.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": ["issue-demo-016"],
    },
    {
        "issue_id": "issue-demo-018",
        "title": "No retry or fallback when compute rejects a dispatched task",
        "description": "If a compute rejects work (e.g., already busy), the task is lost. Add retry logic with exponential backoff and fallback to the next available compute.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-017"],
    },
    {
        "issue_id": "issue-demo-019",
        "title": "Issues marked in_progress before being dispatched to compute",
        "description": "Status transitions to in_progress when work is created, not when actually dispatched. This gives false progress signals in the UI.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-016"],
    },
    {
        "issue_id": "issue-demo-020",
        "title": "Enforce max concurrent Claude Code instances per compute",
        "description": "A compute can currently receive unlimited concurrent tasks. Add configurable max_concurrent limit and reject assignments when at capacity.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-018"],
    },
    {
        "issue_id": "issue-demo-021",
        "title": "Fast compute registration: separate API from SSE connection",
        "description": "Registration and SSE connection are coupled, causing slow registration. Split into: immediate API registration, then async SSE connection establishment.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["code-writer"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-022",
        "title": "Deregistering compute does not disconnect SSE — work assigned to dead instances",
        "description": "When a compute is deregistered via API, its SSE connection stays open. The dispatcher still sees it as available and routes work to it.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": ["issue-demo-021"],
    },
    {
        "issue_id": "issue-demo-023",
        "title": "Add circuit-breaker for deterministic failures on single-compute retries",
        "description": "If a compute keeps failing the same task, stop retrying on that compute. Implement a circuit-breaker pattern that marks compute-task pairs as incompatible after N failures.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P3",
        "status": "done",
        "goal_id": "goal-demo-dispatcher",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-020"],
    },
]

# ==============================================================================
# Goal: Conflict Resolution & Merge Pipeline (in_progress)
# ==============================================================================

GOAL_CONFLICTS = {
    "goal_id": "goal-demo-conflicts",
    "title": "Conflict Resolution & Merge Pipeline",
    "description": (
        "Handle merge conflicts, dependency chains between work items, and ensure "
        "code lands on main correctly. Includes conflict detection, notification to "
        "compute, and resolution workflows."
    ),
    "priority": "P1",
    "status": "in_progress",
    "created_by": "demo-user",
}

ISSUES_CONFLICTS = [
    {
        "issue_id": "issue-demo-024",
        "title": "Auto-merge fails: dubious ownership in check_mergeable and merge methods",
        "description": "The merge process runs git commands in a directory owned by a different user. Need to add safe.directory config for the merge worker.",
        "issue_type": "bug",
        "area": "infra",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-025",
        "title": "Branch verification uses wrong repo path — git_project_name mismatch",
        "description": "The branch existence check looks in the wrong directory because git_project_name doesn't match the actual repo directory name on disk.",
        "issue_type": "bug",
        "area": "infra",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["debugger"],
        "depends_on": ["issue-demo-024"],
    },
    {
        "issue_id": "issue-demo-026",
        "title": "Compute not recognized as available after characterization task completes",
        "description": "After the initial characterization task finishes, the compute isn't transitioned back to idle/available, so it never receives real work.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-027",
        "title": "Work items complete as done but code never lands on main",
        "description": "Work status transitions to COMPLETED when compute finishes, but the actual merge to main never triggers. The PR queue is not processing completed branches.",
        "issue_type": "bug",
        "area": "infra",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": ["issue-demo-025"],
    },
    {
        "issue_id": "issue-demo-028",
        "title": "Dependent work items start from stale main — no branch integration",
        "description": "When work item B depends on A, B's branch should be based on main after A's merge. Currently B branches from stale main, causing conflicts.",
        "issue_type": "feature",
        "area": "infra",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["code-writer", "git-workflow"],
        "depends_on": ["issue-demo-027"],
    },
    {
        "issue_id": "issue-demo-029",
        "title": "Double work completion status transition — MCP vs claude_code_completed race",
        "description": "Both the MCP progress report and the claude_code_completed event try to transition work to COMPLETED, causing a race condition and duplicate notifications.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": ["issue-demo-026"],
    },
    {
        "issue_id": "issue-demo-030",
        "title": "Add merge conflict SSE handler in compute event client",
        "description": "Compute needs to listen for merge_conflict SSE events and trigger conflict resolution workflows when its branch conflicts with main.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-028"],
    },
    {
        "issue_id": "issue-demo-031",
        "title": "Fix safety-net commit/push SSH key and ownership issues",
        "description": "The safety-net mechanism (auto-commit uncommitted work before timeout) fails due to SSH key permissions and directory ownership in containers.",
        "issue_type": "bug",
        "area": "infra",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["debugger", "infrastructure-engineer"],
        "depends_on": ["issue-demo-024"],
    },
    {
        "issue_id": "issue-demo-032",
        "title": "Send branch cleanup signal to compute after successful merge",
        "description": "After a branch is merged to main, serving should notify the owning compute to delete the local branch. Keeps compute workspaces clean without tearing down the repo.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P1",
        "status": "in_progress",
        "goal_id": "goal-demo-conflicts",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-030"],
        "assigned_compute_id": "compute-beta-1",
    },
]

# ==============================================================================
# Phase 2 Work Items (recently completed + in-progress)
# ==============================================================================

PHASE2_WORK_ITEMS = [
    {
        "work_id": "work-demo-001",
        "title": "Implement event-driven dispatcher reconciliation loop",
        "description": "Add periodic reconciliation that checks for stuck/orphaned work items and re-dispatches them.",
        "work_type": "feature",
        "priority": "high",
        "status": "completed",
        "project_id": "demo-claudevn",
        "assigned_to": "compute-alpha-1",
        "progress_percent": 100,
        "required_skills": ["code-writer"],
        "skill_ids": ["code-writer", "refactor-specialist"],
        "branch_name": "feat/reconciliation-loop/compute-alpha-1",
        "tags": ["dispatcher", "reliability"],
        "issue_id": "issue-demo-016",
    },
    {
        "work_id": "work-demo-002",
        "title": "Fix branch merge flow for conflict detection",
        "description": "Update merge pipeline to detect conflicts before attempting merge and notify compute via SSE.",
        "work_type": "bug",
        "priority": "critical",
        "status": "completed",
        "project_id": "demo-claudevn",
        "assigned_to": "compute-alpha-2",
        "progress_percent": 100,
        "required_skills": ["debugger", "code-writer"],
        "skill_ids": ["debugger", "code-writer"],
        "branch_name": "fix/merge-conflict-detection/compute-alpha-2",
        "tags": ["merge", "conflicts"],
        "issue_id": "issue-demo-027",
    },
    {
        "work_id": "work-demo-003",
        "title": "Implement branch cleanup notification",
        "description": "After successful merge, send targeted SSE event to owning compute with branch name to delete.",
        "work_type": "feature",
        "priority": "normal",
        "status": "in_progress",
        "project_id": "demo-claudevn",
        "assigned_to": "compute-beta-1",
        "progress_percent": 45,
        "required_skills": ["code-writer"],
        "skill_ids": ["code-writer"],
        "branch_name": "feat/branch-cleanup-signal/compute-beta-1",
        "tags": ["merge", "cleanup"],
        "issue_id": "issue-demo-032",
    },
    {
        "work_id": "work-demo-004",
        "title": "Add circuit-breaker test suite",
        "description": "Write comprehensive tests for the circuit-breaker pattern including edge cases around retry limits and compute-task pair tracking.",
        "work_type": "task",
        "priority": "normal",
        "status": "completed",
        "project_id": "demo-claudevn",
        "assigned_to": "compute-beta-2",
        "progress_percent": 100,
        "required_skills": ["test-automator"],
        "skill_ids": ["test-automator"],
        "branch_name": "test/circuit-breaker/compute-beta-2",
        "tags": ["testing", "dispatcher"],
        "issue_id": "issue-demo-023",
    },
]

# ==============================================================================
# Aggregated Phase 2 Data
# ==============================================================================

PHASE2_GOALS = [GOAL_DISPATCHER, GOAL_CONFLICTS]
PHASE2_ISSUES = ISSUES_DISPATCHER + ISSUES_CONFLICTS
