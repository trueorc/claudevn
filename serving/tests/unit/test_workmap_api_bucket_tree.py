"""Tests for WorkMap API bucket-tree endpoints.

Verifies that the bucket-tree endpoints correctly interact with
the BucketTreeStore and return appropriate responses.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.work_map import workmap_router
from models.priority_bucket import (
    BucketDefinition,
    BucketItem,
    BucketTree,
    ItemReadiness,
    PriorityBucket,
)


# =============================================================================
# Mock Data Helpers
# =============================================================================


def make_bucket_tree(project_id="proj-1", num_buckets=2):
    """Create a BucketTree for testing."""
    buckets = []
    for i in range(num_buckets):
        bucket_id = f"bucket-{i+1}"
        items = [
            BucketItem(
                item_id=f"item-{bucket_id}-{j+1}",
                readiness=ItemReadiness.READY if j % 2 == 0 else ItemReadiness.BLOCKED,
                priority_score=100.0 - (j * 10),
            )
            for j in range(3)
        ]
        buckets.append(
            PriorityBucket(
                bucket_id=bucket_id,
                rank=i + 1,
                definition=BucketDefinition(
                    name=f"Bucket {i+1}",
                    description=f"Test bucket {i+1}",
                ),
                items=items,
            )
        )

    return BucketTree(
        tree_id=f"tree-{project_id}",
        project_id=project_id,
        buckets=buckets,
        version=1,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_store():
    """Create a mock BucketTreeStore."""
    store = MagicMock()
    store.load = AsyncMock()
    return store


@pytest.fixture
def app():
    """Create a FastAPI app with the workmap router."""
    test_app = FastAPI()
    test_app.include_router(workmap_router)
    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# =============================================================================
# Test GET /workmap/bucket-tree
# =============================================================================


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_tree_success(mock_get_store, client, mock_store):
    """Test successful bucket tree retrieval."""
    mock_get_store.return_value = mock_store
    tree = make_bucket_tree("proj-1", num_buckets=2)
    mock_store.load.return_value = tree

    response = client.get("/workmap/bucket-tree?project_id=proj-1")

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == "proj-1"
    assert data["tree"] is not None
    assert data["tree"]["tree_id"] == "tree-proj-1"
    assert data["summary"] is not None
    assert data["summary"]["total_buckets"] == 2
    assert data["summary"]["total_items"] == 6  # 3 items per bucket * 2 buckets
    assert data["summary"]["total_ready"] == 4  # 2 ready per bucket * 2 buckets
    assert data["summary"]["version"] == 1

    mock_store.load.assert_called_once_with("proj-1")


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_tree_not_found(mock_get_store, client, mock_store):
    """Test bucket tree retrieval when no tree exists."""
    mock_get_store.return_value = mock_store
    mock_store.load.return_value = None

    response = client.get("/workmap/bucket-tree?project_id=proj-1")

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == "proj-1"
    assert data["tree"] is None
    assert data["summary"] is None

    mock_store.load.assert_called_once_with("proj-1")


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_tree_store_not_initialized(mock_get_store, client):
    """Test bucket tree retrieval when store is not initialized."""
    mock_get_store.side_effect = RuntimeError("Bucket tree store not initialized")

    response = client.get("/workmap/bucket-tree?project_id=proj-1")

    assert response.status_code == 503
    assert "not initialized" in response.json()["detail"]


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_tree_missing_project_id(mock_get_store, client):
    """Test bucket tree retrieval without project_id."""
    response = client.get("/workmap/bucket-tree")

    assert response.status_code == 422  # Validation error


# =============================================================================
# Test GET /workmap/bucket-tree/{bucket_id}
# =============================================================================


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_detail_success(mock_get_store, client, mock_store):
    """Test successful bucket detail retrieval."""
    mock_get_store.return_value = mock_store
    tree = make_bucket_tree("proj-1", num_buckets=2)
    mock_store.load.return_value = tree

    response = client.get("/workmap/bucket-tree/bucket-1?project_id=proj-1")

    assert response.status_code == 200
    data = response.json()
    assert data["bucket_id"] == "bucket-1"
    assert data["rank"] == 1
    assert data["definition"]["name"] == "Bucket 1"
    assert len(data["items"]) == 3
    assert data["stats"]["total_items"] == 3
    assert data["stats"]["ready_items"] == 2
    assert data["stats"]["blocked_items"] == 1

    mock_store.load.assert_called_once_with("proj-1")


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_detail_tree_not_found(mock_get_store, client, mock_store):
    """Test bucket detail when tree doesn't exist."""
    mock_get_store.return_value = mock_store
    mock_store.load.return_value = None

    response = client.get("/workmap/bucket-tree/bucket-1?project_id=proj-1")

    assert response.status_code == 404
    assert "No bucket tree found" in response.json()["detail"]

    mock_store.load.assert_called_once_with("proj-1")


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_detail_bucket_not_found(mock_get_store, client, mock_store):
    """Test bucket detail when bucket doesn't exist in tree."""
    mock_get_store.return_value = mock_store
    tree = make_bucket_tree("proj-1", num_buckets=2)
    mock_store.load.return_value = tree

    response = client.get("/workmap/bucket-tree/nonexistent-bucket?project_id=proj-1")

    assert response.status_code == 404
    assert "Bucket 'nonexistent-bucket' not found" in response.json()["detail"]

    mock_store.load.assert_called_once_with("proj-1")


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_detail_store_not_initialized(mock_get_store, client):
    """Test bucket detail when store is not initialized."""
    mock_get_store.side_effect = RuntimeError("Bucket tree store not initialized")

    response = client.get("/workmap/bucket-tree/bucket-1?project_id=proj-1")

    assert response.status_code == 503
    assert "not initialized" in response.json()["detail"]


@patch("api.work_map.get_bucket_tree_store")
def test_get_bucket_detail_missing_project_id(mock_get_store, client):
    """Test bucket detail without project_id."""
    response = client.get("/workmap/bucket-tree/bucket-1")

    assert response.status_code == 422  # Validation error
