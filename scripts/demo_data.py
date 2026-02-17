#!/usr/bin/env python3
"""Demo data script for ClaudeVN development testing."""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid
import random

# Add project root to path for imports
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import models (deferred to allow --help without dependencies)
def _import_models():
    """Import models lazily to allow --help to work without full dependencies."""
    global Project, ProjectStatus, RepoConfig
    global Goal, GoalStatus, Issue, IssueStatus, IssueType, IssueArea, IssuePriority
    global WorkItem, WorkStatus, WorkPriority, Blocker, BlockerType
    global ComputeInstance, InstanceStatus, InstanceCapabilities, InstanceResources
    global Skill, SkillCreateRequest

    from serving.models.project import Project, ProjectStatus, RepoConfig
    from serving.models.work_map import (
        Goal, GoalStatus, Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
        WorkItem, WorkStatus, WorkPriority, Blocker, BlockerType
    )
    from serving.models.compute import (
        ComputeInstance, InstanceStatus, InstanceCapabilities, InstanceResources
    )
    from marketplace.models import Skill, SkillCreateRequest


# ==============================================================================
# Demo Data Definitions
# ==============================================================================

DEMO_PROJECTS = [
    {
        "project_id": "demo-ecommerce",
        "name": "E-Commerce Platform",
        "description": "A modern e-commerce platform with microservices architecture",
        "repos": [
            {
                "repo_id": "ecom-api",
                "name": "ecommerce-api",
                "url": "git@github.com:demo/ecommerce-api.git",
                "default_branch": "main"
            },
            {
                "repo_id": "ecom-frontend",
                "name": "ecommerce-frontend",
                "url": "git@github.com:demo/ecommerce-frontend.git",
                "default_branch": "main"
            }
        ],
        "metadata": {"demo": True, "category": "e-commerce"}
    },
    {
        "project_id": "demo-analytics",
        "name": "Analytics Dashboard",
        "description": "Real-time analytics dashboard with ClickHouse backend",
        "repos": [
            {
                "repo_id": "analytics-backend",
                "name": "analytics-backend",
                "url": "git@github.com:demo/analytics-backend.git",
                "default_branch": "main"
            }
        ],
        "metadata": {"demo": True, "category": "analytics"}
    },
    {
        "project_id": "demo-mobile",
        "name": "Mobile App",
        "description": "Cross-platform mobile application using React Native",
        "repos": [
            {
                "repo_id": "mobile-app",
                "name": "mobile-app",
                "url": "git@github.com:demo/mobile-app.git",
                "default_branch": "develop"
            }
        ],
        "metadata": {"demo": True, "category": "mobile"}
    }
]

DEMO_GOALS = [
    {
        "goal_id": "goal-auth-system",
        "title": "Implement User Authentication System",
        "description": "Build a complete user authentication system with OAuth2, JWT tokens, and role-based access control",
        "priority": "P0",
        "status": "in_progress",
        "created_by": "demo-user"
    },
    {
        "goal_id": "goal-search-feature",
        "title": "Product Search and Filtering",
        "description": "Implement advanced product search with filters, sorting, and full-text search capabilities",
        "priority": "P1",
        "status": "planning",
        "created_by": "demo-user"
    },
    {
        "goal_id": "goal-notifications",
        "title": "Real-time Notification System",
        "description": "Build a real-time notification system using WebSockets for instant updates",
        "priority": "P2",
        "status": "done",
        "created_by": "demo-user"
    },
    {
        "goal_id": "goal-api-optimization",
        "title": "API Performance Optimization",
        "description": "Optimize API response times and implement caching strategies",
        "priority": "P1",
        "status": "in_progress",
        "created_by": "demo-user"
    }
]

DEMO_ISSUES = [
    # Auth system issues (P0 goal)
    {
        "issue_id": "issue-001",
        "title": "Set up OAuth2 provider integration",
        "description": "Integrate with Google, GitHub, and Microsoft OAuth2 providers",
        "issue_type": "feature",
        "area": "api",
        "priority": "P0",
        "status": "done",
        "goal_id": "goal-auth-system",
        "required_skills": ["code-writer", "api-integration"],
        "depends_on": []
    },
    {
        "issue_id": "issue-002",
        "title": "Implement JWT token generation and validation",
        "description": "Create JWT token service with refresh token support",
        "issue_type": "feature",
        "area": "api",
        "priority": "P0",
        "status": "in_progress",
        "goal_id": "goal-auth-system",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-001"],
        "assigned_compute_id": "compute-demo-001"
    },
    {
        "issue_id": "issue-003",
        "title": "Add role-based access control",
        "description": "Implement RBAC with user, admin, and moderator roles",
        "issue_type": "feature",
        "area": "api",
        "priority": "P0",
        "status": "ready",
        "goal_id": "goal-auth-system",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-002"]
    },
    {
        "issue_id": "issue-004",
        "title": "Write auth system integration tests",
        "description": "Create comprehensive integration tests for authentication flows",
        "issue_type": "test",
        "area": "api",
        "priority": "P1",
        "status": "backlog",
        "goal_id": "goal-auth-system",
        "required_skills": ["test-automator"],
        "depends_on": ["issue-003"]
    },
    # Search feature issues (P1 goal)
    {
        "issue_id": "issue-005",
        "title": "Design search API schema",
        "description": "Define OpenAPI schema for search endpoints with filters",
        "issue_type": "feature",
        "area": "api",
        "priority": "P1",
        "status": "done",
        "goal_id": "goal-search-feature",
        "required_skills": ["code-writer"],
        "depends_on": []
    },
    {
        "issue_id": "issue-006",
        "title": "Implement Elasticsearch integration",
        "description": "Set up Elasticsearch indexing and query service",
        "issue_type": "feature",
        "area": "database",
        "priority": "P1",
        "status": "blocked",
        "goal_id": "goal-search-feature",
        "required_skills": ["code-writer", "database-migration"],
        "depends_on": ["issue-005"]
    },
    {
        "issue_id": "issue-007",
        "title": "Build search UI components",
        "description": "Create React components for search input, filters, and results",
        "issue_type": "feature",
        "area": "frontend",
        "priority": "P1",
        "status": "backlog",
        "goal_id": "goal-search-feature",
        "required_skills": ["code-writer"],
        "depends_on": ["issue-006"]
    },
    # Standalone issues
    {
        "issue_id": "issue-008",
        "title": "Fix memory leak in WebSocket handler",
        "description": "Investigate and fix memory leak when clients disconnect unexpectedly",
        "issue_type": "bug",
        "area": "api",
        "priority": "P0",
        "status": "in_progress",
        "required_skills": ["debugger", "code-writer"],
        "depends_on": [],
        "assigned_compute_id": "compute-demo-002"
    },
    {
        "issue_id": "issue-009",
        "title": "Update API documentation",
        "description": "Refresh API documentation with latest endpoint changes",
        "issue_type": "docs",
        "area": "other",
        "priority": "P3",
        "status": "ready",
        "required_skills": ["doc-writer"],
        "depends_on": []
    },
    {
        "issue_id": "issue-010",
        "title": "Refactor database connection pooling",
        "description": "Improve database connection management with proper pooling",
        "issue_type": "refactor",
        "area": "database",
        "priority": "P2",
        "status": "ready",
        "required_skills": ["code-writer", "database-migration"],
        "depends_on": []
    }
]

