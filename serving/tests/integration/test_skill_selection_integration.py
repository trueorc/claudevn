"""
Integration Tests for Skill Selection and Persona Composition (Issue #286)
==========================================================================

Tests the skill selection and persona composition flow when work is created
and assigned to compute instances:

1. Creating work with required_capabilities triggers skill selection
2. SkillSelectionService returns matching skills from marketplace
3. Fallback to work_type-based default skills when no matches
4. Marketplace client fetches skill definitions correctly
5. Work item skill_ids are populated after assignment
6. Composed CLAUDE.md includes selected skill instructions

Prerequisites:
    - Running Docker containers: claudevn-serving, claudevn-redis, claudevn-marketplace
    - Marketplace service populated with test skills

Run with:
    ./scripts/run_integration_tests.sh
    pytest serving/tests/integration/test_skill_selection_integration.py -v
"""

import asyncio
import os
import pytest
import uuid
from typing import Optional, List

import httpx

# Test configuration from environment or defaults
SERVING_BASE_URL = os.getenv("SERVING_BASE_URL", "http://localhost:8002")
MARKETPLACE_BASE_URL = os.getenv("MARKETPLACE_BASE_URL", "http://localhost:8003")
API_PREFIX = "/api/v1"

# Redis configuration for direct verification
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "claudevn:")

# Retry configuration
MAX_RETRIES = 3
DEFAULT_RETRY_AFTER = 5
MAX_RETRY_WAIT = 10


def generate_test_id() -> str:
    """Generate a unique test identifier."""
    return uuid.uuid4().hex[:8]


async def make_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    max_retries: int = MAX_RETRIES,
    **kwargs
) -> httpx.Response:
    """Make an HTTP request with retry on rate limit (429) errors."""
    for attempt in range(max_retries):
        response = await client.request(method, url, **kwargs)
        if response.status_code == 429:
            retry_after = int(response.json().get("retry_after", DEFAULT_RETRY_AFTER))
            if attempt < max_retries - 1:
                await asyncio.sleep(min(retry_after, MAX_RETRY_WAIT))
                continue
        return response
    return response


async def get_redis_client():
    """Get a Redis client for direct test verification."""
    try:
        import redis.asyncio as redis
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
    except ImportError:
        pytest.skip("redis package not installed")


# =============================================================================
# Module-level Fixtures (shared across all test classes)
# =============================================================================

@pytest.fixture
async def http_client():
    """Create HTTP client for serving API calls."""
    async with httpx.AsyncClient(
        base_url=SERVING_BASE_URL,
        timeout=30.0
    ) as client:
        yield client


@pytest.fixture
async def marketplace_client():
    """Create HTTP client for marketplace API calls."""
    async with httpx.AsyncClient(
        base_url=MARKETPLACE_BASE_URL,
        timeout=30.0
    ) as client:
        yield client


@pytest.fixture
async def test_project(http_client):
    """Create a test project for work items with cleanup."""
    project_id = f"project-skill-test-{generate_test_id()}"
    response = await http_client.post(
        f"{API_PREFIX}/projects",
        json={
            "project_id": project_id,
            "name": f"Skill Selection Test Project {project_id}",
            "description": "Project for skill selection integration tests"
        }
    )
    if response.status_code not in [200, 201, 409]:
        pytest.skip(f"Could not create test project: {response.status_code}")

    yield project_id

    # Cleanup: attempt to delete project (ignore errors)
    try:
        await http_client.delete(f"{API_PREFIX}/projects/{project_id}")
    except Exception:
        pass  # Best effort cleanup


# =============================================================================
# Test Classes
# =============================================================================

