"""Unit tests for characterization data models."""

import pytest
from pydantic import ValidationError

from models.characterization import (
    # Meaning models
    BusinessMeaning,
    TechnicalMeaning,
    ContextualMeaning,
    ContextualRole,
    MeaningAssessment,
    # Dependency models
    DependencyType,
    DependencyRelation,
    ContextualDependency,
    # Characterization result
    CharacterizationResult,
    CharacterizationStatus,
    # Request/Response
    CharacterizationRequest,
    BatchCharacterizationRequest,
    BatchCharacterizationResponse,
    # Topology
    TopologyItem,
    WorkTopology,
)
from models.ontology import (
    LifecycleStage,
    OntologyTags,
    ProjectSpecificTags,
    TechnicalDomain,
    UniversalTags,
    WorkType,
)


# =============================================================================
# Fixtures
# =============================================================================


def make_universal_tags(**overrides):
    defaults = dict(
        work_type=WorkType.FEATURE,
        lifecycle_stage=LifecycleStage.BUILD,
        technical_domains=[TechnicalDomain.BACKEND],
    )
    defaults.update(overrides)
    return UniversalTags(**defaults)


def make_ontology_tags(**overrides):
    return OntologyTags(
        universal=overrides.get("universal", make_universal_tags()),
        project_specific=overrides.get(
            "project_specific",
            ProjectSpecificTags(cluster_ids=["cluster-abc"]),
        ),
    )


def make_meaning():
    return MeaningAssessment(
        business=BusinessMeaning(
            summary="Enables user self-service",
            user_impact="Users can manage their own settings",
            business_value="Reduces support tickets",
        ),
        technical=TechnicalMeaning(
            summary="Adds REST endpoint with validation",
            components_affected=["api-gateway", "user-service"],
            technical_risk="Low — standard CRUD pattern",
        ),
        contextual=ContextualMeaning(
            summary="Foundational for upcoming admin features",
            role=ContextualRole.FOUNDATIONAL,
            related_work_summary="Blocks admin-panel and audit-log work",
        ),
    )


def make_result(**overrides):
    defaults = dict(
        item_id="item-001",
        project_id="proj-1",
        ontology_tags=make_ontology_tags(),
        meaning=make_meaning(),
        confidence=0.85,
        status=CharacterizationStatus.COMPLETED,
    )
    defaults.update(overrides)
    return CharacterizationResult(**defaults)


# =============================================================================
# Meaning Assessment Tests
# =============================================================================


class TestContextualRole:
    def test_all_values(self):
        expected = {"foundational", "incremental", "enabling", "blocking"}
        assert {r.value for r in ContextualRole} == expected


class TestBusinessMeaning:
    def test_creation(self):
        bm = BusinessMeaning(summary="Drives revenue growth")
        assert bm.summary == "Drives revenue growth"
        assert bm.user_impact == ""
        assert bm.business_value == ""

    def test_summary_required(self):
        with pytest.raises(ValidationError):
            BusinessMeaning()


class TestTechnicalMeaning:
    def test_creation(self):
        tm = TechnicalMeaning(
            summary="Implements OAuth2 flow",
            components_affected=["auth-service", "api-gateway"],
        )
        assert len(tm.components_affected) == 2

    def test_summary_required(self):
        with pytest.raises(ValidationError):
            TechnicalMeaning()


class TestContextualMeaning:
    def test_creation(self):
        cm = ContextualMeaning(
            summary="Core enabler",
            role=ContextualRole.ENABLING,
        )
        assert cm.role == ContextualRole.ENABLING

    def test_both_fields_required(self):
        with pytest.raises(ValidationError):
            ContextualMeaning(summary="Missing role")


class TestMeaningAssessment:
    def test_creation(self):
        m = make_meaning()
        assert m.business.summary == "Enables user self-service"
        assert m.technical.components_affected == ["api-gateway", "user-service"]
        assert m.contextual.role == ContextualRole.FOUNDATIONAL


# =============================================================================
# Contextual Dependency Tests
# =============================================================================


class TestDependencyType:
    def test_values(self):
        assert DependencyType.STRUCTURAL == "structural"
        assert DependencyType.CONTEXTUAL == "contextual"


class TestDependencyRelation:
    def test_all_values(self):
        expected = {"blocks", "enables", "related_to", "extends", "conflicts_with"}
        assert {r.value for r in DependencyRelation} == expected


class TestContextualDependency:
    def test_structural(self):
        dep = ContextualDependency(
            target_item_id="item-002",
            relation=DependencyRelation.BLOCKS,
            dependency_type=DependencyType.STRUCTURAL,
            reasoning="Database schema must exist first",
            confidence=0.95,
        )
        assert dep.dependency_type == DependencyType.STRUCTURAL
        assert dep.confidence == 0.95

    def test_contextual(self):
        dep = ContextualDependency(
            target_item_id="item-003",
            relation=DependencyRelation.RELATED_TO,
            dependency_type=DependencyType.CONTEXTUAL,
        )
        assert dep.dependency_type == DependencyType.CONTEXTUAL
        assert dep.confidence == 0.8  # default

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            ContextualDependency(
                target_item_id="item-002",
                relation=DependencyRelation.BLOCKS,
                dependency_type=DependencyType.STRUCTURAL,
                confidence=1.5,
            )