DEMO_WORK_ITEMS = [
    {
        "work_id": "work-001",
        "title": "Implement JWT refresh token rotation",
        "description": "Add automatic token rotation on refresh with revocation support",
        "work_type": "feature",
        "priority": "high",
        "status": "in_progress",
        "project_id": "demo-ecommerce",
        "assigned_to": "compute-demo-001",
        "progress_percent": 65,
        "required_skills": ["code-writer"],
        "skill_ids": ["code-writer"],
        "branch_name": "feat/jwt-rotation/compute-demo-001",
        "tags": ["auth", "security"]
    },
    {
        "work_id": "work-002",
        "title": "Debug WebSocket memory issue",
        "description": "Profile and fix memory leak in WebSocket connection handling",
        "work_type": "bug",
        "priority": "critical",
        "status": "in_progress",
        "project_id": "demo-ecommerce",
        "assigned_to": "compute-demo-002",
        "progress_percent": 30,
        "required_skills": ["debugger"],
        "skill_ids": ["debugger", "code-writer"],
        "branch_name": "fix/ws-memory/compute-demo-002",
        "tags": ["bug", "performance"]
    },
    {
        "work_id": "work-003",
        "title": "Add search filter component",
        "description": "Create reusable filter component for product search",
        "work_type": "feature",
        "priority": "normal",
        "status": "pending",
        "project_id": "demo-ecommerce",
        "required_skills": ["code-writer"],
        "branch_name": None,
        "tags": ["frontend", "search"]
    },
    {
        "work_id": "work-004",
        "title": "Review authentication PR",
        "description": "Code review for OAuth2 implementation PR",
        "work_type": "review",
        "priority": "high",
        "status": "completed",
        "project_id": "demo-ecommerce",
        "required_skills": ["code-reviewer"],
        "skill_ids": ["code-reviewer"],
        "branch_name": "feat/oauth2/compute-demo-001",
        "tags": ["review", "auth"],
        "result": {"approved": True, "comments": 3}
    },
    {
        "work_id": "work-005",
        "title": "Set up Elasticsearch cluster",
        "description": "Configure and deploy Elasticsearch cluster for search",
        "work_type": "task",
        "priority": "high",
        "status": "blocked",
        "project_id": "demo-analytics",
        "required_skills": ["code-writer"],
        "required_labels": ["production-access"],
        "branch_name": None,
        "tags": ["infra", "search"],
        "blockers": [
            {
                "blocker_id": "blocker-001",
                "blocker_type": "external",
                "description": "Waiting for cloud provider approval for new resources"
            }
        ]
    }
]

DEMO_COMPUTE_INSTANCES = [
    {
        "instance_id": "compute-demo-001",
        "name": "Development Workstation 1",
        "endpoint": "http://localhost:8101",
        "health_endpoint": "http://localhost:8101/health",
        "status": "online",
        "capabilities": {
            "agents": ["code-writer", "test-automator", "debugger"],
            "tools": ["python-executor", "git", "docker"],
            "labels": ["development"],
            "tools_available": [],
            "resources": {
                "cpu_count": 8,
                "memory_gb": 32.0,
                "storage_gb": 500.0
            }
        },
        "metadata": {"location": "local", "owner": "demo-dev-1", "demo": True}
    },
    {
        "instance_id": "compute-demo-002",
        "name": "Development Workstation 2",
        "endpoint": "http://localhost:8102",
        "health_endpoint": "http://localhost:8102/health",
        "status": "online",
        "capabilities": {
            "agents": ["code-writer", "debugger", "code-reviewer"],
            "tools": ["python-executor", "git", "profiler"],
            "labels": ["development"],
            "tools_available": [],
            "resources": {
                "cpu_count": 16,
                "memory_gb": 64.0,
                "gpu_count": 1,
                "gpu_type": "NVIDIA RTX 4090",
                "storage_gb": 1000.0
            }
        },
        "metadata": {"location": "local", "owner": "demo-dev-2", "demo": True}
    },
    {
        "instance_id": "compute-demo-003",
        "name": "Production Deployer",
        "endpoint": "http://prod-compute:8100",
        "health_endpoint": "http://prod-compute:8100/health",
        "status": "online",
        "capabilities": {
            "agents": ["code-writer", "prod-deployment"],
            "tools": ["git", "docker", "kubectl"],
            "labels": ["production-access", "deployment"],
            "tools_available": ["deploy_prod", "rollback_prod"],
            "resources": {
                "cpu_count": 4,
                "memory_gb": 16.0,
                "storage_gb": 200.0
            }
        },
        "metadata": {"location": "cloud", "environment": "production", "demo": True}
    },
    {
        "instance_id": "compute-demo-004",
        "name": "Database Admin Node",
        "endpoint": "http://db-compute:8100",
        "health_endpoint": "http://db-compute:8100/health",
        "status": "degraded",
        "capabilities": {
            "agents": ["database-migration", "code-writer"],
            "tools": ["psql", "redis-cli", "git"],
            "labels": ["database-admin", "production-access"],
            "tools_available": ["db_migrate", "db_backup"],
            "resources": {
                "cpu_count": 4,
                "memory_gb": 8.0,
                "storage_gb": 100.0
            }
        },
        "metadata": {"location": "cloud", "environment": "production", "demo": True}
    },
    {
        "instance_id": "compute-demo-005",
        "name": "Offline Worker",
        "endpoint": "http://offline-compute:8100",
        "status": "offline",
        "capabilities": {
            "agents": ["code-writer"],
            "tools": ["git"],
            "labels": ["development"],
            "tools_available": []
        },
        "metadata": {"location": "remote", "demo": True}
    }
]

DEMO_SKILLS = [
    {
        "id": "demo-api-builder",
        "name": "API Builder",
        "description": "Specializes in building RESTful and GraphQL APIs with proper error handling",
        "instructions": """# API Builder

## Role
You build robust APIs with proper request validation, error handling, and documentation.

## Approach
1. Design API schema first (OpenAPI or GraphQL)
2. Implement endpoints with proper HTTP methods
3. Add request validation and error responses
4. Write API documentation

## Best Practices
- Use proper HTTP status codes
- Validate all input data
- Return consistent error formats
- Include pagination for list endpoints
""",
        "tags": ["api", "rest", "graphql", "backend"],
        "specialized_tools": [],
        "dependencies": ["code-writer"]
    },
    {
        "id": "demo-data-engineer",
        "name": "Data Engineer",
        "description": "Handles data pipelines, ETL processes, and database optimization",
        "instructions": """# Data Engineer

## Role
You design and implement data pipelines and optimize database performance.

## Approach
1. Analyze data requirements and flow
2. Design efficient data models
3. Implement ETL pipelines
4. Optimize queries and indexes

## Focus Areas
- Data modeling and normalization
- Query optimization
- Pipeline reliability
- Data validation
""",
        "tags": ["data", "etl", "database", "analytics"],
        "specialized_tools": [],
        "dependencies": []
    },
    {
        "id": "demo-security-analyst",
        "name": "Security Analyst",
        "description": "Reviews code for security vulnerabilities and implements security measures",
        "instructions": """# Security Analyst

## Role
You identify and remediate security vulnerabilities in code and infrastructure.

## Approach
1. Review code for OWASP Top 10 vulnerabilities
2. Check for secrets and credentials exposure
3. Verify authentication and authorization
4. Test for injection vulnerabilities

## Security Checklist
- Input validation
- Authentication/Authorization
- Secrets management
- Encryption
- Logging and monitoring
""",
        "tags": ["security", "audit", "vulnerability", "compliance"],
        "specialized_tools": [],
        "dependencies": ["code-reviewer"]
    }
]


# ==============================================================================
# Data Population Functions
# ==============================================================================

def generate_timestamps(base_offset_days: int = 0) -> Dict[str, datetime]:
    """Generate realistic timestamps for demo data."""
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=base_offset_days + random.randint(1, 30))
    updated = created + timedelta(hours=random.randint(1, 48))
    return {
        "created_at": created,
        "updated_at": min(updated, now)
    }


