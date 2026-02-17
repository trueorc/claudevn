"""Unit tests for ontology data models (Layer 1 + Layer 2)."""

import pytest
from pydantic import ValidationError

from models.ontology import (
    # Layer 1 — Universal
    WorkType,
    LifecycleStage,
    TechnicalDomain,
    UniversalTags,
    # Layer 2 — Project-Specific
    DomainCluster,
    DomainClusterStatus,
    ProjectOntology,
    ProjectSpecificTags,
    # Combined
    OntologyTags,
    # Weights
    OntologyWeights,
    # Migration helpers
    ISSUE_TYPE_TO_WORK_TYPE,
    ISSUE_AREA_TO_TECHNICAL_DOMAIN,
    # Request/Response
    DomainClusterCreateRequest,
    DomainClusterUpdateRequest,
    ConsolidateClustersRequest,
    ProjectOntologyResponse,
)


# =============================================================================
# Layer 1 — Universal Ontology Tests
# =============================================================================


class TestWorkType:
    """Tests for WorkType enum."""

    def test_all_values_present(self):
        expected = {"feature", "bug_fix", "refactor", "test", "documentation", "infrastructure", "integration"}
        actual = {wt.value for wt in WorkType}
        assert actual == expected

    def test_string_enum(self):
        assert WorkType.FEATURE == "feature"
        assert isinstance(WorkType.BUG_FIX, str)


class TestLifecycleStage:
    """Tests for LifecycleStage enum."""

    def test_all_values_present(self):
        expected = {"design", "build", "test", "validate", "deploy"}
        actual = {ls.value for ls in LifecycleStage}
        assert actual == expected


class TestTechnicalDomain:
    """Tests for TechnicalDomain enum."""

    def test_all_values_present(self):
        expected = {"frontend", "backend", "data", "api", "security", "devops", "testing", "documentation"}
        actual = {td.value for td in TechnicalDomain}
        assert actual == expected


class TestUniversalTags:
    """Tests for UniversalTags model."""

    def test_valid_creation(self):
        tags = UniversalTags(
            work_type=WorkType.FEATURE,
            lifecycle_stage=LifecycleStage.BUILD,
            technical_domains=[TechnicalDomain.FRONTEND, TechnicalDomain.API],
        )
        assert tags.work_type == WorkType.FEATURE
        assert tags.lifecycle_stage == LifecycleStage.BUILD
        assert len(tags.technical_domains) == 2

    def test_empty_domains_rejected(self):
        with pytest.raises(ValidationError, match="At least one technical domain"):
            UniversalTags(
                work_type=WorkType.FEATURE,
                lifecycle_stage=LifecycleStage.BUILD,
                technical_domains=[],
            )

    def test_omitted_domains_rejected(self):
        """technical_domains is required — omitting it raises."""
        with pytest.raises(ValidationError):
            UniversalTags(
                work_type=WorkType.FEATURE,
                lifecycle_stage=LifecycleStage.BUILD,
            )


# =============================================================================
# Layer 2 — Project-Specific Ontology Tests
# =============================================================================


class TestDomainCluster:
    """Tests for DomainCluster model."""

    def test_creation_defaults(self):
        cluster = DomainCluster(
            cluster_id="cluster-abc123",
            name="payment processing",
        )
        assert cluster.status == DomainClusterStatus.ACTIVE
        assert cluster.work_item_count == 0
        assert cluster.consolidated_into is None
        assert cluster.created_from is None

    def test_full_creation(self):
        cluster = DomainCluster(
            cluster_id="cluster-abc123",
            name="user authentication",
            description="All auth-related work",
            status=DomainClusterStatus.ACTIVE,
            created_from="goal-001",
            work_item_count=5,
        )
        assert cluster.name == "user authentication"
        assert cluster.created_from == "goal-001"
        assert cluster.work_item_count == 5


class TestProjectOntology:
    """Tests for ProjectOntology model."""

    def test_empty_project(self):
        ontology = ProjectOntology(project_id="proj-1")
        assert ontology.clusters == {}
        assert ontology.active_clusters == {}
        assert ontology.cluster_names == []

    def test_active_clusters_filter(self):
        ontology = ProjectOntology(
            project_id="proj-1",
            clusters={
                "c1": DomainCluster(cluster_id="c1", name="payments", status=DomainClusterStatus.ACTIVE),
                "c2": DomainCluster(cluster_id="c2", name="old-auth", status=DomainClusterStatus.CONSOLIDATED),
                "c3": DomainCluster(cluster_id="c3", name="reporting", status=DomainClusterStatus.ACTIVE),
                "c4": DomainCluster(cluster_id="c4", name="legacy", status=DomainClusterStatus.ARCHIVED),
            },
        )
        active = ontology.active_clusters
        assert len(active) == 2
        assert "c1" in active
        assert "c3" in active
        assert "c2" not in active

    def test_cluster_names(self):
        ontology = ProjectOntology(
            project_id="proj-1",
            clusters={
                "c1": DomainCluster(cluster_id="c1", name="payments", status=DomainClusterStatus.ACTIVE),
                "c2": DomainCluster(cluster_id="c2", name="old-auth", status=DomainClusterStatus.CONSOLIDATED),
            },
        )
        names = ontology.cluster_names
        assert names == ["payments"]


class TestProjectSpecificTags:
    """Tests for ProjectSpecificTags model."""

    def test_empty_default(self):
        tags = ProjectSpecificTags()
        assert tags.cluster_ids == []

    def test_with_clusters(self):
        tags = ProjectSpecificTags(cluster_ids=["c1", "c2"])
        assert len(tags.cluster_ids) == 2


