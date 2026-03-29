---
name: Queue-based over polling
description: User wants all inter-service communication to be queue/event-based, no polling
type: feedback
---

All communication between components should be queue-based or event-driven. No unnecessary polling decisions.

**Why:** Polling adds latency, wastes resources, and introduces timing decisions that shouldn't need to be made. The v1.0 architecture has monitoring loops and polling patterns that should be eliminated.

**How to apply:** When designing inter-service communication, default to queues, event buses, or pub/sub. If something looks like a polling loop, replace it with an event-driven alternative. This applies across all phases of the v2.0 migration.
