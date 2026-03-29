"""Environment analyzer — detects runtime requirements from work units and codebase.

Runs during Layer 1 planning. Examines target files, existing config files
(package.json, pyproject.toml, go.mod, Cargo.toml, etc.), and work unit
descriptions to determine what the compute environment needs.

Produces a ComputeEnvironmentSpec with a generated Dockerfile for human review.
"""

import logging
import os
import json
from typing import Dict, List, Optional, Set, Tuple

from models.work_unit.compute_environment import (
    ComputeEnvironmentSpec,
    RuntimeRequirement,
)
from models.work_unit.work_unit import WorkUnit
from .goal_analyzer import CodebaseAnalysis

logger = logging.getLogger(__name__)


# Config file → runtime mapping
_CONFIG_DETECTORS = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "requirements.txt": "python",
    "Pipfile": "python",
    "package.json": "node",
    "yarn.lock": "node",
    "pnpm-lock.yaml": "node",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "Gemfile": "ruby",
    "composer.json": "php",
    "build.gradle": "java",
    "pom.xml": "java",
}

# File extension → runtime
_EXTENSION_RUNTIMES = {
    ".py": "python",
    ".js": "node",
    ".jsx": "node",
    ".ts": "node",
    ".tsx": "node",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "dotnet",
}

# Runtime → base Docker image (keep current as of 2026)
_BASE_IMAGES = {
    "python": "python:3.13-slim",
    "node": "node:22-slim",
    "go": "golang:1.24-bookworm",
    "rust": "rust:1.85-slim",
    "ruby": "ruby:3.4-slim",
    "multi": "ubuntu:24.04",
}

# Runtime → common tools to detect
_TOOL_DETECTORS = {
    "python": [
        ("pytest", "pip install pytest"),
        ("ruff", "pip install ruff"),
        ("mypy", "pip install mypy"),
        ("black", "pip install black"),
    ],
    "node": [
        ("jest", "npm install -g jest"),
        ("vitest", "npm install -g vitest"),
        ("eslint", "npm install -g eslint"),
        ("typescript", "npm install -g typescript"),
        ("vite", "npm install -g vite"),
    ],
    "go": [
        ("golangci-lint", "go install github.com/golangci-lint/golangci-lint/cmd/golangci-lint@latest"),
    ],
}