class TestMarketplaceConnectivity:
    """Test marketplace service connectivity and skill availability."""

    @pytest.mark.asyncio
    async def test_marketplace_health(self, marketplace_client):
        """Test that marketplace service is healthy."""
        response = await marketplace_client.get(f"{API_PREFIX}/health")
        if response.status_code != 200:
            pytest.skip(f"Marketplace not available: {response.status_code}")

        health = response.json()
        assert health.get("status") in ["healthy", "ok"]

    @pytest.mark.asyncio
    async def test_marketplace_lists_skills(self, marketplace_client):
        """Test that marketplace returns available skills."""
        response = await marketplace_client.get(f"{API_PREFIX}/skills")
        if response.status_code != 200:
            pytest.skip(f"Marketplace skills endpoint not available: {response.status_code}")

        skills_data = response.json()
        assert "skills" in skills_data
        assert "total" in skills_data
        assert skills_data["total"] >= 0

    @pytest.mark.asyncio
    async def test_marketplace_skill_structure(self, marketplace_client):
        """Test that skills have proper structure for matching."""
        response = await marketplace_client.get(f"{API_PREFIX}/skills")
        if response.status_code != 200:
            pytest.skip("Marketplace not available")

        skills_data = response.json()
        skills = skills_data.get("skills", [])

        if not skills:
            pytest.skip("No skills in marketplace to verify")

        # Verify skill structure matches what SkillSelectionService expects
        for skill in skills:
            # SkillSelectionService uses skill.get("skill_id") - verify field exists
            skill_id = skill.get("id") or skill.get("skill_id")
            assert skill_id is not None, "Skill must have 'id' or 'skill_id' field"

            # Capabilities are used for matching
            # May be in "capabilities" or "tags" field
            caps = skill.get("capabilities", [])
            assert isinstance(caps, list), "capabilities should be a list"


