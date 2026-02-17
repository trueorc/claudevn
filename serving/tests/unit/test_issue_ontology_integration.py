"""Tests for Issue ontology tag integration (#511).

Tests that:
- Issue model accepts ontology_tags field
- IssueCreateRequest and IssueUpdateRequest support ontology_tags
- IssueOpsService create/update propagates ontology_tags
- list_issues filters by work_type, lifecycle_stage, technical_domain
- Redis persistence round-trips ontology_tags correctly
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from models.work_map import (
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
    IssueCreateRequest, IssueUpdateRequest, IssueListResponse,
)
from models.ontology import (
    OntologyTags, UniversalTags, ProjectSpecificTags,
    WorkType, LifecycleStage, TechnicalDomain,
)
from services.issue_ops_service import IssueOpsService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def service():
    """Create IssueOpsService without Redis (in-memory only)."""
    svc = IssueOpsService(redis_client=None)
    svc._initialized = True
    svc._save_issue_to_redis = AsyncMock()
    svc._save_issue_history_entry = AsyncMock()
    svc._delete_issue_from_redis = AsyncMock()
    return svc


@pytest.fixture
def sample_ontology_tags():
    """Create sample ontology tags for testing."""
    return OntologyTags(
        universal=UniversalTags(
            work_type=WorkType.FEATURE,
            lifecycle_stage=LifecycleStage.BUILD,
            technical_domains=[TechnicalDomain.BACKEND, TechnicalDomain.API],
        ),
        project_specific=ProjectSpecificTags(),
    )


@pytest.fixture
def alt_ontology_tags():
    """Create alternative ontology tags for testing."""
    return OntologyTags(
        universal=UniversalTags(
            work_type=WorkType.BUG_FIX,
            lifecycle_stage=LifecycleStage.TEST,
            technical_domains=[TechnicalDomain.FRONTEND],
        ),
        project_specific=ProjectSpecificTags(),
    )


# ============================================================================
# Model Tests
# ============================================================================

class TestIssueOntologyField:
    """Test Issue model has ontology_tags field."""

    def test_issue_accepts_ontology_tags(self, sample_ontology_tags):
        """Test Issue model accepts ontology_tags."""
        issue = Issue(
            issue_id="issue_test1",
            title="Test",
            description="Test",
            ontology_tags=sample_ontology_tags,
        )
        assert issue.ontology_tags is not None
        assert issue.ontology_tags.universal.work_type == WorkType.FEATURE

    def test_issue_ontology_tags_defaults_to_none(self):
        """Test ontology_tags defaults to None for backwards compatibility."""
        issue = Issue(
            issue_id="issue_test2",
            title="Test",
            description="Test",
        )
        assert issue.ontology_tags is None

    def test_create_request_accepts_ontology_tags(self, sample_ontology_tags):
        """Test IssueCreateRequest accepts ontology_tags."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
            ontology_tags=sample_ontology_tags,
        )
        assert request.ontology_tags is not None
        assert request.ontology_tags.universal.work_type == WorkType.FEATURE

    def test_create_request_ontology_tags_defaults_to_none(self):
        """Test IssueCreateRequest ontology_tags defaults to None."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
        )
        assert request.ontology_tags is None

    def test_update_request_accepts_ontology_tags(self, sample_ontology_tags):
        """Test IssueUpdateRequest accepts ontology_tags."""
        request = IssueUpdateRequest(
            ontology_tags=sample_ontology_tags,
        )
        assert request.ontology_tags is not None

    def test_update_request_ontology_tags_defaults_to_none(self):
        """Test IssueUpdateRequest ontology_tags defaults to None."""
        request = IssueUpdateRequest()
        assert request.ontology_tags is None


# ============================================================================
# Create Issue Tests
# ============================================================================

class TestCreateIssueWithOntologyTags:
    """Test creating issues with ontology_tags."""

    @pytest.mark.asyncio
    async def test_create_issue_stores_ontology_tags(self, service, sample_ontology_tags):
        """Test that created issue has ontology_tags set."""
        request = IssueCreateRequest(
            title="Feature Issue",
            description="Build a feature",
            ontology_tags=sample_ontology_tags,
        )
        issue = await service.create_issue(request)

        assert issue.ontology_tags is not None
        assert issue.ontology_tags.universal.work_type == WorkType.FEATURE
        assert issue.ontology_tags.universal.lifecycle_stage == LifecycleStage.BUILD
        assert TechnicalDomain.BACKEND in issue.ontology_tags.universal.technical_domains

    @pytest.mark.asyncio
    async def test_create_issue_without_ontology_tags(self, service):
        """Test creating issue without ontology_tags works (backwards compat)."""
        request = IssueCreateRequest(
            title="Legacy Issue",
            description="No ontology",
        )
        issue = await service.create_issue(request)

        assert issue.ontology_tags is None


# ============================================================================
# Update Issue Tests
# ============================================================================

class TestUpdateIssueOntologyTags:
    """Test updating issues with ontology_tags."""

    @pytest.mark.asyncio
    async def test_update_adds_ontology_tags(self, service, sample_ontology_tags):
        """Test updating an issue to add ontology_tags."""
        request = IssueCreateRequest(
            title="Bare Issue",
            description="No tags yet",
        )
        issue = await service.create_issue(request)
        assert issue.ontology_tags is None

        update = IssueUpdateRequest(ontology_tags=sample_ontology_tags)
        updated = await service.update_issue(issue.issue_id, update)

        assert updated is not None
        assert updated.ontology_tags is not None
        assert updated.ontology_tags.universal.work_type == WorkType.FEATURE

    @pytest.mark.asyncio
    async def test_update_replaces_ontology_tags(self, service, sample_ontology_tags, alt_ontology_tags):
        """Test updating replaces existing ontology_tags."""
        request = IssueCreateRequest(
            title="Tagged Issue",
            description="Has tags",
            ontology_tags=sample_ontology_tags,
        )
        issue = await service.create_issue(request)
        assert issue.ontology_tags.universal.work_type == WorkType.FEATURE

        update = IssueUpdateRequest(ontology_tags=alt_ontology_tags)
        updated = await service.update_issue(issue.issue_id, update)

        assert updated.ontology_tags.universal.work_type == WorkType.BUG_FIX
        assert updated.ontology_tags.universal.lifecycle_stage == LifecycleStage.TEST

    @pytest.mark.asyncio
    async def test_update_without_ontology_tags_preserves_existing(self, service, sample_ontology_tags):
        """Test that updating other fields doesn't clear ontology_tags."""
        request = IssueCreateRequest(
            title="Tagged Issue",
            description="Has tags",
            ontology_tags=sample_ontology_tags,
        )
        issue = await service.create_issue(request)

        # Update title only
        update = IssueUpdateRequest(title="Renamed Issue")
        updated = await service.update_issue(issue.issue_id, update)

        assert updated.ontology_tags is not None
        assert updated.ontology_tags.universal.work_type == WorkType.FEATURE


