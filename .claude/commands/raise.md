---
description: Raise a GitHub issue - create a well-formed issue with labels and board placement. No implementation.
---

# Raise GitHub Issue

Create a GitHub issue from a short description. Infer priority, type, area labels, and size. Add to project board. Do NOT implement anything.

## Input

$ARGUMENTS

## Steps

### 1. Parse the Description

From the user's short description, infer:

- **Priority**: Default P2 unless urgency words suggest otherwise (e.g., "broken"/"crash"/"blocker" = P0, "important"/"should" = P1)
- **Type**: `bug` (broken/wrong/fix/error), `enhancement` (add/improve/new/support), or `documentation` (docs/readme/guide)
- **Area labels**: Infer from keywords:
  - Frontend/UI/CSS/React/panel/sidebar/button = `area:frontend`
  - API/endpoint/route/service/FastAPI = `area:serving`
  - Git/branch/merge/PR/worktree = `area:git`
  - MCP/tool/protocol = `area:mcp`
  - Compute/worker/Claude Code/instance = `area:compute`
  - Skill/marketplace/registry = `area:marketplace`
  - If unclear, ask the user
- **Size**: XS (typo/config), S (single file), M (few files), L (cross-component), XL (architecture)
- **Title**: Clean up the description into `[PRIORITY] Brief description` format

### 2. Create the Issue (skip confirmation unless there are open questions)

If the description is clear enough to infer all fields, proceed directly to creating the issue without asking for confirmation. Only pause to ask the user if:
- The area label is ambiguous and can't be inferred
- The description is too vague to write meaningful acceptance criteria
- The user explicitly asked a question in their description

### 3. Create the Issue

```bash
gh issue create \
  --title "[PRIORITY] Description" \
  --label "TYPE,PRIORITY,AREA_LABELS" \
  --body "$(cat <<'EOF'
## Problem
<problem statement>

## Required State
<what we need>

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Reference
- Related: <any related issues or docs if obvious>
EOF
)"
```

Capture the issue number from the output.

### 4. Add to Project Board and Set Fields

Read project board config from CLAUDE.md. Use the project-specific IDs found there.

```bash
# Extract owner/repo from git remote
OWNER="trueorc"
REPO=$(basename $(git remote get-url origin) .git)

# Get project config from CLAUDE.md
# PROJECT_ID, STATUS_FIELD_ID, PRIORITY_FIELD_ID, SIZE_FIELD_ID and their option IDs

# Add issue to project (if not auto-added)
ISSUE_NODE_ID=$(gh api graphql -f query="{ repository(owner: \"$OWNER\", name: \"$REPO\") { issue(number: $ISSUE_NUM) { id } } }" --jq '.data.repository.issue.id')

ITEM_ID=$(gh api graphql -f query="mutation { addProjectV2ItemById(input: { projectId: \"$PROJECT_ID\" contentId: \"$ISSUE_NODE_ID\" }) { item { id } } }" --jq '.data.addProjectV2ItemById.item.id')

# Set Status to Backlog
gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\" itemId: \"$ITEM_ID\" fieldId: \"$STATUS_FIELD_ID\" value: { singleSelectOptionId: \"$BACKLOG_OPTION_ID\" } }) { projectV2Item { id } } }"

# Set Priority
gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\" itemId: \"$ITEM_ID\" fieldId: \"$PRIORITY_FIELD_ID\" value: { singleSelectOptionId: \"$PRIORITY_OPTION_ID\" } }) { projectV2Item { id } } }"

# Set Size
gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\" itemId: \"$ITEM_ID\" fieldId: \"$SIZE_FIELD_ID\" value: { singleSelectOptionId: \"$SIZE_OPTION_ID\" } }) { projectV2Item { id } } }"
```

### 5. Report

```
Created: #<NUMBER> [PRIORITY] Description
Labels: type, priority, area(s)
Board: Backlog | Priority | Size
URL: <issue URL>
```

Done. Do not offer to implement it.

## Rules

- NEVER start implementation, create branches, or write code
- Only ask for confirmation if there are open questions or ambiguity — otherwise create immediately
- If description is ambiguous, ask clarifying questions
- If multiple areas apply, use multiple area labels
- Default to Backlog status (not Ready) unless user says it's ready to work
