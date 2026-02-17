"""Tests for skill registry service with Git-backed storage.

These tests verify that the SkillRegistry correctly uses Git storage for user skills
while maintaining compatibility with the non-Git mode tested in test_skill_registry.py.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
import yaml

from models import Skill, SkillCreateRequest, SkillUpdateRequest, SkillVersion, ToolTier
from skill_registry import SkillRegistry
from git_storage import MarketplaceGitStorage


class MockGitStorage:
    """Mock Git storage for testing without real Git operations."""

    def __init__(self):
        self._files: dict = {}
        self._history: dict = {}
        self._commit_count = 0

    def list_files(self, directory: str, pattern: str = "*.yaml"):
        """List files in a directory."""
        result = []
        for path in self._files.keys():
            if path.startswith(directory) and path.endswith(".yaml"):
                result.append(Path(path))
        return result

    def load_yaml(self, relative_path: str):
        """Load YAML content from a file."""
        return self._files.get(relative_path)

    def save_yaml(self, relative_path: str, content: str, commit_message: str):
        """Save YAML content and record history."""
        self._files[relative_path] = content
        self._commit_count += 1
        commit_hash = f"commit{self._commit_count:06d}"

        if relative_path not in self._history:
            self._history[relative_path] = []

        self._history[relative_path].insert(0, {
            "commit": commit_hash,
            "author": "test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": commit_message,
            "content": content,
        })
        return True

    def delete_file(self, relative_path: str, commit_message: str):
        """Delete a file and record in history."""
        if relative_path in self._files:
            del self._files[relative_path]
            return True
        return False

    def file_exists(self, relative_path: str):
        """Check if file exists."""
        return relative_path in self._files

    def get_file_history(self, relative_path: str, max_entries: int = 50):
        """Get file history."""
        history = self._history.get(relative_path, [])
        return [
            {
                "commit": h["commit"],
                "author": h["author"],
                "timestamp": h["timestamp"],
                "message": h["message"],
            }
            for h in history[:max_entries]
        ]

    def get_file_at_commit(self, relative_path: str, commit_hash: str):
        """Get file content at a specific commit."""
        history = self._history.get(relative_path, [])
        for entry in history:
            if entry["commit"] == commit_hash:
                return entry["content"]
        return None


@pytest.fixture
def mock_git_storage():
    """Create a mock Git storage instance."""
    return MockGitStorage()


@pytest.fixture
def temp_skills_path_for_git(tmp_path):
    """Create a temporary skills directory for Git-backed tests."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "system").mkdir()

    # Create a sample system skill
    system_skill = skills_dir / "system" / "test-skill.yaml"
    system_skill.write_text("""id: test-skill
name: Test Skill
description: A test skill for unit tests
version: "1.0.0"
author: system

instructions: |
  # Test Skill
  You are a test skill used in unit tests.

specialized_tools:
  - test_tool

tags:
  - testing
  - automation

constraints:
  - Do not modify production code
""")

    return str(skills_dir)


@pytest.fixture
async def git_backed_registry(temp_skills_path_for_git, mock_git_storage):
    """Create a registry with mock Git storage."""
    reg = SkillRegistry(skills_path=temp_skills_path_for_git, git_storage=mock_git_storage)
    await reg.initialize()
    return reg