def create_project(data: Dict[str, Any]) -> Project:
    """Create a Project instance from demo data."""
    timestamps = generate_timestamps(base_offset_days=30)
    repos = [
        RepoConfig(
            repo_id=r["repo_id"],
            name=r["name"],
            url=r["url"],
            default_branch=r.get("default_branch", "main"),
            added_at=timestamps["created_at"]
        )
        for r in data.get("repos", [])
    ]

    return Project(
        project_id=data["project_id"],
        name=data["name"],
        description=data.get("description", ""),
        status=ProjectStatus.ACTIVE,
        repos=repos,
        primary_repo_id=repos[0].repo_id if repos else None,
        metadata=data.get("metadata", {}),
        created_at=timestamps["created_at"],
        updated_at=timestamps["updated_at"]
    )


def create_goal(data: Dict[str, Any]) -> Goal:
    """Create a Goal instance from demo data."""
    timestamps = generate_timestamps(base_offset_days=14)
    status_map = {
        "planning": GoalStatus.PLANNING,
        "in_progress": GoalStatus.IN_PROGRESS,
        "done": GoalStatus.DONE
    }
    priority_map = {
        "P0": IssuePriority.P0,
        "P1": IssuePriority.P1,
        "P2": IssuePriority.P2,
        "P3": IssuePriority.P3
    }

    return Goal(
        goal_id=data["goal_id"],
        title=data["title"],
        description=data["description"],
        priority=priority_map.get(data.get("priority", "P1"), IssuePriority.P1),
        status=status_map.get(data.get("status", "planning"), GoalStatus.PLANNING),
        issue_ids=[],  # Will be populated after issues are created
        created_at=timestamps["created_at"],
        updated_at=timestamps["updated_at"],
        created_by=data.get("created_by", "demo")
    )


def create_issue(data: Dict[str, Any]) -> Issue:
    """Create an Issue instance from demo data."""
    timestamps = generate_timestamps(base_offset_days=7)

    status_map = {
        "backlog": IssueStatus.BACKLOG,
        "ready": IssueStatus.READY,
        "in_progress": IssueStatus.IN_PROGRESS,
        "blocked": IssueStatus.BLOCKED,
        "done": IssueStatus.DONE,
        "failed": IssueStatus.FAILED
    }
    type_map = {
        "feature": IssueType.FEATURE,
        "bug": IssueType.BUG,
        "refactor": IssueType.REFACTOR,
        "docs": IssueType.DOCS,
        "test": IssueType.TEST
    }
    area_map = {
        "api": IssueArea.API,
        "database": IssueArea.DATABASE,
        "frontend": IssueArea.FRONTEND,
        "infra": IssueArea.INFRA,
        "other": IssueArea.OTHER
    }
    priority_map = {
        "P0": IssuePriority.P0,
        "P1": IssuePriority.P1,
        "P2": IssuePriority.P2,
        "P3": IssuePriority.P3
    }

    issue = Issue(
        issue_id=data["issue_id"],
        title=data["title"],
        description=data["description"],
        issue_type=type_map.get(data.get("issue_type", "feature"), IssueType.FEATURE),
        area=area_map.get(data.get("area", "other"), IssueArea.OTHER),
        priority=priority_map.get(data.get("priority", "P2"), IssuePriority.P2),
        status=status_map.get(data.get("status", "backlog"), IssueStatus.BACKLOG),
        required_skills=data.get("required_skills", []),
        required_labels=data.get("required_labels", []),
        required_tools=data.get("required_tools", []),
        depends_on=data.get("depends_on", []),
        goal_id=data.get("goal_id"),
        assigned_compute_id=data.get("assigned_compute_id"),
        created_at=timestamps["created_at"],
        updated_at=timestamps["updated_at"]
    )

    # Set started_at for in_progress issues
    if issue.status == IssueStatus.IN_PROGRESS:
        issue.started_at = timestamps["updated_at"] - timedelta(hours=random.randint(1, 12))

    # Set completed_at for done issues
    if issue.status == IssueStatus.DONE:
        issue.completed_at = timestamps["updated_at"]

    return issue


def create_work_item(data: Dict[str, Any]) -> WorkItem:
    """Create a WorkItem instance from demo data."""
    timestamps = generate_timestamps(base_offset_days=3)

    status_map = {
        "pending": WorkStatus.PENDING,
        "assigned": WorkStatus.ASSIGNED,
        "in_progress": WorkStatus.IN_PROGRESS,
        "blocked": WorkStatus.BLOCKED,
        "review": WorkStatus.REVIEW,
        "completed": WorkStatus.COMPLETED,
        "failed": WorkStatus.FAILED
    }
    priority_map = {
        "critical": WorkPriority.CRITICAL,
        "high": WorkPriority.HIGH,
        "normal": WorkPriority.NORMAL,
        "low": WorkPriority.LOW
    }

    # Create blockers if any
    blockers = []
    for b in data.get("blockers", []):
        blocker_type_map = {
            "dependency": BlockerType.DEPENDENCY,
            "external": BlockerType.EXTERNAL,
            "resource": BlockerType.RESOURCE,
            "clarification": BlockerType.CLARIFICATION,
            "technical": BlockerType.TECHNICAL
        }
        blockers.append(Blocker(
            blocker_id=b["blocker_id"],
            blocker_type=blocker_type_map.get(b.get("blocker_type", "technical"), BlockerType.TECHNICAL),
            description=b["description"],
            created_at=timestamps["created_at"]
        ))

    work = WorkItem(
        work_id=data["work_id"],
        title=data["title"],
        description=data["description"],
        work_type=data.get("work_type", "task"),
        priority=priority_map.get(data.get("priority", "normal"), WorkPriority.NORMAL),
        status=status_map.get(data.get("status", "pending"), WorkStatus.PENDING),
        project_id=data["project_id"],
        assigned_to=data.get("assigned_to"),
        progress_percent=data.get("progress_percent", 0),
        required_skills=data.get("required_skills", []),
        required_capabilities=data.get("required_capabilities", []),
        required_labels=data.get("required_labels", []),
        required_tools=data.get("required_tools", []),
        skill_ids=data.get("skill_ids", []),
        branch_name=data.get("branch_name"),
        tags=data.get("tags", []),
        blockers=blockers,
        result=data.get("result"),
        created_at=timestamps["created_at"],
        updated_at=timestamps["updated_at"]
    )

    # Set timestamps for assigned/started work
    if work.assigned_to:
        work.assigned_at = timestamps["updated_at"] - timedelta(hours=random.randint(1, 6))
    if work.status == WorkStatus.IN_PROGRESS:
        work.started_at = work.assigned_at or (timestamps["updated_at"] - timedelta(hours=2))
        work.last_activity_at = timestamps["updated_at"]
    if work.status == WorkStatus.COMPLETED:
        work.completed_at = timestamps["updated_at"]

    return work


def create_compute_instance(data: Dict[str, Any]) -> ComputeInstance:
    """Create a ComputeInstance from demo data."""
    timestamps = generate_timestamps(base_offset_days=60)

    status_map = {
        "online": InstanceStatus.ONLINE,
        "offline": InstanceStatus.OFFLINE,
        "degraded": InstanceStatus.DEGRADED,
        "error": InstanceStatus.ERROR
    }

    # Build capabilities
    caps_data = data.get("capabilities", {})
    resources = None
    if caps_data.get("resources"):
        resources = InstanceResources(**caps_data["resources"])

    capabilities = InstanceCapabilities(
        agents=caps_data.get("agents", []),
        tools=caps_data.get("tools", []),
        labels=caps_data.get("labels", []),
        tools_available=caps_data.get("tools_available", []),
        resources=resources
    )

    return ComputeInstance(
        instance_id=data["instance_id"],
        name=data["name"],
        endpoint=data["endpoint"],
        health_endpoint=data.get("health_endpoint"),
        status=status_map.get(data.get("status", "online"), InstanceStatus.ONLINE),
        capabilities=capabilities,
        metadata=data.get("metadata", {}),
        registered_at=timestamps["created_at"],
        last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=random.randint(5, 120))
    )


