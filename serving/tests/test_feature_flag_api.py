"""Unit tests for feature flags API router."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.feature_flags import router
from models.feature_flag import FeatureFlag, FlagCategory
from services.feature_flag_service import FeatureFlagService


@pytest.fixture
def mock_service():
    """Create a mock FeatureFlagService."""
    service = AsyncMock(spec=FeatureFlagService)
    return service


@pytest.fixture
def client(mock_service):
    """Create a test client with the feature flags router."""
    app = FastAPI()
    app.include_router(router)

    with patch(
        "api.feature_flags.get_feature_flag_service",
        return_value=mock_service,
    ):
        yield TestClient(app)


def _make_flag(name="test-flag", enabled=False, category="experimental", desc=""):
    return FeatureFlag(
        name=name,
        description=desc,
        enabled=enabled,
        category=FlagCategory(category),
    )


class TestListFlags:
    def test_list_returns_flags(self, client, mock_service):
        mock_service.list_flags.return_value = [
            _make_flag("flag-a", enabled=True),
            _make_flag("flag-b", enabled=False),
        ]
        resp = client.get("/feature-flags")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["flags"]) == 2
        assert data["flags"][0]["name"] == "flag-a"
        assert data["flags"][0]["enabled"] is True

    def test_list_empty(self, client, mock_service):
        mock_service.list_flags.return_value = []
        resp = client.get("/feature-flags")
        assert resp.status_code == 200
        assert resp.json()["flags"] == []


class TestGetFlag:
    def test_get_existing(self, client, mock_service):
        mock_service.get_flag.return_value = _make_flag("my-flag", desc="hello")
        resp = client.get("/feature-flags/my-flag")
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-flag"
        assert resp.json()["description"] == "hello"

    def test_get_not_found(self, client, mock_service):
        mock_service.get_flag.return_value = None
        resp = client.get("/feature-flags/missing")
        assert resp.status_code == 404


class TestCreateFlag:
    def test_create_success(self, client, mock_service):
        mock_service.create_flag.return_value = _make_flag("new-flag")
        resp = client.post("/feature-flags", json={
            "name": "new-flag",
            "description": "A new flag",
            "category": "ui",
            "enabled": False,
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "new-flag"

    def test_create_duplicate(self, client, mock_service):
        mock_service.create_flag.side_effect = ValueError("already exists")
        resp = client.post("/feature-flags", json={"name": "dup"})
        assert resp.status_code == 409

    def test_create_invalid_name(self, client, mock_service):
        resp = client.post("/feature-flags", json={"name": "Invalid Name!"})
        assert resp.status_code == 422


class TestToggleFlag:
    def test_toggle_success(self, client, mock_service):
        mock_service.toggle_flag.return_value = _make_flag("toggled", enabled=True)
        resp = client.put("/feature-flags/toggled", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_toggle_not_found(self, client, mock_service):
        mock_service.toggle_flag.return_value = None
        resp = client.put("/feature-flags/missing", json={"enabled": True})
        assert resp.status_code == 404


class TestDeleteFlag:
    def test_delete_success(self, client, mock_service):
        mock_service.delete_flag.return_value = True
        resp = client.delete("/feature-flags/doomed")
        assert resp.status_code == 204

    def test_delete_not_found(self, client, mock_service):
        mock_service.delete_flag.return_value = False
        resp = client.delete("/feature-flags/missing")
        assert resp.status_code == 404


class TestServiceUnavailable:
    def test_503_when_service_none(self):
        app = FastAPI()
        app.include_router(router)
        with patch(
            "api.feature_flags.get_feature_flag_service",
            return_value=None,
        ):
            client = TestClient(app)
            resp = client.get("/feature-flags")
            assert resp.status_code == 503