class TestGitBackedSkillRegistryInit:
    """Tests for Git-backed registry initialization."""

    @pytest.mark.asyncio
    async def test_initialize_with_git_storage(self, temp_skills_path_for_git, mock_git_storage):
        """Test that registry initializes with Git storage."""
        registry = SkillRegistry(
            skills_path=temp_skills_path_for_git,
            git_storage=mock_git_storage
        )
        await registry.initialize()

        assert registry._initialized is True
        assert registry._git_storage is mock_git_storage

    @pytest.mark.asyncio
    async def test_initialize_loads_system_skills_from_filesystem(
        self, temp_skills_path_for_git, mock_git_storage
    ):
        """Test that system skills are loaded from filesystem, not Git."""
        registry = SkillRegistry(
            skills_path=temp_skills_path_for_git,
            git_storage=mock_git_storage
        )
        await registry.initialize()

        # System skill should be loaded
        assert "test-skill" in registry.skills
        assert registry.skills["test-skill"].author == "system"

    @pytest.mark.asyncio
    async def test_initialize_loads_user_skills_from_git(
        self, temp_skills_path_for_git, mock_git_storage
    ):
        """Test that user skills are loaded from Git storage."""
        # Pre-populate Git storage with a user skill
        user_skill_content = """id: git-user-skill
name: Git User Skill
description: A user skill from Git
version: "1.0.0"
author: user:testuser
instructions: |
  # Git User Skill
  Instructions here.
specialized_tools: []
tags:
  - git
  - user
constraints: []
dependencies: []
"""
        mock_git_storage.save_yaml("skills/user/git-user-skill.yaml", user_skill_content, "Initial")

        registry = SkillRegistry(
            skills_path=temp_skills_path_for_git,
            git_storage=mock_git_storage
        )
        await registry.initialize()

        # User skill should be loaded from Git
        assert "git-user-skill" in registry.skills
        assert registry.skills["git-user-skill"].author == "user:testuser"

    @pytest.mark.asyncio
    async def test_set_git_storage_after_init(self, temp_skills_path_for_git, mock_git_storage):
        """Test setting Git storage after initialization."""
        registry = SkillRegistry(skills_path=temp_skills_path_for_git)
        registry.set_git_storage(mock_git_storage)

        assert registry._git_storage is mock_git_storage


class TestGitBackedSkillCreate:
    """Tests for creating skills with Git storage."""

    @pytest.mark.asyncio
    async def test_create_user_skill_saves_to_git(self, git_backed_registry, mock_git_storage):
        """Test that creating a user skill saves to Git."""
        request = SkillCreateRequest(
            id="new-user-skill",
            name="New User Skill",
            description="A new user-created skill",
            instructions="# New User Skill\n\nInstructions here.",
            tags=["new", "user"],
            version="1.0.0"
        )

        skill = await git_backed_registry.create_skill(request, author="testuser")

        assert skill.id == "new-user-skill"
        assert skill.author == "user:testuser"

        # Verify saved to Git
        git_path = "skills/user/new-user-skill.yaml"
        assert mock_git_storage.file_exists(git_path)

        # Verify content
        content = mock_git_storage.load_yaml(git_path)
        assert "new-user-skill" in content
        assert "user:testuser" in content

    @pytest.mark.asyncio
    async def test_create_system_skill_saves_to_filesystem(
        self, git_backed_registry, mock_git_storage, temp_skills_path_for_git
    ):
        """Test that creating a system skill saves to filesystem, not Git."""
        request = SkillCreateRequest(
            id="new-system-skill",
            name="New System Skill",
            description="A new system skill",
            instructions="# New System Skill",
            version="1.0.0"
        )

        skill = await git_backed_registry.create_skill(request, author="system")

        assert skill.author == "system"

        # Should be saved to filesystem
        file_path = Path(temp_skills_path_for_git) / "system" / "new-system-skill.yaml"
        assert file_path.exists()

        # Should NOT be in Git
        assert not mock_git_storage.file_exists("skills/user/new-system-skill.yaml")
        assert not mock_git_storage.file_exists("skills/system/new-system-skill.yaml")