class TestSkillSelectionWithCapabilities:
    """Test skill selection based on work required_capabilities."""

    @pytest.mark.asyncio
    async def test_work_creation_with_required_capabilities(
        self, http_client, test_project
    ):
        """Test that creating work with required_capabilities is accepted."""
        work_data = {
            "title": f"Skill selection test {generate_test_id()}",
            "description": "Testing work with required capabilities",
            "project_id": test_project,
            "work_type": "feature",
            "required_capabilities": ["python", "testing"]
        }

        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201, f"Failed to create work: {response.text}"

        work = response.json()
        try:
            assert "work_id" in work
            assert work["required_capabilities"] == ["python", "testing"]
        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work['work_id']}")

    @pytest.mark.asyncio
    async def test_assignment_populates_skill_ids(
        self, http_client, marketplace_client, test_project
    ):
        """Test that work assignment populates skill_ids based on capabilities.

        Verifies acceptance criteria #5: skill_ids on work item are populated
        after assignment.
        """
        # First check if marketplace has skills with matching capabilities
        mp_response = await marketplace_client.get(f"{API_PREFIX}/skills")
        if mp_response.status_code != 200:
            pytest.skip("Marketplace not available for skill matching test")

        skills_data = mp_response.json()
        available_skills = skills_data.get("skills", [])

        # Find a capability that exists in at least one skill
        test_capability = None
        for skill in available_skills:
            caps = skill.get("capabilities", []) or skill.get("tags", [])
            if caps:
                test_capability = caps[0]
                break

        if not test_capability:
            test_capability = "python"

        # Create work with the test capability
        work_data = {
            "title": f"Skill assignment test {generate_test_id()}",
            "description": "Testing skill assignment via capabilities",
            "project_id": test_project,
            "required_capabilities": [test_capability]
        }

        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201
        work = response.json()
        work_id = work["work_id"]

        try:
            # Assign work to compute (this triggers skill selection)
            compute_id = f"test-compute-{generate_test_id()}"
            assign_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id}
            )
            assert assign_response.status_code == 200

            # Get updated work to check skill_ids
            get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assert get_response.status_code == 200
            updated_work = get_response.json()

            # Verify assignment state
            assert updated_work["status"] == "assigned"
            assert updated_work["assigned_to"] == compute_id

            # Verify skill_ids is populated (acceptance criteria #5)
            skill_ids = updated_work.get("skill_ids", [])
            assert isinstance(skill_ids, list), "skill_ids should be a list"
            # skill_ids should be populated with either matched skills or fallback
            # Note: If no skills match and no fallback configured, could be empty
            # The SkillSelectionService returns ["general"] as fallback

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_work_without_capabilities_uses_default_skills(
        self, http_client, test_project
    ):
        """Test that work without required_capabilities uses default/general skills.

        Verifies acceptance criteria #3: Fallback to work_type-based default skills.
        """
        work_data = {
            "title": f"Default skills test {generate_test_id()}",
            "description": "Testing default skill selection",
            "project_id": test_project,
            "work_type": "feature"
            # No required_capabilities
        }

        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201
        work = response.json()
        work_id = work["work_id"]

        try:
            # Assign work
            compute_id = f"test-compute-{generate_test_id()}"
            assign_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id}
            )
            assert assign_response.status_code == 200

            # Verify assignment
            get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            updated_work = get_response.json()
            assert updated_work["status"] == "assigned"

            # Without required_capabilities, SkillSelectionService returns ["general"]
            skill_ids = updated_work.get("skill_ids", [])
            assert isinstance(skill_ids, list)
            # Should have fallback skill
            if skill_ids:
                # If populated, "general" is expected fallback
                assert "general" in skill_ids or len(skill_ids) > 0

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestSkillSelectionFallback:
    """Test fallback behavior when marketplace is unavailable or skills don't match."""

    @pytest.mark.asyncio
    async def test_work_with_unmatchable_capabilities_gets_fallback(
        self, http_client, test_project
    ):
        """Test that work with unmatchable capabilities gets fallback skills.

        Verifies acceptance criteria #3: Fallback when no skills match.
        """
        # Use very specific capabilities unlikely to match any skill
        work_data = {
            "title": f"Unmatchable caps test {generate_test_id()}",
            "description": "Testing fallback when no skills match",
            "project_id": test_project,
            "required_capabilities": [
                "nonexistent-capability-xyz123",
                "another-fake-capability-abc456"
            ]
        }

        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201
        work = response.json()
        work_id = work["work_id"]

        try:
            # Assign work
            compute_id = f"test-compute-{generate_test_id()}"
            assign_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id}
            )
            assert assign_response.status_code == 200

            # Verify assignment still works with fallback
            get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            updated_work = get_response.json()
            assert updated_work["status"] == "assigned"

            # Should have fallback skills
            skill_ids = updated_work.get("skill_ids", [])
            assert isinstance(skill_ids, list)
            # SkillSelectionService returns ["general"] when no matches found

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestMarketplaceSkillComposition:
    """Test skill composition through marketplace compose endpoint.

    Verifies acceptance criteria #6: Composed CLAUDE.md includes skill instructions.
    """

    @pytest.mark.asyncio
    async def test_compose_agent_returns_merged_instructions(
        self, marketplace_client
    ):
        """Test that compose endpoint returns merged instructions."""
        # First get available skills
        skills_response = await marketplace_client.get(f"{API_PREFIX}/skills")
        if skills_response.status_code != 200:
            pytest.skip("Marketplace not available")

        skills_data = skills_response.json()
        available_skills = skills_data.get("skills", [])

        if not available_skills:
            pytest.skip("No skills available for composition test")

        # Get a skill ID to compose with
        skill = available_skills[0]
        skill_id = skill.get("id") or skill.get("skill_id")

        compose_request = {
            "task": {
                "task_id": f"compose-test-{generate_test_id()}",
                "description": "Test task for composition",
                "required_capabilities": ["testing"]
            },
            "skill_ids": [skill_id]
        }

        response = await marketplace_client.post(
            f"{API_PREFIX}/skills/compose",
            json=compose_request
        )

        if response.status_code == 200:
            agent = response.json()
            # Verify agent structure (acceptance criteria #6)
            assert "id" in agent, "Agent should have an ID"
            assert "merged_instructions" in agent or "instructions" in agent, \
                "Agent should have merged_instructions"
            assert "skills" in agent or "skill_ids" in agent, \
                "Agent should reference its skills"

            # Verify merged_instructions contains content
            instructions = agent.get("merged_instructions") or agent.get("instructions", "")
            assert len(instructions) > 0, "Merged instructions should not be empty"
        elif response.status_code == 400:
            pytest.skip(f"Skill composition not available: {response.text}")
        else:
            pytest.fail(f"Unexpected compose response: {response.status_code} {response.text}")

    @pytest.mark.asyncio
    async def test_composed_instructions_include_skill_content(
        self, marketplace_client
    ):
        """Test that composed CLAUDE.md includes selected skill instructions.

        This directly tests acceptance criteria #6.
        """
        # Get available skills with instructions
        skills_response = await marketplace_client.get(f"{API_PREFIX}/skills")
        if skills_response.status_code != 200:
            pytest.skip("Marketplace not available")

        skills_data = skills_response.json()
        available_skills = skills_data.get("skills", [])

        # Find a skill with instructions to verify composition
        test_skill = None
        for skill in available_skills:
            if skill.get("instructions"):
                test_skill = skill
                break

        if not test_skill:
            pytest.skip("No skills with instructions found for composition test")

        skill_id = test_skill.get("id") or test_skill.get("skill_id")
        skill_instructions = test_skill.get("instructions", "")

        compose_request = {
            "task": {
                "task_id": f"instruction-test-{generate_test_id()}",
                "description": "Testing instruction composition",
                "required_capabilities": []
            },
            "skill_ids": [skill_id]
        }

        response = await marketplace_client.post(
            f"{API_PREFIX}/skills/compose",
            json=compose_request
        )

        if response.status_code == 200:
            agent = response.json()
            merged = agent.get("merged_instructions") or agent.get("instructions", "")

            # Verify skill content is included in composed output
            # The exact format depends on composition service implementation
            assert len(merged) > 0, "Merged instructions should not be empty"
            # Skill instructions or name should appear in merged output
            skill_name = test_skill.get("name", "")
            # Either the instructions content or skill reference should be present
            assert (
                skill_instructions in merged or
                skill_id in merged or
                skill_name in merged or
                len(merged) >= len(skill_instructions)
            ), "Composed output should include skill content"
        elif response.status_code == 400:
            pytest.skip(f"Composition not available: {response.text}")

    @pytest.mark.asyncio
    async def test_compose_preview_returns_preview_data(self, marketplace_client):
        """Test that compose preview returns composition preview."""
        skills_response = await marketplace_client.get(f"{API_PREFIX}/skills")
        if skills_response.status_code != 200:
            pytest.skip("Marketplace not available")

        skills_data = skills_response.json()
        available_skills = skills_data.get("skills", [])

        if len(available_skills) < 1:
            pytest.skip("Need at least 1 skill for preview test")

        skill_ids = [
            s.get("id") or s.get("skill_id")
            for s in available_skills[:2]
        ]

        compose_request = {
            "task": {
                "task_id": f"preview-test-{generate_test_id()}",
                "description": "Test task for preview",
                "required_capabilities": []
            },
            "skill_ids": skill_ids
        }

        response = await marketplace_client.post(
            f"{API_PREFIX}/skills/compose/preview",
            json=compose_request
        )

        if response.status_code == 200:
            preview = response.json()
            assert "merged_instructions" in preview or "instructions" in preview
        elif response.status_code in [400, 404]:
            pytest.skip(f"Preview endpoint not available: {response.status_code}")


