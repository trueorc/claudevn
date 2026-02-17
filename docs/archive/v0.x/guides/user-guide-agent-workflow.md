# User Guide: Agent Creation and Approval Workflow

**Version**: 0.1.4  
**Last Updated**: November 23, 2025

---

## Overview

This guide walks through the complete agent creation and approval workflow from a user's perspective. You'll learn how to:
1. Create new agents in your organization
2. Submit agents for approval to parent organizations
3. Review and approve/reject pending agents (admin only)

---

## Prerequisites

**Access the Marketplace:**
- **URL**: http://localhost:8001
- **Default Login**: username: `admin`, password: `admin123`

**Organization Structure:**
```
<global>
└── Corp1 (Sample organization)
```

**Pre-loaded Agents:**
- **Global Agents** (7): Available to everyone
  - Goal Decomposer, Team Assembler, Execution Coordinator
  - Progress Tracker, Result Synthesizer
  - Content Writer, Research Agent

- **Corp1 Agents** (2): Only available to Corp1
  - Sales Forecaster Agent
  - Customer Sentiment Analyzer

---

## Workflow 1: Creating a New Agent

### Step 1: Navigate to Agent Creation

1. Log in to the marketplace
2. Click **"Create Agent"** in the top navigation
3. Ensure the correct organization scope is selected (shown at top of page)

### Step 2: Fill Out Agent Details

**Basic Information:**
- **Agent Name**: Descriptive name (e.g., "Invoice Processor")
- **Description**: What the agent does, its purpose, key features
- **Agent Type**: 
  - **Specialized**: Performs specific tasks
  - **Coordinating**: Orchestrates other agents
- **Version**: Semantic version (e.g., 1.0.0)

**Capabilities:**
- **Capabilities**: Comma-separated list (e.g., "invoice processing, data extraction, validation")
- **Tags**: Optional categorization (e.g., "finance, automation, specialized")

**Technical Specifications:**
- **Supported Input Types**: MIME types (e.g., "application/json, application/pdf")
- **Supported Output Types**: MIME types (e.g., "application/json, text/csv")
- **Complexity Level**: Low, Medium, or High
- **Estimated Duration**: Average execution time in seconds
- **Language Model**: Optional (e.g., "gpt-4", "claude-3")

### Step 3: Submit

1. Review all fields
2. Click **"Create Agent"**
3. Success message will appear
4. You'll be redirected to the agent detail page

**Result**: Agent is created with status `active` in your current organization.

---

## Workflow 2: Submitting an Agent for Approval

### Step 1: Navigate to Your Agent

1. Go to the marketplace home
2. Find your agent in the list (filter by your organization if needed)
3. Click on the agent to view details

### Step 2: Review Agent Details

- Verify all information is correct
- The agent shows your organization badge (e.g., "📁 Corp1")
- Status shows as `active`

### Step 3: Submit for Approval

1. Look for the **"Submit to [Parent Org] for Approval"** button
2. Click the button
3. Confirm the submission in the popup

**What Happens:**
- Agent status changes to `pending_approval` (⏳ Pending badge appears)
- Agent remains visible in your organization
- Admin at parent organization can now review it
- Agent no longer shows the submit button (already pending)

---

## Workflow 3: Reviewing Pending Agents (Admin Only)

### Step 1: Access Approval Dashboard

1. Log in as an admin user
2. Select the organization scope where you're admin
3. Click **"Approvals"** in the top navigation

### Step 2: Review Pending Agents

The dashboard shows all agents pending approval for your organization:

**Agent Information Displayed:**
- Agent name and type badge
- Current organization (where it was created)
- Full description
- Capabilities and technical specs
- Version and complexity

### Step 3: Make a Decision

**Option A: Approve**
1. Click **"✓ Approve"** button
2. Optionally add approval notes (e.g., "Great work! Approved for company-wide use")
3. Confirm

**What Happens:**
- Agent moves to your organization
- Status changes back to `active`
- Agent now visible to your org and all child organizations
- Approval notes saved on the agent
- Creator can see the agent is now in parent org

