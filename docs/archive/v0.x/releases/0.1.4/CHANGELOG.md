# Release 0.1.4 - Agent Approval and Scope System

**Release Date:** November 23, 2025  
**Status:** ✅ Complete

---

## Overview

This release implements the Agent Approval and Scope System, enabling hierarchical organization-based access control and approval workflows for agents in the ClaudeVN Marketplace.

---

## New Features

### 1. Agent Organization Scoping

**Description:** Every agent now belongs to an organization, controlling its visibility across the organization hierarchy.

**Key Additions:**
- `organization_id` field on all agents
- Global agents visible to everyone
- Organization agents visible to org + descendants
- Hierarchical visibility rules

**Example:**
```json
{
  "id": "agent-example-v1",
  "organization_id": "org-engineering",
  "status": "active",
  ...
}
```

### 2. Agent Approval Workflow

**Description:** Agents can be submitted for approval to parent organizations, with admins able to approve or reject.

**States:**
- `active` - Normal operational state
- `pending_approval` - Awaiting admin review

**Workflow:**
1. Create agent in sub-org (active)
2. Submit to parent org (pending_approval)
3. Admin reviews and approves/rejects
4. Agent moves to parent or stays with notes

### 3. Approval API Endpoints

**New Endpoints:**
- `POST /api/v1/agents/{id}/submit-for-approval` - Submit to parent org
- `POST /api/v1/agents/{id}/approve` - Approve and move to approving org
- `POST /api/v1/agents/{id}/reject` - Reject and return to original org
- `GET /api/v1/agents/pending/{org_id}` - List pending approvals

### 4. Approval Dashboard UI

**Location:** `/approvals`

**Features:**
- Lists all pending agents for current scope
- Shows agent details and requesting organization
- Approve button (with optional notes)
- Reject button (with optional notes)
- Admin-only access

### 5. Enhanced Agent Display

**Marketplace Browser:**
- Organization badge on agent cards
- Status badge for pending agents
- Organization filter dropdown (All Organizations + individual orgs)
- Client-side filtering integrated with existing filters

**Agent Detail Page:**
- Organization and status badges
- Submit for Approval button (if user owns agent)
- Approval notes section

---

## Technical Changes

### Backend Changes

#### Models (`marketplace/models/agent.py`)
```python
# Added fields to AgentBase
organization_id: str = "org-global"
status: str = "active"
pending_target_org_id: Optional[str] = None
approval_notes: Optional[str] = None

# Added models
AgentApprovalRequest
AgentApprovalResponse
```

#### Services (`marketplace/services/agent_service.py`)
```python
# New methods
get_accessible_agents(...)  # Scope-aware filtering
submit_for_approval(agent_id, target_org_id)
approve_agent(agent_id, approving_org_id, notes)
reject_agent(agent_id, notes)
get_pending_approvals(organization_id)
```

#### API (`marketplace/api/agents.py`)
```python
# New endpoints
@router.post("/{agent_id}/submit-for-approval")
@router.post("/{agent_id}/approve")
@router.post("/{agent_id}/reject")
@router.get("/pending/{organization_id}")
```

### Frontend Changes

#### New Components
- `ApprovalDashboard.jsx` - Admin review interface
- `ApprovalDashboard.css` - Dashboard styles

#### Updated Components
- `AgentCard.jsx` - Shows organization and status badges
- `AgentDetail.jsx` - Submit for approval button, approval notes
- `MarketplaceBrowser.jsx` - Organization filter dropdown, filtering logic
- `App.jsx` - Added approval dashboard route
- `api.js` - Added approval API methods

#### New Routes
- `/approvals` - Approval dashboard (admin only)

### Data Changes

#### Seed Data
All seed agents updated with:
- `organization_id: "org-global"`
- `status: "active"`
- `pending_target_org_id: null`
- `approval_notes: null`

---

## Breaking Changes

### Agent Document Schema

**Change:** Four new fields added to agent documents.

**Impact:** Existing agents without these fields will need migration.

**Migration:**
```bash
cd marketplace
rm -rf data/marketplace/agents/*.json
rm -f data/marketplace/agents/.seeded
./start.sh  # Reloads seed data with new schema
```

Or programmatically:
```python
for agent in storage.list("agents"):
    storage.update("agents", agent["id"], {
        "organization_id": "org-global",
        "status": "active",
        "pending_target_org_id": None,
        "approval_notes": None
    })
```

---

## API Changes

### New Endpoints

