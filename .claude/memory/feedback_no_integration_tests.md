---
name: No integration tests during v2.0 changes
description: User does not want integration or system unit tests run during the v2.0 migration work
type: feedback
---

Do not run integration or system unit tests during v2.0 architecture changes. Functional, mockable unit tests are acceptable if they are part of the plan.

**Why:** The v2.0 migration touches so much that integration tests against the full stack would constantly break and waste time. Focus on unit-level correctness.

**How to apply:** When building new v2.0 services, only write/run isolated unit tests with mocks. Don't attempt to boot the full serving app or run the existing test suite.