class TestGitBackedSkillUpdate:
    """Tests for updating skills with Git storage."""

    @pytest.mark.asyncio
    async def test_update_user_skill_saves_to_git(self, git_backed_registry, mock_git_storage):
        """Test that updating a user skill saves to Git."""
        # Create skill first
        create_request = SkillCreateRequest(
            id="update-test-skill",
            name="Update Test",
            description="Test skill for update",
            instructions="Original",
            version="1.0.0"
        )
        await git_backed_registry.create_skill(create_request, author="testuser")

        # Update it
        update_request = SkillUpdateRequest(
            name="Updated Test",
            instructions="Updated instructions",
            version="1.1.0"
        )
        skill = await git_backed_registry.update_skill("update-test-skill", update_request)

        assert skill.name == "Updated Test"
        assert skill.version == "1.1.0"

        # Verify Git history has 2 entries
        history = mock_git_storage.get_file_history("skills/user/update-test-skill.yaml")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_update_system_skill_saves_to_filesystem(
        self, git_backed_registry, mock_git_storage, temp_skills_path_for_git
    ):
        """Test that updating a system skill saves to filesystem."""
        update_request = SkillUpdateRequest(
            description="Updated system skill description"
        )

        skill = await git_backed_registry.update_skill("test-skill", update_request)

        assert skill.description == "Updated system skill description"

        # Verify saved to filesystem
        file_path = Path(temp_skills_path_for_git) / "system" / "test-skill.yaml"
        content = file_path.read_text()
        assert "Updated system skill description" in content


class TestGitBackedSkillDelete:
    """Tests for deleting skills with Git storage."""

    @pytest.mark.asyncio
    async def test_delete_user_skill_removes_from_git(self, git_backed_registry, mock_git_storage):
        """Test that deleting a user skill removes from Git."""
        # Create skill first
        create_request = SkillCreateRequest(
            id="delete-test-skill",
            name="Delete Test",
            description="Test skill for deletion",
            instructions="Test",
            version="1.0.0"
        )
        await git_backed_registry.create_skill(create_request, author="testuser")

        assert mock_git_storage.file_exists("skills/user/delete-test-skill.yaml")

        # Delete it
        result = await git_backed_registry.delete_skill("delete-test-skill")

        assert result is True
        assert not mock_git_storage.file_exists("skills/user/delete-test-skill.yaml")
        assert "delete-test-skill" not in git_backed_registry.skills

    @pytest.mark.asyncio
    async def test_delete_system_skill_raises_error(self, git_backed_registry):
        """Test that deleting a system skill raises error."""
        with pytest.raises(ValueError, match="Cannot delete system skills"):
            await git_backed_registry.delete_skill("test-skill")


class TestGitBackedSkillVersioning:
    """Tests for skill versioning with Git history."""

    @pytest.mark.asyncio
    async def test_list_skill_versions_uses_git_history(self, git_backed_registry, mock_git_storage):
        """Test that list_skill_versions uses Git history for user skills."""
        # Create and update skill to create history
        create_request = SkillCreateRequest(
            id="versioned-skill",
            name="Versioned Skill",
            description="Test versioning",
            instructions="v1 instructions",
            version="1.0.0"
        )
        await git_backed_registry.create_skill(create_request, author="testuser")

        await git_backed_registry.update_skill("versioned-skill", SkillUpdateRequest(
            version="1.1.0",
            instructions="v1.1 instructions"
        ))

        versions = git_backed_registry.list_skill_versions("versioned-skill")

        # Should have 2 versions from Git history
        assert len(versions) == 2
        assert versions[0].version == "1.1.0"
        assert versions[1].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_list_skill_versions_returns_empty_for_system_skills(self, git_backed_registry):
        """Test that list_skill_versions returns empty for system skills."""
        versions = git_backed_registry.list_skill_versions("test-skill")
        assert versions == []

    @pytest.mark.asyncio
    async def test_get_skill_version_retrieves_from_git_history(
        self, git_backed_registry, mock_git_storage
    ):
        """Test that get_skill_version retrieves from Git history."""
        # Create and update skill
        create_request = SkillCreateRequest(
            id="history-skill",
            name="History Skill",
            description="Test history retrieval",
            instructions="v1 original",
            version="1.0.0"
        )
        await git_backed_registry.create_skill(create_request, author="testuser")

        await git_backed_registry.update_skill("history-skill", SkillUpdateRequest(
            version="2.0.0",
            instructions="v2 updated"
        ))

        # Get old version
        v1 = git_backed_registry.get_skill_version("history-skill", "1.0.0")
        assert v1 is not None
        assert v1.version == "1.0.0"
        assert v1.instructions == "v1 original"

        # Get current version
        current = git_backed_registry.get_skill("history-skill")
        assert current.version == "2.0.0"
        assert current.instructions == "v2 updated"

    @pytest.mark.asyncio
    async def test_get_skill_version_returns_none_for_nonexistent_version(
        self, git_backed_registry, mock_git_storage
    ):
        """Test get_skill_version returns None for nonexistent version."""
        create_request = SkillCreateRequest(
            id="version-test",
            name="Version Test",
            description="Test",
            instructions="Test",
            version="1.0.0"
        )
        await git_backed_registry.create_skill(create_request, author="testuser")

        result = git_backed_registry.get_skill_version("version-test", "99.0.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_skill_version_system_skill_returns_current_if_match(
        self, git_backed_registry
    ):
        """Test that get_skill_version returns current skill if version matches for system skills."""
        skill = git_backed_registry.get_skill_version("test-skill", "1.0.0")
        assert skill is not None
        assert skill.id == "test-skill"

        # Non-matching version returns None
        skill = git_backed_registry.get_skill_version("test-skill", "2.0.0")
        assert skill is None