class EnvironmentAnalyzer:
    """Analyzes work units and codebase to produce compute environment specs.

    Called during Layer 1 planning after work units are produced.
    Examines target files, project config files, and dependencies
    to determine what the execution environment needs.
    """

    def __init__(self, repo_path: str):
        self._repo_path = repo_path

    def analyze(
        self,
        work_units: List[WorkUnit],
        codebase: Optional[CodebaseAnalysis] = None,
        project_id: str = "",
        spec_id: str = "",
    ) -> ComputeEnvironmentSpec:
        """Analyze work units and produce a compute environment spec.

        Args:
            work_units: Work units that need an execution environment.
            codebase: Optional codebase analysis for richer detection.
            project_id: Project ID for the spec.
            spec_id: Unique spec ID.

        Returns:
            ComputeEnvironmentSpec with detected requirements and Dockerfile.
        """
        requirements = []
        runtimes_needed: Set[str] = set()

        # Detect runtimes from target files
        for unit in work_units:
            for filepath in unit.formal_spec.target_files:
                ext = os.path.splitext(filepath)[1].lower()
                runtime = _EXTENSION_RUNTIMES.get(ext)
                if runtime:
                    runtimes_needed.add(runtime)

        # Detect runtimes from config files in repo
        config_runtimes = self._detect_from_config_files()
        runtimes_needed.update(config_runtimes.keys())

        # Build requirements list
        for runtime in sorted(runtimes_needed):
            version = self._detect_version(runtime, config_runtimes.get(runtime))
            requirements.append(RuntimeRequirement(
                name=runtime,
                version=version,
                reason=f"Detected from target files and project config",
            ))

            # Detect tools for this runtime
            tool_reqs = self._detect_tools(runtime)
            requirements.extend(tool_reqs)

        # Detect package install requirements
        pkg_reqs = self._detect_package_installs(runtimes_needed)
        requirements.extend(pkg_reqs)

        # Choose base image
        if len(runtimes_needed) > 1:
            base_image = _BASE_IMAGES["multi"]
        elif len(runtimes_needed) == 1:
            base_image = _BASE_IMAGES.get(next(iter(runtimes_needed)), "ubuntu:22.04")
        else:
            base_image = "ubuntu:22.04"

        # Generate Dockerfile
        dockerfile = self._generate_dockerfile(base_image, runtimes_needed, requirements)

        return ComputeEnvironmentSpec(
            id=spec_id or f"env-{project_id}",
            project_id=project_id,
            requirements=requirements,
            base_image=base_image,
            dockerfile_content=dockerfile,
            work_unit_ids=[u.id for u in work_units],
        )

    def _detect_from_config_files(self) -> Dict[str, Optional[str]]:
        """Detect runtimes from config files present in the repo.

        Searches both the repo root and immediate subdirectories
        to find nested config files (e.g., serving/requirements.txt).
        """
        found = {}
        # Check root
        for config_file, runtime in _CONFIG_DETECTORS.items():
            path = os.path.join(self._repo_path, config_file)
            if os.path.exists(path):
                found[runtime] = path

        # Check one level of subdirectories
        try:
            for entry in os.scandir(self._repo_path):
                if entry.is_dir() and not entry.name.startswith('.'):
                    for config_file, runtime in _CONFIG_DETECTORS.items():
                        path = os.path.join(entry.path, config_file)
                        if os.path.exists(path) and runtime not in found:
                            found[runtime] = path
                        # Also check one more level (e.g., serving/frontend/package.json)
                        try:
                            for sub_entry in os.scandir(entry.path):
                                if sub_entry.is_dir() and not sub_entry.name.startswith('.'):
                                    path = os.path.join(sub_entry.path, config_file)
                                    if os.path.exists(path) and runtime not in found:
                                        found[runtime] = path
                        except OSError:
                            pass
        except OSError:
            pass

        return found

    def _detect_version(self, runtime: str, config_path: Optional[str]) -> Optional[str]:
        """Try to detect the required version from config files."""
        if not config_path or not os.path.exists(config_path):
            return None

        try:
            if runtime == "python" and config_path.endswith("pyproject.toml"):
                content = open(config_path).read()
                # Look for requires-python
                for line in content.split("\n"):
                    if "requires-python" in line and ">=" in line:
                        # Extract version like ">=3.10"
                        parts = line.split(">=")
                        if len(parts) > 1:
                            return parts[1].strip().strip('"').strip("'")

            if runtime == "node" and config_path.endswith("package.json"):
                data = json.loads(open(config_path).read())
                engines = data.get("engines", {})
                if "node" in engines:
                    return engines["node"]

        except Exception:
            pass

        return None

    def _detect_tools(self, runtime: str) -> List[RuntimeRequirement]:
        """Detect which tools are used for a runtime based on config files.

        Only emits install commands for tools that need global installation.
        Tools in package.json devDependencies are installed by npm install
        (the package install step), so they're listed as requirements for
        visibility but without a separate install command.
        """
        requirements = []
        detectors = _TOOL_DETECTORS.get(runtime, [])

        for tool_name, install_cmd in detectors:
            if self._tool_is_used(runtime, tool_name):
                # Check if this tool is a project dependency (installed by npm install)
                is_project_dep = self._is_project_dependency(runtime, tool_name)
                requirements.append(RuntimeRequirement(
                    name=tool_name,
                    reason="Project devDependency (installed by npm install)" if is_project_dep else "Detected in project configuration",
                    install_cmd=None if is_project_dep else install_cmd,
                ))

        return requirements

    def _is_project_dependency(self, runtime: str, tool_name: str) -> bool:
        """Check if a tool is already a project dependency (not needing global install)."""
        if runtime == "node":
            pkg_path = self._find_file("package.json")
            if pkg_path:
                try:
                    data = json.loads(open(pkg_path).read())
                    all_deps = {
                        **data.get("dependencies", {}),
                        **data.get("devDependencies", {}),
                    }
                    return tool_name in all_deps
                except Exception:
                    pass
        if runtime == "python":
            req_path = self._find_file("requirements.txt")
            if req_path:
                try:
                    return tool_name in open(req_path).read()
                except Exception:
                    pass
        return False

    def _find_file(self, filename: str) -> Optional[str]:
        """Find a file in the repo root or up to 2 levels deep."""
        root = os.path.join(self._repo_path, filename)
        if os.path.exists(root):
            return root
        try:
            for entry in os.scandir(self._repo_path):
                if entry.is_dir() and not entry.name.startswith('.'):
                    path = os.path.join(entry.path, filename)
                    if os.path.exists(path):
                        return path
                    try:
                        for sub in os.scandir(entry.path):
                            if sub.is_dir() and not sub.name.startswith('.'):
                                path = os.path.join(sub.path, filename)
                                if os.path.exists(path):
                                    return path
                    except OSError:
                        pass
        except OSError:
            pass
        return None

    def _tool_is_used(self, runtime: str, tool_name: str) -> bool:
        """Check if a tool is referenced in project config."""
        if runtime == "python":
            pyproject = self._find_file("pyproject.toml")
            if pyproject:
                try:
                    if tool_name in open(pyproject).read():
                        return True
                except Exception:
                    pass
            for req_file in ["requirements.txt", "requirements-dev.txt"]:
                req_path = self._find_file(req_file)
                if req_path:
                    try:
                        if tool_name in open(req_path).read():
                            return True
                    except Exception:
                        pass

        if runtime == "node":
            pkg_path = self._find_file("package.json")
            if pkg_path:
                try:
                    data = json.loads(open(pkg_path).read())
                    all_deps = {
                        **data.get("dependencies", {}),
                        **data.get("devDependencies", {}),
                    }
                    if tool_name in all_deps:
                        return True
                except Exception:
                    pass

        return False

    def _detect_package_installs(self, runtimes: Set[str]) -> List[RuntimeRequirement]:
        """Detect project package managers — listed for visibility only.

        Project dependencies are installed at runtime when the compute
        clones the repo, NOT baked into the Docker image. The image
        only provides the runtime and global tools.
        """
        requirements = []

        if "python" in runtimes:
            req_path = self._find_file("requirements.txt")
            if req_path:
                rel = os.path.relpath(req_path, self._repo_path)
                requirements.append(RuntimeRequirement(
                    name="python-packages",
                    reason=f"{rel} — installed at runtime after repo clone",
                    install_cmd=None,  # Not a build-time command
                ))

        if "node" in runtimes:
            pkg_path = self._find_file("package.json")
            if pkg_path:
                pkg_dir = os.path.relpath(os.path.dirname(pkg_path), self._repo_path)
                requirements.append(RuntimeRequirement(
                    name="node-packages",
                    reason=f"{pkg_dir}/package.json — installed at runtime after repo clone",
                    install_cmd=None,  # Not a build-time command
                ))

        return requirements

    def _generate_dockerfile(
        self,
        base_image: str,
        runtimes: Set[str],
        requirements: List[RuntimeRequirement],
    ) -> str:
        """Generate a Dockerfile extending the compute base image.

        Builds on top of the ClaudeVN compute infrastructure image which
        provides: Python runtime, compute engine (SSE client), entrypoint
        with credential provisioning, Claude CLI, and the MCP server.

        This Dockerfile adds project-specific runtimes and tools on top.
        """
        lines = [
            "# Generated by ClaudeVN Layer 1 planning",
            "# Extends compute base with project-specific runtimes",
            "# Base provides: Python, compute SSE engine, Claude CLI, MCP, entrypoint",
            "",
            "FROM claudevn-compute-base",
            "",
            "# Install as root — entrypoint handles drop to compute user via gosu",
            "",
        ]

        # Additional runtimes beyond what the base image provides
        extra_packages = []
        if "node" in runtimes:
            # Base has Python; add Node.js 22 LTS
            lines.extend([
                "# Node.js 22 LTS via nodesource",
                "RUN apt-get update && apt-get install -y gnupg \\",
                "    && mkdir -p /etc/apt/keyrings \\",
                "    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \\",
                '    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \\',
                "    && apt-get update && apt-get install -y nodejs \\",
                "    && rm -rf /var/lib/apt/lists/*",
                "",
            ])
        if "go" in runtimes:
            extra_packages.append("golang")
        if "rust" in runtimes:
            lines.extend([
                "# Rust toolchain",
                "RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                'ENV PATH="/root/.cargo/bin:${PATH}"',
                "",
            ])
        if extra_packages:
            lines.append(f"RUN apt-get update && apt-get install -y {' '.join(extra_packages)} && rm -rf /var/lib/apt/lists/*")
            lines.append("")

        # Global tools only (not project devDependencies)
        global_cmds = [r.install_cmd for r in requirements if r.install_cmd]
        if global_cmds:
            lines.append("# Additional global tools")
            for cmd in global_cmds:
                lines.append(f"RUN {cmd}")
            lines.append("")

        # No USER or CMD override — inherited from base:
        # ENTRYPOINT ["/app/entrypoint.sh"] (runs as root, drops to compute via gosu)
        # CMD ["python", "app.py"] (compute SSE engine)

        return "\n".join(lines)
