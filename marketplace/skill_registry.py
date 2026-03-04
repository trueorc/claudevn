"""Skill Registry Service - manages the skill catalog.

User skills are stored in a Git-backed repository for durability and version history.
System skills remain in the main codebase (read-only reference).
"""

import re
import yaml
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, timezone

from models import Skill, SkillCreateRequest, SkillUpdateRequest, SkillVersion, ToolDefinition, ToolTier, MarketplaceTier

if TYPE_CHECKING:
    from git_storage import MarketplaceGitStorage
    from persona_registry import PersonaRegistry

logger = logging.getLogger(__name__)


# Global registry instance
_skill_registry: Optional["SkillRegistry"] = None


def get_skill_registry() -> "SkillRegistry":
    """Get the global skill registry instance."""
    if _skill_registry is None:
        raise RuntimeError("Skill registry not initialized")
    return _skill_registry


def set_skill_registry(registry: "SkillRegistry") -> None:
    """Set the global skill registry instance."""
    global _skill_registry
    _skill_registry = registry


class SkillRegistry:
    """Registry for managing skills and tools.

    Storage architecture:
    - System skills: Loaded from local filesystem (read-only)
    - User skills: Stored in Git-backed repository (full version history)
    - Tools: Loaded from global definitions and skill grants
    """

    def __init__(
        self,
        skills_path: str = "./skills",
        git_storage: Optional["MarketplaceGitStorage"] = None,
        marketplace_id: Optional[str] = None,
        marketplace_name: Optional[str] = None,
        marketplace_tier: Optional[MarketplaceTier] = None,
        namespace: Optional[str] = None,
    ):
        """Initialize the skill registry.

        Args:
            skills_path: Path to system skills (local filesystem)
            git_storage: Git storage instance for user skills (optional)
            marketplace_id: ID of this marketplace instance
            marketplace_name: Human-readable name of this marketplace
            marketplace_tier: Hierarchy tier of this marketplace
            namespace: Optional namespace prefix for non-ROOT skills.
                When set, user skills are stored under namespaced IDs
                (e.g., "acme:code-writer") to prevent collisions across
                marketplaces. ROOT-tier skills are never namespaced.
        """
        self.skills_path = Path(skills_path)
        self.skills: Dict[str, Skill] = {}
        self.tools: Dict[str, ToolDefinition] = {}
        self._git_storage = git_storage
        self._persona_registry: Optional["PersonaRegistry"] = None
        self._initialized = False

        # Marketplace source identification
        self._marketplace_id = marketplace_id
        self._marketplace_name = marketplace_name
        self._marketplace_tier = marketplace_tier
        self._namespace = namespace

    def set_git_storage(self, git_storage: "MarketplaceGitStorage") -> None:
        """Set the Git storage instance for user skills."""
        self._git_storage = git_storage

    def set_persona_registry(self, persona_registry: "PersonaRegistry") -> None:
        """Set the persona registry for invalidation on skill updates."""
        self._persona_registry = persona_registry

    async def initialize(self) -> None:
        """Initialize the registry by loading skills from disk and Git."""
        if self._initialized:
            return

        # Ensure local directories exist for system skills
        (self.skills_path / "system").mkdir(parents=True, exist_ok=True)

        # Load global tools
        self._load_global_tools()

        # Load specialized tool definitions from YAML
        self._load_specialized_tools()

        # Load system skills from local filesystem
        await self._load_skills_from_directory(self.skills_path / "system", "system")

        # Load user skills from Git storage if available
        if self._git_storage:
            await self._load_user_skills_from_git()
        else:
            # Fallback to local filesystem for user skills (non-Git mode)
            (self.skills_path / "user").mkdir(parents=True, exist_ok=True)
            await self._load_skills_from_directory(self.skills_path / "user", "user")

        self._initialized = True
        logger.info(f"Skill registry initialized: {len(self.skills)} skills, {len(self.tools)} tools")

    def _load_global_tools(self) -> None:
        """Load global tool definitions."""
        global_tools = [
            ToolDefinition(
                id="read", name="Read", description="Read files from disk",
                tier=ToolTier.GLOBAL, granted_by=[], security_level="standard"
            ),
            ToolDefinition(
                id="write", name="Write", description="Write files to disk",
                tier=ToolTier.GLOBAL, granted_by=[], security_level="standard"
            ),
            ToolDefinition(
                id="edit", name="Edit", description="Edit files in place",
                tier=ToolTier.GLOBAL, granted_by=[], security_level="standard"
            ),
            ToolDefinition(
                id="bash", name="Bash", description="Execute bash commands",
                tier=ToolTier.GLOBAL, granted_by=[], security_level="standard"
            ),
            ToolDefinition(
                id="glob", name="Glob", description="Find files by pattern",
                tier=ToolTier.GLOBAL, granted_by=[], security_level="standard"
            ),
            ToolDefinition(
                id="grep", name="Grep", description="Search file contents",
                tier=ToolTier.GLOBAL, granted_by=[], security_level="standard"
            ),
        ]
        for tool in global_tools:
            self.tools[tool.id] = tool

    def _load_specialized_tools(self) -> None:
        """Load specialized tool definitions from YAML file.

        Specialized tools have explicit definitions with required_labels
        for two-tier authorization (skill grants + compute capability).
        """
        tools_file = self.skills_path.parent / "tools" / "specialized.yaml"
        if not tools_file.exists():
            logger.debug("No specialized tools file found at %s", tools_file)
            return

        try:
            with open(tools_file, "r") as f:
                data = yaml.safe_load(f)

            if data is None or "tools" not in data:
                return

            for tool_data in data["tools"]:
                tool = ToolDefinition(
                    id=tool_data["id"],
                    name=tool_data["name"],
                    description=tool_data["description"],
                    tier=ToolTier.SPECIALIZED,
                    granted_by=tool_data.get("granted_by", []),
                    required_labels=tool_data.get("required_labels", []),
                    security_level=tool_data.get("security_level", "elevated")
                )
                self.tools[tool.id] = tool
                logger.debug(f"Loaded specialized tool: {tool.id}")

            logger.info(f"Loaded {len(data['tools'])} specialized tools from {tools_file}")
        except Exception as e:
            logger.error(f"Failed to load specialized tools from {tools_file}: {e}")

    async def _load_skills_from_directory(self, directory: Path, author_prefix: str) -> None:
        """Load skill definitions from a local directory."""
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

                # Set marketplace source fields
                data["marketplace_id"] = self._marketplace_id
                data["marketplace_name"] = self._marketplace_name
                # System skills get root tier, others inherit marketplace tier
                if author_prefix == "system":
                    data["marketplace_tier"] = MarketplaceTier.ROOT
                else:
                    data["marketplace_tier"] = self._marketplace_tier or MarketplaceTier.EXTENDED

                # Apply namespace for non-ROOT skills when configured
                if self._namespace and author_prefix != "system":
                    data["namespace"] = self._namespace
                    # Store under namespaced key to prevent flat-dict collisions
                    original_id = data.get("id", "")
                    if original_id and ":" not in original_id:
                        namespaced_id = f"{self._namespace}:{original_id}"
                        data["id"] = namespaced_id

                skill = Skill(**data)
                self.skills[skill.id] = skill
                self._register_skill_tools(skill)

                logger.debug(f"Loaded skill: {skill.id}")
            except Exception as e:
                logger.error(f"Failed to load skill from {file_path}: {e}")

    async def _load_user_skills_from_git(self) -> None:
        """Load user skills from Git storage."""
        if not self._git_storage:
            return

        # List all YAML files in skills/user directory
        skill_files = self._git_storage.list_files("skills/user", "*.yaml")

        for file_path in skill_files:
            try:
                relative_path = f"skills/user/{file_path.name}"
                content = self._git_storage.load_yaml(relative_path)

                if content is None:
                    continue

                data = yaml.safe_load(content)
                if data is None:
                    continue

                # Ensure user author prefix
                if "author" not in data or not data["author"].startswith("user:"):
                    data["author"] = "user:unknown"

                # Set marketplace source fields
                data["marketplace_id"] = self._marketplace_id
                data["marketplace_name"] = self._marketplace_name
                data["marketplace_tier"] = self._marketplace_tier or MarketplaceTier.EXTENDED

                # Apply namespace for non-ROOT user skills
                if self._namespace:
                    data["namespace"] = self._namespace
                    original_id = data.get("id", "")
                    if original_id and ":" not in original_id:
                        data["id"] = f"{self._namespace}:{original_id}"

                skill = Skill(**data)
                self.skills[skill.id] = skill
                self._register_skill_tools(skill)

                logger.debug(f"Loaded user skill from Git: {skill.id}")
            except Exception as e:
                logger.error(f"Failed to load skill from Git {file_path}: {e}")

    def _register_skill_tools(self, skill: Skill) -> None:
        """Register specialized tools granted by a skill."""
        for tool_id in skill.specialized_tools:
            if tool_id not in self.tools:
                self.tools[tool_id] = ToolDefinition(
                    id=tool_id,
                    name=tool_id.replace("_", " ").title(),
                    description=f"Specialized tool from {skill.id}",
                    tier=ToolTier.SPECIALIZED,
                    granted_by=[skill.id],
                    security_level="elevated"
                )
            else:
                if skill.id not in self.tools[tool_id].granted_by:
                    self.tools[tool_id].granted_by.append(skill.id)

    def _skill_to_yaml(self, skill: Skill) -> str:
        """Convert a skill to YAML string."""
        data = {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "author": skill.author,
            "instructions": skill.instructions,
            "specialized_tools": skill.specialized_tools,
            "tags": skill.tags,
            "conflicts_with": skill.conflicts_with,
            "constraints": skill.constraints,
            "dependencies": skill.dependencies,
        }
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def _get_skill_git_path(self, skill_id: str) -> str:
        """Get the Git path for a user skill."""
        return f"skills/user/{skill_id}.yaml"

    def list_skill_versions(self, skill_id: str) -> List[SkillVersion]:
        """List all versions of a skill (newest first).

        Uses Git history for user skills.
        """
        skill = self.skills.get(skill_id)
        if not skill:
            return []

        # System skills don't have Git-backed versioning
        if skill.author == "system":
            return []

        # Use Git history for user skills
        if not self._git_storage:
            return []

        relative_path = self._get_skill_git_path(skill_id)
        history = self._git_storage.get_file_history(relative_path)

        versions = []
        for entry in history:
            # Parse version from commit message (format: "create: skill-id v1.0.0" or "update: skill-id v1.1.0")
            message = entry.get("message", "")
            version_match = re.search(r'v(\d+\.\d+\.\d+)', message)
            version_str = version_match.group(1) if version_match else "unknown"

            # Extract changelog from commit message (after the skill ID)
            changelog = None
            if " - " in message:
                changelog = message.split(" - ", 1)[1]

            # Get the skill content at this commit
            content = self._git_storage.get_file_at_commit(relative_path, entry["commit"])
            if content:
                try:
                    data = yaml.safe_load(content)
                    version_entry = SkillVersion(
                        skill_id=skill_id,
                        version=data.get("version", version_str),
                        instructions=data.get("instructions", ""),
                        specialized_tools=data.get("specialized_tools", []),
                        changelog=changelog,
                        created_at=datetime.fromisoformat(entry["timestamp"])
                    )
                    versions.append(version_entry)
                except Exception as e:
                    logger.warning(f"Failed to parse skill version at {entry['commit']}: {e}")

        return versions

    def get_skill_version(self, skill_id: str, version: str) -> Optional[Skill]:
        """Get a specific version of a skill.

        Uses Git history for user skills.
        """
        skill = self.skills.get(skill_id)
        if not skill:
            return None

        # System skills don't have Git-backed versioning
        if skill.author == "system":
            return skill if skill.version == version else None

        # Use Git history for user skills
        if not self._git_storage:
            return skill if skill.version == version else None

        relative_path = self._get_skill_git_path(skill_id)
        history = self._git_storage.get_file_history(relative_path)

        for entry in history:
            content = self._git_storage.get_file_at_commit(relative_path, entry["commit"])
            if content:
                try:
                    data = yaml.safe_load(content)
                    if data.get("version") == version:
                        return Skill(
                            id=data["id"],
                            name=data["name"],
                            description=data["description"],
                            version=data["version"],
                            author=data.get("author", "user:unknown"),
                            instructions=data["instructions"],
                            specialized_tools=data.get("specialized_tools", []),
                            tags=data.get("tags", []),
                            conflicts_with=data.get("conflicts_with", []),
                            constraints=data.get("constraints", []),
                            dependencies=data.get("dependencies", []),
                            created_at=skill.created_at,
                            updated_at=datetime.fromisoformat(entry["timestamp"])
                        )
                except Exception as e:
                    logger.warning(f"Failed to parse skill version at {entry['commit']}: {e}")

        return None

    def list_skills(
        self,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None
    ) -> List[Skill]:
        """List skills with optional filtering."""
        result = list(self.skills.values())

        if tags:
            result = [s for s in result if any(t in s.tags for t in tags)]

        if author:
            result = [s for s in result if s.author == author or s.author.startswith(f"{author}:")]

        return result

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a skill by ID, supporting both namespaced and bare lookups.

        Lookup order:
        1. Exact match (e.g., "acme:code-writer" or "code-writer")
        2. If bare ID and namespace is configured, try "namespace:skill_id"
        3. If namespaced ID, try the bare part as fallback

        Args:
            skill_id: Skill ID, optionally namespace-qualified (e.g., "acme:code-writer")

        Returns:
            Matching Skill or None
        """
        # 1. Exact match
        skill = self.skills.get(skill_id)
        if skill is not None:
            return skill

        # 2. Bare ID → try with namespace prefix
        if ":" not in skill_id and self._namespace:
            namespaced = f"{self._namespace}:{skill_id}"
            skill = self.skills.get(namespaced)
            if skill is not None:
                return skill

        # 3. Namespaced ID → try bare part as fallback
        if ":" in skill_id:
            _, bare_id = skill_id.split(":", 1)
            return self.skills.get(bare_id)

        return None

    def search_by_capabilities(self, capabilities: List[str]) -> List[Skill]:
        """Search skills that match required capabilities (tags)."""
        result = []
        for skill in self.skills.values():
            # Check if skill tags match any required capability
            if any(cap in skill.tags for cap in capabilities):
                result.append(skill)
        return result

    def search_by_capabilities_with_fallback(
        self,
        capabilities: List[str],
        default_skill_id: str = "code-writer",
        max_results: int = 5,
    ) -> List[Skill]:
        """Search skills with tiered fallback matching.

        Implements a multi-tier search strategy:
        1. Exact tag match (capability exactly in skill.tags)
        2. Partial tag match (capability is substring of tag or vice versa)
        3. Token-based match (any word in capability matches any word in tag)
        4. Default fallback if all else fails

        Args:
            capabilities: List of required capability strings to match
            default_skill_id: ID of skill to return as fallback
            max_results: Maximum number of skills to return

        Returns:
            List of matching skills, sorted by relevance score
        """
        if not capabilities:
            # No capabilities requested - return default
            default = self.get_skill(default_skill_id)
            return [default] if default else []

        # Normalize capabilities for matching
        normalized_caps = [cap.lower().strip() for cap in capabilities]

        # Calculate match scores for all skills
        scored_skills: List[tuple] = []

        for skill in self.skills.values():
            score = self._calculate_match_score(skill, normalized_caps)
            if score > 0:
                scored_skills.append((skill, score))

        # Sort by score (descending)
        scored_skills.sort(key=lambda x: x[1], reverse=True)

        if scored_skills:
            return [skill for skill, _ in scored_skills[:max_results]]

        # Fallback: return default skill
        default = self.get_skill(default_skill_id)
        return [default] if default else []

    def _calculate_match_score(
        self,
        skill: Skill,
        normalized_caps: List[str],
    ) -> float:
        """Calculate match score between a skill and capabilities.

        Scoring weights:
        - Exact match: 10 points per tag
        - Partial match (substring): 5 points per tag
        - Token match (word overlap): 2 points per matching word

        Args:
            skill: The skill to score
            normalized_caps: Normalized (lowercase) capability strings

        Returns:
            Total match score (0 if no match)
        """
        score = 0.0
        normalized_tags = [tag.lower().strip() for tag in skill.tags]

        for cap in normalized_caps:
            cap_tokens = set(self._tokenize(cap))

            for tag in normalized_tags:
                # Tier 1: Exact match
                if cap == tag:
                    score += 10.0
                    continue

                # Tier 2: Partial match (substring)
                if cap in tag or tag in cap:
                    score += 5.0
                    continue

                # Tier 3: Token overlap
                tag_tokens = set(self._tokenize(tag))
                overlap = cap_tokens & tag_tokens
                if overlap:
                    # Score based on proportion of matching tokens
                    score += 2.0 * len(overlap) / max(len(cap_tokens), len(tag_tokens))

        return score

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words for matching.

        Splits on common delimiters: hyphen, underscore, space.

        Args:
            text: Text to tokenize

        Returns:
            List of word tokens
        """
        # Split on hyphens, underscores, spaces, and camelCase
        tokens = re.split(r'[-_\s]+', text.lower())
        # Filter out empty tokens
        return [t for t in tokens if t]

    async def create_skill(self, request: SkillCreateRequest, author: str = "user") -> Skill:
        """Create a new skill.

        User skills are stored in Git for durability.
        System skills are stored in local filesystem.
        """
        if request.id in self.skills:
            raise ValueError(f"Skill {request.id} already exists")

        # Determine marketplace tier based on author
        if author == "system":
            tier = MarketplaceTier.ROOT
        else:
            tier = self._marketplace_tier or MarketplaceTier.EXTENDED

        skill = Skill(
            id=request.id,
            name=request.name,
            description=request.description,
            instructions=request.instructions,
            specialized_tools=request.specialized_tools,
            tags=request.tags,
            conflicts_with=request.conflicts_with,
            constraints=request.constraints,
            dependencies=request.dependencies,
            version=request.version,
            author=author if author == "system" else f"user:{author}",
            marketplace_id=self._marketplace_id,
            marketplace_name=self._marketplace_name,
            marketplace_tier=tier,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # Save to appropriate storage
        if author == "system":
            # System skills go to local filesystem
            file_path = self.skills_path / "system" / f"{skill.id}.yaml"
            await self._save_skill_to_file(skill, file_path)
        elif self._git_storage:
            # User skills go to Git storage
            relative_path = self._get_skill_git_path(skill.id)
            content = self._skill_to_yaml(skill)
            self._git_storage.save_yaml(
                relative_path,
                content,
                f"create: {skill.id} v{skill.version} - Initial version"
            )
        else:
            # Fallback to local filesystem
            file_path = self.skills_path / "user" / f"{skill.id}.yaml"
            await self._save_skill_to_file(skill, file_path)

        self.skills[skill.id] = skill
        self._register_skill_tools(skill)

        logger.info(f"Created skill: {skill.id}")
        return skill

    async def update_skill(self, skill_id: str, request: SkillUpdateRequest) -> Optional[Skill]:
        """Update an existing skill.

        When a skill is updated, any personas that reference it are automatically
        marked as stale. Their merged_instructions will be regenerated lazily
        on the next retrieval via get_persona().
        """
        skill = self.skills.get(skill_id)
        if not skill:
            return None

        # Extract changelog before processing other fields
        changelog = request.changelog

        # Track if version changed for version history
        old_version = skill.version

        # Track if instruction-affecting fields changed (for persona invalidation)
        update_data = request.model_dump(exclude_unset=True, exclude={"changelog"})
        instruction_fields = {'instructions', 'constraints', 'name'}
        affects_instructions = any(key in instruction_fields for key in update_data.keys())

        # Update fields that were provided (excluding changelog which is not a skill field)
        for key, value in update_data.items():
            if value is not None:
                setattr(skill, key, value)

        skill.updated_at = datetime.now(timezone.utc)

        # Save to appropriate storage
        if skill.author == "system":
            # System skills go to local filesystem
            file_path = self.skills_path / "system" / f"{skill.id}.yaml"
            await self._save_skill_to_file(skill, file_path)
        elif self._git_storage:
            # User skills go to Git storage
            relative_path = self._get_skill_git_path(skill.id)
            content = self._skill_to_yaml(skill)
            commit_msg = f"update: {skill.id} v{skill.version}"
            if changelog:
                commit_msg += f" - {changelog}"
            self._git_storage.save_yaml(relative_path, content, commit_msg)
        else:
            # Fallback to local filesystem
            file_path = self.skills_path / "user" / f"{skill.id}.yaml"
            await self._save_skill_to_file(skill, file_path)

        # Invalidate personas that reference this skill (if instruction-affecting fields changed)
        if affects_instructions and self._persona_registry:
            self._persona_registry.invalidate_personas_referencing_skill(skill_id)

        logger.info(f"Updated skill: {skill.id}")
        return skill

    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill."""
        skill = self.skills.get(skill_id)
        if not skill:
            return False

        # Don't allow deleting system skills
        if skill.author == "system":
            raise ValueError("Cannot delete system skills")

        # Delete from appropriate storage
        if self._git_storage:
            relative_path = self._get_skill_git_path(skill_id)
            self._git_storage.delete_file(
                relative_path,
                f"delete: {skill_id} - Skill removed"
            )
        else:
            # Fallback to local filesystem
            file_path = self.skills_path / "user" / f"{skill_id}.yaml"
            if file_path.exists():
                file_path.unlink()

        del self.skills[skill_id]
        logger.info(f"Deleted skill: {skill_id}")
        return True

    async def _save_skill_to_file(self, skill: Skill, file_path: Path) -> None:
        """Save a skill to a local YAML file (for system skills or fallback mode)."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(self._skill_to_yaml(skill))

    def list_tools(self, tier: Optional[ToolTier] = None) -> List[ToolDefinition]:
        """List tools with optional tier filter."""
        result = list(self.tools.values())
        if tier:
            result = [t for t in result if t.tier == tier]
        return result

    def get_tool(self, tool_id: str) -> Optional[ToolDefinition]:
        """Get a tool by ID."""
        return self.tools.get(tool_id)

    def get_global_tools(self) -> List[str]:
        """Get list of global tool IDs."""
        return [t.id for t in self.tools.values() if t.tier == ToolTier.GLOBAL]

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        by_author = {}
        for skill in self.skills.values():
            author_type = "system" if skill.author == "system" else "user"
            by_author[author_type] = by_author.get(author_type, 0) + 1

        return {
            "total_skills": len(self.skills),
            "total_tools": len(self.tools),
            "global_tools": len([t for t in self.tools.values() if t.tier == ToolTier.GLOBAL]),
            "specialized_tools": len([t for t in self.tools.values() if t.tier == ToolTier.SPECIALIZED]),
            "by_author": by_author,
            "git_backed": self._git_storage is not None
        }