def create_skill(data: Dict[str, Any]) -> Skill:
    """Create a Skill from demo data."""
    timestamps = generate_timestamps(base_offset_days=90)

    return Skill(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        version="1.0.0",
        author="user:demo",
        instructions=data["instructions"],
        specialized_tools=data.get("specialized_tools", []),
        tags=data.get("tags", []),
        dependencies=data.get("dependencies", []),
        created_at=timestamps["created_at"],
        updated_at=timestamps["updated_at"]
    )


# ==============================================================================
# API Interaction Functions
# ==============================================================================

async def populate_serving_data(
    dry_run: bool = False,
    base_url: str = "http://localhost:8002"
) -> Dict[str, int]:
    """Populate serving component with demo data via API."""
    import httpx

    base_url = f"{base_url}/api/v1"
    results = {"projects": 0, "goals": 0, "issues": 0, "work_items": 0, "compute": 0}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create projects
        print("\n  Creating projects...")
        for data in DEMO_PROJECTS:
            project = create_project(data)
            if dry_run:
                print(f"    [DRY RUN] Would create project: {project.name}")
                results["projects"] += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/projects",
                    json={
                        "name": project.name,
                        "description": project.description,
                        "metadata": project.metadata
                    }
                )
                if resp.status_code == 201:
                    results["projects"] += 1
                    print(f"    Created project: {project.name}")
                elif resp.status_code == 409:
                    print(f"    Project already exists: {project.name}")
                else:
                    print(f"    Failed to create project {project.name}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating project {project.name}: {e}")

        # Create goals
        print("\n  Creating goals...")
        for data in DEMO_GOALS:
            goal = create_goal(data)
            if dry_run:
                print(f"    [DRY RUN] Would create goal: {goal.title}")
                results["goals"] += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/goals",
                    json={
                        "title": goal.title,
                        "description": goal.description,
                        "priority": goal.priority.value
                    }
                )
                if resp.status_code == 201:
                    results["goals"] += 1
                    print(f"    Created goal: {goal.title}")
                else:
                    print(f"    Failed to create goal {goal.title}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating goal {goal.title}: {e}")

        # Create issues
        print("\n  Creating issues...")
        for data in DEMO_ISSUES:
            issue = create_issue(data)
            if dry_run:
                print(f"    [DRY RUN] Would create issue: {issue.title}")
                results["issues"] += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/issues",
                    json={
                        "title": issue.title,
                        "description": issue.description,
                        "issue_type": issue.issue_type.value,
                        "area": issue.area.value,
                        "priority": issue.priority.value,
                        "required_skills": issue.required_skills,
                        "depends_on": issue.depends_on,
                        "goal_id": issue.goal_id
                    }
                )
                if resp.status_code == 201:
                    results["issues"] += 1
                    print(f"    Created issue: {issue.title}")
                else:
                    print(f"    Failed to create issue {issue.title}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating issue {issue.title}: {e}")

        # Create work items
        print("\n  Creating work items...")
        for data in DEMO_WORK_ITEMS:
            work = create_work_item(data)
            if dry_run:
                print(f"    [DRY RUN] Would create work item: {work.title}")
                results["work_items"] += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/work",
                    json={
                        "title": work.title,
                        "description": work.description,
                        "work_type": work.work_type,
                        "priority": work.priority.value,
                        "tags": work.tags,
                        "required_skills": work.required_skills,
                        "required_labels": work.required_labels,
                        "required_tools": work.required_tools,
                        "project_id": work.project_id,
                        "base_branch": work.base_branch
                    }
                )
                if resp.status_code == 201:
                    results["work_items"] += 1
                    print(f"    Created work item: {work.title}")
                else:
                    print(f"    Failed to create work item {work.title}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating work item {work.title}: {e}")

        # Create compute instances
        print("\n  Registering compute instances...")
        for data in DEMO_COMPUTE_INSTANCES:
            instance = create_compute_instance(data)
            if dry_run:
                print(f"    [DRY RUN] Would register compute: {instance.name}")
                results["compute"] += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/compute/register",
                    json={
                        "instance_id": instance.instance_id,
                        "name": instance.name,
                        "endpoint": instance.endpoint,
                        "health_endpoint": instance.health_endpoint,
                        "capabilities": {
                            "agents": instance.capabilities.agents,
                            "tools": instance.capabilities.tools,
                            "labels": instance.capabilities.labels,
                            "tools_available": instance.capabilities.tools_available,
                            "resources": instance.capabilities.resources.model_dump() if instance.capabilities.resources else None
                        },
                        "metadata": instance.metadata
                    }
                )
                if resp.status_code in (200, 201):
                    results["compute"] += 1
                    print(f"    Registered compute: {instance.name}")
                elif resp.status_code == 409:
                    print(f"    Compute already registered: {instance.name}")
                else:
                    print(f"    Failed to register compute {instance.name}: {resp.status_code}")
            except Exception as e:
                print(f"    Error registering compute {instance.name}: {e}")

    return results


