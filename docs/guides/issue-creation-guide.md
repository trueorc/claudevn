# ClaudeVN Issue Creation Guide

This guide ensures consistent GitHub issue creation with proper project board integration.

---

## Quick Reference

### Issue Title Format

```
[PRIORITY] Brief description
```

**Examples:**
- `[P0] Implement SSH Git Server for Compute Push/Pull`
- `[P1] Add Work Timeout Detection`
- `[P2] Deploy Git Hooks to Repositories`

### Required Labels

Every issue MUST have:

1. **Priority Label** (exactly one):
   - `P0` - Critical priority (blocks other work)
   - `P1` - High priority (important for next milestone)
   - `P2` - Medium priority (should be done soon)
   - `P3` - Low priority (nice to have)

2. **Type Label** (exactly one):
   - `bug` - Something isn't working
   - `enhancement` - New feature or improvement
   - `documentation` - Documentation only

3. **Functional Area Label** (one or more):
   - `area:serving` - Serving component
   - `area:compute` - Compute component
   - `area:marketplace` - Marketplace component
   - `area:git` - Git infrastructure
   - `area:mcp` - MCP tools/server
   - `area:frontend` - Frontend/UI

4. **Special Labels** (when applicable):
   - `test` - Test-related issue
   - `architecture` - Architecture/design change

---

## Project Board Fields

The GitHub Project Board (ClaudeVN DevPlan) has these fields that must be set:

| Field | Description | Values |
|-------|-------------|--------|
| **Status** | Current state | Backlog, Ready, In progress, In review, Done |
| **Priority** | Priority level | P0, P1, P2 (P3 not available in board) |
| **Size** | Effort estimate | XS, S, M, L, XL |

### Status Workflow

```
Backlog → Ready → In progress → In review → Done
```

- **Backlog**: Captured but not ready to work
- **Ready**: Fully specified, ready to start
- **In progress**: Someone is actively working
- **In review**: PR created, awaiting review
- **Done**: Merged and closed

---

## Creating Issues with gh CLI

### Full Issue Creation Command

```bash
gh issue create \
  --title "[P1] My Issue Title" \
  --label "enhancement,P1,area:serving" \
  --body "$(cat <<'EOF'
## Problem
Describe the problem or need.

## Current State
What exists today.

## Required State
What we need to achieve.

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Reference
- Related docs: docs/design/...
- Related issues: #XX
EOF
)"
```

### Setting Project Board Fields

After creating an issue, set the project board fields:

```bash
# Get the issue's project item ID
ITEM_ID=$(gh api graphql -f query='
{
  repository(owner: "Guarrdon", name: "claudevn") {
    issue(number: ISSUE_NUMBER) {
      projectItems(first: 1) {
        nodes { id }
      }
    }
  }
}' --jq '.data.repository.issue.projectItems.nodes[0].id')

# Set Priority field (P0, P1, or P2)
gh api graphql -f query="
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: \"PVT_kwHOAP6mx84BNtCx\"
    itemId: \"$ITEM_ID\"
    fieldId: \"PVTSSF_lAHOAP6mx84BNtCxzg8nxLg\"
    value: { singleSelectOptionId: \"OPTION_ID\" }
  }) { projectV2Item { id } }
}"

# Set Status field
gh api graphql -f query="
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: \"PVT_kwHOAP6mx84BNtCx\"
    itemId: \"$ITEM_ID\"
    fieldId: \"PVTSSF_lAHOAP6mx84BNtCxzg8nxFg\"
    value: { singleSelectOptionId: \"OPTION_ID\" }
  }) { projectV2Item { id } }
}"
```

---

## Project Board Field IDs

### Project ID
```
PVT_kwHOAP6mx84BNtCx
```

### Status Field
```yaml
field_id: PVTSSF_lAHOAP6mx84BNtCxzg8nxFg
options:
  backlog: f75ad846
  ready: 08afe404
  in_progress: 47fc9ee4
  in_review: 4cc61d42
  done: 98236657
```

