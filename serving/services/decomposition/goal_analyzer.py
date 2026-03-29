"""Goal analyzer — programmatic codebase analysis for decomposition.

Performs static analysis of the repository to inform decomposition:
file tree, dependency graph, module boundaries, interface definitions,
test coverage. This is computational analysis, not LLM exploration.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Metadata about a single file in the repository."""
    path: str
    size_bytes: int
    extension: str
    module: str = ""  # Inferred module/package this belongs to


@dataclass
class ModuleBoundary:
    """A detected module boundary in the codebase."""
    name: str
    root_path: str
    files: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    imports_from: List[str] = field(default_factory=list)


@dataclass
class CodebaseAnalysis:
    """Result of analyzing a codebase for decomposition.

    This is purely computational — no LLM involved. Provides the
    structural foundation that the LLM-assisted scope identification
    builds on.
    """
    file_tree: List[FileInfo] = field(default_factory=list)
    modules: List[ModuleBoundary] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0


# Common patterns for identifying module boundaries
_MODULE_MARKERS = {
    "python": ["__init__.py", "setup.py", "pyproject.toml"],
    "javascript": ["package.json", "index.js", "index.ts"],
    "go": ["go.mod"],
}

# File extensions to include in analysis
_CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
}

_TEST_PATTERNS = {"test_", "_test.", ".test.", ".spec.", "tests/", "test/", "__tests__/"}
_CONFIG_PATTERNS = {
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".json", ".env",
    "Dockerfile", "Makefile", ".gitignore", "requirements.txt",
}


class GoalAnalyzer:
    """Analyzes a codebase to provide structured input for decomposition.

    Does not use LLMs — this is purely programmatic analysis. The output
    feeds into the LLM-assisted scope identification step.
    """

    def __init__(self, repo_path: str):
        self._repo_path = Path(repo_path)

    async def analyze(
        self,
        max_files: int = 5000,
        exclude_dirs: Optional[Set[str]] = None,
    ) -> CodebaseAnalysis:
        """Analyze the repository structure.

        Args:
            max_files: Safety limit on files to scan.
            exclude_dirs: Directory names to skip (defaults include
                .git, node_modules, __pycache__, .venv, etc.)

        Returns:
            CodebaseAnalysis with file tree, modules, and test files.
        """
        if exclude_dirs is None:
            exclude_dirs = {
                ".git", "node_modules", "__pycache__", ".venv", "venv",
                ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
                ".next", ".nuxt", "coverage", ".coverage",
            }

        analysis = CodebaseAnalysis()
        file_count = 0

        for root, dirs, files in os.walk(self._repo_path):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for filename in files:
                if file_count >= max_files:
                    break

                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, self._repo_path)
                ext = os.path.splitext(filename)[1].lower()

                try:
                    size = os.path.getsize(filepath)
                except OSError:
                    continue

                file_info = FileInfo(
                    path=rel_path,
                    size_bytes=size,
                    extension=ext,
                )

                # Classify the file
                if ext in _CODE_EXTENSIONS:
                    analysis.file_tree.append(file_info)
                    file_count += 1

                if self._is_test_file(rel_path, filename):
                    analysis.test_files.append(rel_path)

                if self._is_config_file(filename, ext):
                    analysis.config_files.append(rel_path)

            if file_count >= max_files:
                logger.warning(f"Hit max_files limit ({max_files}), analysis truncated")
                break

        analysis.total_files = len(analysis.file_tree)

        # Detect module boundaries
        analysis.modules = self._detect_modules(analysis.file_tree)

        # Assign files to modules
        for file_info in analysis.file_tree:
            file_info.module = self._classify_file_module(
                file_info.path, analysis.modules
            )

        logger.info(
            f"Codebase analysis complete: {analysis.total_files} code files, "
            f"{len(analysis.modules)} modules, {len(analysis.test_files)} test files"
        )

        return analysis

    def _is_test_file(self, rel_path: str, filename: str) -> bool:
        """Check if a file is a test file."""
        lower_path = rel_path.lower()
        lower_name = filename.lower()
        return any(pattern in lower_path or pattern in lower_name for pattern in _TEST_PATTERNS)

    def _is_config_file(self, filename: str, ext: str) -> bool:
        """Check if a file is a configuration file."""
        return ext in _CONFIG_PATTERNS or filename in _CONFIG_PATTERNS

    def _detect_modules(self, files: List[FileInfo]) -> List[ModuleBoundary]:
        """Detect module boundaries from file tree.

        Looks for standard module markers (e.g., __init__.py, package.json)
        to identify package/module boundaries.
        """
        modules: Dict[str, ModuleBoundary] = {}
        all_markers = set()
        for markers in _MODULE_MARKERS.values():
            all_markers.update(markers)

        for file_info in files:
            dirname = os.path.dirname(file_info.path)
            filename = os.path.basename(file_info.path)

            if filename in all_markers and dirname:
                if dirname not in modules:
                    modules[dirname] = ModuleBoundary(
                        name=dirname.replace(os.sep, "."),
                        root_path=dirname,
                    )
                modules[dirname].files.append(file_info.path)

        # Also add top-level directories as implicit modules
        top_dirs: Set[str] = set()
        for file_info in files:
            parts = file_info.path.split(os.sep)
            if len(parts) > 1:
                top_dirs.add(parts[0])

        for top_dir in top_dirs:
            if top_dir not in modules:
                modules[top_dir] = ModuleBoundary(
                    name=top_dir,
                    root_path=top_dir,
                )

        return list(modules.values())

    def _classify_file_module(
        self, file_path: str, modules: List[ModuleBoundary]
    ) -> str:
        """Determine which module a file belongs to."""
        # Find the longest matching module path
        best_match = ""
        for module in modules:
            if file_path.startswith(module.root_path + os.sep):
                if len(module.root_path) > len(best_match):
                    best_match = module.root_path
        return best_match or "(root)"
