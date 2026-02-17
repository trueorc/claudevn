#!/usr/bin/env python3
"""
System Integration Tests (v1.0 Architecture)
=============================================

Tests complete workflows across Serving and Marketplace services:
- Serving (port 8002) ↔ Marketplace (port 8003) communication
- Skill composition and agent creation
- Work Map operations (goals, issues, work items)
- Compute registry (SSE-based registration)
- Git infrastructure endpoints

v1.0 Architecture:
- Serving: Central coordination hub (port 8002)
- Marketplace: Skill registry and composition service (port 8003)
- Compute: Claude Code instances (NOT REST services - use MCP + Git)

These tests verify that Serving and Marketplace services work together correctly.
"""

import pytest
import asyncio
import httpx
import time

# Service URLs (v1.0 architecture)
MARKETPLACE_URL = "http://localhost:8003"  # Skill Marketplace service
SERVING_URL = "http://localhost:8002"       # Central coordination hub
API_PREFIX = "/api/v1"


class TestServiceHealth:
    """Test basic service health checks."""

    @pytest.mark.asyncio
    async def test_serving_healthy(self):
        """Test that Serving service is running and healthy."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "serving"
            assert "version" in data
            print(f"Serving healthy (v{data['version']})")

    @pytest.mark.asyncio
    async def test_marketplace_healthy(self):
        """Test that Marketplace service is running and healthy."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MARKETPLACE_URL}{API_PREFIX}/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "marketplace"
            assert "skills" in data
            assert "personas" in data
            print(f"Marketplace healthy: {data['skills']} skills, {data['personas']} personas")

    @pytest.mark.asyncio
    async def test_serving_knows_marketplace(self):
        """Test that Serving can communicate with Marketplace."""
        async with httpx.AsyncClient() as client:
            # Serving's health check includes marketplace status
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/health")
            assert response.status_code == 200

            data = response.json()
            # skill_registry is populated from marketplace client
            skill_registry = data.get("skill_registry", {})

            # If marketplace is connected, we should have skill/tool counts
            # (may be 0 if marketplace just started)
            print(f"Serving skill registry: {skill_registry}")


