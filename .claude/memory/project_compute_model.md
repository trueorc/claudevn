---
name: v2.0 compute model direction
description: Compute environments are derived from planning, human-gated, Docker-based — not pre-configured types
type: project
---

Compute model for v2.0: environments are a **product of planning**, not pre-configured assumptions.

Key principles:
- Layer 1 planning analyzes work and identifies runtime requirements (SDKs, tools, packages)
- Planning produces a **compute environment spec** (Dockerfile) alongside work units
- Human reviews and approves the compute spec before anything is provisioned — same gate pattern as decomposition approval
- No auto-provisioning, no surprise Docker builds — just preparation with a gate
- Builder and verifier are **phases within the same compute** — same image, same toolchain
- Truly independent work (across different environments) can run in parallel on separate computes
- If planning detects a new dependency mid-project, it proposes an updated compute spec for approval

**Why:** Pre-typed computes (Python box, Node box) break when work spans runtimes or when the project evolves. The compute should match the work, not the other way around. Docker makes environment specs reproducible and versionable.

**How to apply:** Don't hard-code compute types. Don't auto-provision. Planning identifies requirements → generates Dockerfile → human approves → compute is available for dispatch. Work units declare what they need, dispatch matches to approved computes that have those capabilities.
