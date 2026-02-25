# Code Issue Workflow

Take a GitHub issue through the full development cycle: analyze, code, test, document, and PR.

## Arguments
- `$ARGUMENTS` - GitHub issue number, optionally followed by `--branch <branch-name>`
  - Examples: `42`, `42 --branch feat/safe-clone`

## Feature Grouping

Issues can share a single branch/worktree/PR using one of two methods:

1. **Label-based** (preferred): Add a `feature:*` label to related issues (e.g., `feature:safe-clone`). All issues with the same feature label share branch `feat/{feature-name}`.
2. **Explicit**: Pass `--branch <name>` to specify the branch directly.
3. **Default**: No feature label and no `--branch` → one branch per issue (current behavior).

## Critical: Worktree Isolation

Each feature branch gets its own worktree. Multiple issues in the same feature share the same worktree — they are worked on sequentially within it, each as a separate commit.

See `docs/guides/worktree-workflow.md` for detailed worktree usage.

---

## Workflow

### 1. Fetch and Analyze Issue

```bash
gh issue view {ISSUE_NUMBER} --json title,body,labels,assignees,projectItems
```

Parse the issue to understand:
- **Problem statement** - What needs to be solved
- **Acceptance criteria** - Definition of done
- **Area labels** - Which components are affected (area:serving, area:frontend, etc.)
- **Priority** - P0/P1/P2/P3 for urgency context
- **Feature label** - Any `feature:*` label for branch grouping

### 2. Determine Branch Strategy

Parse `$ARGUMENTS` to extract the issue number and optional `--branch` flag.

Then determine the branch name using this priority:

1. **`feature:*` label found** on the issue:
   - Extract feature name from label (e.g., `feature:safe-clone` → `safe-clone`)
   - Branch: `feat/{feature-name}` (e.g., `feat/safe-clone`)
   - Worktree: `../worktrees/feat-{feature-name}`

2. **`--branch` flag provided** in arguments:
   - Branch: use the provided name exactly
   - Worktree: `../worktrees/{branch-name-with-slashes-replaced-by-dashes}`

3. **Neither** (default — single-issue mode):
   - Branch: `{type}/issue-{N}-{short-description}` (type from issue labels: bug→fix, enhancement→feat, etc.)
   - Worktree: `../worktrees/issue-{N}`

### 3. Update DevBoard Status

Set issue status to "In Progress":
```bash
ITEM_ID=$(gh api graphql -f query='{ repository(owner: "trueorc", name: "claudevn") { issue(number: {ISSUE_NUMBER}) { projectItems(first: 1) { nodes { id } } } } }' --jq '.data.repository.issue.projectItems.nodes[0].id')

gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwHOAP6mx84BNtCx\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lAHOAP6mx84BNtCxzg8nxFg\" value: { singleSelectOptionId: \"47fc9ee4\" } }) { projectV2Item { id } } }"
```

### 4. Set Up Worktree (with reuse)

```bash
git fetch origin main
mkdir -p ../worktrees
```

**Check if the branch and worktree already exist** (critical for feature-grouped issues):

- **Worktree already exists** → `cd` into it. Do NOT create a new one.
- **Branch exists on remote but no worktree** → `git worktree add ../worktrees/{name} {branch-name}` (track existing branch, not origin/main)
- **Branch doesn't exist** → `git worktree add ../worktrees/{name} -b {branch-name} origin/main` (create new)

```bash
# Example: reuse existing worktree
if [ -d "../worktrees/{worktree-name}" ]; then
    cd ../worktrees/{worktree-name}
    git pull origin {branch-name}  # get latest from shared branch
else
    # Check if branch exists on remote
    if git ls-remote --heads origin {branch-name} | grep -q {branch-name}; then
        git worktree add ../worktrees/{worktree-name} {branch-name}
    else
        git worktree add ../worktrees/{worktree-name} -b {branch-name} origin/main
    fi
    cd ../worktrees/{worktree-name}
fi
```

### 5. Explore Relevant Code

Based on area labels, explore the codebase:
- `area:serving` → `serving/` directory (Python/FastAPI)
- `area:frontend` → `serving/frontend/src/` (React/JS)
- `area:marketplace` → `marketplace/` (Python)
- `area:compute` → `compute/` (Python)
- `area:git` → `serving/git/` (Python)
- `area:mcp` → `serving/mcp/` (Python)

Understand existing patterns before writing code.

### 6. Implement Solution

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

### 7. Write and Run Tier 1 Unit Tests

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

### 8. Update Documentation

If the change affects:
- API endpoints → Update relevant docs in `docs/`
- Architecture → Update `docs/design/` files
- User-facing features → Update README or guides

### 9. Commit Changes

Follow conventional commit format. **Always reference the individual issue number:**
```bash
git add {specific files}
git commit -m "{type}: {description} (#{ISSUE_NUMBER})"
```

Examples:
- `feat: Add user authentication endpoint (#42)`
- `fix: Correct race condition in event handler (#43)`

### 10. Push and Create/Update PR

```bash
git push -u origin {branch-name}
```

**Check if a PR already exists for this branch:**

```bash
EXISTING_PR=$(gh pr list --head {branch-name} --json number --jq '.[0].number')
```

**If PR exists** (feature-grouped — another issue already created it):
- Update the PR body to add this issue to the list:
```bash
# Get current body, append new issue reference
CURRENT_BODY=$(gh pr view "$EXISTING_PR" --json body --jq '.body')
# Update body to include new issue in the Issues section
gh pr edit "$EXISTING_PR" --body "{updated body with Closes #{ISSUE_NUMBER} added}"
```

**If no PR exists** (first issue in the feature, or single-issue mode):
```bash
gh pr create \
  --title "{type}: {Feature or Issue Description}" \
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

## Issues
Closes #{ISSUE_NUMBER}
EOF
)"
```

**PR Title Convention:**
- Feature-grouped: `feat: {Feature Name}` (from label, e.g., `feat: Safe bare clone`)
- Single-issue: `{type}: {Description} (#{N})`

### 11. Update DevBoard Status

Set issue status to "In Review":
```bash
gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwHOAP6mx84BNtCx\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lAHOAP6mx84BNtCxzg8nxFg\" value: { singleSelectOptionId: \"4cc61d42\" } }) { projectV2Item { id } } }"
```

### 12. Cleanup Worktree (After PR Merged)

**Only clean up when ALL issues in the feature group are done.**

For single-issue mode:
```bash
git worktree remove ../worktrees/issue-{N}
git worktree prune
```

For feature-grouped mode — check if other issues in the group are still open:
```bash
# List other issues with the same feature label
gh issue list --label "feature:{name}" --state open --json number --jq '.[].number'

# Only remove worktree if no open issues remain
git worktree remove ../worktrees/feat-{name}
git worktree prune
```

---

## Checklist

- [ ] Issue analyzed and understood
- [ ] Branch strategy determined (feature label / --branch / single-issue)
- [ ] DevBoard status updated to "In Progress"
- [ ] **Worktree created or reused** (critical for parallel work)
- [ ] Code implemented following project patterns
- [ ] **Tier 1 unit tests written and passing** (`./scripts/run_unit_tests.sh`)
- [ ] Documentation updated if needed
- [ ] Commit message follows convention (references individual issue)
- [ ] PR created or updated (references all issues in feature group)
- [ ] DevBoard status updated to "In Review"
- [ ] (Follow-up) Issue created for Tier 2 integration tests if applicable

---

## Related Documentation

- [Worktree Workflow Guide](../docs/guides/worktree-workflow.md)
- [Test Tier Strategy](../docs/guides/test-tier-strategy.md)