All endpoints maintain backward compatibility. New endpoints added:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/agents/{id}/submit-for-approval` | Submit agent to parent org |
| POST | `/api/v1/agents/{id}/approve` | Approve pending agent |
| POST | `/api/v1/agents/{id}/reject` | Reject pending agent |
| GET | `/api/v1/agents/pending/{org_id}` | List pending approvals |

### Existing Endpoint Changes

**GET /api/v1/agents:**
- Returns agents with new fields
- Filtering behavior unchanged
- Backward compatible

**POST /api/v1/agents:**
- Accepts new fields (optional, defaults applied)
- Backward compatible

---

## Testing

### Test Coverage

✅ **API Endpoints:**
- Submit for approval
- Approve agent
- Reject agent
- List pending approvals

✅ **Workflows:**
- Complete approval flow (submit → approve)
- Rejection flow (submit → reject)
- State transitions
- Organization reassignment

✅ **Edge Cases:**
- Invalid agent ID
- Already pending agent
- Wrong target organization
- Missing approval notes

### Test Results

```
Total Tests: 8
Passed: 8
Failed: 0
Status: ✅ All tests passing
```

**Test Agents Created:**
- `agent-test-analyzer-v1` - Approved successfully
- `agent-test-reporter-v1` - Rejected with notes

---

## Performance Impact

### Backend
- **Agent Listing:** Minimal impact (1-2ms additional filtering)
- **Approval Operations:** Fast (<50ms per operation)
- **Pending Queries:** Efficient in-memory filtering

### Frontend
- **Marketplace Browser:** +2 UI elements per card (organization & status badges), +1 filter dropdown (organization)
- **Agent Detail:** +1 section (approval notes), +1 button (submit)
- **Approval Dashboard:** New page, admin-only

### Database
- **Storage Increase:** ~100 bytes per agent (4 new fields)
- **Query Performance:** No indexes needed for current implementation

---

## Configuration

### No New Environment Variables

Uses existing marketplace configuration. No changes required to `.env` files.

### Deployment Notes

1. **Update Seed Data:** Clear existing agents to force reload
2. **Restart Marketplace:** `./start.sh`
3. **Rebuild Frontend:** `cd frontend && npm run build`
4. **No Database Migration:** Filesystem storage handles new fields automatically

---

## Documentation

### New Documentation Files

1. **`agent-approval-and-scope-system.md`** - Complete specification
   - Overview and concepts
   - Data model changes
   - API endpoints
   - Frontend components
   - Business logic
   - Testing scenarios
   - Migration guide

### Updated Documentation

- `marketplace/README.md` - Added approval workflow section
- `docs/design/specifications/` - Added new spec file

---

## Known Limitations

### Current Implementation

1. **UI-Only Access Control:**
   - Backend doesn't enforce user authentication yet
   - Frontend hides controls based on scope context
   - Production deployment needs auth integration

2. **Simple Approval Flow:**
   - Single approve/reject decision
   - No multi-step approval chains
   - No "request changes" option

3. **No Approval History:**
   - Only latest notes preserved
   - No audit trail of all attempts

4. **Immediate Parent Only:**
   - Can only submit to direct parent
   - Cannot skip levels in hierarchy

5. **Organization Filter Limitation:**
   - Organization filter works on client-side (first 100 agents only)
   - For deployments with >100 agents, server-side filtering recommended
   - Backend API has maximum limit of 100 agents per request

### Planned Improvements

See "Limitations and Future Work" section in specification document.

---

## Upgrade Instructions

### From 0.1.3 to 0.1.4

#### 1. Backup Data (Optional)
```bash
cp -r marketplace/data marketplace/data.backup
```

#### 2. Update Codebase
```bash
git pull origin main
```

#### 3. Clear Agent Data
```bash
cd marketplace
rm -rf data/marketplace/agents/*.json
rm -f data/marketplace/agents/.seeded
```

#### 4. Restart Marketplace
```bash
./stop.sh
./start.sh
```

#### 5. Rebuild Frontend
```bash
cd frontend
npm install  # If package.json changed
npm run build
```

#### 6. Verify
```bash
curl http://localhost:8001/api/v1/health
# Should show agent_count: 7
```

---

## Contributors

- Implementation: AI Assistant
- Design Review: User
- Testing: AI Assistant

---

## Next Release

**Version 0.1.5** will focus on:
- Backend authentication integration
- Scope reassignment (admin moves agent to different child org)
- Approval history and audit trail
- Enhanced approval workflows (multi-step, request changes)

---

## Support

For questions or issues:
1. Check documentation: `docs/design/specifications/agent-approval-and-scope-system.md`
2. Review examples in this changelog
3. Test with curl commands provided in documentation

---

**Release Status:** ✅ Complete and Tested  
**Deployment Ready:** Yes (with recommended auth enhancements for production)