# =============================================================================
# Combined Ontology Tags Tests
# =============================================================================


class TestOntologyTags:
    """Tests for combined OntologyTags model."""

    def test_full_tags(self):
        tags = OntologyTags(
            universal=UniversalTags(
                work_type=WorkType.BUG_FIX,
                lifecycle_stage=LifecycleStage.TEST,
                technical_domains=[TechnicalDomain.BACKEND],
            ),
            project_specific=ProjectSpecificTags(cluster_ids=["c1"]),
        )
        assert tags.universal.work_type == WorkType.BUG_FIX
        assert tags.project_specific.cluster_ids == ["c1"]

    def test_default_project_specific(self):
        tags = OntologyTags(
            universal=UniversalTags(
                work_type=WorkType.FEATURE,
                lifecycle_stage=LifecycleStage.BUILD,
                technical_domains=[TechnicalDomain.FRONTEND],
            ),
        )
        assert tags.project_specific.cluster_ids == []


# =============================================================================
# Ontology Weights Tests
# =============================================================================


class TestOntologyWeights:
    """Tests for OntologyWeights model."""

    def test_empty_defaults(self):
        weights = OntologyWeights()
        assert weights.work_type_weights == {}
        assert weights.cluster_weights == {}

    def test_default_weight_values(self):
        weights = OntologyWeights()
        assert weights.get_work_type_weight(WorkType.FEATURE) == 0.5
        assert weights.get_lifecycle_stage_weight(LifecycleStage.BUILD) == 0.5
        assert weights.get_technical_domain_weight(TechnicalDomain.FRONTEND) == 0.5
        assert weights.get_cluster_weight("nonexistent") == 0.5

    def test_custom_weights(self):
        weights = OntologyWeights(
            work_type_weights={"feature": 0.9, "bug_fix": 0.8},
            lifecycle_stage_weights={"test": 0.95},
            cluster_weights={"c1": 0.7},
        )
        assert weights.get_work_type_weight(WorkType.FEATURE) == 0.9
        assert weights.get_work_type_weight(WorkType.BUG_FIX) == 0.8
        assert weights.get_work_type_weight(WorkType.REFACTOR) == 0.5  # default
        assert weights.get_lifecycle_stage_weight(LifecycleStage.TEST) == 0.95
        assert weights.get_cluster_weight("c1") == 0.7

    def test_weight_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="must be between 0.0 and 1.0"):
            OntologyWeights(work_type_weights={"feature": 1.5})

    def test_weight_negative_rejected(self):
        with pytest.raises(ValidationError, match="must be between 0.0 and 1.0"):
            OntologyWeights(cluster_weights={"c1": -0.1})


# =============================================================================
# Migration Mapping Tests
# =============================================================================


class TestMigrationMappings:
    """Tests for legacy enum → ontology migration helpers."""

    def test_issue_type_mapping_coverage(self):
        """All legacy IssueType values should have a mapping."""
        legacy_values = {"feature", "bug", "refactor", "docs", "test"}
        assert set(ISSUE_TYPE_TO_WORK_TYPE.keys()) == legacy_values

    def test_issue_type_mapping_values(self):
        assert ISSUE_TYPE_TO_WORK_TYPE["feature"] == WorkType.FEATURE
        assert ISSUE_TYPE_TO_WORK_TYPE["bug"] == WorkType.BUG_FIX
        assert ISSUE_TYPE_TO_WORK_TYPE["docs"] == WorkType.DOCUMENTATION

    def test_issue_area_mapping_coverage(self):
        """All legacy IssueArea values should have a mapping."""
        legacy_values = {"api", "database", "frontend", "infra", "other"}
        assert set(ISSUE_AREA_TO_TECHNICAL_DOMAIN.keys()) == legacy_values

    def test_issue_area_mapping_values(self):
        assert ISSUE_AREA_TO_TECHNICAL_DOMAIN["api"] == TechnicalDomain.API
        assert ISSUE_AREA_TO_TECHNICAL_DOMAIN["database"] == TechnicalDomain.DATA
        assert ISSUE_AREA_TO_TECHNICAL_DOMAIN["frontend"] == TechnicalDomain.FRONTEND
        assert ISSUE_AREA_TO_TECHNICAL_DOMAIN["infra"] == TechnicalDomain.DEVOPS


# =============================================================================
# Request/Response Model Tests
# =============================================================================


class TestRequestModels:
    """Tests for request/response models."""

    def test_cluster_create_request(self):
        req = DomainClusterCreateRequest(
            name="payment processing",
            description="All payment-related work",
            created_from="goal-001",
        )
        assert req.name == "payment processing"
        assert req.created_from == "goal-001"

    def test_cluster_create_request_name_required(self):
        with pytest.raises(ValidationError):
            DomainClusterCreateRequest(name="")

    def test_cluster_update_request_partial(self):
        req = DomainClusterUpdateRequest(name="updated name")
        assert req.name == "updated name"
        assert req.description is None
        assert req.status is None

    def test_consolidate_request(self):
        req = ConsolidateClustersRequest(
            source_cluster_ids=["c1", "c2"],
            target_cluster_id="c3",
        )
        assert len(req.source_cluster_ids) == 2
        assert req.target_cluster_id == "c3"

    def test_consolidate_request_needs_sources(self):
        with pytest.raises(ValidationError):
            ConsolidateClustersRequest(
                source_cluster_ids=[],
                target_cluster_id="c3",
            )

    def test_project_ontology_response(self):
        resp = ProjectOntologyResponse(
            project_id="proj-1",
            clusters=[],
            active_count=0,
            consolidated_count=0,
            archived_count=0,
        )
        assert resp.project_id == "proj-1"
