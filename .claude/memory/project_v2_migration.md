---
name: v2.0 migration strategy
description: v2.0 architecture redesign is underway — feature branch, phased approach, UI overhaul planned
type: project
---

Major architecture redesign from v1.0 multi-agent orchestration to v2.0 three-layer intelligence model (decomposition, execution, verification). Work happening on a dedicated feature branch.

**Why:** Research shows multi-agent coordination hurts performance. v1.0's coordination overhead is a net negative. v2.0 focuses on decomposition intelligence, context preparation, and integration verification.

**How to apply:** All v2.0 work goes on the feature branch. Phases: 0 (foundation/schema), 1 (decomposition layer), 2 (verification layer), 3 (slim execution), 4 (remove coordination overhead), 5 (marketplace decision). UI is getting a dramatic overhaul as part of this — details TBD.
