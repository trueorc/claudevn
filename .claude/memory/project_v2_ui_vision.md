---
name: v2.0 UI vision
description: UI rework decisions — dashboard shift to L1/L3, new verification page, chat-driven decomposition
type: project
---

Key UI decisions for v2.0:

1. **Dashboard/Control Center:** Keep the layout concept but rework content from execution-focused to Layer 1 + Layer 3 focused, with a little Layer 2. Not a redesign of the shell — a rework of what's shown.

2. **Decomposition/Goals Page:** Stays as a separate page from dashboard. Needs dramatic changes to support formal work unit specs, independence auditing, dependency DAG, but retains AI chat as the primary interaction model.

3. **New Verification Page:** Dedicated page for Layer 3 integration verification — per-unit results, cross-unit integration status, combined diffs, quality metrics, gap analysis.

4. **Execution Plan Page:** Dramatically simplified — just the queue, no orchestration controls.

5. **AI Chat:** Retained as primary interaction method for decomposition refinement. Structured visualizations augment the chat.

**How to apply:** When building v2.0 frontend, evolve existing page structure rather than starting from scratch. The shell (IconBar, layout) is fine. The content within pages changes significantly.
