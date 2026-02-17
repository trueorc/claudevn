"""Tests for the persona versioning API endpoints."""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from datetime import datetime, timezone

from models import PersonaVersion, PersonaVersionListResponse
from api import persona_router
from persona_registry import PersonaRegistry, set_persona_registry


@pytest.fixture
def temp_personas_path(tmp_path):
    """Create a temporary personas directory."""
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "system").mkdir()
    (personas_dir / "user").mkdir()
    (personas_dir / "versions").mkdir()

    # Create a sample system persona
    system_persona = personas_dir / "system" / "test-persona.yaml"
    system_persona.write_text("""id: test-persona
name: Test Persona
description: A test persona for unit tests
version: "1.0.0"
author: system

instructions: |
  # Test Persona

  You are a test persona.

references_skills: []

tags:
  - testing

constraints:
  - Test constraint

merged_instructions: ""
""")

    return str(personas_dir)


@pytest.fixture
async def registry(temp_personas_path):
    """Create a registry for testing."""
    reg = PersonaRegistry(personas_path=temp_personas_path)
    await reg.initialize()
    set_persona_registry(reg)
    return reg


@pytest.fixture
def app(registry):
    """Create FastAPI app with router."""
    app = FastAPI()
    app.include_router(persona_router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_list_persona_versions_empty(client, registry):
    """Test listing versions for persona with no version history."""
    response = client.get("/api/v1/personas/test-persona/versions")

    assert response.status_code == 200
    data = response.json()
    assert data["persona_id"] == "test-persona"
    assert data["versions"] == []
    assert data["total"] == 0
    assert data["current_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_list_persona_versions_nonexistent(client, registry):
    """Test listing versions for nonexistent persona returns 404."""
    response = client.get("/api/v1/personas/nonexistent/versions")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_persona_versions_with_history(client, registry):
    """Test listing versions returns version history."""
    # Create a persona first (adds initial version)
    create_data = {
        "id": "versioned-persona",
        "name": "Versioned Persona",
        "description": "Test versioning",
        "instructions": "v1 instructions",
        "references_skills": ["skill-a"],
        "version": "1.0.0"
    }
    response = client.post("/api/v1/personas", json=create_data)
    assert response.status_code == 201

    # Update with new version
    update_data = {
        "version": "1.1.0",
        "instructions": "v1.1 instructions",
        "references_skills": ["skill-a", "skill-b"],
        "changelog": "Added skill-b"
    }
    response = client.put("/api/v1/personas/versioned-persona", json=update_data)
    assert response.status_code == 200

    # List versions
    response = client.get("/api/v1/personas/versioned-persona/versions")
    assert response.status_code == 200

    data = response.json()
    assert data["persona_id"] == "versioned-persona"
    assert data["total"] == 2
    assert data["current_version"] == "1.1.0"

    # Versions should be newest first
    assert len(data["versions"]) == 2
    assert data["versions"][0]["version"] == "1.1.0"
    assert data["versions"][0]["changelog"] == "Added skill-b"
    assert data["versions"][1]["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_get_persona_current_version(client, registry):
    """Test getting persona without version param returns current."""
    response = client.get("/api/v1/personas/test-persona")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-persona"
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_get_persona_specific_version(client, registry):
    """Test getting persona with version param returns that version."""
    # Create a persona with version history
    create_data = {
        "id": "multi-ver-persona",
        "name": "Multi Version Persona",
        "description": "Has versions",
        "instructions": "Original v1.0.0",
        "references_skills": ["skill-v1"],
        "version": "1.0.0"
    }
    client.post("/api/v1/personas", json=create_data)

    # Update to v1.1.0
    update_data = {
        "version": "1.1.0",
        "instructions": "Updated v1.1.0",
        "references_skills": ["skill-v1", "skill-v2"],
        "changelog": "Added skill-v2"
    }
    client.put("/api/v1/personas/multi-ver-persona", json=update_data)

    # Get v1.0.0
    response = client.get("/api/v1/personas/multi-ver-persona?version=1.0.0")
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "1.0.0"
    assert data["instructions"] == "Original v1.0.0"
    assert data["references_skills"] == ["skill-v1"]


@pytest.mark.asyncio
async def test_get_persona_nonexistent_version(client, registry):
    """Test getting nonexistent version returns 404."""
    # Create a persona first
    create_data = {
        "id": "ver-test-persona",
        "name": "Version Test",
        "description": "Test",
        "instructions": "Test",
        "version": "1.0.0"
    }
    client.post("/api/v1/personas", json=create_data)

    response = client.get("/api/v1/personas/ver-test-persona?version=99.0.0")

    assert response.status_code == 404
    assert "version" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_persona_nonexistent_persona_with_version(client, registry):
    """Test getting version of nonexistent persona returns 404."""
    response = client.get("/api/v1/personas/nonexistent?version=1.0.0")

    assert response.status_code == 404
    assert "persona" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_persona_adds_version_entry(client, registry):
    """Test updating persona with changelog adds version entry."""
    # Create persona
    create_data = {
        "id": "update-ver-persona",
        "name": "Update Ver",
        "description": "Test",
        "instructions": "Original",
        "version": "1.0.0"
    }
    client.post("/api/v1/personas", json=create_data)

    # Update with changelog (no version bump)
    update_data = {
        "instructions": "Improved",
        "changelog": "Minor improvement"
    }
    response = client.put("/api/v1/personas/update-ver-persona", json=update_data)
    assert response.status_code == 200

    # Check version history
    response = client.get("/api/v1/personas/update-ver-persona/versions")
    data = response.json()

    assert data["total"] == 2
    assert data["versions"][0]["changelog"] == "Minor improvement"


@pytest.mark.asyncio
async def test_version_response_contains_references_skills(client, registry):
    """Test that version history contains references_skills field."""
    # Create persona with skills
    create_data = {
        "id": "skills-persona",
        "name": "Skills Persona",
        "description": "Has skills",
        "instructions": "Test",
        "references_skills": ["skill-1", "skill-2"],
        "version": "1.0.0"
    }
    client.post("/api/v1/personas", json=create_data)

    # Get version history
    response = client.get("/api/v1/personas/skills-persona/versions")
    data = response.json()

    assert data["total"] == 1
    assert data["versions"][0]["references_skills"] == ["skill-1", "skill-2"]
