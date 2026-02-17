"""Persona Registry Service - manages the persona catalog.

User personas are stored in a Git-backed repository for durability and version history.
System personas remain in the main codebase (read-only reference).
"""

import yaml
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING
from datetime import datetime, timezone

from models import Persona, PersonaCreateRequest, PersonaUpdateRequest, PersonaVersion, Skill, ExpandedPersona

if TYPE_CHECKING:
    from skill_registry import SkillRegistry
    from git_storage import MarketplaceGitStorage

logger = logging.getLogger(__name__)


# Global registry instance
_persona_registry: Optional["PersonaRegistry"] = None


def get_persona_registry() -> "PersonaRegistry":
    """Get the global persona registry instance."""
    if _persona_registry is None:
        raise RuntimeError("Persona registry not initialized")
    return _persona_registry


def set_persona_registry(registry: "PersonaRegistry") -> None:
    """Set the global persona registry instance."""
    global _persona_registry
    _persona_registry = registry


class PersonaRegistry:
    """Registry for managing personas.

    Storage architecture:
    - System personas: Loaded from local filesystem (read-only)
    - User personas: Stored in Git-backed repository (full version history)
    """

    def __init__(self, personas_path: str = "./personas", git_storage: Optional["MarketplaceGitStorage"] = None):
        """Initialize the persona registry.

        Args:
            personas_path: Path to system personas (local filesystem)
            git_storage: Git storage instance for user personas (optional)
        """
        self.personas_path = Path(personas_path)
        self.personas: Dict[str, Persona] = {}
        self.persona_versions: Dict[str, List[PersonaVersion]] = {}  # persona_id -> list of versions
        self._initialized = False
        self._skill_registry: Optional["SkillRegistry"] = None
        self._git_storage = git_storage

    def set_skill_registry(self, skill_registry: "SkillRegistry") -> None:
        """Set the skill registry for merged instruction generation."""
        self._skill_registry = skill_registry

    def set_git_storage(self, git_storage: "MarketplaceGitStorage") -> None:
        """Set the Git storage instance for user personas."""
        self._git_storage = git_storage

    def _get_skills_for_persona(self, skill_ids: List[str]) -> Tuple[List[Skill], List[str]]:
        """Get skills by IDs, returning found skills and missing IDs."""
        if not self._skill_registry:
            return [], skill_ids

        found_skills = []
        missing_ids = []

        for skill_id in skill_ids:
            skill = self._skill_registry.get_skill(skill_id)
            if skill:
                found_skills.append(skill)
            else:
                missing_ids.append(skill_id)

        return found_skills, missing_ids

    def _generate_merged_instructions(self, persona_name: str, persona_instructions: str,
                                       skills: List[Skill], constraints: List[str]) -> str:
        """Generate pre-merged instructions from persona and its skills."""
        sections = []

        # Header
        sections.append(f"# Persona: {persona_name}\n")

        # Persona-specific instructions
        if persona_instructions:
            sections.append("## Persona Instructions\n")
            sections.append(persona_instructions)
            sections.append("\n")

        # Skill instructions
        if skills:
            sections.append("## Skill Instructions\n")
            for skill in skills:
                sections.append(f"\n### {skill.name}\n")
                sections.append(skill.instructions)
                sections.append("\n")

        # Aggregated constraints (persona + skills)
        all_constraints = list(constraints)
        for skill in skills:
            all_constraints.extend(skill.constraints)

        if all_constraints:
            sections.append("\n## Constraints\n")
            for constraint in all_constraints:
                sections.append(f"- {constraint}\n")

        return "\n".join(sections)

    def expand_persona(self, persona_id: str) -> Optional[ExpandedPersona]:
        """Expand a persona to include its constituent skill objects."""
        persona = self.personas.get(persona_id)
        if not persona:
            return None

        skills, missing_ids = self._get_skills_for_persona(persona.references_skills)

        return ExpandedPersona(
            persona=persona,
            skills=skills,
            missing_skills=missing_ids
        )

    def _persona_to_yaml(self, persona: Persona) -> str:
        """Convert a persona to YAML string."""
        data = {
            "id": persona.id,
            "name": persona.name,
            "description": persona.description,
            "version": persona.version,
            "author": persona.author,
            "instructions": persona.instructions,
            "references_skills": persona.references_skills,
            "merged_instructions": persona.merged_instructions,
            "instructions_stale": persona.instructions_stale,
            "tags": persona.tags,
            "constraints": persona.constraints,
        }
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def _get_persona_git_path(self, persona_id: str) -> str:
        """Get the Git path for a user persona."""
        return f"personas/user/{persona_id}.yaml"

    async def regenerate_merged_instructions(self, persona_id: str) -> Optional[Persona]:
        """Regenerate merged instructions for a persona from its referenced skills."""
        persona = self.personas.get(persona_id)
        if not persona:
            return None

        skills, _ = self._get_skills_for_persona(persona.references_skills)
        persona.merged_instructions = self._generate_merged_instructions(
            persona.name, persona.instructions, skills, persona.constraints
        )
        persona.updated_at = datetime.now(timezone.utc)

        # Save to appropriate storage
        if persona.author == "system":
            file_path = self.personas_path / "system" / f"{persona.id}.yaml"
            await self._save_persona_to_local_file(persona, file_path)
        elif self._git_storage:
            relative_path = self._get_persona_git_path(persona.id)
            content = self._persona_to_yaml(persona)
            self._git_storage.save_yaml(
                relative_path,
                content,
                f"regenerate: {persona.id} v{persona.version} - Merged instructions updated"
            )
        else:
            file_path = self.personas_path / "user" / f"{persona.id}.yaml"
            await self._save_persona_to_local_file(persona, file_path)

        logger.info(f"Regenerated merged instructions for persona: {persona_id}")
        return persona

    async def initialize(self) -> None:
        """Initialize the registry by loading personas from disk and Git."""
        if self._initialized:
            return

        # Ensure local directories exist for system personas
        (self.personas_path / "system").mkdir(parents=True, exist_ok=True)
        (self.personas_path / "versions").mkdir(parents=True, exist_ok=True)

        # Load system personas from local filesystem
        await self._load_personas_from_directory(self.personas_path / "system", "system")

        # Load user personas from Git storage if available
        if self._git_storage:
            await self._load_user_personas_from_git()
        else:
            # Fallback to local filesystem for user personas (non-Git mode)
            (self.personas_path / "user").mkdir(parents=True, exist_ok=True)
            await self._load_personas_from_directory(self.personas_path / "user", "user")

        # Load version history
        await self._load_version_history()

        self._initialized = True
        logger.info(f"Persona registry initialized: {len(self.personas)} personas")

    async def _load_personas_from_directory(self, directory: Path, author_prefix: str) -> None:
        """Load persona definitions from a local directory."""
        if not directory.exists():
            return

        for file_path in directory.glob("*.yaml"):
            try:
                with open(file_path, "r") as f:
                    data = yaml.safe_load(f)

                if data is None:
                    continue

                # Set author based on directory
                if "author" not in data:
                    data["author"] = author_prefix

                persona = Persona(**data)
                self.personas[persona.id] = persona

                logger.debug(f"Loaded persona: {persona.id}")
            except Exception as e:
                logger.error(f"Failed to load persona from {file_path}: {e}")

    async def _load_user_personas_from_git(self) -> None:
        """Load user personas from Git storage."""
        if not self._git_storage:
            return

        # List all YAML files in personas/user directory
        persona_files = self._git_storage.list_files("personas/user", "*.yaml")

        for file_path in persona_files:
            try:
                relative_path = f"personas/user/{file_path.name}"
                content = self._git_storage.load_yaml(relative_path)

                if content is None:
                    continue

                data = yaml.safe_load(content)
                if data is None:
                    continue

                # Ensure user author prefix
                if "author" not in data or not data["author"].startswith("user:"):
                    data["author"] = "user:unknown"

                persona = Persona(**data)
                self.personas[persona.id] = persona

                logger.debug(f"Loaded user persona from Git: {persona.id}")
            except Exception as e:
                logger.error(f"Failed to load persona from Git {file_path}: {e}")

    async def _load_version_history(self) -> None:
        """Load version history from disk."""
        versions_dir = self.personas_path / "versions"
        if not versions_dir.exists():
            return

        for file_path in versions_dir.glob("*.yaml"):
            try:
                with open(file_path, "r") as f:
                    data = yaml.safe_load(f)

                if data is None or "versions" not in data:
                    continue

                persona_id = data.get("persona_id", file_path.stem)
                versions = []
                for v_data in data["versions"]:
                    version = PersonaVersion(**v_data)
                    versions.append(version)

                # Sort by created_at descending (newest first)
                versions.sort(key=lambda v: v.created_at, reverse=True)
                self.persona_versions[persona_id] = versions

                logger.debug(f"Loaded {len(versions)} versions for persona: {persona_id}")
            except Exception as e:
                logger.error(f"Failed to load version history from {file_path}: {e}")

    async def _save_version_history(self, persona_id: str) -> None:
        """Save version history to disk."""
        versions = self.persona_versions.get(persona_id, [])
        if not versions:
            return

        file_path = self.personas_path / "versions" / f"{persona_id}.yaml"
        data = {
            "persona_id": persona_id,
            "versions": [
                {
                    "persona_id": v.persona_id,
                    "version": v.version,
                    "instructions": v.instructions,
                    "references_skills": v.references_skills,
                    "changelog": v.changelog,
                    "created_at": v.created_at.isoformat(),
                }
                for v in versions
            ]
        }

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    async def _add_version_entry(
        self,
        persona: Persona,
        changelog: Optional[str] = None
    ) -> PersonaVersion:
        """Add a version entry for a persona."""
        version_entry = PersonaVersion(
            persona_id=persona.id,
            version=persona.version,
            instructions=persona.instructions,
            references_skills=persona.references_skills,
            changelog=changelog,
            created_at=datetime.now(timezone.utc)
        )

        if persona.id not in self.persona_versions:
            self.persona_versions[persona.id] = []

        # Insert at beginning (newest first)
        self.persona_versions[persona.id].insert(0, version_entry)

        # Save to disk
        await self._save_version_history(persona.id)

        logger.debug(f"Added version {persona.version} for persona: {persona.id}")
        return version_entry

    def list_persona_versions(self, persona_id: str) -> List[PersonaVersion]:
        """List all versions of a persona (newest first)."""
        return self.persona_versions.get(persona_id, [])

    def get_persona_version(self, persona_id: str, version: str) -> Optional[Persona]:
        """Get a specific version of a persona.

        Returns a Persona object with the state at that version.
        """
        versions = self.persona_versions.get(persona_id, [])
        for v in versions:
            if v.version == version:
                # Get current persona for metadata, overlay with version data
                current_persona = self.personas.get(persona_id)
                if not current_persona:
                    return None

                # Create persona with version-specific data
                return Persona(
                    id=current_persona.id,
                    name=current_persona.name,
                    description=current_persona.description,
                    version=v.version,
                    author=current_persona.author,
                    instructions=v.instructions,
                    references_skills=v.references_skills,
                    merged_instructions=current_persona.merged_instructions,
                    tags=current_persona.tags,
                    constraints=current_persona.constraints,
                    created_at=current_persona.created_at,
                    updated_at=v.created_at
                )

        return None

    def list_personas(
        self,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None
    ) -> List[Persona]:
        """List personas with optional filtering."""
        result = list(self.personas.values())

        if tags:
            result = [p for p in result if any(t in p.tags for t in tags)]

        if author:
            result = [p for p in result if p.author == author or p.author.startswith(f"{author}:")]

        return result

    def get_persona(self, persona_id: str) -> Optional[Persona]:
        """Get a persona by ID.

        Implements lazy regeneration: if the persona's instructions are marked
        as stale (due to skill updates), regenerates merged_instructions on retrieval.
        """
        persona = self.personas.get(persona_id)
        if persona and persona.instructions_stale:
            # Lazy regeneration - update merged instructions from current skills
            skills, _ = self._get_skills_for_persona(persona.references_skills)
            persona.merged_instructions = self._generate_merged_instructions(
                persona.name, persona.instructions, skills, persona.constraints
            )
            persona.instructions_stale = False
            persona.updated_at = datetime.now(timezone.utc)
            logger.info(f"Lazily regenerated merged instructions for persona: {persona_id}")
        return persona

    def invalidate_personas_referencing_skill(self, skill_id: str) -> List[str]:
        """Mark personas referencing a skill as stale.

        Called when a skill is updated to invalidate any personas that reference it.
        The personas will be lazily regenerated on next retrieval via get_persona().

        Args:
            skill_id: The ID of the skill that was updated

        Returns:
            List of persona IDs that were marked as stale
        """
        invalidated_personas = []
        for persona in self.personas.values():
            if skill_id in persona.references_skills and not persona.instructions_stale:
                persona.instructions_stale = True
                invalidated_personas.append(persona.id)
                logger.debug(f"Marked persona {persona.id} as stale due to skill {skill_id} update")

        if invalidated_personas:
            logger.info(f"Invalidated {len(invalidated_personas)} personas referencing skill {skill_id}: {invalidated_personas}")

        return invalidated_personas

    async def create_persona(self, request: PersonaCreateRequest, author: str = "user") -> Persona:
        """Create a new persona with pre-merged instructions.

        User personas are stored in Git for durability.
        System personas are stored in local filesystem.
        """
        if request.id in self.personas:
            raise ValueError(f"Persona {request.id} already exists")

        # Get skills for merged instructions
        skills, _ = self._get_skills_for_persona(request.references_skills)
        merged_instructions = self._generate_merged_instructions(
            request.name, request.instructions, skills, request.constraints
        )

        persona = Persona(
            id=request.id,
            name=request.name,
            description=request.description,
            instructions=request.instructions,
            references_skills=request.references_skills,
            merged_instructions=merged_instructions,
            tags=request.tags,
            constraints=request.constraints,
            version=request.version,
            author=author if author == "system" else f"user:{author}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # Save to appropriate storage
        if author == "system":
            # System personas go to local filesystem
            file_path = self.personas_path / "system" / f"{persona.id}.yaml"
            await self._save_persona_to_local_file(persona, file_path)
        elif self._git_storage:
            # User personas go to Git storage
            relative_path = self._get_persona_git_path(persona.id)
            content = self._persona_to_yaml(persona)
            self._git_storage.save_yaml(
                relative_path,
                content,
                f"create: {persona.id} v{persona.version} - Initial version"
            )
        else:
            # Fallback to local filesystem
            file_path = self.personas_path / "user" / f"{persona.id}.yaml"
            await self._save_persona_to_local_file(persona, file_path)

        self.personas[persona.id] = persona

        # Add initial version entry
        await self._add_version_entry(persona, changelog="Initial version")

        logger.info(f"Created persona: {persona.id}")
        return persona

    async def update_persona(self, persona_id: str, request: PersonaUpdateRequest) -> Optional[Persona]:
        """Update an existing persona, regenerating merged instructions if needed."""
        persona = self.personas.get(persona_id)
        if not persona:
            return None

        # Extract changelog before processing other fields
        changelog = request.changelog

        # Track if version changed for version history
        old_version = persona.version

        # Update fields that were provided (excluding changelog which is not a persona field)
        update_data = request.model_dump(exclude_unset=True, exclude={"changelog"})
        needs_regeneration = False

        for key, value in update_data.items():
            if value is not None:
                setattr(persona, key, value)
                # Track if we need to regenerate merged instructions
                if key in ('references_skills', 'instructions', 'constraints', 'name'):
                    needs_regeneration = True

        # Regenerate merged instructions if relevant fields changed
        if needs_regeneration:
            skills, _ = self._get_skills_for_persona(persona.references_skills)
            persona.merged_instructions = self._generate_merged_instructions(
                persona.name, persona.instructions, skills, persona.constraints
            )

        persona.updated_at = datetime.now(timezone.utc)

        # Save to appropriate storage
        if persona.author == "system":
            # System personas go to local filesystem
            file_path = self.personas_path / "system" / f"{persona.id}.yaml"
            await self._save_persona_to_local_file(persona, file_path)
        elif self._git_storage:
            # User personas go to Git storage
            relative_path = self._get_persona_git_path(persona.id)
            content = self._persona_to_yaml(persona)
            self._git_storage.save_yaml(
                relative_path,
                content,
                f"update: {persona.id} v{persona.version}"
            )
        else:
            # Fallback to local filesystem
            file_path = self.personas_path / "user" / f"{persona.id}.yaml"
            await self._save_persona_to_local_file(persona, file_path)

        # Add version entry if version changed or if there was a changelog provided
        if persona.version != old_version or changelog:
            await self._add_version_entry(persona, changelog=changelog)

        logger.info(f"Updated persona: {persona.id}")
        return persona

    async def delete_persona(self, persona_id: str) -> bool:
        """Delete a persona."""
        persona = self.personas.get(persona_id)
        if not persona:
            return False

        # Don't allow deleting system personas
        if persona.author == "system":
            raise ValueError("Cannot delete system personas")

        # Delete from appropriate storage
        if self._git_storage:
            relative_path = self._get_persona_git_path(persona_id)
            self._git_storage.delete_file(
                relative_path,
                f"delete: {persona_id} - Persona removed"
            )
        else:
            # Fallback to local filesystem
            file_path = self.personas_path / "user" / f"{persona_id}.yaml"
            if file_path.exists():
                file_path.unlink()

        del self.personas[persona_id]
        logger.info(f"Deleted persona: {persona_id}")
        return True

    async def _save_persona_to_local_file(self, persona: Persona, file_path: Path) -> None:
        """Save a persona to a local YAML file (for system personas or fallback mode)."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(self._persona_to_yaml(persona))

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        by_author = {}
        for persona in self.personas.values():
            author_type = "system" if persona.author == "system" else "user"
            by_author[author_type] = by_author.get(author_type, 0) + 1

        return {
            "total_personas": len(self.personas),
            "by_author": by_author,
            "git_backed": self._git_storage is not None
        }
