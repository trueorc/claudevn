# Marketplace Module Audit

**Date:** 2026-02-28
**Type:** Standard Functional Audit
**Branch:** feat/backlog-buckets
**Result:** Pass with observations

---

## Executive Summary

The marketplace module is substantially implemented and the core skill distribution pipeline functions end-to-end. However, three meaningful gaps exist: (1) skill composition in the orchestrator bypasses the marketplace's `compose` endpoint and does a lightweight inline merge that omits dependency resolution and conflict checking; (2) the multi-marketplace skill resolution has no override or extension semantics — it is presence-based, not content-based; and (3) when the marketplace is unavailable, fallback personas are returned as skill-shaped dicts creating a silent type mismatch.

---

## Focus Areas

### 1. Skill Distribution to Compute

**Status:** Partially Working | **Severity:** High

**Pipeline Flow:**
1. `work_orchestrator.py:1015` — calls `_select_skills_for_work(work)` to get skill IDs
2. `work_orchestrator.py:1122` — calls `_compose_skills_for_sse(skills, compute_id)` which fetches each skill individually via `marketplace_client.get_skill()` and concatenates instructions with simple headers
3. `work_orchestrator.py:1179` — places result into SSE `work_assigned` event as `skills={"ids": skills, "merged_instructions": skills_content}`
4. `compute/services/sse_event_client.py:149` — passes event to `spawner.spawn(data)`
5. `compute/services/claude_code_spawner.py:970` — reads `skills.get("merged_instructions", "")` and writes into `CLAUDE.md`

**The pipeline is connected end-to-end — skills flow from marketplace through serving to compute.**

**Gaps Identified:**

| Gap | Description |
|-----|-------------|
| **A - Bypassed compose endpoint** | `_compose_skills_for_sse` (line 1230) manually fetches and concatenates skills inline. The marketplace's `POST /api/v1/skills/compose` endpoint (which provides dependency resolution, conflict detection, tool aggregation, structured CLAUDE.md) is never called. `marketplace_client.compose_agent()` exists but is unused. |
| **B - Dependency resolution skipped** | Because composition is inline, `CompositionService.resolve_dependencies()` (lines 52-95) is never invoked. Skills declaring `dependencies: [skill-b]` won't auto-include skill B. |
| **C - Conflict checking skipped** | `CompositionService.check_conflicts()` (lines 129-164) is never called during work assignment. Conflicting skill combinations pass through silently. |
| **D - Fallback type mismatch** | `marketplace_client.py:93` `_get_fallback_skill()` returns persona YAML dicts, not skill dicts. Fields like `specialized_tools` and `constraints` will be absent. |

---

### 2. Skill Merging / Composition

**Status:** Working (within the marketplace service itself) | **Severity:** Medium

**Working Components:**
- **Dependency resolution** (`resolve_dependencies`, lines 52-95): BFS traversal with transitive deps, no duplicates
- **Conflict detection** (`check_conflicts`, lines 129-164): Bidirectional `conflicts_with` checks, tool overlap advisory warnings
- **Instruction merging** (`merge_instructions`, lines 436-474): Structured CLAUDE.md with headers, context, per-skill sections, constraints
- **Tool aggregation** (`aggregate_tools`, lines 476-487): Global + specialized tool combination
- **Full compose** (`compose`, lines 567-628): Cached `Agent` objects with usage analytics

**Gaps Identified:**

| Gap | Description |
|-----|-------------|
| **A - No intelligent merging** | Spec describes contextual conflict resolution ("Prioritize rapid implementation for this prototype"). Actual implementation is simple concatenation. Documented design choice, but means Claude Code must self-reconcile conflicting instructions. |
| **B - Empty persona merged_instructions** | `fullstack-developer.yaml:40` and `orchestrator.yaml:47` have `merged_instructions: ""`. Lazy regeneration on `get_persona()` works, but cold-start edge case could deliver empty instructions. |
| **C - No namespace collision handling** | Same skill ID from different marketplaces — `SkillRegistry.skills` is a flat dict, last writer wins silently. |

---

### 3. Multi-Marketplace Support

**Status:** Partially Working — registry exists, override semantics do not | **Severity:** High

**What Exists:**
- `MarketplaceInstance` model with `tier: MarketplaceTier` (ROOT/ENTERPRISE/TEAM/PROJECT/USER) and `priority: int`
- `MarketplaceRegistry` tracks multiple instances, sorts by priority, provides `get_marketplace_for_query()`
- `Skill` model has `marketplace_id`, `marketplace_name`, `marketplace_tier`, `namespace` fields
- Registration endpoint accepts tier, priority, capabilities metadata

**What Does NOT Exist:**

| Gap | Description |
|-----|-------------|
| **A - No cross-marketplace resolution** | `get_marketplace_for_query()` selects ONE marketplace and queries only that one. No mechanism to query multiple and merge catalogs with tier-based overrides. |
| **B - No override semantics** | `MarketplaceTier` hierarchy implies team overrides root, but no code implements this. A TEAM `code-writer` cannot shadow the ROOT version. |
| **C - Namespace field unused** | `Skill.namespace` (models.py:102) is stored but never used for qualified lookups or collision prevention. |
| **D - Single-endpoint client** | `marketplace_client.py` is initialized with one `base_url`. No concept of querying multiple marketplaces or merging results. |
| **E - No override/extend registration** | No `overrides` or `extends` relationship in registration payload. Cannot declare "this TEAM marketplace overrides ROOT for skills matching `acme-*`". |

---

## Recommendations

1. **Short-term (P1):** Wire up the orchestrator to use the marketplace compose endpoint — this unlocks dependency resolution and conflict checking that is already built but unused.
2. **Medium-term (P1):** Implement multi-marketplace skill resolution with tier-based overrides — the data model is ready, the runtime logic needs to be built.
3. **Maintenance (P2):** Fix the fallback persona/skill type mismatch and empty merged_instructions edge cases.
4. **Foundation (P2):** Activate the namespace field for safe multi-marketplace skill ID management.

---

## Issues Created

| # | Title | Priority | Type |
|---|-------|----------|------|
| [#90](https://github.com/trueorc/claudevn/issues/90) | Orchestrator should use marketplace compose endpoint | P1 | enhancement |
| [#91](https://github.com/trueorc/claudevn/issues/91) | Implement multi-marketplace skill resolution with tier-based override semantics | P1 | enhancement |
| [#92](https://github.com/trueorc/claudevn/issues/92) | Fallback persona data returned as skill-shaped dict causing field mismatches | P2 | bug |
| [#93](https://github.com/trueorc/claudevn/issues/93) | System persona YAML files have empty merged_instructions | P2 | bug |
| [#94](https://github.com/trueorc/claudevn/issues/94) | Skill namespace field defined but never applied | P2 | enhancement |

---

## Key Files Referenced

- `serving/services/work_orchestrator.py`
- `serving/services/marketplace_client.py`
- `serving/services/marketplace_registry.py`
- `marketplace/composition_service.py`
- `marketplace/skill_registry.py`
- `marketplace/api.py`
- `marketplace/models.py`
- `serving/models/marketplace.py`
- `compute/services/sse_event_client.py`
- `compute/services/claude_code_spawner.py`
- `docs/design/specifications/skill-marketplace.md`
