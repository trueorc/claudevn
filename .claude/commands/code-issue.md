# Code Issue Workflow

Take a GitHub issue through the full development cycle: analyze, code, test, document, and PR.

## Arguments
- `$ARGUMENTS` - GitHub issue number (e.g., `42`)

## Critical: Worktree Isolation

**IMPORTANT**: When running parallel `/code-issue` commands, each MUST use an isolated Git worktree to prevent conflicts.

```bash
# Create isolated worktree for this issue (relative to repo root)
git worktree add ../worktrees/issue-$ARGUMENTS -b {type}/issue-$ARGUMENTS-{short-description} origin/main

# Work in the isolated worktree
cd ../worktrees/issue-$ARGUMENTS

# Cleanup when done (after PR merged)
git worktree remove ../worktrees/issue-$ARGUMENTS
```

This prevents:
- Stash conflicts between parallel tasks
- Branch checkout races
- Uncommitted changes bleeding between issues

See `docs/guides/worktree-workflow.md` for detailed worktree usage.

---

## Workflow

### 1. Fetch and Analyze Issue

```bash
gh issue view $ARGUMENTS --json title,body,labels,assignees,projectItems
```

Parse the issue to understand:
- **Problem statement** - What needs to be solved
- **Acceptance criteria** - Definition of done
- **Area labels** - Which components are affected (area:serving, area:frontend, etc.)
- **Priority** - P0/P1/P2/P3 for urgency context

### 2. Update DevBoard Status

Set issue status to "In Progress":
```bash
# Get item ID and update status to in_progress
ITEM_ID=$(gh api graphql -f query='{ repository(owner: "Guarrdon", name: "claudevn") { issue(number: $ARGUMENTS) { projectItems(first: 1) { nodes { id } } } } }' --jq '.data.repository.issue.projectItems.nodes[0].id')

gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwHOAP6mx84BNtCx\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lAHOAP6mx84BNtCxzg8nxFg\" value: { singleSelectOptionId: \"47fc9ee4\" } }) { projectV2Item { id } } }"
```

### 3. Create Isolated Worktree

**For parallel work, always use worktrees:**

```bash
# Fetch latest main
git fetch origin main

# Ensure worktrees directory exists
mkdir -p ../worktrees

# Create isolated worktree with feature branch (relative to repo root)
git worktree add ../worktrees/issue-$ARGUMENTS -b {type}/issue-$ARGUMENTS-{short-description} origin/main

# Work in the isolated directory
cd ../worktrees/issue-$ARGUMENTS
```

Types based on issue labels:
- `bug` label → `fix/`
- `enhancement` label → `feat/`
- `documentation` label → `docs/`
- `test` label → `test/`

### 4. Explore Relevant Code

Based on area labels, explore the codebase:
- `area:serving` → `serving/` directory (Python/FastAPI)
- `area:frontend` → `serving/frontend/src/` (React/JS)
- `area:marketplace` → `marketplace/` (Python)
- `area:compute` → `compute/` (Python)
- `area:git` → `serving/git/` (Python)
- `area:mcp` → `serving/mcp/` (Python)

Understand existing patterns before writing code.

### 5. Implement Solution

**For Python (FastAPI) changes:**
- Models in `{component}/models/{domain}.py` using Pydantic v2
- Services in `{component}/services/{domain}_service.py` with singleton pattern
- API routes in `{component}/api/{domain}.py`
- Use `datetime.now(timezone.utc)` not `datetime.utcnow()`

**For React/JS changes:**
- Components in `serving/frontend/src/components/{domain}/`
- CSS co-located as `{ComponentName}.css`
- Hooks in `serving/frontend/src/hooks/use{Feature}.js`
- API clients in `serving/frontend/src/api/{domain}.js`
- Use `.jsx` extension, functional components with hooks

### 6. Write and Run Tier 1 Unit Tests

**Test Tier Strategy** (see `docs/guides/test-tier-strategy.md`):
- **Tier 1 (this workflow)**: Unit tests - fast, mocked, no server required
- **Tier 2 (separate issue)**: Integration tests - require running server

**Write unit tests for your feature:**
- Test file: `{component}/tests/test_{module}.py`
- Fixtures for mocks and instances
- Test classes grouped by feature (`TestFeatureInit`, `TestFeatureCreate`)
- `@pytest.mark.asyncio` for async tests
- Use `AsyncMock` for async method mocking

**Run Tier 1 unit tests using the specialized script:**

```bash
# Run all Tier 1 unit tests
./scripts/run_unit_tests.sh

# Run specific test file
./scripts/run_unit_tests.sh {component}/tests/test_{module}.py

# With verbose output
./scripts/run_unit_tests.sh -v

# With coverage
./scripts/run_unit_tests.sh -c
```

**DO NOT run integration tests** - create a follow-up issue for Tier 2 tests if needed.

**JavaScript tests (Jest):**
```bash
cd serving/frontend && npm test -- --testPathPattern={component}
```

### 7. Update Documentation

If the change affects:
- API endpoints → Update relevant docs in `docs/`
- Architecture → Update `docs/design/` files
- User-facing features → Update README or guides

### 8. Commit Changes

Follow conventional commit format:
```bash
git add {specific files}
git commit -m "{type}: {description} (#$ARGUMENTS)"
```

Examples:
- `feat: Add user authentication endpoint (#42)`
- `fix: Correct race condition in event handler (#42)`

### 9. Push and Create PR

```bash
git push -u origin {branch-name}

gh pr create \
  --title "{type}: {Description} (#$ARGUMENTS)" \
  --body "$(cat <<'EOF'
## Summary
- Brief description of changes

## Changes
- List of specific changes made

## Testing
- [ ] Tier 1 unit tests added/updated
- [ ] All Tier 1 unit tests passing (`./scripts/run_unit_tests.sh`)

## Follow-up
- [ ] Create issue for Tier 2 integration tests if needed

## Issue
Closes #$ARGUMENTS
EOF
)"
```

### 10. Update DevBoard Status

Set issue status to "In Review":
```bash
gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwHOAP6mx84BNtCx\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lAHOAP6mx84BNtCxzg8nxFg\" value: { singleSelectOptionId: \"4cc61d42\" } }) { projectV2Item { id } } }"
```

### 11. Cleanup Worktree (After PR Merged)

```bash
# Remove the worktree when done
git worktree remove ../worktrees/issue-$ARGUMENTS

# Clean up stale worktree references
git worktree prune
```

---

## Checklist

- [ ] Issue analyzed and understood
- [ ] DevBoard status updated to "In Progress"
- [ ] **Isolated worktree created** (critical for parallel work)
- [ ] Code implemented following project patterns
- [ ] **Tier 1 unit tests written and passing** (`./scripts/run_unit_tests.sh`)
- [ ] Documentation updated if needed
- [ ] Commit message follows convention
- [ ] PR created and linked to issue
- [ ] DevBoard status updated to "In Review"
- [ ] (Follow-up) Issue created for Tier 2 integration tests if applicable

---

## Related Documentation

- [Worktree Workflow Guide](../docs/guides/worktree-workflow.md)
- [Test Tier Strategy](../docs/guides/test-tier-strategy.md)
