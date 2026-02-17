"""Tests for the skill versioning API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from datetime import datetime, timezone

from models import (
    Skill, SkillVersion, SkillVersionListResponse,
    SkillCreateRequest, SkillUpdateRequest
)
from api import router
from skill_registry import SkillRegistry, set_skill_registry


@pytest.fixture
def temp_skills_path(tmp_path):
    """Create a temporary skills directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()
    (skills_dir / "user").mkdir()
    (skills_dir / "versions").mkdir()

    # Create a sample system skill
    system_skill = skills_dir / "system" / "test-skill.yaml"
    system_skill.write_text("""id: test-skill
name: Test Skill
description: A test skill for unit tests
version: "1.0.0"
author: system

instructions: |
  # Test Skill

  You are a test skill.

specialized_tools:
  - test_tool

tags:
  - testing

constraints:
  - Test constraint
""")

    return str(skills_dir)


@pytest.fixture
async def registry(temp_skills_path):
    """Create a registry for testing."""
    reg = SkillRegistry(skills_path=temp_skills_path)
    await reg.initialize()
    set_skill_registry(reg)
    return reg


@pytest.fixture
def app(registry):
    """Create FastAPI app with router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_list_skill_versions_empty(client, registry):
    """Test listing versions for skill with no version history."""
    response = client.get("/api/v1/skills/test-skill/versions")

    assert response.status_code == 200
    data = response.json()
    assert data["skill_id"] == "test-skill"
    assert data["versions"] == []
    assert data["total"] == 0
    assert data["current_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_list_skill_versions_nonexistent(client, registry):
    """Test listing versions for nonexistent skill returns 404."""
    response = client.get("/api/v1/skills/nonexistent/versions")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_skill_current_version(client, registry):
    """Test getting skill without version param returns current."""
    response = client.get("/api/v1/skills/test-skill")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-skill"
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_get_skill_nonexistent_version(client, registry):
    """Test getting nonexistent version returns 404."""
    # Create a skill first
    create_data = {
        "id": "ver-test-skill",
        "name": "Version Test",
        "description": "Test",
        "instructions": "Test",
        "version": "1.0.0"
    }
    client.post("/api/v1/skills", json=create_data)

    response = client.get("/api/v1/skills/ver-test-skill?version=99.0.0")

    assert response.status_code == 404
    assert "version" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_skill_nonexistent_skill_with_version(client, registry):
    """Test getting version of nonexistent skill returns 404."""
    response = client.get("/api/v1/skills/nonexistent?version=1.0.0")

    assert response.status_code == 404
    assert "skill" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_version_response_model():
    """Test SkillVersionListResponse model structure."""
    version = SkillVersion(
        skill_id="test",
        version="1.0.0",
        instructions="Test instructions",
        specialized_tools=["tool1"],
        changelog="Initial",
        created_at=datetime.now(timezone.utc)
    )

    response = SkillVersionListResponse(
        skill_id="test",
        versions=[version],
        total=1,
        current_version="1.0.0"
    )

    assert response.skill_id == "test"
    assert len(response.versions) == 1
    assert response.total == 1
    assert response.current_version == "1.0.0"