class TestGitBackedRegistryStats:
    """Tests for registry statistics with Git storage."""

    @pytest.mark.asyncio
    async def test_stats_includes_git_backed_flag(self, git_backed_registry):
        """Test that stats include git_backed flag."""
        stats = git_backed_registry.get_stats()

        assert stats["git_backed"] is True

    @pytest.mark.asyncio
    async def test_stats_without_git_storage(self, temp_skills_path_for_git):
        """Test stats when Git storage is not configured."""
        registry = SkillRegistry(skills_path=temp_skills_path_for_git)
        await registry.initialize()

        stats = registry.get_stats()
        assert stats["git_backed"] is False


class TestGitBackedRegistryFallback:
    """Tests for fallback behavior when Git storage is unavailable."""

    @pytest.mark.asyncio
    async def test_create_skill_falls_back_to_filesystem(self, temp_skills_path_for_git):
        """Test that skill creation falls back to filesystem without Git."""
        # Create user directory for fallback
        (Path(temp_skills_path_for_git) / "user").mkdir(exist_ok=True)

        registry = SkillRegistry(skills_path=temp_skills_path_for_git)
        await registry.initialize()

        request = SkillCreateRequest(
            id="fallback-skill",
            name="Fallback Skill",
            description="Test fallback",
            instructions="Test",
            version="1.0.0"
        )
        skill = await registry.create_skill(request, author="testuser")

        assert skill.id == "fallback-skill"

        # Should be saved to filesystem
        file_path = Path(temp_skills_path_for_git) / "user" / "fallback-skill.yaml"
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_skill_falls_back_to_filesystem(self, temp_skills_path_for_git):
        """Test that skill deletion falls back to filesystem without Git."""
        # Create user directory and skill for fallback
        user_dir = Path(temp_skills_path_for_git) / "user"
        user_dir.mkdir(exist_ok=True)

        skill_file = user_dir / "delete-fallback.yaml"
        skill_file.write_text("""id: delete-fallback
name: Delete Fallback
description: Test
version: "1.0.0"
author: user:test
instructions: Test
specialized_tools: []
tags: []
constraints: []
dependencies: []
""")

        registry = SkillRegistry(skills_path=temp_skills_path_for_git)
        await registry.initialize()

        assert "delete-fallback" in registry.skills

        result = await registry.delete_skill("delete-fallback")

        assert result is True
        assert not skill_file.exists()