# =============================================================================
# CharacterizationResult Tests
# =============================================================================


class TestCharacterizationResult:
    def test_full_creation(self):
        result = make_result()
        assert result.item_id == "item-001"
        assert result.confidence == 0.85
        assert result.status == CharacterizationStatus.COMPLETED
        assert result.evaluated_in_isolation is True
        assert result.evaluated_in_context is False

    def test_dependency_filtering(self):
        result = make_result(
            dependencies=[
                ContextualDependency(
                    target_item_id="item-002",
                    relation=DependencyRelation.BLOCKS,
                    dependency_type=DependencyType.STRUCTURAL,
                ),
                ContextualDependency(
                    target_item_id="item-003",
                    relation=DependencyRelation.RELATED_TO,
                    dependency_type=DependencyType.CONTEXTUAL,
                ),
                ContextualDependency(
                    target_item_id="item-004",
                    relation=DependencyRelation.ENABLES,
                    dependency_type=DependencyType.STRUCTURAL,
                ),
            ]
        )
        assert len(result.structural_dependencies) == 2
        assert len(result.contextual_dependencies_only) == 1

    def test_status_values(self):
        expected = {"pending", "in_progress", "completed", "failed"}
        assert {s.value for s in CharacterizationStatus} == expected

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            make_result(confidence=1.5)


# =============================================================================
# Request/Response Tests
# =============================================================================


class TestCharacterizationRequest:
    def test_creation(self):
        req = CharacterizationRequest(
            item_id="item-001",
            project_id="proj-1",
            title="Add user settings endpoint",
            description="REST API for user preferences",
            issue_type_hint="feature",
            area_hint="api",
        )
        assert req.item_id == "item-001"
        assert req.issue_type_hint == "feature"

    def test_minimal(self):
        req = CharacterizationRequest(
            item_id="item-001",
            project_id="proj-1",
            title="Fix bug",
            description="Details",
        )
        assert req.issue_type_hint is None


class TestBatchCharacterizationRequest:
    def test_creation(self):
        req = BatchCharacterizationRequest(
            project_id="proj-1",
            items=[
                CharacterizationRequest(
                    item_id="item-001",
                    project_id="proj-1",
                    title="Task 1",
                    description="Desc 1",
                ),
                CharacterizationRequest(
                    item_id="item-002",
                    project_id="proj-1",
                    title="Task 2",
                    description="Desc 2",
                ),
            ],
            source_goal_id="goal-42",
        )
        assert len(req.items) == 2
        assert req.source_goal_id == "goal-42"

    def test_empty_items_rejected(self):
        with pytest.raises(ValidationError):
            BatchCharacterizationRequest(
                project_id="proj-1",
                items=[],
            )


class TestBatchCharacterizationResponse:
    def test_creation(self):
        resp = BatchCharacterizationResponse(
            project_id="proj-1",
            total=5,
            completed=3,
            failed=1,
            new_clusters_created=["cluster-new1"],
        )
        assert resp.total == 5
        assert resp.completed == 3


# =============================================================================
# Work Topology Tests
# =============================================================================


class TestTopologyItem:
    def test_creation(self):
        item = TopologyItem(
            item_id="item-001",
            title="Add endpoint",
            ontology_tags=make_ontology_tags(),
            contextual_role=ContextualRole.FOUNDATIONAL,
            cluster_ids=["cluster-abc"],
        )
        assert item.item_id == "item-001"
        assert item.contextual_role == ContextualRole.FOUNDATIONAL


class TestWorkTopology:
    def test_empty(self):
        topo = WorkTopology(project_id="proj-1")
        assert topo.item_count == 0
        assert topo.items_by_cluster == {}

    def test_items_by_cluster(self):
        topo = WorkTopology(
            project_id="proj-1",
            items=[
                TopologyItem(
                    item_id="i1",
                    title="Task A",
                    ontology_tags=make_ontology_tags(),
                    contextual_role=ContextualRole.FOUNDATIONAL,
                    cluster_ids=["c1", "c2"],
                ),
                TopologyItem(
                    item_id="i2",
                    title="Task B",
                    ontology_tags=make_ontology_tags(),
                    contextual_role=ContextualRole.INCREMENTAL,
                    cluster_ids=["c1"],
                ),
                TopologyItem(
                    item_id="i3",
                    title="Task C",
                    ontology_tags=make_ontology_tags(),
                    contextual_role=ContextualRole.ENABLING,
                    cluster_ids=["c3"],
                ),
            ],
        )
        by_cluster = topo.items_by_cluster
        assert len(by_cluster["c1"]) == 2
        assert len(by_cluster["c2"]) == 1
        assert len(by_cluster["c3"]) == 1
        assert topo.item_count == 3