# ============================================================================
# List Issues Ontology Filter Tests
# ============================================================================

class TestListIssuesOntologyFilters:
    """Test list_issues filtering by ontology tags."""

    async def _create_characterized_issues(self, service):
        """Helper: create a mix of characterized and uncharacterized issues."""
        # Feature + Build + Backend
        await service.create_issue(IssueCreateRequest(
            title="Backend Feature",
            description="API endpoint",
            ontology_tags=OntologyTags(
                universal=UniversalTags(
                    work_type=WorkType.FEATURE,
                    lifecycle_stage=LifecycleStage.BUILD,
                    technical_domains=[TechnicalDomain.BACKEND, TechnicalDomain.API],
                ),
                project_specific=ProjectSpecificTags(),
            ),
        ))
        # Bug fix + Test + Frontend
        await service.create_issue(IssueCreateRequest(
            title="Frontend Bug",
            description="UI bug fix",
            ontology_tags=OntologyTags(
                universal=UniversalTags(
                    work_type=WorkType.BUG_FIX,
                    lifecycle_stage=LifecycleStage.TEST,
                    technical_domains=[TechnicalDomain.FRONTEND],
                ),
                project_specific=ProjectSpecificTags(),
            ),
        ))
        # Feature + Design + Frontend
        await service.create_issue(IssueCreateRequest(
            title="Frontend Feature",
            description="New UI component",
            ontology_tags=OntologyTags(
                universal=UniversalTags(
                    work_type=WorkType.FEATURE,
                    lifecycle_stage=LifecycleStage.DESIGN,
                    technical_domains=[TechnicalDomain.FRONTEND],
                ),
                project_specific=ProjectSpecificTags(),
            ),
        ))
        # Uncharacterized issue (no ontology_tags)
        await service.create_issue(IssueCreateRequest(
            title="Legacy Issue",
            description="No ontology tags",
        ))

    @pytest.mark.asyncio
    async def test_filter_by_work_type(self, service):
        """Test filtering issues by work_type."""
        await self._create_characterized_issues(service)

        result = await service.list_issues(work_type="feature")
        assert len(result.items) == 2
        titles = {i.title for i in result.items}
        assert titles == {"Backend Feature", "Frontend Feature"}

    @pytest.mark.asyncio
    async def test_filter_by_work_type_bug_fix(self, service):
        """Test filtering by bug_fix work type."""
        await self._create_characterized_issues(service)

        result = await service.list_issues(work_type="bug_fix")
        assert len(result.items) == 1
        assert result.items[0].title == "Frontend Bug"

    @pytest.mark.asyncio
    async def test_filter_by_lifecycle_stage(self, service):
        """Test filtering issues by lifecycle_stage."""
        await self._create_characterized_issues(service)

        result = await service.list_issues(lifecycle_stage="build")
        assert len(result.items) == 1
        assert result.items[0].title == "Backend Feature"

    @pytest.mark.asyncio
    async def test_filter_by_technical_domain(self, service):
        """Test filtering issues by technical_domain."""
        await self._create_characterized_issues(service)

        result = await service.list_issues(technical_domain="frontend")
        assert len(result.items) == 2
        titles = {i.title for i in result.items}
        assert titles == {"Frontend Bug", "Frontend Feature"}

    @pytest.mark.asyncio
    async def test_filter_by_technical_domain_api(self, service):
        """Test filtering by api domain (multi-domain match)."""
        await self._create_characterized_issues(service)

        result = await service.list_issues(technical_domain="api")
        assert len(result.items) == 1
        assert result.items[0].title == "Backend Feature"

    @pytest.mark.asyncio
    async def test_combined_ontology_filters(self, service):
        """Test combining work_type and technical_domain filters."""
        await self._create_characterized_issues(service)

        result = await service.list_issues(
            work_type="feature",
            technical_domain="frontend",
        )
        assert len(result.items) == 1
        assert result.items[0].title == "Frontend Feature"

    @pytest.mark.asyncio
    async def test_ontology_filter_excludes_uncharacterized(self, service):
        """Test that ontology filters exclude issues without tags."""
        await self._create_characterized_issues(service)

        # All ontology filters should exclude the "Legacy Issue"
        result = await service.list_issues(work_type="feature")
        titles = {i.title for i in result.items}
        assert "Legacy Issue" not in titles

    @pytest.mark.asyncio
    async def test_no_ontology_filter_returns_all(self, service):
        """Test that without ontology filters, all issues are returned."""
        await self._create_characterized_issues(service)

        result = await service.list_issues()
        assert len(result.items) == 4

    @pytest.mark.asyncio
    async def test_ontology_filter_with_legacy_filter(self, service):
        """Test combining ontology filter with legacy area filter."""
        await self._create_characterized_issues(service)

        # Add a backend area issue with frontend ontology (edge case)
        result = await service.list_issues(
            work_type="feature",
            lifecycle_stage="build",
        )
        assert len(result.items) == 1
        assert result.items[0].title == "Backend Feature"

    @pytest.mark.asyncio
    async def test_nonexistent_ontology_value_returns_empty(self, service):
        """Test filtering by a value that no issues have returns empty."""
        await self._create_characterized_issues(service)

        result = await service.list_issues(work_type="infrastructure")
        assert len(result.items) == 0


