# Memory Index

## User
- [Matt Lyons](user_matt.md) — Project owner, matt@optionsquared.com

## Feedback
- [Small composable Python files](feedback_file_structure.md) — Prefer small focused modules over large monolithic service files
- [Queue-based over polling](feedback_queue_based.md) — All inter-service communication should be queue/event-driven, no polling
- [AI chat for decomposition](feedback_ai_chat_decomposition.md) — Keep conversational AI chat as primary decomposition interaction
- [No integration tests during v2.0](feedback_no_integration_tests.md) — Only functional mockable unit tests during migration

## Project
- [v2.0 migration strategy](project_v2_migration.md) — Feature branch, phased approach, UI overhaul planned
- [Marketplace kept for now](project_v2_marketplace.md) — Retained during v2.0 migration, long-term TBD
- [Multi-user retained](project_multi_user.md) — Multi-user atmosphere kept, future potential
- [v2.0 UI vision](project_v2_ui_vision.md) — Dashboard L1/L3 focus, new verification page, chat-driven decomposition
- [v2.0 compute model](project_compute_model.md) — Runtime-typed computes, builder+verifier phases within runtime, parallel across runtimes
