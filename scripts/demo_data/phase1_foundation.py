"""Phase 1 - Foundation: Project, Git Infrastructure, Auth System.

Everything here is completed work. This represents the settled base of the
ClaudeVN platform — the project exists, Git transport works, auth is in place.
"""

# ==============================================================================
# Project
# ==============================================================================

DEMO_PROJECTS = [
    {
        "project_id": "demo-claudevn",
        "name": "ClaudeVN - AI Agent Orchestration",
        "description": (
            "AI agent orchestration platform enabling emergent, conversation-driven "
            "coordination between specialized AI agents. Claude Code instances serve "
            "as compute workers with Git-based state management and MCP tools for "
            "communication."
        ),
        "repos": [
            {
                "repo_id": "claudevn-main",
                "name": "claudevn",
                "url": "internal://claudevn/claudevn",
                "default_branch": "main",
                "is_internal": True,
            }
        ],
        "metadata": {
            "demo": True,
            "category": "ai-orchestration",
            "tech_stack": ["python", "fastapi", "react", "redis"],
        },
    }
]

# ==============================================================================
# Goal: Git Infrastructure & Transport (done)
# ==============================================================================

GOAL_GIT = {
    "goal_id": "goal-demo-git-infra",
    "title": "Implement Git Infrastructure & Transport",
    "description": (
        "Build the core Git infrastructure including bare repository management, "
        "branch workflow, merge pipeline, and transport layer. This is the foundation "
        "for all compute work — every task creates a branch, pushes code, and merges "
        "via PR."
    ),
    "priority": "P0",
    "status": "done",
    "created_by": "demo-user",
}

ISSUES_GIT = [
    {
        "issue_id": "issue-demo-001",
        "title": "Fix Git dubious ownership error blocking compute work execution",
        "description": "Git refuses to operate in the repo directory due to ownership mismatch between the container user and the repo files. Need to configure safe.directory.",
        "issue_type": "bug",
        "area": "infra",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["code-writer", "debugger"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-002",
        "title": "Replace worktree setup with simple branch workflow in compute spawner",
        "description": "The worktree approach is fragile in containers. Switch to a simpler branch-based workflow where compute clones once and creates/switches branches per task.",
        "issue_type": "bug",
        "area": "infra",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-001"],
    },
    {
        "issue_id": "issue-demo-003",
        "title": "Fix branch naming to match pre-receive hook validation",
        "description": "Branch names created by compute don't match the pattern validated by the Git pre-receive hook. Align naming convention: {type}/{task}/{compute-id}.",
        "issue_type": "bug",
        "area": "infra",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-002"],
    },
    {
        "issue_id": "issue-demo-004",
        "title": "Persist assigned branch_name to WorkItem for merge flow",
        "description": "The branch name assigned during work dispatch isn't saved to the WorkItem model, so the merge flow can't find the branch to merge.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-003"],
    },
    {
        "issue_id": "issue-demo-005",
        "title": "Fix project creation git clone — incorrect branching and main setup",
        "description": "When creating a project with an internal repo, the bare repo initialization doesn't set up the main branch correctly, causing clone failures.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["code-writer"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-006",
        "title": "Internal repo creation must seed initial commit on main branch",
        "description": "Bare repos need at least one commit on main for cloning and branching to work. Seed with an initial README.md commit.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-005"],
    },
    {
        "issue_id": "issue-demo-007",
        "title": "Add end-to-end integration test for compute git workflow",
        "description": "Create a comprehensive test that validates the full lifecycle: clone, branch, commit, push, and merge. Run in CI with a real Git server.",
        "issue_type": "test",
        "area": "infra",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["test-automator"],
        "depends_on": ["issue-demo-004"],
    },
    {
        "issue_id": "issue-demo-008",
        "title": "Replace SSH Git transport with Git Smart HTTP protocol",
        "description": "SSH transport adds complexity with key management in containers. Switch to Git Smart HTTP which is simpler, uses existing auth tokens, and works through firewalls.",
        "issue_type": "feature",
        "area": "infra",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-git-infra",
        "required_skills": ["code-writer", "infrastructure-engineer"],
        "depends_on": ["issue-demo-007"],
    },
]

# ==============================================================================
# Goal: Auth & Credential System (done)
# ==============================================================================

GOAL_AUTH = {
    "goal_id": "goal-demo-auth",
    "title": "Build User Auth & Credential System",
    "description": (
        "Implement user authentication, compute authorization with API keys, "
        "and credential management. Ensure secure communication between serving "
        "and compute instances."
    ),
    "priority": "P1",
    "status": "done",
    "created_by": "demo-user",
}

ISSUES_AUTH = [
    {
        "issue_id": "issue-demo-009",
        "title": "User registration and authentication",
        "description": "Implement user registration flow with username/email, login/logout endpoints, and session management via Redis.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-auth",
        "required_skills": ["code-writer", "security-reviewer"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-010",
        "title": "User-to-component ownership model",
        "description": "Track which user owns which compute instances and projects. Enforce ownership-based access control.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-auth",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-009"],
    },
    {
        "issue_id": "issue-demo-011",
        "title": "User profile and token management page",
        "description": "Frontend page for users to view their profile, manage API tokens, and see connected compute instances.",
        "issue_type": "feature",
        "area": "frontend",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-auth",
        "required_skills": ["frontend-specialist"],
        "depends_on": ["issue-demo-009"],
    },
    {
        "issue_id": "issue-demo-012",
        "title": "Auth system documentation and setup guide",
        "description": "Write documentation covering the auth architecture, setup instructions, and troubleshooting guide.",
        "issue_type": "docs",
        "area": "other",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-auth",
        "required_skills": ["doc-writer"],
        "depends_on": ["issue-demo-010"],
    },
    {
        "issue_id": "issue-demo-013",
        "title": "Characterization MCP auth uses fake API key causing 401 errors",
        "description": "During the characterization phase, the MCP client is configured with a placeholder API key instead of a real per-task key, causing all MCP calls to fail with 401.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-demo-auth",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": [],
    },
    {
        "issue_id": "issue-demo-014",
        "title": "MCP tool 401 Unauthorized during work execution",
        "description": "Compute receives 401 when calling MCP tools mid-task. The API key is valid but the auth middleware isn't recognizing per-task keys correctly.",
        "issue_type": "bug",
        "area": "api",
        "priority": "P2",
        "status": "done",
        "goal_id": "goal-demo-auth",
        "required_skills": ["debugger"],
        "depends_on": ["issue-demo-013"],
    },
    {
        "issue_id": "issue-demo-015",
        "title": "SSE find_matching_connection should filter by auth_status",
        "description": "When finding a compute connection for work dispatch, filter out instances that haven't completed auth handshake to avoid sending work to unauthorized computes.",
        "issue_type": "feature",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-demo-auth",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-demo-014"],
    },
]

# ==============================================================================
# Aggregated Phase 1 Data
# ==============================================================================

PHASE1_GOALS = [GOAL_GIT, GOAL_AUTH]
PHASE1_ISSUES = ISSUES_GIT + ISSUES_AUTH