async def populate_marketplace_data(
    dry_run: bool = False,
    base_url: str = "http://localhost:8003"
) -> Dict[str, int]:
    """Populate marketplace with demo skills via API."""
    import httpx

    base_url = f"{base_url}/api/v1/skills"
    results = {"skills": 0}

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n  Creating skills...")
        for data in DEMO_SKILLS:
            skill = create_skill(data)
            if dry_run:
                print(f"    [DRY RUN] Would create skill: {skill.name}")
                results["skills"] += 1
                continue

            try:
                resp = await client.post(
                    base_url,
                    json={
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description,
                        "instructions": skill.instructions,
                        "specialized_tools": skill.specialized_tools,
                        "tags": skill.tags,
                        "dependencies": skill.dependencies,
                        "version": skill.version
                    }
                )
                if resp.status_code == 201:
                    results["skills"] += 1
                    print(f"    Created skill: {skill.name}")
                elif resp.status_code == 409:
                    print(f"    Skill already exists: {skill.name}")
                else:
                    print(f"    Failed to create skill {skill.name}: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"    Error creating skill {skill.name}: {e}")

    return results


async def clear_demo_data(
    dry_run: bool = False,
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003"
) -> Dict[str, int]:
    """Clear all demo data from the system."""
    import httpx

    results = {"projects": 0, "goals": 0, "issues": 0, "work_items": 0, "compute": 0, "skills": 0}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Clear serving data
        serving_url = f"{serving_url}/api/v1"

        # Delete compute instances with demo metadata
        print("\n  Removing compute instances...")
        try:
            resp = await client.get(f"{serving_url}/compute")
            if resp.status_code == 200:
                instances = resp.json().get("instances", [])
                for instance in instances:
                    if instance.get("metadata", {}).get("demo"):
                        instance_id = instance["instance_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete compute: {instance_id}")
                            results["compute"] += 1
                        else:
                            del_resp = await client.delete(f"{serving_url}/compute/{instance_id}")
                            if del_resp.status_code in (200, 204):
                                results["compute"] += 1
                                print(f"    Deleted compute: {instance_id}")
        except Exception as e:
            print(f"    Error clearing compute instances: {e}")

        # Delete work items
        print("\n  Removing work items...")
        try:
            resp = await client.get(f"{serving_url}/work-map/work")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("work_id", "").startswith("work-"):
                        work_id = item["work_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete work: {work_id}")
                            results["work_items"] += 1
                        else:
                            del_resp = await client.delete(f"{serving_url}/work-map/work/{work_id}")
                            if del_resp.status_code in (200, 204):
                                results["work_items"] += 1
                                print(f"    Deleted work: {work_id}")
        except Exception as e:
            print(f"    Error clearing work items: {e}")

        # Delete issues
        print("\n  Removing issues...")
        try:
            resp = await client.get(f"{serving_url}/work-map/issues")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("issue_id", "").startswith("issue-"):
                        issue_id = item["issue_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete issue: {issue_id}")
                            results["issues"] += 1
                        else:
                            del_resp = await client.delete(f"{serving_url}/work-map/issues/{issue_id}")
                            if del_resp.status_code in (200, 204):
                                results["issues"] += 1
                                print(f"    Deleted issue: {issue_id}")
        except Exception as e:
            print(f"    Error clearing issues: {e}")

        # Delete goals
        print("\n  Removing goals...")
        try:
            resp = await client.get(f"{serving_url}/work-map/goals")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("goal_id", "").startswith("goal-"):
                        goal_id = item["goal_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete goal: {goal_id}")
                            results["goals"] += 1
                        else:
                            del_resp = await client.delete(f"{serving_url}/work-map/goals/{goal_id}")
                            if del_resp.status_code in (200, 204):
                                results["goals"] += 1
                                print(f"    Deleted goal: {goal_id}")
        except Exception as e:
            print(f"    Error clearing goals: {e}")

        # Delete projects with demo metadata
        print("\n  Removing projects...")
        try:
            resp = await client.get(f"{serving_url}/projects")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("metadata", {}).get("demo"):
                        project_id = item["project_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete project: {project_id}")
                            results["projects"] += 1
                        else:
                            del_resp = await client.delete(f"{serving_url}/projects/{project_id}")
                            if del_resp.status_code in (200, 204):
                                results["projects"] += 1
                                print(f"    Deleted project: {project_id}")
        except Exception as e:
            print(f"    Error clearing projects: {e}")

        # Delete demo skills from marketplace
        marketplace_url = f"{marketplace_url}/api/v1/skills"
        print("\n  Removing skills...")
        for skill_data in DEMO_SKILLS:
            skill_id = skill_data["id"]
            if dry_run:
                print(f"    [DRY RUN] Would delete skill: {skill_id}")
                results["skills"] += 1
            else:
                try:
                    del_resp = await client.delete(f"{marketplace_url}/{skill_id}")
                    if del_resp.status_code in (200, 204):
                        results["skills"] += 1
                        print(f"    Deleted skill: {skill_id}")
                except Exception as e:
                    print(f"    Error deleting skill {skill_id}: {e}")

    return results


async def get_status(
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003"
) -> Dict[str, Any]:
    """Get current data counts from the system."""
    import httpx

    status = {
        "serving": {"projects": 0, "goals": 0, "issues": 0, "work_items": 0, "compute": 0},
        "marketplace": {"skills": 0},
        "errors": []
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        serving_url = f"{serving_url}/api/v1"

        try:
            resp = await client.get(f"{serving_url}/projects")
            if resp.status_code == 200:
                status["serving"]["projects"] = resp.json().get("total", 0)
        except Exception as e:
            status["errors"].append(f"Projects: {e}")

        try:
            resp = await client.get(f"{serving_url}/work-map/goals")
            if resp.status_code == 200:
                status["serving"]["goals"] = resp.json().get("total", 0)
        except Exception as e:
            status["errors"].append(f"Goals: {e}")

        try:
            resp = await client.get(f"{serving_url}/work-map/issues")
            if resp.status_code == 200:
                status["serving"]["issues"] = resp.json().get("total", 0)
        except Exception as e:
            status["errors"].append(f"Issues: {e}")

        try:
            resp = await client.get(f"{serving_url}/work-map/work")
            if resp.status_code == 200:
                status["serving"]["work_items"] = resp.json().get("total", 0)
        except Exception as e:
            status["errors"].append(f"Work items: {e}")

        try:
            resp = await client.get(f"{serving_url}/compute")
            if resp.status_code == 200:
                status["serving"]["compute"] = resp.json().get("total", 0)
        except Exception as e:
            status["errors"].append(f"Compute: {e}")

        skills_url = f"{marketplace_url}/api/v1/skills"
        try:
            resp = await client.get(skills_url)
            if resp.status_code == 200:
                status["marketplace"]["skills"] = resp.json().get("total", 0)
        except Exception as e:
            status["errors"].append(f"Skills: {e}")

    return status


# ==============================================================================
# Category-Specific Operations
# ==============================================================================

async def clear_projects(
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002"
) -> int:
    """Clear only project data."""
    import httpx

    count = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if verbose:
            print("  Fetching projects...")
        try:
            resp = await client.get(f"{base_url}/projects")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("metadata", {}).get("demo"):
                        project_id = item["project_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete project: {project_id}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/projects/{project_id}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted project: {project_id}")
        except Exception as e:
            print(f"    Error clearing projects: {e}")

    return count


async def clear_goals(
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002"
) -> int:
    """Clear only goal data."""
    import httpx

    count = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if verbose:
            print("  Fetching goals...")
        try:
            resp = await client.get(f"{base_url}/work-map/goals")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("goal_id", "").startswith("goal-"):
                        goal_id = item["goal_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete goal: {goal_id}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/goals/{goal_id}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted goal: {goal_id}")
        except Exception as e:
            print(f"    Error clearing goals: {e}")

    return count


async def clear_work(
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002"
) -> int:
    """Clear work items, issues, and related data."""
    import httpx

    count = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Delete work items
        if verbose:
            print("  Fetching work items...")
        try:
            resp = await client.get(f"{base_url}/work-map/work")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("work_id", "").startswith("work-"):
                        work_id = item["work_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete work: {work_id}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/work/{work_id}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted work: {work_id}")
        except Exception as e:
            print(f"    Error clearing work items: {e}")

        # Delete issues
        if verbose:
            print("  Fetching issues...")
        try:
            resp = await client.get(f"{base_url}/work-map/issues")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("issue_id", "").startswith("issue-"):
                        issue_id = item["issue_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete issue: {issue_id}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/issues/{issue_id}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted issue: {issue_id}")
        except Exception as e:
            print(f"    Error clearing issues: {e}")

    return count


async def clear_skills(
    dry_run: bool = False,
    verbose: bool = False,
    marketplace_url: str = "http://localhost:8003"
) -> int:
    """Clear only user skills (demo skills)."""
    import httpx

    count = 0
    skills_url = f"{marketplace_url}/api/v1/skills"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if verbose:
            print("  Clearing demo skills...")
        for skill_data in DEMO_SKILLS:
            skill_id = skill_data["id"]
            if dry_run:
                print(f"    [DRY RUN] Would delete skill: {skill_id}")
                count += 1
            else:
                try:
                    del_resp = await client.delete(f"{skills_url}/{skill_id}")
                    if del_resp.status_code in (200, 204):
                        count += 1
                        if verbose:
                            print(f"    Deleted skill: {skill_id}")
                except Exception as e:
                    if verbose:
                        print(f"    Error deleting skill {skill_id}: {e}")

    return count


async def populate_projects(
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    serving_url: str = "http://localhost:8002"
) -> int:
    """Populate only project data."""
    import httpx

    if seed is not None:
        random.seed(seed)

    created = 0
    base_url = f"{serving_url}/api/v1"
    projects_to_create = DEMO_PROJECTS[:count] if count > 0 else DEMO_PROJECTS

    async with httpx.AsyncClient(timeout=30.0) as client:
        if verbose:
            print(f"  Creating {len(projects_to_create)} projects...")
        for data in projects_to_create:
            project = create_project(data)
            if dry_run:
                print(f"    [DRY RUN] Would create project: {project.name}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/projects",
                    json={
                        "name": project.name,
                        "description": project.description,
                        "metadata": project.metadata
                    }
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created project: {project.name}")
                elif resp.status_code == 409:
                    if verbose:
                        print(f"    Project already exists: {project.name}")
                else:
                    if verbose:
                        print(f"    Failed to create project {project.name}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating project {project.name}: {e}")

    return created


async def populate_goals(
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    serving_url: str = "http://localhost:8002"
) -> int:
    """Populate only goal data."""
    import httpx

    if seed is not None:
        random.seed(seed)

    created = 0
    base_url = f"{serving_url}/api/v1"
    goals_to_create = DEMO_GOALS[:count] if count > 0 else DEMO_GOALS

    async with httpx.AsyncClient(timeout=30.0) as client:
        if verbose:
            print(f"  Creating {len(goals_to_create)} goals...")
        for data in goals_to_create:
            goal = create_goal(data)
            if dry_run:
                print(f"    [DRY RUN] Would create goal: {goal.title}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/goals",
                    json={
                        "title": goal.title,
                        "description": goal.description,
                        "priority": goal.priority.value
                    }
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created goal: {goal.title}")
                else:
                    if verbose:
                        print(f"    Failed to create goal {goal.title}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating goal {goal.title}: {e}")

    return created


async def populate_work(
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    serving_url: str = "http://localhost:8002"
) -> int:
    """Populate work items and issues."""
    import httpx

    if seed is not None:
        random.seed(seed)

    created = 0
    base_url = f"{serving_url}/api/v1"

    # Limit by count if specified
    issues_to_create = DEMO_ISSUES[:count] if count > 0 else DEMO_ISSUES
    work_to_create = DEMO_WORK_ITEMS[:count] if count > 0 else DEMO_WORK_ITEMS

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create issues
        if verbose:
            print(f"  Creating {len(issues_to_create)} issues...")
        for data in issues_to_create:
            issue = create_issue(data)
            if dry_run:
                print(f"    [DRY RUN] Would create issue: {issue.title}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/issues",
                    json={
                        "title": issue.title,
                        "description": issue.description,
                        "issue_type": issue.issue_type.value,
                        "area": issue.area.value,
                        "priority": issue.priority.value,
                        "required_skills": issue.required_skills,
                        "depends_on": issue.depends_on,
                        "goal_id": issue.goal_id
                    }
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created issue: {issue.title}")
                else:
                    if verbose:
                        print(f"    Failed to create issue {issue.title}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating issue {issue.title}: {e}")

        # Create work items
        if verbose:
            print(f"  Creating {len(work_to_create)} work items...")
        for data in work_to_create:
            work = create_work_item(data)
            if dry_run:
                print(f"    [DRY RUN] Would create work item: {work.title}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/work",
                    json={
                        "title": work.title,
                        "description": work.description,
                        "work_type": work.work_type,
                        "priority": work.priority.value,
                        "tags": work.tags,
                        "required_skills": work.required_skills,
                        "required_labels": work.required_labels,
                        "required_tools": work.required_tools,
                        "project_id": work.project_id,
                        "base_branch": work.base_branch
                    }
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created work item: {work.title}")
                else:
                    if verbose:
                        print(f"    Failed to create work item {work.title}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating work item {work.title}: {e}")

    return created


async def populate_skills(
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    marketplace_url: str = "http://localhost:8003"
) -> int:
    """Populate only skill data."""
    import httpx

    if seed is not None:
        random.seed(seed)

    created = 0
    skills_url = f"{marketplace_url}/api/v1/skills"
    skills_to_create = DEMO_SKILLS[:count] if count > 0 else DEMO_SKILLS

    async with httpx.AsyncClient(timeout=30.0) as client:
        if verbose:
            print(f"  Creating {len(skills_to_create)} skills...")
        for data in skills_to_create:
            skill = create_skill(data)
            if dry_run:
                print(f"    [DRY RUN] Would create skill: {skill.name}")
                created += 1
                continue

            try:
                resp = await client.post(
                    skills_url,
                    json={
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description,
                        "instructions": skill.instructions,
                        "specialized_tools": skill.specialized_tools,
                        "tags": skill.tags,
                        "dependencies": skill.dependencies,
                        "version": skill.version
                    }
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created skill: {skill.name}")
                elif resp.status_code == 409:
                    if verbose:
                        print(f"    Skill already exists: {skill.name}")
                else:
                    if verbose:
                        print(f"    Failed to create skill {skill.name}: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"    Error creating skill {skill.name}: {e}")

    return created


async def refresh_data(
    categories: List[str],
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003"
) -> Dict[str, int]:
    """Refresh existing demo data (update timestamps)."""
    import httpx

    results = {}
    now = datetime.now(timezone.utc)
    base_url = f"{serving_url}/api/v1"

    all_categories = not categories or len(categories) == 0
    refresh_projects = all_categories or "projects" in categories
    refresh_goals = all_categories or "goals" in categories
    refresh_work = all_categories or "work" in categories
    refresh_skills = all_categories or "skills" in categories

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Refresh projects
        if refresh_projects:
            count = 0
            if verbose:
                print("  Refreshing projects...")
            try:
                resp = await client.get(f"{base_url}/projects")
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        if item.get("metadata", {}).get("demo"):
                            project_id = item["project_id"]
                            if dry_run:
                                print(f"    [DRY RUN] Would refresh project: {project_id}")
                                count += 1
                            else:
                                # Update with current timestamp via metadata update
                                patch_resp = await client.patch(
                                    f"{base_url}/projects/{project_id}",
                                    json={"metadata": {"demo": True, "refreshed_at": now.isoformat()}}
                                )
                                if patch_resp.status_code in (200, 204):
                                    count += 1
                                    if verbose:
                                        print(f"    Refreshed project: {project_id}")
            except Exception as e:
                print(f"    Error refreshing projects: {e}")
            results["projects"] = count

        # Refresh goals
        if refresh_goals:
            count = 0
            if verbose:
                print("  Refreshing goals...")
            try:
                resp = await client.get(f"{base_url}/work-map/goals")
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        if item.get("goal_id", "").startswith("goal-"):
                            goal_id = item["goal_id"]
                            if dry_run:
                                print(f"    [DRY RUN] Would refresh goal: {goal_id}")
                                count += 1
                            else:
                                # Touch the goal to update timestamp
                                patch_resp = await client.patch(
                                    f"{base_url}/work-map/goals/{goal_id}",
                                    json={"description": item.get("description", "") + " "}
                                )
                                if patch_resp.status_code in (200, 204):
                                    count += 1
                                    if verbose:
                                        print(f"    Refreshed goal: {goal_id}")
            except Exception as e:
                print(f"    Error refreshing goals: {e}")
            results["goals"] = count

        # Refresh work items
        if refresh_work:
            count = 0
            if verbose:
                print("  Refreshing work items...")
            try:
                resp = await client.get(f"{base_url}/work-map/work")
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        if item.get("work_id", "").startswith("work-"):
                            work_id = item["work_id"]
                            if dry_run:
                                print(f"    [DRY RUN] Would refresh work: {work_id}")
                                count += 1
                            else:
                                # Touch the work item
                                patch_resp = await client.patch(
                                    f"{base_url}/work-map/work/{work_id}",
                                    json={"description": item.get("description", "") + " "}
                                )
                                if patch_resp.status_code in (200, 204):
                                    count += 1
                                    if verbose:
                                        print(f"    Refreshed work: {work_id}")
            except Exception as e:
                print(f"    Error refreshing work items: {e}")
            results["work_items"] = count

    return results


# ==============================================================================
# Delete All / Start Fresh
# ==============================================================================

async def delete_all_data(
    dry_run: bool = False,
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003"
) -> Dict[str, int]:
    """Delete ALL data from the system (not just demo-tagged).

    Removes goals, issues, work items, projects, auth credentials,
    stale compute instances, and stale marketplace instances.
    """
    import httpx

    results = {
        "goals": 0, "issues": 0, "work_items": 0, "projects": 0,
        "auth": 0, "compute": 0, "marketplaces": 0
    }
    base = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Delete all goals (hard delete)
        print("\n  Deleting all goals...")
        try:
            resp = await client.get(f"{base}/goals")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    gid = item["goal_id"]
                    if dry_run:
                        print(f"    [DRY RUN] Would delete goal: {gid}")
                    else:
                        del_resp = await client.delete(f"{base}/goals/{gid}?hard=true")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deleted goal: {gid}")
                        else:
                            print(f"    Failed to delete goal {gid}: {del_resp.status_code}")
                    results["goals"] += 1
        except Exception as e:
            print(f"    Error deleting goals: {e}")

        # 2. Delete all issues
        print("\n  Deleting all issues...")
        try:
            resp = await client.get(f"{base}/issues")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    iid = item["issue_id"]
                    if dry_run:
                        print(f"    [DRY RUN] Would delete issue: {iid}")
                    else:
                        del_resp = await client.delete(f"{base}/issues/{iid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deleted issue: {iid}")
                        else:
                            print(f"    Failed to delete issue {iid}: {del_resp.status_code}")
                    results["issues"] += 1
        except Exception as e:
            print(f"    Error deleting issues: {e}")

        # 3. Delete all work items
        print("\n  Deleting all work items...")
        try:
            resp = await client.get(f"{base}/work")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    wid = item["work_id"]
                    if dry_run:
                        print(f"    [DRY RUN] Would delete work: {wid}")
                    else:
                        del_resp = await client.delete(f"{base}/work/{wid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deleted work: {wid}")
                        else:
                            print(f"    Failed to delete work {wid}: {del_resp.status_code}")
                    results["work_items"] += 1
        except Exception as e:
            print(f"    Error deleting work items: {e}")

        # 4. Delete all projects (and their unified directives)
        print("\n  Deleting all projects and unified directives...")
        try:
            resp = await client.get(f"{base}/projects")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    pid = item["project_id"]
                    # Delete unified directives for this project
                    if dry_run:
                        print(f"    [DRY RUN] Would delete directives for project: {pid}")
                    else:
                        dir_resp = await client.delete(
                            f"{base}/unified-directives",
                            params={"project_id": pid},
                        )
                        if dir_resp.status_code == 200:
                            deleted = dir_resp.json().get("deleted", 0)
                            if deleted:
                                print(f"    Deleted {deleted} directives for project: {pid}")
                        else:
                            print(f"    Failed to delete directives for {pid}: {dir_resp.status_code}")
                    results["directives"] = results.get("directives", 0) + 1

                    # Delete the project itself
                    if dry_run:
                        print(f"    [DRY RUN] Would delete project: {pid}")
                    else:
                        del_resp = await client.delete(f"{base}/projects/{pid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deleted project: {pid}")
                        else:
                            print(f"    Failed to delete project {pid}: {del_resp.status_code}")
                    results["projects"] += 1
        except Exception as e:
            print(f"    Error deleting projects: {e}")

        # 5. Deregister stale compute instances (not live SSE-connected ones)
        print("\n  Cleaning up stale compute instances...")
        try:
            resp = await client.get(f"{base}/compute")
            if resp.status_code == 200:
                data = resp.json()
                instances = data.get("instances", data.get("items", []))
                for inst in instances:
                    iid = inst["instance_id"]
                    status = inst.get("status", "")
                    # Skip live SSE-connected computes
                    metadata = inst.get("metadata", {})
                    connection_type = metadata.get("connection_type", "")
                    if connection_type == "sse" and status in ("online", "idle"):
                        print(f"    Skipping live compute: {iid}")
                        continue
                    if dry_run:
                        print(f"    [DRY RUN] Would deregister compute: {iid} ({status})")
                    else:
                        del_resp = await client.delete(f"{base}/compute/{iid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deregistered compute: {iid} ({status})")
                        else:
                            print(f"    Failed to deregister {iid}: {del_resp.status_code}")
                    results["compute"] += 1
        except Exception as e:
            print(f"    Error cleaning compute instances: {e}")

        # 6. Clear auth credentials
        print("\n  Skipping clearing auth credentials for testing...")
        # try:
        #     resp = await client.post(f"{base}/auth/logout")
        #     if resp.status_code == 200:
        #         data = resp.json()
        #         if data.get("cleared"):
        #             print("    Cleared auth credentials")
        #         else:
        #             print("    No auth credentials to clear")
        #         results["auth"] = 1
        #     elif resp.status_code in (404, 503):
        #         print("    Auth service not enabled (skipped)")
        #     else:
        #         print(f"    Failed to clear auth: {resp.status_code}")
        # except Exception as e:
        #     print(f"    Error clearing auth: {e}")

        # 7. Deregister stale marketplace instances
        print("\n  Cleaning up stale marketplace instances...")
        try:
            resp = await client.get(f"{base}/marketplaces")
            if resp.status_code == 200:
                data = resp.json()
                instances = data.get("marketplaces", data.get("items", []))
                for mp in instances:
                    mid = mp.get("marketplace_id", mp.get("id", ""))
                    status = mp.get("status", "")
                    # Skip healthy ones
                    if status in ("healthy", "online"):
                        print(f"    Skipping healthy marketplace: {mid}")
                        continue
                    if dry_run:
                        print(f"    [DRY RUN] Would deregister marketplace: {mid} ({status})")
                    else:
                        del_resp = await client.delete(f"{base}/marketplaces/{mid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deregistered marketplace: {mid} ({status})")
                        else:
                            print(f"    Failed to deregister {mid}: {del_resp.status_code}")
                    results["marketplaces"] += 1
        except Exception as e:
            print(f"    Error cleaning marketplace instances: {e}")

    return results


async def create_default_project(
    dry_run: bool = False,
    serving_url: str = "http://localhost:8002"
) -> Optional[str]:
    """Create a default project to work from.

    Returns the project_id if created, None otherwise.
    """
    import httpx

    base = f"{serving_url}/api/v1"
    project_data = {
        "name": "Default Project",
        "description": "Default working project for ClaudeVN development",
        "metadata": {"default": True}
    }

    if dry_run:
        print("  [DRY RUN] Would create default project: Default Project")
        return None

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{base}/projects", json=project_data)
            if resp.status_code == 201:
                result = resp.json()
                pid = result.get("project_id", "unknown")
                print(f"  Created default project: {pid}")
                return pid
            else:
                print(f"  Failed to create default project: {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            print(f"  Error creating default project: {e}")
            return None


# ==============================================================================
# Main
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="demo_data",
        description="""
ClaudeVN Demo Data Script

Populates the system with realistic sample data for development testing:
  - Projects with repository configurations
  - Goals with decomposed issues
  - Work items with dependencies and blockers
  - Compute instances with various capabilities
  - Skills in the marketplace
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           Populate all demo data
  %(prog)s --populate --projects     Only populate projects
  %(prog)s --clear --goals           Clear only goals
  %(prog)s --refresh --work          Refresh work items
  %(prog)s --status                  Show current data counts
  %(prog)s --clear --populate        Full reset (clear then populate)
  %(prog)s --populate --count 10     Generate 10 items per category
  %(prog)s --populate --seed 12345   Reproducible data generation
  %(prog)s --dry-run --clear         Preview what would be deleted
  %(prog)s --delete                  Delete ALL data (projects, goals, issues, etc.)
  %(prog)s --delete --start          Delete everything, then create a default project
  %(prog)s --start                   Create a default project (without deleting)

Endpoints (must be running):
  Serving:     http://localhost:8002
  Marketplace: http://localhost:8003
        """
    )

    # Action modes
    action_group = parser.add_argument_group("Actions")
    action_group.add_argument(
        "--clear",
        action="store_true",
        help="Remove demo data"
    )
    action_group.add_argument(
        "--populate",
        action="store_true",
        help="Create demo data"
    )
    action_group.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh existing demo data (update timestamps)"
    )
    action_group.add_argument(
        "--status",
        action="store_true",
        help="Display current data counts from all components"
    )
    action_group.add_argument(
        "--delete",
        action="store_true",
        help="Delete ALL data (goals, issues, work items, projects, auth, stale compute/marketplace)"
    )
    action_group.add_argument(
        "--start",
        action="store_true",
        help="Create a default project to work from (use with --delete for fresh start)"
    )

    # Category selection
    category_group = parser.add_argument_group(
        "Category Selection",
        "By default, all categories are affected. Use these flags to target specific ones."
    )
    category_group.add_argument(
        "--projects",
        action="store_true",
        help="Only affect projects data"
    )
    category_group.add_argument(
        "--goals",
        action="store_true",
        help="Only affect goals data"
    )
    category_group.add_argument(
        "--work",
        action="store_true",
        help="Only affect work items and issues data"
    )
    category_group.add_argument(
        "--skills",
        action="store_true",
        help="Only affect skills data (user skills only)"
    )

    # Legacy component selection (for backwards compatibility)
    legacy_group = parser.add_argument_group(
        "Legacy Options",
        "These options are kept for backwards compatibility."
    )
    legacy_group.add_argument(
        "--serving",
        action="store_true",
        help="Serving component (projects, goals, work items)"
    )
    legacy_group.add_argument(
        "--marketplace",
        action="store_true",
        help="Marketplace component (skills)"
    )

    # Options
    options_group = parser.add_argument_group("Options")
    options_group.add_argument(
        "--seed",
        type=int,
        metavar="NUMBER",
        help="Random seed for reproducible data generation"
    )
    options_group.add_argument(
        "--count",
        type=int,
        default=0,
        metavar="NUMBER",
        help="Number of items to generate per category (default: all)"
    )
    options_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    options_group.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Preview changes without making any API calls"
    )
    options_group.add_argument(
        "--serving-url",
        default="http://localhost:8002",
        metavar="URL",
        help="Serving API base URL (default: http://localhost:8002)"
    )
    options_group.add_argument(
        "--marketplace-url",
        default="http://localhost:8003",
        metavar="URL",
        help="Marketplace API base URL (default: http://localhost:8003)"
    )

    args = parser.parse_args()

    # Determine which categories to affect
    categories = []
    if args.projects:
        categories.append("projects")
    if args.goals:
        categories.append("goals")
    if args.work:
        categories.append("work")
    if args.skills:
        categories.append("skills")

    # Handle legacy options
    if args.serving and not categories:
        categories = ["projects", "goals", "work"]
    if args.marketplace and not categories:
        categories = ["skills"]

    # If no categories specified, affect all
    all_categories = len(categories) == 0

    # Set up verbose output
    verbose = args.verbose

    print("=" * 60)
    print("ClaudeVN Demo Data Script")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]")

    # Handle status check
    if args.status:
        if verbose:
            print("\nFetching current status...")
        status = asyncio.run(get_status(
            serving_url=args.serving_url,
            marketplace_url=args.marketplace_url
        ))
        print("\nServing Component:")
        print(f"  Projects:    {status['serving']['projects']}")
        print(f"  Goals:       {status['serving']['goals']}")
        print(f"  Issues:      {status['serving']['issues']}")
        print(f"  Work Items:  {status['serving']['work_items']}")
        print(f"  Compute:     {status['serving']['compute']}")
        print("\nMarketplace Component:")
        print(f"  Skills:      {status['marketplace']['skills']}")
        if status["errors"]:
            print("\nErrors:")
            for error in status["errors"]:
                print(f"  - {error}")
        return

    # Handle --delete and --start early (these are standalone actions)
    if args.delete or args.start:
        # Import models not needed for delete/start (API-only operations)
        total_results: Dict[str, int] = {}

        if args.delete:
            print("\nDeleting ALL data...")
            results = asyncio.run(delete_all_data(
                dry_run=args.dry_run,
                serving_url=args.serving_url,
                marketplace_url=args.marketplace_url
            ))
            for key, value in results.items():
                total_results[f"{key}_deleted"] = value

        if args.start:
            print("\nCreating default project...")
            project_id = asyncio.run(create_default_project(
                dry_run=args.dry_run,
                serving_url=args.serving_url
            ))
            if project_id:
                total_results["default_project"] = 1
                print(f"\n  Project ready: {project_id}")
                print(f"  Open http://localhost:8002 and select it to begin.")

        # Print summary
        if total_results:
            print("\n" + "=" * 60)
            print("Summary")
            print("=" * 60)
            for key, value in total_results.items():
                display_key = key.replace("_", " ").title()
                print(f"  {display_key}: {value}")
        print("\n" + "=" * 60)
        print("Done!")
        print("=" * 60)
        return

    # Import models for populate/clear/refresh operations
    _import_models()

    # Initialize results
    total_results: Dict[str, int] = {}

    # Handle clear
    if args.clear:
        print("\nClearing demo data...")
        if verbose:
            cats = ", ".join(categories) if categories else "all"
            print(f"  Categories: {cats}")

        if all_categories or "projects" in categories:
            count = asyncio.run(clear_projects(
                dry_run=args.dry_run,
                verbose=verbose,
                serving_url=args.serving_url
            ))
            total_results["projects_cleared"] = count

        if all_categories or "goals" in categories:
            count = asyncio.run(clear_goals(
                dry_run=args.dry_run,
                verbose=verbose,
                serving_url=args.serving_url
            ))
            total_results["goals_cleared"] = count

        if all_categories or "work" in categories:
            count = asyncio.run(clear_work(
                dry_run=args.dry_run,
                verbose=verbose,
                serving_url=args.serving_url
            ))
            total_results["work_cleared"] = count

        if all_categories or "skills" in categories:
            count = asyncio.run(clear_skills(
                dry_run=args.dry_run,
                verbose=verbose,
                marketplace_url=args.marketplace_url
            ))
            total_results["skills_cleared"] = count

    # Handle refresh
    if args.refresh:
        print("\nRefreshing demo data...")
        if verbose:
            cats = ", ".join(categories) if categories else "all"
            print(f"  Categories: {cats}")

        results = asyncio.run(refresh_data(
            categories=categories,
            dry_run=args.dry_run,
            verbose=verbose,
            serving_url=args.serving_url,
            marketplace_url=args.marketplace_url
        ))
        for key, value in results.items():
            total_results[f"{key}_refreshed"] = value

    # Handle populate
    if args.populate or (not args.clear and not args.refresh and not args.status):
        print("\nPopulating demo data...")
        if verbose:
            cats = ", ".join(categories) if categories else "all"
            print(f"  Categories: {cats}")
            if args.seed is not None:
                print(f"  Seed: {args.seed}")
            if args.count > 0:
                print(f"  Count: {args.count}")

        if all_categories or "projects" in categories:
            count = asyncio.run(populate_projects(
                dry_run=args.dry_run,
                verbose=verbose,
                count=args.count,
                seed=args.seed,
                serving_url=args.serving_url
            ))
            total_results["projects_created"] = count

        if all_categories or "goals" in categories:
            count = asyncio.run(populate_goals(
                dry_run=args.dry_run,
                verbose=verbose,
                count=args.count,
                seed=args.seed,
                serving_url=args.serving_url
            ))
            total_results["goals_created"] = count

        if all_categories or "work" in categories:
            count = asyncio.run(populate_work(
                dry_run=args.dry_run,
                verbose=verbose,
                count=args.count,
                seed=args.seed,
                serving_url=args.serving_url
            ))
            total_results["work_created"] = count

        if all_categories or "skills" in categories:
            count = asyncio.run(populate_skills(
                dry_run=args.dry_run,
                verbose=verbose,
                count=args.count,
                seed=args.seed,
                marketplace_url=args.marketplace_url
            ))
            total_results["skills_created"] = count

    # Print summary
    if total_results:
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        for key, value in total_results.items():
            display_key = key.replace("_", " ").title()
            print(f"  {display_key}: {value}")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