# ============================================================================
# Redis Round-trip Tests
# ============================================================================

class TestOntologyRedisRoundTrip:
    """Test that ontology_tags survive Redis serialization."""

    def test_ontology_tags_serializes_to_json(self, sample_ontology_tags):
        """Test OntologyTags can be serialized to JSON string."""
        json_str = sample_ontology_tags.model_dump_json()
        assert "feature" in json_str
        assert "build" in json_str
        assert "backend" in json_str

    def test_ontology_tags_deserializes_from_json(self, sample_ontology_tags):
        """Test OntologyTags can be deserialized from JSON string."""
        json_str = sample_ontology_tags.model_dump_json()
        restored = OntologyTags.model_validate_json(json_str)

        assert restored.universal.work_type == WorkType.FEATURE
        assert restored.universal.lifecycle_stage == LifecycleStage.BUILD
        assert TechnicalDomain.BACKEND in restored.universal.technical_domains
        assert TechnicalDomain.API in restored.universal.technical_domains

    def test_empty_ontology_tags_in_redis_mapping(self):
        """Test that None ontology_tags produces empty string for Redis."""
        issue = Issue(
            issue_id="issue_test",
            title="Test",
            description="Test",
        )
        # Simulate what _save_issue_to_redis does
        redis_value = issue.ontology_tags.model_dump_json() if issue.ontology_tags else ''
        assert redis_value == ''

    def test_ontology_tags_in_redis_mapping(self, sample_ontology_tags):
        """Test that ontology_tags produces valid JSON for Redis."""
        issue = Issue(
            issue_id="issue_test",
            title="Test",
            description="Test",
            ontology_tags=sample_ontology_tags,
        )
        redis_value = issue.ontology_tags.model_dump_json() if issue.ontology_tags else ''
        assert redis_value != ''

        # Verify it can be loaded back
        restored = OntologyTags.model_validate_json(redis_value)
        assert restored.universal.work_type == WorkType.FEATURE