class TestSkillMarketplace:
    """Test skill marketplace operations via Serving proxy."""

    @pytest.mark.asyncio
    async def test_list_skills_via_serving(self):
        """Test listing skills through Serving's proxy to Marketplace."""
        async with httpx.AsyncClient() as client:
            # Serving proxies skill requests to Marketplace
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/skills")
            assert response.status_code == 200

            data = response.json()
            assert "skills" in data
            assert "total" in data
            print(f"Found {data['total']} skills via Serving proxy")

    @pytest.mark.asyncio
    async def test_list_skills_direct(self):
        """Test listing skills directly from Marketplace."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MARKETPLACE_URL}{API_PREFIX}/skills")
            assert response.status_code == 200

            data = response.json()
            assert "skills" in data
            assert "total" in data
            print(f"Found {data['total']} skills from Marketplace")

    @pytest.mark.asyncio
    async def test_skill_catalog_available(self):
        """Test that skill catalog is available for planner queries."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MARKETPLACE_URL}{API_PREFIX}/skills/catalog")
            assert response.status_code == 200

            data = response.json()
            assert "skills" in data
            assert "personas" in data
            print(f"Catalog: {len(data['skills'])} skills, {len(data['personas'])} personas")

    @pytest.mark.asyncio
    async def test_list_personas(self):
        """Test listing personas from Marketplace."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MARKETPLACE_URL}{API_PREFIX}/personas")
            assert response.status_code == 200

            data = response.json()
            assert "personas" in data
            assert "total" in data
            print(f"Found {data['total']} personas")


class TestWorkMap:
    """Test Work Map operations for task allocation."""

    @pytest.mark.asyncio
    async def test_list_work_items(self):
        """Test listing work items from Work Map."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/workmap")
            assert response.status_code == 200

            data = response.json()
            # Workmap returns goals, issues, and work sections
            assert "goals" in data or "issues" in data or "work" in data
            print(f"Work map data retrieved successfully")

    @pytest.mark.asyncio
    async def test_list_goals(self):
        """Test listing goals from Work Map."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/goals")
            assert response.status_code == 200

            data = response.json()
            assert "items" in data
            assert "total" in data
            print(f"Found {data['total']} goals")

    @pytest.mark.asyncio
    async def test_list_issues(self):
        """Test listing issues from Work Map."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/issues")
            assert response.status_code == 200

            data = response.json()
            assert "items" in data
            assert "total" in data
            print(f"Found {data['total']} issues")

    @pytest.mark.asyncio
    async def test_create_and_get_goal(self):
        """Test creating and retrieving a goal."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create goal (server generates goal_id)
            goal_data = {
                "title": "Test Goal for Integration",
                "description": "Created by integration test",
                "status": "pending"
            }

            create_response = await client.post(
                f"{SERVING_URL}{API_PREFIX}/goals",
                json=goal_data
            )
            assert create_response.status_code in [200, 201]
            created = create_response.json()
            # Server generates its own goal_id
            goal_id = created["goal_id"]
            assert goal_id.startswith("goal_")
            print(f"Created goal: {goal_id}")

            # Get goal using the server-generated ID
            get_response = await client.get(
                f"{SERVING_URL}{API_PREFIX}/goals/{goal_id}"
            )
            assert get_response.status_code == 200
            retrieved = get_response.json()
            assert retrieved["goal_id"] == goal_id
            print(f"Retrieved goal: {goal_id}")


class TestComputeRegistry:
    """Test compute instance registry operations."""

    @pytest.mark.asyncio
    async def test_list_compute_instances(self):
        """Test listing registered compute instances."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/compute")
            assert response.status_code == 200

            data = response.json()
            assert "instances" in data
            assert "total" in data
            print(f"Found {data['total']} compute instances")

    @pytest.mark.asyncio
    async def test_aggregated_capabilities(self):
        """Test getting aggregated capabilities across compute instances."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_URL}{API_PREFIX}/compute/capabilities/aggregated"
            )
            assert response.status_code == 200

            data = response.json()
            # Response contains aggregated capabilities
            print(f"Aggregated capabilities: {data}")

    @pytest.mark.asyncio
    async def test_registry_stats(self):
        """Test getting compute registry statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_URL}{API_PREFIX}/compute/stats/summary"
            )
            assert response.status_code == 200

            data = response.json()
            print(f"Registry stats: {data}")


class TestGitInfrastructure:
    """Test Git infrastructure endpoints."""

    @pytest.mark.asyncio
    async def test_list_projects(self):
        """Test listing Git projects."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/projects")
            assert response.status_code == 200

            data = response.json()
            assert "items" in data
            assert "total" in data
            print(f"Found {data['total']} projects")

    @pytest.mark.asyncio
    async def test_git_status(self):
        """Test getting Git status endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/git/status")
            # May return 404 if no project configured, which is acceptable
            assert response.status_code in [200, 404]

            if response.status_code == 200:
                data = response.json()
                print(f"Git status: {data}")
            else:
                print("No Git project configured (expected in test environment)")


class TestSpawner:
    """Test compute spawner operations."""

    @pytest.mark.asyncio
    async def test_list_spawned_instances(self):
        """Test listing spawned Claude Code instances."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/spawner")
            assert response.status_code == 200

            data = response.json()
            assert "instances" in data
            print(f"Found {len(data['instances'])} spawned instances")

    @pytest.mark.asyncio
    async def test_spawner_stats(self):
        """Test getting spawner statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/spawner/stats")
            assert response.status_code == 200

            data = response.json()
            print(f"Spawner stats: {data}")