**Option B: Reject**
1. Click **"✗ Reject"** button
2. Add rejection notes (e.g., "Needs more testing" or "Duplicate functionality")
3. Confirm

**What Happens:**
- Agent stays in original organization
- Status changes back to `active`
- Rejection notes saved on agent
- Creator can see rejection notes and revise
- Agent can be resubmitted after improvements

---

## Example Scenarios

### Scenario 1: Corp1 User Creates a Finance Agent

```
User: Alice (Corp1 member)
Action: Create "Budget Analyzer Agent"

1. Alice logs in and selects Corp1 scope
2. Navigates to "Create Agent"
3. Fills out form:
   - Name: "Budget Analyzer Agent"
   - Type: Specialized
   - Capabilities: "budget analysis, variance detection, forecast generation"
   - Input Types: "application/json, text/csv"
   - Complexity: Medium
4. Clicks "Create Agent"
5. Agent created in Corp1 with ID: agent-budget-analyzer-v1
6. Status: active
7. Visibility: Only Corp1 can see it
```

### Scenario 2: Submitting Budget Analyzer to Global

```
User: Alice (Corp1 member)
Current State: Budget Analyzer exists in Corp1

1. Alice navigates to Budget Analyzer detail page
2. Sees button: "Submit to <global> for Approval"
3. Clicks button and confirms
4. Agent status → pending_approval
5. Badge shows: "⏳ Pending"
6. Agent still visible to Corp1
7. Agent appears in global admin's approval dashboard
```

### Scenario 3: Global Admin Reviews Budget Analyzer

```
User: Admin (Global admin)
Action: Review pending Budget Analyzer

1. Admin logs in
2. Selects <global> scope
3. Navigates to "Approvals"
4. Sees Budget Analyzer in pending list:
   - From: Corp1
   - Name: Budget Analyzer Agent
   - Capabilities: budget analysis, variance detection, forecast generation
5. Admin decides it's useful for everyone
6. Clicks "Approve"
7. Adds note: "Excellent tool for financial planning. Approved for global use."
8. Confirms

Result:
- Agent moves from Corp1 to <global>
- Status: active
- Now visible to everyone (all organizations)
- Alice can see it's been promoted to global
```

### Scenario 4: Rejection and Resubmission

```
User: Bob (Corp1 member)
Action: Submit "Email Parser Agent" for approval

Initial Submission:
1. Bob creates Email Parser Agent in Corp1
2. Submits to global for approval
3. Status: pending_approval

Admin Review:
1. Global admin reviews
2. Finds it needs more features
3. Clicks "Reject"
4. Adds note: "Please add support for attachments and HTML emails"
5. Confirms

After Rejection:
- Agent stays in Corp1
- Status: active (no longer pending)
- Rejection notes visible to Bob
- Bob can see the feedback

Bob's Response:
1. Bob sees rejection notes
2. Updates agent (adds requested features)
3. Can submit again when ready
4. Submits for approval again
5. Process repeats
```

---

## UI Features Reference

### Marketplace Home
- **Agent Cards**: Show organization badge and status
- **Filtering**: By type (dropdown), organization (dropdown), capabilities, search
- **Organization Filter**: Dropdown shows "All Organizations" plus each available org
- **Search**: Find agents by name/description

### Agent Detail Page
- **Organization Badge**: Shows which org owns the agent
- **Status Badge**: Shows if pending approval
- **Submit Button**: Appears if you own the agent and it's active
- **Approval Notes**: Shows feedback from last approval/rejection

### Create Agent Page
- **Form Validation**: Real-time error checking
- **Scope Display**: Shows which org you're creating in
- **Auto-ID Generation**: Creates agent ID from name + version

### Approval Dashboard (Admin Only)
- **Pending List**: All agents awaiting your review
- **Agent Details**: Full information for each agent
- **Approve/Reject**: Quick action buttons
- **Notes Support**: Add context to decisions

