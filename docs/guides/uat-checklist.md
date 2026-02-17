# ClaudeVN UAT Checklist

User Acceptance Testing guide for validating ClaudeVN platform functionality.

**Prerequisites:**
```bash
# Start the platform
docker compose up -d

# Wait for services to be healthy
docker compose ps

# (Optional) Load demo data
python scripts/demo_data.py
```

**Access Points:**
- Frontend UI: http://localhost:8002
- Serving API: http://localhost:8002/api/v1
- Marketplace API: http://localhost:8003/api/v1
- API Docs: http://localhost:8002/docs

---

## UI Support Legend

Each test indicates its UI support status:

| Symbol | Meaning |
|--------|---------|
| UI | Full UI support - can be done entirely from web interface |
| API | API only - requires curl/API calls, no UI support |
| Partial | Some UI support but limited functionality |

---

## UI Gaps Summary

The following features lack proper UI support and have GitHub issues filed:

| Gap | Issue | Priority | Status |
|-----|-------|----------|--------|
| Infrastructure Health Dashboard | [#328](https://github.com/Guarrdon/claudevn/issues/328) | P2 | Backlog |
| Goal Creation UI | [#329](https://github.com/Guarrdon/claudevn/issues/329) | P2 | Backlog |
| Skill Creation UI | [#330](https://github.com/Guarrdon/claudevn/issues/330) | P3 | Backlog |
| Issue Creation/Editing in WorkMap | [#331](https://github.com/Guarrdon/claudevn/issues/331) | P1 | Backlog |

---

## Understanding Goals, Issues, and Work Items

Before testing, understand the three-tier work hierarchy:

```
┌─────────────────────────────────────────────────────────────────┐
│  GOAL (User Intent)                                             │
│  "Implement user authentication with OAuth2"                    │
│  Status: planning → in_progress → done                          │
│  Storage: Git (persistent)                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Planner decomposes into...
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ISSUES (Units of Work)                                         │
│  - "Set up OAuth2 provider integration"                         │
│  - "Implement JWT token service"                                │
│  - "Add role-based access control"                              │
│  Status: backlog → ready → in_progress → done/failed            │
│  Storage: Git (persistent, with full history)                   │
│  Dependencies: Issues can depend on other issues                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ When assigned to compute...
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  WORK ITEM (Active Execution)                                   │
│  - Links an Issue to a Compute instance                         │
│  - Tracks progress (0-100%), blockers, branch name              │
│  Status: pending → assigned → in_progress → completed/failed    │
│  Storage: Redis (ephemeral, deleted when done)                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Concepts:**
- **Goals** are high-level objectives from users
- **Issues** are the atomic work units with dependencies
- **Work Items** are temporary tracking objects during execution
- Dependencies cascade: when an issue completes, dependent issues become "ready"

---

## Phase 1: Infrastructure Health

> **UI Gap:** No health dashboard exists. See [#328](https://github.com/Guarrdon/claudevn/issues/328)

### 1.1 Service Health Checks

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 1 | Redis health | API | `docker compose exec redis redis-cli ping` | `PONG` |
| 2 | Serving health | API | `curl http://localhost:8002/api/v1/health` | `{"status": "healthy"}` |
| 3 | Marketplace health | API | `curl http://localhost:8003/api/v1/health` | `{"status": "healthy"}` |
| 4 | Frontend loads | UI | Open http://localhost:8002 in browser | Dashboard renders |

### 1.2 Compute Registration

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 5 | List compute instances | UI | Navigate to Network page | Shows compute-001, compute-002, compute-003 |
| 6 | Compute detail view | UI | Click on compute instance | Modal shows capabilities, metadata |
| 7 | Compute status filter | UI | Use status filter dropdown | Filters by online/degraded/offline |
| 8 | Network map view | UI | Toggle to Map view | Visual network diagram |
| 9 | Deregister compute | UI | Click deregister button | Instance removed (with confirmation) |

---

## Phase 2: Marketplace & Skills

> **UI Gap:** Cannot create skills from UI. See [#330](https://github.com/Guarrdon/claudevn/issues/330)

### 2.1 Skill Management

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 10 | List skills | UI | Navigate to Skills page | Skills displayed with tags |
| 11 | Filter skills by author | UI | Use author filter (system/user) | List filters appropriately |
| 12 | View skill detail | UI | Click on a skill | Modal shows instructions, dependencies |
| 13 | Create skill | API | POST to `/api/v1/skills` | Skill created (no UI) |
| 14 | View marketplace status | UI | Check Network page marketplace panel | Shows connected marketplaces |

**Sample create skill (API only):**
```bash
curl -X POST http://localhost:8003/api/v1/skills \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-skill",
    "name": "My Custom Skill",
    "description": "A custom skill for testing",
    "instructions": "# Instructions\n\nDo the thing.",
    "tags": ["test"],
    "version": "1.0.0"
  }'
```

---

## Phase 3: Project Management

> **UI Status:** Fully implemented

### 3.1 Project CRUD

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 15 | Create project | UI | Click "New Project", fill form | Project created |
| 16 | List projects | UI | Navigate to Projects page | Projects displayed as cards |
| 17 | Edit project | UI | Click edit on project card | Form modal opens, can update |
| 18 | Add repository | UI | Click "Add Repo" in project | Repository added to project |
| 19 | Remove repository | UI | Click remove on repo | Repository removed |
| 20 | Delete project | UI | Click delete, confirm | Project deleted |

---

## Phase 4: Work Map - Goals

> **UI Gap:** Cannot create goals from UI. See [#329](https://github.com/Guarrdon/claudevn/issues/329)

### 4.1 Goal Management

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 21 | Create goal | API | POST `/api/v1/work-map/goals` | Goal created (no UI) |
| 22 | List goals | UI | Goals appear in WorkMap and Goals pages | Goals visible |
| 23 | View goal in WorkMap | UI | Check WorkMap backlog | Goal with nested issues |
| 24 | Goal decomposition | UI | Navigate to Goals page, select goal | Decomposition workflow starts |
| 25 | Review decomposition | UI | After decomposition runs | Issues grouped by phase |
| 26 | Approve execution plan | UI | Click approve in workflow | Plan executes |

**Sample create goal (API only):**
```bash
curl -X POST http://localhost:8002/api/v1/work-map/goals \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add user profile feature",
    "description": "Users should be able to view and edit their profile information",
    "priority": "P1"
  }'
```

---

## Phase 5: Work Map - Issues

> **UI Gap:** Cannot create/edit issues directly. See [#331](https://github.com/Guarrdon/claudevn/issues/331)

### 5.1 Issue Creation & Dependencies

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 27 | Create issue (no deps) | API | POST `/api/v1/work-map/issues` | Status: ready |
| 28 | Create issue (with deps) | API | POST with `depends_on` | Status: backlog |
| 29 | Batch create issues | API | POST `/api/v1/work-map/issues/batch` | Multiple issues created |
| 30 | View issues in backlog | UI | Check WorkMap page | Issues grouped by goal |
| 31 | Expand/collapse goals | UI | Click goal header | Issues show/hide |
| 32 | View dependency graph | UI | Switch to Graph tab | Dependency visualization |

**Sample issue creation (API only):**
```bash
curl -X POST http://localhost:8002/api/v1/work-map/issues \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Design user profile API schema",
    "description": "Create OpenAPI spec for profile endpoints",
    "issue_type": "feature",
    "area": "api",
    "priority": "P1",
    "required_skills": ["code-writer"]
  }'
```

### 5.2 Issue Filtering & Display

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 33 | Filter by status | UI | Use status dropdown | Only matching issues shown |
| 34 | Filter by priority | UI | Use priority dropdown | Only matching issues shown |
| 35 | Drag-drop priority | UI | Drag issue between priority zones | Priority updates |
| 36 | View issue stats | UI | Check WorkMap stats panel | Counts by status |
| 37 | Update issue status | API | POST `/api/v1/work-map/issues/{id}/status` | No direct UI control |

### 5.3 Dependency Cascade

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 38 | Complete parent issue | API | Mark parent done | Child becomes ready |
| 39 | Verify cascade in UI | UI | Watch backlog after completion | Status badges update |

---

## Phase 6: Work Items & Assignment

> **UI Status:** Fully implemented

### 6.1 Work Creation & Assignment

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 40 | Create work item (inline) | UI | Use inline form on Work page | Work item created |
| 41 | Create work item (modal) | UI | Click "New Work", fill form | Work item created |
| 42 | View work list | UI | Navigate to Work page | Work items displayed |
| 43 | Filter by status | UI | Use status dropdown | List filters |
| 44 | Filter by priority | UI | Use priority dropdown | List filters |
| 45 | Filter by project | UI | Use project dropdown | List filters |
| 46 | Assign work | UI | Select compute from dropdown | Work assigned |
| 47 | View active work | UI | Check sidebar panel | In-progress items shown |

### 6.2 Progress & Completion

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 48 | Report progress | UI | Adjust progress slider | Progress updates (0-100%) |
| 49 | Change status | UI | Use status dropdown | Status changes |
| 50 | Add blocker | UI | Click "Add Blocker", fill form | Blocker added, status blocked |
| 51 | View blockers | UI | Check blocker list | Active blockers displayed |
| 52 | Resolve blocker | UI | Click resolve button | Blocker resolved, status resumes |
| 53 | Complete work | UI | Set status to completed | Work marked done |
| 54 | Delete work | UI | Click delete, confirm | Work removed |

---

## Phase 7: WorkMap Views

> **UI Status:** Fully implemented

### 7.1 Backlog View

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 55 | View backlog | UI | Navigate to WorkMap page | Goals with nested issues |
| 56 | Expand all goals | UI | Click "Expand All" | All goals expanded |
| 57 | Collapse all goals | UI | Click "Collapse All" | All goals collapsed |
| 58 | See blocker count | UI | Check issue badges | Blocker count shown |
| 59 | See dependency list | UI | Expand issue | Dependencies listed |

### 7.2 Graph View

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 60 | View dependency graph | UI | Switch to Graph tab | SVG visualization renders |
| 61 | Goal nodes | UI | Check left column | Goal nodes displayed |
| 62 | Issue nodes | UI | Check right column | Issue nodes displayed |
| 63 | Dependency edges | UI | Check connecting lines | "depends_on" relationships |
| 64 | Status colors | UI | Check node colors | Green=ready, Blue=in_progress, etc. |

### 7.3 Statistics & Real-time

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 65 | View stats | UI | Check stats panel | Total, ready, in_progress, blocked, done |
| 66 | Progress bar | UI | Check overall progress | Percentage and bar |
| 67 | Real-time updates | UI | Make API change | UI updates automatically |
| 68 | Active work sidebar | UI | Check right sidebar | In-progress items with progress |

---

## Phase 8: End-to-End Workflow

### 8.1 Complete Workflow Test

This tests the full cycle from goal to completed work. Steps marked with UI can be done from the interface; API steps require curl commands.

| Step | UI | Action | Verification |
|------|-----|--------|--------------|
| 1 | API | Create a goal | Goal appears in WorkMap |
| 2 | API | Create issue A (no deps) | A: ready in backlog |
| 3 | API | Create issue B (depends on A) | B: backlog |
| 4 | API | Create issue C (depends on B) | C: backlog |
| 5 | UI | Create work item for issue A | Work item appears |
| 6 | UI | Assign work to compute-001 | Work assigned |
| 7 | UI | Report 50% progress | Progress bar updates |
| 8 | UI | Complete work item | Work completed |
| 9 | API | Mark issue A done | A: done |
| 10 | UI | Verify B is now ready | B status changes in UI |
| 11 | UI | Create and complete work for B | B workflow |
| 12 | API | Mark issue B done | B: done, C becomes ready |
| 13 | UI | Complete C workflow | All issues done |
| 14 | UI | Verify goal shows as done | Goal status updates |

---

## Phase 9: Error Handling & Edge Cases

| # | Test | UI | Command/Action | Expected Result |
|---|------|-----|----------------|-----------------|
| 69 | Duplicate project | UI | Create project with same name | Error message shown |
| 70 | Invalid status transition | API | Ready → Done directly | 400 Bad Request |
| 71 | Assign to offline compute | UI | Try to assign to offline | Only online shown in dropdown |
| 72 | Delete assigned work | UI | Delete in-progress work | Confirmation required |
| 73 | Circular dependency | API | A depends on B, B depends on A | Validation error |

---

## Phase 10: Demo Data Verification

After running `python scripts/demo_data.py`:

| # | Test | UI | Verification |
|---|------|-----|--------------|
| 74 | Projects created | UI | 3 demo projects visible on Projects page |
| 75 | Goals created | UI | 4 demo goals visible in WorkMap |
| 76 | Issues created | UI | 10 issues with dependencies in backlog |
| 77 | Work items created | UI | 5 work items on Work page |
| 78 | Demo compute registered | UI | Demo compute instances on Network page |
| 79 | Skills created | UI | 3 demo skills on Skills page |

**Clear demo data:**
```bash
python scripts/demo_data.py --clear
```

---

## Quick Reference: API Endpoints

### Goals
```
POST   /api/v1/work-map/goals           Create goal
GET    /api/v1/work-map/goals           List goals
GET    /api/v1/work-map/goals/{id}      Get goal
DELETE /api/v1/work-map/goals/{id}      Delete goal
```

### Issues
```
POST   /api/v1/work-map/issues          Create issue
POST   /api/v1/work-map/issues/batch    Batch create
GET    /api/v1/work-map/issues          List (with filters)
GET    /api/v1/work-map/issues/stats    Statistics
GET    /api/v1/work-map/issues/{id}     Get issue
PATCH  /api/v1/work-map/issues/{id}     Update issue
POST   /api/v1/work-map/issues/{id}/status    Change status
POST   /api/v1/work-map/issues/{id}/complete  Mark done
DELETE /api/v1/work-map/issues/{id}     Delete issue
```

### Work Items
```
POST   /api/v1/work-map/work                    Create work
GET    /api/v1/work-map/work                    List work
GET    /api/v1/work-map/work/{id}               Get work
POST   /api/v1/work-map/work/{id}/assign        Assign
POST   /api/v1/work-map/work/{id}/status        Change status
POST   /api/v1/work-map/work/{id}/progress      Report progress
POST   /api/v1/work-map/work/{id}/complete      Complete
POST   /api/v1/work-map/work/{id}/blockers      Add blocker
POST   /api/v1/work-map/work/{id}/blockers/{bid}/resolve  Resolve blocker
DELETE /api/v1/work-map/work/{id}               Delete work
```

### WorkMap Views
```
GET    /api/v1/work-map/workmap             Full state
GET    /api/v1/work-map/workmap/ready       Ready queue
GET    /api/v1/work-map/workmap/in-progress Active items
GET    /api/v1/work-map/workmap/blocked     Blocked items
GET    /api/v1/work-map/workmap/stats       Statistics
```

---

## Status Cheat Sheet

### Goal Status
| Status | Meaning |
|--------|---------|
| `planning` | Being broken into issues |
| `in_progress` | Issues being worked |
| `done` | All issues complete |

### Issue Status
| Status | Meaning |
|--------|---------|
| `backlog` | Has unmet dependencies |
| `ready` | Dependencies met, awaiting assignment |
| `in_progress` | Assigned and being worked |
| `blocked` | Waiting on blocker resolution |
| `done` | Successfully completed |
| `failed` | Failed after retries |

### Work Item Status
| Status | Meaning |
|--------|---------|
| `pending` | Created, awaiting assignment |
| `assigned` | Assigned to compute |
| `in_progress` | Actively being worked |
| `blocked` | Has active blocker |
| `review` | Work done, awaiting review |
| `completed` | Successfully finished |
| `failed` | Failed |

---

## Notes

- **Real-time updates**: UI updates automatically via WebSocket with polling fallback
- **Demo compute instances**: The demo script creates fake compute instances (compute-demo-*) for UI testing; real instances (compute-001, 002, 003) register automatically via Docker
- **Priority scoring**: Lower score = higher priority (P0 issues process before P3)
- **Dependency cascade**: Completing an issue automatically unlocks dependent issues
- **Navigation**: Sidebar provides access to Network, Skills, Projects, Work, WorkMap, and Goals pages