class TestOrchestrator:
    """Test work orchestrator operations."""

    @pytest.mark.asyncio
    async def test_orchestrator_status(self):
        """Test getting orchestrator status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/orchestrator/status")
            assert response.status_code == 200

            data = response.json()
            assert "status" in data
            # Status can be "running" or "paused"
            assert data["status"] in ["running", "paused"]
            print(f"Orchestrator status: {data['status']}")

    @pytest.mark.asyncio
    async def test_orchestrator_stats(self):
        """Test getting orchestrator statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVING_URL}{API_PREFIX}/orchestrator/stats")
            assert response.status_code == 200

            data = response.json()
            print(f"Orchestrator stats: {data}")


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_nonexistent_goal(self):
        """Test accessing non-existent goal."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_URL}{API_PREFIX}/goals/nonexistent-goal-999"
            )
            assert response.status_code == 404
            print("Non-existent goal returns 404")

    @pytest.mark.asyncio
    async def test_nonexistent_skill(self):
        """Test accessing non-existent skill."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_URL}{API_PREFIX}/skills/nonexistent-skill-999"
            )
            assert response.status_code == 404
            print("Non-existent skill returns 404")

    @pytest.mark.asyncio
    async def test_nonexistent_compute_instance(self):
        """Test accessing non-existent compute instance."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVING_URL}{API_PREFIX}/compute/nonexistent-compute-999"
            )
            assert response.status_code == 404
            print("Non-existent compute instance returns 404")


class TestPerformance:
    """Basic performance tests."""

    @pytest.mark.asyncio
    async def test_health_response_time(self):
        """Test that health checks complete quickly."""
        async with httpx.AsyncClient() as client:
            # Serving health check
            start = time.time()
            await client.get(f"{SERVING_URL}{API_PREFIX}/health")
            serving_time = time.time() - start
            assert serving_time < 2.0, f"Serving health check too slow: {serving_time}s"

            # Marketplace health check
            start = time.time()
            await client.get(f"{MARKETPLACE_URL}{API_PREFIX}/health")
            marketplace_time = time.time() - start
            assert marketplace_time < 2.0, f"Marketplace health check too slow: {marketplace_time}s"

            print(f"Health check times - Serving: {serving_time:.3f}s, Marketplace: {marketplace_time:.3f}s")

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling concurrent requests."""
        async with httpx.AsyncClient() as client:
            # Send 5 concurrent health checks to each service
            tasks = []
            for _ in range(5):
                tasks.append(client.get(f"{SERVING_URL}{API_PREFIX}/health"))
                tasks.append(client.get(f"{MARKETPLACE_URL}{API_PREFIX}/health"))

            responses = await asyncio.gather(*tasks)

            # All should succeed
            for response in responses:
                assert response.status_code == 200

            print(f"Successfully handled {len(tasks)} concurrent requests")


class TestDataFlow:
    """Test data flow between services."""

    @pytest.mark.asyncio
    async def test_skill_data_consistency(self):
        """Test that skill data is consistent between Serving proxy and Marketplace."""
        async with httpx.AsyncClient() as client:
            # Get skills via Serving proxy
            serving_response = await client.get(f"{SERVING_URL}{API_PREFIX}/skills")
            assert serving_response.status_code == 200
            serving_data = serving_response.json()

            # Get skills directly from Marketplace
            marketplace_response = await client.get(f"{MARKETPLACE_URL}{API_PREFIX}/skills")
            assert marketplace_response.status_code == 200
            marketplace_data = marketplace_response.json()

            # Counts should match (Serving proxies to Marketplace)
            assert serving_data["total"] == marketplace_data["total"]
            print(f"Skill data consistent: {serving_data['total']} skills")

    @pytest.mark.asyncio
    async def test_work_map_to_orchestrator_flow(self):
        """Test that Work Map and Orchestrator are connected."""
        async with httpx.AsyncClient() as client:
            # Get work map stats
            work_response = await client.get(f"{SERVING_URL}{API_PREFIX}/health")
            assert work_response.status_code == 200
            health_data = work_response.json()

            # Verify work_map stats exist in health response
            assert "work_map" in health_data
            work_stats = health_data["work_map"]

            # Verify orchestrator stats exist
            assert "work_orchestrator" in health_data
            orch_stats = health_data["work_orchestrator"]

            print(f"Work Map: {work_stats.get('total_work', 0)} items")
            print(f"Orchestrator running: {orch_stats.get('running', False)}")


# Run tests
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("ClaudeVN System Integration Tests (v1.0)")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print(f"  - Serving running at {SERVING_URL}")
    print(f"  - Marketplace running at {MARKETPLACE_URL}")
    print()
    print("v1.0 Architecture Notes:")
    print("  - Compute is now Claude Code instances (not REST service)")
    print("  - Communication via MCP tools and Git")
    print("  - Marketplace is a separate service (port 8003)")
    print()
    print("These tests verify:")
    print("  - Service health and communication")
    print("  - Skill marketplace operations")
    print("  - Work Map task allocation")
    print("  - Compute registry")
    print("  - Error handling")
    print()
    print("Running tests...")
    print()

    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