---

## API Equivalent Commands

For developers or automation, here are the API endpoints:

### Create Agent
```bash
curl -X POST http://localhost:8001/api/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "id": "agent-my-agent-v1",
    "name": "My Agent",
    "description": "Does something useful",
    "agent_type": "specialized",
    "version": "1.0.0",
    "capabilities": ["capability1"],
    "capability_descriptions": {"capability1": "Description"},
    "supported_input_types": ["application/json"],
    "supported_output_types": ["application/json"],
    "organization_id": "org-corp1"
  }'
```

### Submit for Approval
```bash
curl -X POST "http://localhost:8001/api/v1/agents/agent-my-agent-v1/submit-for-approval?target_org_id=org-global"
```

### List Pending Approvals
```bash
curl http://localhost:8001/api/v1/agents/pending/org-global
```

### Approve Agent
```bash
curl -X POST "http://localhost:8001/api/v1/agents/agent-my-agent-v1/approve?approving_org_id=org-global" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Looks great!"}'
```

### Reject Agent
```bash
curl -X POST "http://localhost:8001/api/v1/agents/agent-my-agent-v1/reject" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Needs improvement"}'
```

---

## Tips and Best Practices

### For Agent Creators

1. **Be Descriptive**: Write clear descriptions explaining what your agent does
2. **List All Capabilities**: Include all relevant capabilities for better discoverability
3. **Tag Appropriately**: Use tags to help others find your agent
4. **Test First**: Ensure your agent works well before submitting for approval
5. **Read Feedback**: If rejected, carefully read the notes and address concerns

### For Admins

1. **Review Thoroughly**: Check if the agent fills a real need
2. **Avoid Duplicates**: Look for similar existing agents before approving
3. **Give Clear Feedback**: Rejection notes should be specific and actionable
4. **Consider Scope**: Think about whether the agent is truly useful at the parent org level
5. **Test if Possible**: Ideally, test the agent before approving

### General

1. **Organize by Team**: Use Corp1 (or create sub-orgs) for team-specific agents
2. **Promote Wisely**: Only submit for approval agents that are useful beyond your team
3. **Version Properly**: Follow semantic versioning (1.0.0, 1.1.0, 2.0.0)
4. **Update Descriptions**: Keep agent information current
5. **Track Status**: Check approval dashboard regularly if you're an admin

---

## Troubleshooting

### "Submit for Approval" button not visible
- **Check**: Are you viewing an agent in your own organization?
- **Check**: Is the agent already pending approval?
- **Check**: Does the organization have a parent org to submit to?

### Can't see approval dashboard
- **Check**: Are you logged in as an admin?
- **Check**: Is the correct scope selected?
- **Note**: Only admins at an organization can approve agents for that org

### Agent not appearing after creation
- **Check**: Is the correct organization scope selected?
- **Check**: Try refreshing the page
- **Check**: Look in the marketplace home, not just approvals

### Can't resubmit after rejection
- **Check**: Has the agent status returned to `active`?
- **Solution**: Rejection automatically makes it active again, should be resubmittable

---

## Security Notes

**Current Implementation (v0.1.4):**
- UI controls visibility based on scope context
- Backend validates state transitions
- No deep authentication checks yet

**For Production:**
- Full authentication integration recommended
- Backend permission checks should be added
- Audit logging for all approval actions
- Rate limiting on creation and approval

---

## Next Steps

After mastering the basic workflow:

1. **Create Sub-Organizations**: Organize your teams hierarchically
2. **Build Agent Libraries**: Create collections of related agents
3. **Establish Approval Policies**: Define when agents should be promoted
4. **Monitor Usage**: Track which agents are most valuable
5. **Iterate**: Improve agents based on feedback

---

**Questions or Issues?**
- Check the API docs: http://localhost:8001/docs
- Review the technical spec: `docs/design/specifications/agent-approval-and-scope-system.md`
- Check the changelog: `docs/releases/0.1.4/CHANGELOG.md`

