"""Tests for SkillSelectionService.

Tests the skill selection algorithm that matches work requirements
to available skill capabilities.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.skill_selection_service import SkillSelectionService, get_skill_selection_service, set_skill_selection_service
from models.work_map import WorkItem, WorkStatus


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_marketplace_client():
    """Create mock marketplace client."""
    with patch('services.skill_selection_service.get_marketplace_client') as mock_get_client:
        client = MagicMock()
        client.list_skills = AsyncMock(return_value={
            "skills": [
                {"skill_id": "code-implementation", "capabilities": ["python", "typescript", "coding"]},
                {"skill_id": "bug-investigation", "capabilities": ["debugging", "python", "error-analysis"]},
                {"skill_id": "test-creation", "capabilities": ["testing", "pytest", "python"]},
                {"skill_id": "general", "capabilities": []}
            ]
        })
        mock_get_client.return_value = client
        yield client


@pytest.fixture
def skill_selection_service(mock_marketplace_client):
    """Create SkillSelectionService with mocked marketplace client."""
    return SkillSelectionService()


@pytest.fixture
def sample_work():
    """Create sample work item."""
    return WorkItem(
        work_id="work_001",
        title="Test Work",
        description="Test description",
        project_id="proj_001",
        required_capabilities=["python", "coding"]
    )


# =============================================================================
# Test: calculate_match method
# =============================================================================

class TestCalculateMatch:
    """Test capability matching algorithm."""

    def test_calculate_match_perfect_match(self, skill_selection_service):
        """Test perfect match returns 1.0."""
        skill_caps = ["python", "typescript", "coding"]
        required_caps = ["python", "typescript"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        assert score == 1.0

    def test_calculate_match_partial_match(self, skill_selection_service):
        """Test partial match returns fractional score."""
        skill_caps = ["python", "typescript"]
        required_caps = ["python", "javascript", "go"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        # 1 out of 3 capabilities match
        assert score == pytest.approx(1.0 / 3.0)

    def test_calculate_match_no_match(self, skill_selection_service):
        """Test no matching capabilities returns 0.0."""
        skill_caps = ["python", "typescript"]
        required_caps = ["java", "rust", "c++"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        assert score == 0.0

    def test_calculate_match_empty_required(self, skill_selection_service):
        """Test empty required capabilities returns 0.5 (neutral)."""
        skill_caps = ["python", "typescript"]
        required_caps = []

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        assert score == 0.5

    def test_calculate_match_empty_skill_caps(self, skill_selection_service):
        """Test empty skill capabilities returns 0.0."""
        skill_caps = []
        required_caps = ["python", "typescript"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        assert score == 0.0

    def test_calculate_match_multiple_matches(self, skill_selection_service):
        """Test multiple matching capabilities."""
        skill_caps = ["python", "debugging", "testing", "pytest"]
        required_caps = ["python", "debugging"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        # 2 out of 2 capabilities match
        assert score == 1.0

    def test_calculate_match_case_sensitive(self, skill_selection_service):
        """Test matching is case-sensitive."""
        skill_caps = ["Python", "TYPESCRIPT"]
        required_caps = ["python", "typescript"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        # No match due to case differences
        assert score == 0.0

    def test_calculate_match_duplicate_capabilities(self, skill_selection_service):
        """Test duplicate capabilities in required_caps are deduplicated by set logic."""
        skill_caps = ["python", "typescript"]
        required_caps = ["python", "typescript", "python"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        # Set intersection deduplicates: {python, typescript} & {python, typescript} = 2 matches
        # len(required_caps) = 3, but set removes duplicates -> score = 2/3
        assert score == pytest.approx(2.0 / 3.0)


# =============================================================================
# Test: select_skills method
# =============================================================================

class TestSelectSkills:
    """Test skill selection logic."""

    @pytest.mark.asyncio
    async def test_select_skills_returns_best_match(self, skill_selection_service, sample_work):
        """Test returns skills with matching capabilities."""
        # work requires python and coding
        # code-implementation has both: score = 1.0
        # bug-investigation has python only: score = 0.5
        # test-creation has python only: score = 0.5

        skill_ids = await skill_selection_service.select_skills(sample_work)

        # Should include all matching skills
        assert "code-implementation" in skill_ids

    @pytest.mark.asyncio
    async def test_select_skills_perfect_match(self, skill_selection_service):
        """Test selects skill with perfect match."""
        work = WorkItem(
            work_id="work_002",
            title="Debug Issue",
            description="Fix bug",
            project_id="proj_001",
            required_capabilities=["debugging", "python", "error-analysis"]
        )

        skill_ids = await skill_selection_service.select_skills(work)

        # bug-investigation has all 3 capabilities: perfect match
        assert "bug-investigation" in skill_ids

    @pytest.mark.asyncio
    async def test_select_skills_falls_back_to_general(self, skill_selection_service):
        """Test falls back to 'general' when no capabilities match."""
        work = WorkItem(
            work_id="work_003",
            title="Java Task",
            description="Java work",
            project_id="proj_001",
            required_capabilities=["java", "spring-boot"]
        )

        skill_ids = await skill_selection_service.select_skills(work)

        # No skill has java capabilities, should use general
        assert skill_ids == ["general"]

    @pytest.mark.asyncio
    async def test_select_skills_no_required_caps(self, skill_selection_service):
        """Test returns 'general' when work has no required capabilities."""
        work = WorkItem(
            work_id="work_004",
            title="Generic Task",
            description="No specific requirements",
            project_id="proj_001",
            required_capabilities=[]
        )

        skill_ids = await skill_selection_service.select_skills(work)

        assert skill_ids == ["general"]

    @pytest.mark.asyncio
    async def test_select_skills_handles_marketplace_error(self, skill_selection_service, sample_work):
        """Test returns 'general' when marketplace client fails."""
        # Make marketplace client raise an error
        skill_selection_service.marketplace_client.list_skills = AsyncMock(
            side_effect=Exception("Marketplace unavailable")
        )

        skill_ids = await skill_selection_service.select_skills(sample_work)

        assert skill_ids == ["general"]

    @pytest.mark.asyncio
    async def test_select_skills_handles_empty_skills_list(self, skill_selection_service, sample_work):
        """Test returns 'general' when marketplace returns no skills."""
        skill_selection_service.marketplace_client.list_skills = AsyncMock(return_value={"skills": []})

        skill_ids = await skill_selection_service.select_skills(sample_work)

        assert skill_ids == ["general"]

    @pytest.mark.asyncio
    async def test_select_skills_handles_missing_skills_key(self, skill_selection_service, sample_work):
        """Test returns 'general' when response has no 'skills' key."""
        skill_selection_service.marketplace_client.list_skills = AsyncMock(return_value={})

        skill_ids = await skill_selection_service.select_skills(sample_work)

        assert skill_ids == ["general"]

    @pytest.mark.asyncio
    async def test_select_skills_returns_multiple_matches(self, skill_selection_service):
        """Test returns all matching skills."""
        work = WorkItem(
            work_id="work_005",
            title="Python Testing",
            description="Write tests",
            project_id="proj_001",
            required_capabilities=["testing", "pytest", "python"]
        )

        skill_ids = await skill_selection_service.select_skills(work)

        # test-creation has all 3: perfect match
        assert "test-creation" in skill_ids


# =============================================================================
# Test: Global instance management
# =============================================================================

class TestGlobalInstance:
    """Test global skill selection service instance management."""

    def test_get_skill_selection_service_creates_instance(self):
        """Test get_skill_selection_service creates instance if not exists."""
        # Reset global
        set_skill_selection_service(None)

        service = get_skill_selection_service()

        assert service is not None
        assert isinstance(service, SkillSelectionService)

    def test_get_skill_selection_service_returns_same_instance(self):
        """Test get_skill_selection_service returns same instance."""
        set_skill_selection_service(None)

        service1 = get_skill_selection_service()
        service2 = get_skill_selection_service()

        assert service1 is service2

    def test_set_skill_selection_service(self):
        """Test setting custom skill selection service."""
        custom_service = SkillSelectionService()

        set_skill_selection_service(custom_service)
        retrieved = get_skill_selection_service()

        assert retrieved is custom_service


# =============================================================================
# Test: Edge cases and integration
# =============================================================================

class TestEdgeCases:
    """Test edge cases and integration scenarios."""

    @pytest.mark.asyncio
    async def test_select_skills_with_work_in_progress(self, skill_selection_service):
        """Test skill selection works regardless of work status."""
        work = WorkItem(
            work_id="work_008",
            title="In Progress Work",
            description="Already started",
            project_id="proj_001",
            status=WorkStatus.IN_PROGRESS,
            required_capabilities=["python", "coding"]
        )

        skill_ids = await skill_selection_service.select_skills(work)

        assert "code-implementation" in skill_ids

    @pytest.mark.asyncio
    async def test_select_skills_with_extra_work_fields(self, skill_selection_service):
        """Test skill selection ignores extra work fields."""
        work = WorkItem(
            work_id="work_009",
            title="Complex Work",
            description="Has many fields",
            project_id="proj_001",
            required_capabilities=["debugging"],
            required_skills=["skill-a"],
            tags=["urgent", "production"],
            priority="high",
            context={"key": "value"}
        )

        skill_ids = await skill_selection_service.select_skills(work)

        # Should still match based on capabilities only
        assert "bug-investigation" in skill_ids

    @pytest.mark.asyncio
    async def test_skill_selection_service_initialization(self, mock_marketplace_client):
        """Test SkillSelectionService initializes with marketplace client."""
        service = SkillSelectionService()

        assert service.marketplace_client is not None

    @pytest.mark.asyncio
    async def test_select_skills_calls_marketplace_once(self, skill_selection_service, sample_work):
        """Test select_skills calls marketplace.list_skills once."""
        await skill_selection_service.select_skills(sample_work)

        skill_selection_service.marketplace_client.list_skills.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_match_with_special_characters(self, skill_selection_service):
        """Test calculate_match handles capabilities with special characters."""
        skill_caps = ["c++", "c#", "node.js"]
        required_caps = ["c++", "node.js"]

        score = skill_selection_service.calculate_match(skill_caps, required_caps)

        assert score == 1.0