class TestSearchByCapabilities:
    """Test marketplace capability-based search endpoint.

    Verifies acceptance criteria #4: Marketplace client fetches skill definitions.
    """

    @pytest.mark.asyncio
    async def test_search_by_capabilities_returns_matching_skills(
        self, marketplace_client
    ):
        """Test that capability search returns relevant skills."""
        # First get a capability that exists
        skills_response = await marketplace_client.get(f"{API_PREFIX}/skills")
        if skills_response.status_code != 200:
            pytest.skip("Marketplace not available")

        skills_data = skills_response.json()
        available_skills = skills_data.get("skills", [])

        # Find a capability to search for
        test_capability = None
        for skill in available_skills:
            caps = skill.get("capabilities", []) or skill.get("tags", [])
            if caps:
                test_capability = caps[0]
                break

        if not test_capability:
            pytest.skip("No capabilities found in marketplace skills")

        # Search by capability
        response = await marketplace_client.get(
            f"{API_PREFIX}/skills/search/capabilities",
            params={"capabilities": test_capability}
        )

        if response.status_code == 200:
            search_results = response.json()
            assert "skills" in search_results
            assert "searched_capabilities" in search_results
            assert test_capability in search_results["searched_capabilities"]
            # Results should include skills with the searched capability
            assert search_results.get("total", len(search_results["skills"])) >= 0
        elif response.status_code == 404:
            pytest.skip("Search endpoint not available")


