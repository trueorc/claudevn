"""API interaction functions for demo data management.

Handles all HTTP communication with the Serving and Marketplace services.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from demo_data.compute import DEMO_COMPUTE_INSTANCES
from demo_data.phase1_foundation import DEMO_PROJECTS, PHASE1_GOALS, PHASE1_ISSUES
from demo_data.phase2_execution import (
    PHASE2_GOALS,
    PHASE2_ISSUES,
    PHASE2_WORK_ITEMS,
)
from demo_data.phase3_growth import (
    PHASE3_GOALS,
    PHASE3_ISSUES,
    PHASE3_WORK_ITEMS,
)
from demo_data.skills import DEMO_SKILLS


# ==============================================================================
# Data Aggregation by Phase
# ==============================================================================

def get_goals_for_phases(phases: list[int]) -> list[dict]:
    """Get goal data for the requested phases."""
    goals = []
    if 1 in phases:
        goals.extend(PHASE1_GOALS)
    if 2 in phases:
        goals.extend(PHASE2_GOALS)
    if 3 in phases:
        goals.extend(PHASE3_GOALS)
    return goals


def get_issues_for_phases(phases: list[int]) -> list[dict]:
    """Get issue data for the requested phases."""
    issues = []
    if 1 in phases:
        issues.extend(PHASE1_ISSUES)
    if 2 in phases:
        issues.extend(PHASE2_ISSUES)
    if 3 in phases:
        issues.extend(PHASE3_ISSUES)
    return issues


def get_work_items_for_phases(phases: list[int]) -> list[dict]:
    """Get work item data for the requested phases."""
    items = []
    if 2 in phases:
        items.extend(PHASE2_WORK_ITEMS)
    if 3 in phases:
        items.extend(PHASE3_WORK_ITEMS)
    return items


# ==============================================================================
# Timestamp Generation
# ==============================================================================

def generate_timestamps(base_offset_days: int = 0) -> Dict[str, datetime]:
    """Generate realistic timestamps for demo data."""
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=base_offset_days + random.randint(1, 30))
    updated = created + timedelta(hours=random.randint(1, 48))
    return {
        "created_at": created,
        "updated_at": min(updated, now),
    }


# ==============================================================================
# Populate Functions
# ==============================================================================

async def populate_projects(
    phases: list[int] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    serving_url: str = "http://localhost:8002",
) -> int:
    """Populate projects via API."""
    import httpx

    if seed is not None:
        random.seed(seed)

    # Projects are always the same regardless of phase
    projects = DEMO_PROJECTS[:count] if count > 0 else DEMO_PROJECTS
    created = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n  Creating projects...")
        for data in projects:
            if dry_run:
                print(f"    [DRY RUN] Would create project: {data['name']}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/projects",
                    json={
                        "name": data["name"],
                        "description": data.get("description", ""),
                        "metadata": data.get("metadata", {}),
                    },
                )
                if resp.status_code == 201:
                    created += 1
                    print(f"    Created project: {data['name']}")
                elif resp.status_code == 409:
                    print(f"    Project already exists: {data['name']}")
                else:
                    print(f"    Failed to create project {data['name']}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating project {data['name']}: {e}")

    return created


async def populate_goals(
    phases: list[int] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    serving_url: str = "http://localhost:8002",
) -> int:
    """Populate goals via API."""
    import httpx

    if seed is not None:
        random.seed(seed)

    phases = phases or [1, 2, 3]
    goals = get_goals_for_phases(phases)
    if count > 0:
        goals = goals[:count]

    created = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"\n  Creating {len(goals)} goals...")
        for data in goals:
            if dry_run:
                print(f"    [DRY RUN] Would create goal: {data['title']}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/goals",
                    json={
                        "title": data["title"],
                        "description": data["description"],
                        "priority": data.get("priority", "P1"),
                    },
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created goal: {data['title']}")
                else:
                    print(f"    Failed to create goal {data['title']}: {resp.status_code}")
                    if verbose:
                        print(f"      Response: {resp.text[:200]}")
            except Exception as e:
                print(f"    Error creating goal {data['title']}: {e}")

    return created


async def populate_work(
    phases: list[int] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    serving_url: str = "http://localhost:8002",
) -> int:
    """Populate issues and work items via API."""
    import httpx

    if seed is not None:
        random.seed(seed)

    phases = phases or [1, 2, 3]
    issues = get_issues_for_phases(phases)
    work_items = get_work_items_for_phases(phases)
    if count > 0:
        issues = issues[:count]
        work_items = work_items[:count]

    created = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create issues
        print(f"\n  Creating {len(issues)} issues...")
        for data in issues:
            if dry_run:
                print(f"    [DRY RUN] Would create issue: {data['title']}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/issues",
                    json={
                        "title": data["title"],
                        "description": data["description"],
                        "issue_type": data.get("issue_type", "feature"),
                        "area": data.get("area", "other"),
                        "priority": data.get("priority", "P2"),
                        "required_skills": data.get("required_skills", []),
                        "depends_on": data.get("depends_on", []),
                        "goal_id": data.get("goal_id"),
                    },
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created issue: {data['title']}")
                else:
                    if verbose:
                        print(f"    Failed to create issue {data['title']}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating issue {data['title']}: {e}")

        # Create work items
        print(f"\n  Creating {len(work_items)} work items...")
        for data in work_items:
            if dry_run:
                print(f"    [DRY RUN] Would create work item: {data['title']}")
                created += 1
                continue

            try:
                resp = await client.post(
                    f"{base_url}/work-map/work",
                    json={
                        "title": data["title"],
                        "description": data["description"],
                        "work_type": data.get("work_type", "task"),
                        "priority": data.get("priority", "normal"),
                        "tags": data.get("tags", []),
                        "required_skills": data.get("required_skills", []),
                        "required_labels": data.get("required_labels", []),
                        "required_tools": data.get("required_tools", []),
                        "project_id": data.get("project_id", "demo-claudevn"),
                        "base_branch": data.get("base_branch", "main"),
                    },
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created work item: {data['title']}")
                else:
                    if verbose:
                        print(f"    Failed to create work {data['title']}: {resp.status_code}")
            except Exception as e:
                print(f"    Error creating work item {data['title']}: {e}")

        # Register compute instances
        print(f"\n  Registering {len(DEMO_COMPUTE_INSTANCES)} compute instances...")
        for data in DEMO_COMPUTE_INSTANCES:
            if dry_run:
                print(f"    [DRY RUN] Would register compute: {data['name']}")
                created += 1
                continue

            try:
                caps = data.get("capabilities", {})
                resources = caps.get("resources")
                resp = await client.post(
                    f"{base_url}/compute/register",
                    json={
                        "instance_id": data["instance_id"],
                        "name": data["name"],
                        "endpoint": data["endpoint"],
                        "health_endpoint": data.get("health_endpoint"),
                        "capabilities": {
                            "agents": caps.get("agents", []),
                            "tools": caps.get("tools", []),
                            "labels": caps.get("labels", []),
                            "tools_available": caps.get("tools_available", []),
                            "resources": resources,
                        },
                        "metadata": data.get("metadata", {}),
                    },
                )
                if resp.status_code in (200, 201):
                    created += 1
                    if verbose:
                        print(f"    Registered compute: {data['name']}")
                elif resp.status_code == 409:
                    if verbose:
                        print(f"    Compute already registered: {data['name']}")
                else:
                    if verbose:
                        print(f"    Failed to register compute {data['name']}: {resp.status_code}")
            except Exception as e:
                print(f"    Error registering compute {data['name']}: {e}")

    return created


async def populate_skills(
    dry_run: bool = False,
    verbose: bool = False,
    count: int = 0,
    seed: Optional[int] = None,
    marketplace_url: str = "http://localhost:8003",
) -> int:
    """Populate marketplace skills via API."""
    import httpx

    if seed is not None:
        random.seed(seed)

    skills = DEMO_SKILLS[:count] if count > 0 else DEMO_SKILLS
    created = 0
    skills_url = f"{marketplace_url}/api/v1/skills"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"\n  Creating {len(skills)} skills...")
        for data in skills:
            if dry_run:
                print(f"    [DRY RUN] Would create skill: {data['name']}")
                created += 1
                continue

            try:
                resp = await client.post(
                    skills_url,
                    json={
                        "id": data["id"],
                        "name": data["name"],
                        "description": data["description"],
                        "instructions": data["instructions"],
                        "specialized_tools": data.get("specialized_tools", []),
                        "tags": data.get("tags", []),
                        "dependencies": data.get("dependencies", []),
                        "version": "1.0.0",
                    },
                )
                if resp.status_code == 201:
                    created += 1
                    if verbose:
                        print(f"    Created skill: {data['name']}")
                elif resp.status_code == 409:
                    if verbose:
                        print(f"    Skill already exists: {data['name']}")
                else:
                    if verbose:
                        print(f"    Failed to create skill {data['name']}: {resp.status_code} - {resp.text[:100]}")
            except Exception as e:
                print(f"    Error creating skill {data['name']}: {e}")

    return created


# ==============================================================================
# Clear Functions
# ==============================================================================

async def clear_demo_data(
    phases: list[int] | None = None,
    dry_run: bool = False,
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003",
) -> Dict[str, int]:
    """Clear all demo data from the system."""
    import httpx

    results = {"projects": 0, "goals": 0, "issues": 0, "work_items": 0, "compute": 0, "skills": 0}

    async with httpx.AsyncClient(timeout=30.0) as client:
        base_url = f"{serving_url}/api/v1"

        # Delete compute instances with demo metadata
        print("\n  Removing compute instances...")
        try:
            resp = await client.get(f"{base_url}/compute")
            if resp.status_code == 200:
                data = resp.json()
                instances = data.get("instances", data.get("items", []))
                for instance in instances:
                    if instance.get("metadata", {}).get("demo"):
                        iid = instance["instance_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete compute: {iid}")
                            results["compute"] += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/compute/{iid}")
                            if del_resp.status_code in (200, 204):
                                results["compute"] += 1
                                print(f"    Deleted compute: {iid}")
        except Exception as e:
            print(f"    Error clearing compute instances: {e}")

        # Delete work items (demo-prefixed)
        print("\n  Removing work items...")
        try:
            resp = await client.get(f"{base_url}/work-map/work")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("work_id", "").startswith("work-demo-"):
                        wid = item["work_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete work: {wid}")
                            results["work_items"] += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/work/{wid}")
                            if del_resp.status_code in (200, 204):
                                results["work_items"] += 1
                                print(f"    Deleted work: {wid}")
        except Exception as e:
            print(f"    Error clearing work items: {e}")

        # Delete issues (demo-prefixed)
        print("\n  Removing issues...")
        try:
            resp = await client.get(f"{base_url}/work-map/issues")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("issue_id", "").startswith("issue-demo-"):
                        iid = item["issue_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete issue: {iid}")
                            results["issues"] += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/issues/{iid}")
                            if del_resp.status_code in (200, 204):
                                results["issues"] += 1
                                print(f"    Deleted issue: {iid}")
        except Exception as e:
            print(f"    Error clearing issues: {e}")

        # Delete goals (demo-prefixed)
        print("\n  Removing goals...")
        try:
            resp = await client.get(f"{base_url}/work-map/goals")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("goal_id", "").startswith("goal-demo-"):
                        gid = item["goal_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete goal: {gid}")
                            results["goals"] += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/goals/{gid}")
                            if del_resp.status_code in (200, 204):
                                results["goals"] += 1
                                print(f"    Deleted goal: {gid}")
        except Exception as e:
            print(f"    Error clearing goals: {e}")

        # Delete projects with demo metadata
        print("\n  Removing projects...")
        try:
            resp = await client.get(f"{base_url}/projects")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    if item.get("metadata", {}).get("demo"):
                        pid = item["project_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete project: {pid}")
                            results["projects"] += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/projects/{pid}")
                            if del_resp.status_code in (200, 204):
                                results["projects"] += 1
                                print(f"    Deleted project: {pid}")
        except Exception as e:
            print(f"    Error clearing projects: {e}")

        # Delete demo skills from marketplace
        skills_url = f"{marketplace_url}/api/v1/skills"
        print("\n  Removing skills...")
        for skill_data in DEMO_SKILLS:
            skill_id = skill_data["id"]
            if dry_run:
                print(f"    [DRY RUN] Would delete skill: {skill_id}")
                results["skills"] += 1
            else:
                try:
                    del_resp = await client.delete(f"{skills_url}/{skill_id}")
                    if del_resp.status_code in (200, 204):
                        results["skills"] += 1
                        print(f"    Deleted skill: {skill_id}")
                except Exception as e:
                    print(f"    Error deleting skill {skill_id}: {e}")

    return results


async def clear_projects(
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002",
) -> int:
    """Clear only project data."""
    import httpx

    count = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{base_url}/projects")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("metadata", {}).get("demo"):
                        pid = item["project_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete project: {pid}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/projects/{pid}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted project: {pid}")
        except Exception as e:
            print(f"    Error clearing projects: {e}")

    return count


async def clear_goals(
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002",
) -> int:
    """Clear only goal data."""
    import httpx

    count = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{base_url}/work-map/goals")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("goal_id", "").startswith("goal-demo-"):
                        gid = item["goal_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete goal: {gid}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/goals/{gid}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted goal: {gid}")
        except Exception as e:
            print(f"    Error clearing goals: {e}")

    return count


async def clear_work(
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002",
) -> int:
    """Clear work items and issues."""
    import httpx

    count = 0
    base_url = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Work items
        try:
            resp = await client.get(f"{base_url}/work-map/work")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("work_id", "").startswith("work-demo-"):
                        wid = item["work_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete work: {wid}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/work/{wid}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted work: {wid}")
        except Exception as e:
            print(f"    Error clearing work items: {e}")

        # Issues
        try:
            resp = await client.get(f"{base_url}/work-map/issues")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("issue_id", "").startswith("issue-demo-"):
                        iid = item["issue_id"]
                        if dry_run:
                            print(f"    [DRY RUN] Would delete issue: {iid}")
                            count += 1
                        else:
                            del_resp = await client.delete(f"{base_url}/work-map/issues/{iid}")
                            if del_resp.status_code in (200, 204):
                                count += 1
                                if verbose:
                                    print(f"    Deleted issue: {iid}")
        except Exception as e:
            print(f"    Error clearing issues: {e}")

    return count


async def clear_skills(
    dry_run: bool = False,
    verbose: bool = False,
    marketplace_url: str = "http://localhost:8003",
) -> int:
    """Clear only demo skills."""
    import httpx

    count = 0
    skills_url = f"{marketplace_url}/api/v1/skills"

    async with httpx.AsyncClient(timeout=30.0) as client:
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


# ==============================================================================
# Status & Utility Functions
# ==============================================================================

async def get_status(
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003",
) -> Dict[str, Any]:
    """Get current data counts from the system."""
    import httpx

    status: Dict[str, Any] = {
        "serving": {"projects": 0, "goals": 0, "issues": 0, "work_items": 0, "compute": 0},
        "marketplace": {"skills": 0},
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        base_url = f"{serving_url}/api/v1"

        for key, endpoint in [
            ("projects", f"{base_url}/projects"),
            ("goals", f"{base_url}/work-map/goals"),
            ("issues", f"{base_url}/work-map/issues"),
            ("work_items", f"{base_url}/work-map/work"),
            ("compute", f"{base_url}/compute"),
        ]:
            try:
                resp = await client.get(endpoint)
                if resp.status_code == 200:
                    status["serving"][key] = resp.json().get("total", 0)
            except Exception as e:
                status["errors"].append(f"{key}: {e}")

        try:
            resp = await client.get(f"{marketplace_url}/api/v1/skills")
            if resp.status_code == 200:
                status["marketplace"]["skills"] = resp.json().get("total", 0)
        except Exception as e:
            status["errors"].append(f"skills: {e}")

    return status


async def delete_all_data(
    dry_run: bool = False,
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003",
) -> Dict[str, int]:
    """Delete ALL data from the system (not just demo-tagged)."""
    import httpx

    results: Dict[str, int] = {
        "goals": 0, "issues": 0, "work_items": 0, "projects": 0,
        "compute": 0, "marketplaces": 0,
    }
    base = f"{serving_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Delete all goals (hard delete)
        print("\n  Deleting all goals...")
        try:
            resp = await client.get(f"{base}/goals")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
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

        # Delete all issues
        print("\n  Deleting all issues...")
        try:
            resp = await client.get(f"{base}/issues")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    iid = item["issue_id"]
                    if dry_run:
                        print(f"    [DRY RUN] Would delete issue: {iid}")
                    else:
                        del_resp = await client.delete(f"{base}/issues/{iid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deleted issue: {iid}")
                    results["issues"] += 1
        except Exception as e:
            print(f"    Error deleting issues: {e}")

        # Delete all work items
        print("\n  Deleting all work items...")
        try:
            resp = await client.get(f"{base}/work")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    wid = item["work_id"]
                    if dry_run:
                        print(f"    [DRY RUN] Would delete work: {wid}")
                    else:
                        del_resp = await client.delete(f"{base}/work/{wid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deleted work: {wid}")
                    results["work_items"] += 1
        except Exception as e:
            print(f"    Error deleting work items: {e}")

        # Delete all projects and directives
        print("\n  Deleting all projects...")
        try:
            resp = await client.get(f"{base}/projects")
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    pid = item["project_id"]
                    if not dry_run:
                        # Delete unified directives first
                        await client.delete(
                            f"{base}/unified-directives",
                            params={"project_id": pid},
                        )
                    if dry_run:
                        print(f"    [DRY RUN] Would delete project: {pid}")
                    else:
                        del_resp = await client.delete(f"{base}/projects/{pid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deleted project: {pid}")
                    results["projects"] += 1
        except Exception as e:
            print(f"    Error deleting projects: {e}")

        # Deregister stale compute instances
        print("\n  Cleaning up compute instances...")
        try:
            resp = await client.get(f"{base}/compute")
            if resp.status_code == 200:
                data = resp.json()
                instances = data.get("instances", data.get("items", []))
                for inst in instances:
                    iid = inst["instance_id"]
                    status = inst.get("status", "")
                    metadata = inst.get("metadata", {})
                    # Skip live SSE-connected computes
                    if metadata.get("connection_type") == "sse" and status in ("online", "idle"):
                        print(f"    Skipping live compute: {iid}")
                        continue
                    if dry_run:
                        print(f"    [DRY RUN] Would deregister compute: {iid}")
                    else:
                        del_resp = await client.delete(f"{base}/compute/{iid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deregistered compute: {iid}")
                    results["compute"] += 1
        except Exception as e:
            print(f"    Error cleaning compute instances: {e}")

        # Clean up stale marketplace instances
        print("\n  Cleaning up marketplace instances...")
        try:
            resp = await client.get(f"{base}/marketplaces")
            if resp.status_code == 200:
                data = resp.json()
                instances = data.get("marketplaces", data.get("items", []))
                for mp in instances:
                    mid = mp.get("marketplace_id", mp.get("id", ""))
                    mp_status = mp.get("status", "")
                    if mp_status in ("healthy", "online"):
                        print(f"    Skipping healthy marketplace: {mid}")
                        continue
                    if dry_run:
                        print(f"    [DRY RUN] Would deregister marketplace: {mid}")
                    else:
                        del_resp = await client.delete(f"{base}/marketplaces/{mid}")
                        if del_resp.status_code in (200, 204):
                            print(f"    Deregistered marketplace: {mid}")
                    results["marketplaces"] += 1
        except Exception as e:
            print(f"    Error cleaning marketplace instances: {e}")

    return results


async def create_default_project(
    dry_run: bool = False,
    serving_url: str = "http://localhost:8002",
) -> Optional[str]:
    """Create a default project."""
    import httpx

    base = f"{serving_url}/api/v1"
    project_data = {
        "name": "Default Project",
        "description": "Default working project for ClaudeVN development",
        "metadata": {"default": True},
    }

    if dry_run:
        print("  [DRY RUN] Would create default project")
        return None

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{base}/projects", json=project_data)
            if resp.status_code == 201:
                pid = resp.json().get("project_id", "unknown")
                print(f"  Created default project: {pid}")
                return pid
            else:
                print(f"  Failed to create default project: {resp.status_code}")
                return None
        except Exception as e:
            print(f"  Error creating default project: {e}")
            return None


async def refresh_data(
    categories: List[str],
    dry_run: bool = False,
    verbose: bool = False,
    serving_url: str = "http://localhost:8002",
    marketplace_url: str = "http://localhost:8003",
) -> Dict[str, int]:
    """Refresh existing demo data (update timestamps)."""
    import httpx

    results: Dict[str, int] = {}
    base_url = f"{serving_url}/api/v1"

    all_categories = not categories or len(categories) == 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        if all_categories or "projects" in categories:
            count = 0
            try:
                resp = await client.get(f"{base_url}/projects")
                if resp.status_code == 200:
                    for item in resp.json().get("items", []):
                        if item.get("metadata", {}).get("demo"):
                            pid = item["project_id"]
                            if dry_run:
                                print(f"    [DRY RUN] Would refresh project: {pid}")
                                count += 1
                            else:
                                now = datetime.now(timezone.utc)
                                patch_resp = await client.patch(
                                    f"{base_url}/projects/{pid}",
                                    json={"metadata": {"demo": True, "refreshed_at": now.isoformat()}},
                                )
                                if patch_resp.status_code in (200, 204):
                                    count += 1
            except Exception as e:
                print(f"    Error refreshing projects: {e}")
            results["projects"] = count

        if all_categories or "goals" in categories:
            count = 0
            try:
                resp = await client.get(f"{base_url}/work-map/goals")
                if resp.status_code == 200:
                    for item in resp.json().get("items", []):
                        if item.get("goal_id", "").startswith("goal-demo-"):
                            gid = item["goal_id"]
                            if dry_run:
                                print(f"    [DRY RUN] Would refresh goal: {gid}")
                                count += 1
                            else:
                                patch_resp = await client.patch(
                                    f"{base_url}/work-map/goals/{gid}",
                                    json={"description": item.get("description", "") + " "},
                                )
                                if patch_resp.status_code in (200, 204):
                                    count += 1
            except Exception as e:
                print(f"    Error refreshing goals: {e}")
            results["goals"] = count

        if all_categories or "work" in categories:
            count = 0
            try:
                resp = await client.get(f"{base_url}/work-map/work")
                if resp.status_code == 200:
                    for item in resp.json().get("items", []):
                        if item.get("work_id", "").startswith("work-demo-"):
                            wid = item["work_id"]
                            if dry_run:
                                print(f"    [DRY RUN] Would refresh work: {wid}")
                                count += 1
                            else:
                                patch_resp = await client.patch(
                                    f"{base_url}/work-map/work/{wid}",
                                    json={"description": item.get("description", "") + " "},
                                )
                                if patch_resp.status_code in (200, 204):
                                    count += 1
            except Exception as e:
                print(f"    Error refreshing work items: {e}")
            results["work_items"] = count

    return results