### Priority Field
```yaml
field_id: PVTSSF_lAHOAP6mx84BNtCxzg8nxLg
options:
  P0: 79628723
  P1: 0a877460
  P2: da944a9c
  P3: f55ea659
```

### Size Field
```yaml
field_id: PVTSSF_lAHOAP6mx84BNtCxzg8nxLk
options:
  XS: eff732af
  S: 9592a5a3
  M: 9728cbdc
  L: c53df028
  XL: 7b141a16
```

---

## Functional Area Mapping

When creating issues, use these area labels based on the component:

| Component | Labels |
|-----------|--------|
| Work Map, Orchestrator, Registry | `area:serving` |
| Compute Spawner, MCP Server | `area:serving`, `area:mcp` |
| Compute Runtime, Agents | `area:compute` |
| Git Infrastructure, PR Service | `area:git`, `area:serving` |
| Skill/Persona Registry | `area:marketplace` |
| Monitoring UI, Frontend | `area:frontend` |
| Claude Code Integration | `area:compute`, `area:mcp` |

---

## Examples

### P0 Critical Issue

```bash
gh issue create \
  --title "[P0] Implement SSH Git Server" \
  --label "enhancement,P0,area:git,area:serving" \
  --body "$(cat <<'EOF'
## Problem
Compute instances cannot push branches - no SSH server exists.

## Current State
- SSHKeyManager exists but no daemon
- Git hooks templates exist but aren't deployed

## Required State
- SSH daemon running on Serving
- Key-based auth via SSHKeyManager
- Pre/post-receive hooks deployed

## Acceptance Criteria
- [ ] SSH daemon running on port 2222
- [ ] Uses authorized_keys from SSHKeyManager
- [ ] Compute can `git push origin branch-name`
- [ ] Redis updated on push events

## Reference
- docs/design/specifications/git-infrastructure.md
EOF
)"
```

### Test Issue

```bash
gh issue create \
  --title "[P1] Add E2E Work Execution Test" \
  --label "enhancement,P1,test,area:serving,area:compute" \
  --body "$(cat <<'EOF'
## Problem
No end-to-end test validates the full work execution flow.

## Test Scope
1. Create work item
2. Spawn compute instance
3. Compute calls MCP tools
4. Work completed and merged

## Acceptance Criteria
- [ ] Test creates work via API
- [ ] Test spawns compute instance
- [ ] Compute successfully gets assignment
- [ ] Work marked complete

## Reference
- Blocked by: #39, #40
EOF
)"
```

---

## Automation Tips

### Add Issue to Project Automatically

Issues are auto-added to the project via GitHub Actions. If not:

```bash
gh project item-add 2 --owner Guarrdon --url https://github.com/Guarrdon/claudevn/issues/XX
```

### Bulk Update Labels

```bash
# Add area label to multiple issues
for issue in 39 40 41; do
  gh issue edit $issue --add-label "area:serving"
done
```

### Query Issues by Area

```bash
gh issue list --label "area:serving" --state open
gh issue list --label "P0" --state open
gh issue list --label "test" --state open
```

---

## Checklist for New Issues

Before creating an issue, verify:

- [ ] Title follows `[PRIORITY] Description` format
- [ ] Priority label (P0/P1/P2/P3) is set
- [ ] Type label (bug/enhancement/documentation) is set
- [ ] At least one `area:*` label is set
- [ ] `test` label added if test-related
- [ ] `architecture` label added if design change
- [ ] Body includes Problem, Required State, Acceptance Criteria
- [ ] Project board Priority field is set
- [ ] Project board Status field is set (usually "Backlog" or "Ready")

---

## Summary

1. **Title**: `[PRIORITY] Brief description`
2. **Labels**: Priority + Type + Area(s) + Special
3. **Body**: Problem → Current → Required → Criteria → Reference
4. **Board Fields**: Status + Priority (via GraphQL API)

Following this guide ensures issues are properly categorized and visible on the project board.
