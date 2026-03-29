---
name: Small composable Python files
description: User prefers small, composable Python files over large monolithic service files
type: feedback
---

Break apart large Python service files into smaller, composable modules that work together. Don't create 1 large file — prefer multiple focused files composed as needed.

**Why:** The existing codebase has many oversized service files (1,000-1,800+ lines). User wants the v2.0 architecture to avoid this pattern.

**How to apply:** When building or refactoring services (especially the decomposer in v2.0), split into focused modules by responsibility. Each file should do one thing well and compose with others.