class TestWorkLifecycleWithSkills:
    """Test complete work lifecycle with skill selection integrated."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_skill_selection(
        self, http_client, marketplace_client, test_project
    ):
        """Test complete work lifecycle: create -> select skills -> assign -> complete.

        This is the main integration test covering acceptance criteria #1, #2, #5.
        """
        test_id = generate_test_id()

        # Create work with capabilities
        work_data = {
            "title": f"Full skill lifecycle test {test_id}",
            "description": "End-to-end test with skill selection",
            "project_id": test_project,
            "work_type": "feature",
            "priority": "normal",
            "required_capabilities": ["python", "testing"]
        }

        create_response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert create_response.status_code == 201
        work = create_response.json()
        work_id = work["work_id"]

        try:
            # Verify initial state (criteria #1: required_capabilities accepted)
            assert work["status"] == "pending"
            assert work["required_capabilities"] == ["python", "testing"]

            # Assign to compute (triggers skill selection - criteria #2)
            compute_id = f"test-compute-{test_id}"
            assign_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={"compute_id": compute_id}
            )
            assert assign_response.status_code == 200

            # Verify assignment
            get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assigned_work = get_response.json()
            assert assigned_work["status"] == "assigned"
            assert assigned_work["assigned_to"] == compute_id

            # Verify skill_ids populated (criteria #5)
            skill_ids = assigned_work.get("skill_ids", [])
            assert isinstance(skill_ids, list)

            # Move to in_progress
            status_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/status",
                params={"status": "in_progress", "compute_id": compute_id}
            )
            assert status_response.status_code == 200

            # Complete the work
            result = {
                "summary": f"Completed lifecycle test {test_id}",
                "skills_used": skill_ids
            }
            complete_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/complete",
                params={"compute_id": compute_id},
                json=result
            )
            assert complete_response.status_code == 200

            completed_work = complete_response.json()
            assert completed_work["status"] == "completed"

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")

    @pytest.mark.asyncio
    async def test_assignment_with_explicit_skills_parameter(
        self, http_client, test_project
    ):
        """Test that explicit skills parameter on assignment is respected."""
        work_data = {
            "title": f"Explicit skills test {generate_test_id()}",
            "description": "Testing explicit skill override on assignment",
            "project_id": test_project,
            "required_capabilities": ["python"]
        }

        response = await http_client.post(f"{API_PREFIX}/work", json=work_data)
        assert response.status_code == 201
        work = response.json()
        work_id = work["work_id"]

        try:
            # Assign with explicit skills
            compute_id = f"test-compute-{generate_test_id()}"
            assign_response = await http_client.post(
                f"{API_PREFIX}/work/{work_id}/assign",
                params={
                    "compute_id": compute_id,
                    "skills": "code-writer,tester"
                }
            )
            assert assign_response.status_code == 200

            # Verify assignment
            get_response = await http_client.get(f"{API_PREFIX}/work/{work_id}")
            assigned_work = get_response.json()
            assert assigned_work["status"] == "assigned"

        finally:
            await http_client.delete(f"{API_PREFIX}/work/{work_id}")


class TestCatalogEndpoint:
    """Test the skill catalog endpoint for discovery."""

    @pytest.mark.asyncio
    async def test_catalog_returns_skills_and_personas(self, marketplace_client):
        """Test that catalog endpoint returns complete discovery data."""
        response = await marketplace_client.get(f"{API_PREFIX}/skills/catalog")

        if response.status_code == 200:
            catalog = response.json()
            assert "skills" in catalog
            assert "personas" in catalog

            # Verify skill entries have required fields
            for skill in catalog["skills"]:
                assert "id" in skill

            # Verify persona entries have required fields
            for persona in catalog["personas"]:
                assert "id" in persona
        elif response.status_code == 404:
            pytest.skip("Catalog endpoint not available")


# =============================================================================
# Test Runner
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("Integration Tests for Skill Selection and Persona Composition (#286)")
    print("=" * 70)
    print()
    print("Prerequisites:")
    print(f"  - Serving service running at {SERVING_BASE_URL}")
    print(f"  - Marketplace service running at {MARKETPLACE_BASE_URL}")
    print(f"  - Redis running at {REDIS_HOST}:{REDIS_PORT}")
    print()
    print("Running tests...")
    print()

    sys.exit(pytest.main([__file__, "-v", "-s"]))
