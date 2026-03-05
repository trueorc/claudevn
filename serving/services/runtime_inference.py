"""Keyword-based runtime tool inference from work item text.

Provides a lightweight fallback for inferring required runtime tools from
issue titles and descriptions. Only matches when the text implies the task
needs to **execute** a dev tool (scaffolding, building, installing deps,
running tests). Does NOT match generic language/framework mentions — writing
code in React or Flask does not require the runtime on the compute.

When ambiguous, returns empty — the capability gap detection (#140) handles
missing capabilities at execution time.
"""

import re
from typing import List

# ── Keyword → runtime mapping ────────────────────────────────────────────────
# Each entry: (set of keywords, runtime tool label)
# Matching is case-insensitive against concatenated title + description.
# IMPORTANT: Only include keywords that imply the task must EXECUTE the
# runtime (scaffold, build, install, test, run). Do NOT include framework
# or library names (react, express, django, flask) — writing code in those
# frameworks does not require the runtime.

_RUNTIME_RULES = [
    # Node.js / JavaScript ecosystem — execution-specific terms only
    (
        {"npm install", "npm run", "npm test", "npm start", "npm build",
         "npx", "create-react-app", "yarn install", "yarn build",
         "pnpm install", "pnpm build", "bun install", "bun run",
         "package.json"},
        "runtime:node",
    ),
    # Python ecosystem — execution-specific terms only
    (
        {"pip install", "requirements.txt", "pytest", "python -m",
         "python script", "poetry install", "uvicorn", "manage.py",
         "django-admin"},
        "runtime:python",
    ),
    # Go ecosystem — execution-specific terms only
    (
        {"go build", "go test", "go run", "go mod", "go.mod",
         "go install"},
        "runtime:go",
    ),
    # Rust ecosystem — execution-specific terms only
    (
        {"cargo build", "cargo test", "cargo run", "cargo.toml",
         "rustc"},
        "runtime:rust",
    ),
    # Java ecosystem — execution-specific terms only
    (
        {"mvn", "maven", "gradle build", "gradle test",
         "pom.xml", "build.gradle"},
        "runtime:java",
    ),
]


def infer_runtime_tools(title: str, description: str) -> List[str]:
    """Infer required runtime tools from issue title and description.

    Uses keyword matching against known runtime ecosystems.
    Returns an empty list when the text is ambiguous.

    Args:
        title: Issue title
        description: Issue description

    Returns:
        List of runtime tool labels (e.g., ["runtime:node"])
    """
    text = f"{title} {description}".lower()
    tools = []

    for keywords, runtime in _RUNTIME_RULES:
        for kw in keywords:
            # Word-boundary matching for all keywords to avoid false positives
            # (e.g., "go mod" must not match "go model")
            if re.search(rf"\b{re.escape(kw)}\b", text):
                tools.append(runtime)
                break

    return tools
