"""Keyword-based runtime tool inference from work item text.

Provides a lightweight fallback for inferring required runtime tools from
issue titles and descriptions. Used alongside LLM-based inference during
goal decomposition. When ambiguous, returns empty — the capability gap
detection (#140) handles missing capabilities at execution time.
"""

import re
from typing import List

# ── Keyword → runtime mapping ────────────────────────────────────────────────
# Each entry: (set of keywords, runtime tool label)
# Matching is case-insensitive against concatenated title + description.
# Only match when keywords are strong indicators — avoid false positives.

_RUNTIME_RULES = [
    # Node.js / JavaScript ecosystem
    (
        {"react", "vite", "next.js", "nextjs", "express", "npm", "npx",
         "node.js", "nodejs", "webpack", "eslint", "jest", "tsx", "jsx",
         "package.json", "yarn", "pnpm", "bun"},
        "runtime:node",
    ),
    # Python ecosystem
    (
        {"django", "flask", "fastapi", "pip install", "requirements.txt",
         "python script", "pytest", "poetry", "uvicorn", "celery",
         "pandas", "numpy", "sqlalchemy"},
        "runtime:python",
    ),
    # Go ecosystem
    (
        {"go module", "go build", "go test", "go.mod", "golang",
         "go binary", "go run"},
        "runtime:go",
    ),
    # Rust ecosystem
    (
        {"cargo", "rustc", "rust", "crate", "cargo.toml"},
        "runtime:rust",
    ),
    # Java ecosystem
    (
        {"maven", "gradle", "spring boot", "java", "jvm",
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
            # Use word-boundary-aware matching for short keywords
            if len(kw) <= 4:
                # Short keywords need word boundaries to avoid false matches
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    tools.append(runtime)
                    break
            else:
                if kw in text:
                    tools.append(runtime)
                    break

    return tools
