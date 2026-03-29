---
name: Plan page next phase — decomposition quality
description: Next phase of Plan page work — chain visualization, complexity scoring, recomposition, interface contracts, confidence scoring
type: project
---

The Plan page needs to evolve from a display into a decomposition workshop. Key items:

1. **Chain visualization** — leverage the existing dependency graph component from the execution page (IssueDependencyGraphView). Show critical path highlighted, parallel chains identified, bottleneck units called out.

2. **Interface contracts** — LLM decomposition prompt needs to produce actual interface specs (function signatures, API schemas, import/export contracts) not just descriptions. These connect the chain — what unit A produces that unit B consumes.

3. **Complexity scoring** — per-unit score based on: file count, estimated scope, dependency depth. Flag units that are too big ("15 files — split?"). Thresholds for suggesting re-decomposition.

4. **Recomposition controls** — merge/split from the Plan page. Chat-driven ("split the frontend unit") or button-driven. This is the interactive refinement from design doc 4.2.3.

5. **Upstream outputs in context** — when executing sequentially, unit B gets unit A's actual diff/output injected. Critical for the sequential-execution-shared-context model.

6. **Acceptance criteria + scoring** — each unit needs clear "done" criteria. Score how well-defined they are (easily attainable, single scope, testable). This drives confidence.

7. **Coherence analysis** (implemented as component, needs LLM wiring) — feeds into recomposition by identifying what needs fixing.

8. **Confidence visualization** — the Plan page should give an overall confidence score for the decomposition. Traffic light: green (ready to execute), yellow (needs attention), red (don't approve yet). Based on: independence quality, complexity scores, interface contract completeness, acceptance criteria clarity.

**Why:** Design doc 4.2.3 says "the user's judgment about decomposition quality is the highest-leverage input in the entire system." The Plan page is where that judgment happens. It needs to provide enough information and tools for the user to make good decisions.

**How to apply:** This is the next implementation phase. Don't start execution wiring (Layer 2 dispatch to actual compute) until the Plan page gives confidence in the decomposition.
