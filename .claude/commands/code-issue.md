# Code Issue Workflow

Take a GitHub issue through the full development cycle: analyze, code, test, document, and PR.

## Arguments
- `$ARGUMENTS` - GitHub issue number, optionally followed by `--branch <branch-name>`
  - Examples: `42`, `42 --branch feat/safe-clone`

## Feature Grouping

Issues can share a single PR and integration branch using one of two methods:

1. **Label-based** (preferred): Add a `feature:*` label to related issues (e.g., `feature:safe-clone`). All issues with the same feature label share integration branch `feat/{feature-name}` and a single PR.
2. **Explicit**: Pass `--branch <name>` to specify the integration branch directly.
3. **Default**: No feature label and no `--branch` → one branch per issue (single-issue mode, unchanged).

## Critical: Parallel Isolation via Sub-branches

Git worktrees cannot check out the same branch simultaneously. In feature-grouped mode, **each instance gets its own sub-branch and worktree**:

```
main
 └── feat/{feature-name}            ← integration branch (PR source, no permanent worktree)
      ├── feat/{feature-name}-{N}   ← instance 1's worktree
      ├── feat/{feature-name}-{M}   ← instance 2's worktree
      └── feat/{feature-name}-{K}   ← instance 3's worktree
```

Each instance:
1. Creates sub-branch `feat/{feature-name}-{ISSUE_NUMBER}` off the integration branch
2. Works and commits on the sub-branch in its own worktree
3. When done, merges the sub-branch into the integration branch (via a temporary worktree)
4. PR is opened/updated from the integration branch to main

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
- **Priority** - P0/P1/P2 for urgency context
- **Feature label** - Any `feature:*` label for branch grouping

### 2. Determine Branch Strategy

Parse `$ARGUMENTS` to extract the issue number and optional `--branch` flag.

Then determine branches using this priority:

1. **`feature:*` label found** on the issue:
   - Extract feature name from label (e.g., `feature:safe-clone` → `safe-clone`)
   - Integration branch: `feat/{feature-name}` (e.g., `feat/safe-clone`)
   - Sub-branch: `feat/{feature-name}-{ISSUE_NUMBER}` (e.g., `feat/safe-clone-42`)
   - Worktree: `../worktrees/feat-{feature-name}-{ISSUE_NUMBER}`

2. **`--branch` flag provided** in arguments:
   - Integration branch: use the provided name exactly (e.g., `feat/safe-clone`)
   - Sub-branch: `{provided-branch}-{ISSUE_NUMBER}` (e.g., `feat/safe-clone-42`)
   - Worktree: `../worktrees/{branch-dashes}-{ISSUE_NUMBER}`

3. **Neither** (default — single-issue mode, unchanged):
   - Branch: `{type}/issue-{N}-{short-description}` (type from issue labels: bug→fix, enhancement→feat, etc.)
   - Worktree: `../worktrees/issue-{N}`
   - No integration branch; this branch IS the PR source.

### 3. Update DevBoard Status

Set issue status to "In Progress":
```bash
ITEM_ID=$(gh api graphql -f query='{ repository(owner: "trueorc", name: "claudevn") { issue(number: {ISSUE_NUMBER}) { projectItems(first: 1) { nodes { id } } } } }' --jq '.data.repository.issue.projectItems.nodes[0].id')

gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwDOD6FTDM4BQFhJ\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lADOD6FTDM4BQFhJzg-Tsck\" value: { singleSelectOptionId: \"47fc9ee4\" } }) { projectV2Item { id } } }"
```

If the issue is not yet on the board, add it first:
```bash
ISSUE_NODE_ID=$(gh api graphql -f query='{ repository(owner: "trueorc", name: "claudevn") { issue(number: {ISSUE_NUMBER}) { id } } }' --jq '.data.repository.issue.id')

ITEM_ID=$(gh api graphql -f query="mutation { addProjectV2ItemById(input: { projectId: \"PVT_kwDOD6FTDM4BQFhJ\" contentId: \"$ISSUE_NODE_ID\" }) { item { id } } }" --jq '.data.addProjectV2ItemById.item.id')
```

### 4. Set Up Worktree

```bash
git fetch origin main
mkdir -p ../worktrees
```

**Single-issue mode** (no feature label, no `--branch`): Unchanged behavior.

```bash
if git ls-remote --heads origin {single-issue-branch} | grep -q {single-issue-branch}; then
    git worktree add ../worktrees/issue-{N} {single-issue-branch}
else
    git worktree add ../worktrees/issue-{N} -b {single-issue-branch} origin/main
fi
cd ../worktrees/issue-{N}
```

**Feature-grouped mode** (label-based or `--branch`): Two-phase setup.

**Phase 1: Ensure integration branch exists on remote.**

```bash
INTEGRATION_BRANCH="feat/{feature-name}"
SUB_BRANCH="feat/{feature-name}-{ISSUE_NUMBER}"
SUB_WORKTREE="../worktrees/feat-{feature-name}-{ISSUE_NUMBER}"

if git ls-remote --heads origin "$INTEGRATION_BRANCH" | grep -q "$INTEGRATION_BRANCH"; then
    # Integration branch already exists — fetch it
    git fetch origin "$INTEGRATION_BRANCH"
else
    # First instance: create integration branch from origin/main via temp worktree
    TEMP_WORKTREE="../worktrees/tmp-integration-$$"
    git worktree add "$TEMP_WORKTREE" -b "$INTEGRATION_BRANCH" origin/main
    # Push — if another instance already created it, this will fail; that's OK
    if ! git -C "$TEMP_WORKTREE" push -u origin "$INTEGRATION_BRANCH" 2>/dev/null; then
        echo "Integration branch was created by another instance — fetching."
        git fetch origin "$INTEGRATION_BRANCH"
    fi
    git worktree remove "$TEMP_WORKTREE"
    git fetch origin "$INTEGRATION_BRANCH"
fi
```

**Phase 2: Create sub-branch and worktree for this instance.**

Sub-branch is always based off the integration branch (not main) to pick up prior work from other instances.

```bash
if [ -d "$SUB_WORKTREE" ]; then
    # Resumed session — reuse existing worktree
    cd "$SUB_WORKTREE"
    git pull origin "$SUB_BRANCH" 2>/dev/null || true
elif git ls-remote --heads origin "$SUB_BRANCH" | grep -q "$SUB_BRANCH"; then
    # Sub-branch exists on remote (resumed session): track it
    git worktree add "$SUB_WORKTREE" "$SUB_BRANCH"
    cd "$SUB_WORKTREE"
else
    # Fresh start: create sub-branch from current tip of integration branch
    git worktree add "$SUB_WORKTREE" -b "$SUB_BRANCH" "origin/$INTEGRATION_BRANCH"
    cd "$SUB_WORKTREE"
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

### 10. Push, Merge Up, and Create/Update PR

**Single-issue mode**: Push directly and create PR.

```bash
git push -u origin {single-issue-branch}
# Then create PR (see PR creation below)
```

**Feature-grouped mode**: Three-phase process.

**Phase 1: Push sub-branch.**

```bash
git push -u origin "$SUB_BRANCH"
```

**Phase 2: Merge sub-branch into integration branch.**

Use a temporary worktree for the integration branch.

```bash
TEMP_MERGE_WORKTREE="../worktrees/tmp-merge-${ISSUE_NUMBER}-$$"

# Fetch latest integration branch
git fetch origin "$INTEGRATION_BRANCH"

# Create temp worktree on integration branch
git worktree add "$TEMP_MERGE_WORKTREE" "$INTEGRATION_BRANCH"
cd "$TEMP_MERGE_WORKTREE"

# Pull latest to ensure we're current
git pull origin "$INTEGRATION_BRANCH"

# Merge the sub-branch with --no-ff to preserve history
git merge --no-ff "$SUB_BRANCH" -m "merge: integrate #${ISSUE_NUMBER} into ${INTEGRATION_BRANCH}"
```

If conflicts occur during merge-up, resolve them in the temp worktree. The sub-branch worktree is still available at `$SUB_WORKTREE` for reference:

```bash
# After resolving conflicts:
git add {resolved-files}
git commit -m "merge: resolve conflicts integrating #${ISSUE_NUMBER}"
```

**Phase 3: Push integration branch and clean up temp worktree.**

```bash
git push origin "$INTEGRATION_BRANCH"

# Return to repo root and clean up
cd {repo-root}
git worktree remove "$TEMP_MERGE_WORKTREE"
git worktree prune
```

**Create PR (single-issue mode only):**

In single-issue mode, create the PR now:

```bash
gh pr create \
  --head "{single-issue-branch}" \
  --base main \
  --title "{type}: {Description} (#{N})" \
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

**Feature-grouped mode: Do NOT create a PR.** The user will create the PR manually when all issues in the feature are complete. Just report what was merged into the integration branch and list any remaining open issues in the feature group:

```bash
OPEN_ISSUES=$(gh issue list --label "feature:{name}" --state open --json number,title --jq '.[] | "#\(.number) \(.title)"')
echo "Merged #${ISSUE_NUMBER} into ${INTEGRATION_BRANCH}."
echo "Remaining open issues in feature group:"
echo "$OPEN_ISSUES"
```

### 11. Update DevBoard Status

Re-fetch the project item ID (shell state from Step 3 is not preserved between commands):

```bash
ITEM_ID=$(gh api graphql -f query='{ repository(owner: "trueorc", name: "claudevn") { issue(number: {ISSUE_NUMBER}) { projectItems(first: 1) { nodes { id } } } } }' --jq '.data.repository.issue.projectItems.nodes[0].id')
```

**Single-issue mode** — set to "In Review":
```bash
gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwDOD6FTDM4BQFhJ\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lADOD6FTDM4BQFhJzg-Tsck\" value: { singleSelectOptionId: \"4cc61d42\" } }) { projectV2Item { id } } }"
```

**Feature-grouped mode** — set to "Testing" (the issue's code is complete and merged into the integration branch, awaiting the feature PR):
```bash
gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwDOD6FTDM4BQFhJ\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lADOD6FTDM4BQFhJzg-Tsck\" value: { singleSelectOptionId: \"60064e37\" } }) { projectV2Item { id } } }"
```

### 12. Cleanup

**Single-issue mode** (after PR merged):
```bash
git worktree remove ../worktrees/issue-{N}
git worktree prune
```

**Feature-grouped mode** — two layers of cleanup:

**Layer 1: Sub-branch worktree (immediate — after merge-up in Step 10).**

Once the sub-branch is merged into the integration branch and pushed, clean up:

```bash
git worktree remove "$SUB_WORKTREE"
git push origin --delete "$SUB_BRANCH"  # optional: sub-branch work is in integration branch
git worktree prune
```

**Layer 2: Integration branch (deferred — only after PR is merged AND all issues done).**

The integration branch has no permanent worktree. After the PR is merged to main:

```bash
# Check if sibling issues in the feature group are still open
OPEN_ISSUES=$(gh issue list --label "feature:{name}" --state open --json number --jq '.[].number')

if [ -z "$OPEN_ISSUES" ]; then
    git push origin --delete "feat/{feature-name}"
    echo "Integration branch cleaned up."
else
    echo "Other issues still open: $OPEN_ISSUES — leaving integration branch."
fi
```

---

## Checklist

- [ ] Issue analyzed and understood
- [ ] Branch strategy determined (feature label / --branch / single-issue)
- [ ] DevBoard status updated to "In Progress"
- [ ] **Integration branch created or confirmed** (feature-grouped mode)
- [ ] **Sub-branch worktree created** (feature-grouped: `feat/{name}-{N}`, single-issue: `issue-{N}`)
- [ ] Code implemented following project patterns
- [ ] **Tier 1 unit tests written and passing** (`./scripts/run_unit_tests.sh`)
- [ ] Documentation updated if needed
- [ ] Commit message follows convention (references individual issue number)
- [ ] **Sub-branch pushed** (feature-grouped mode)
- [ ] **Sub-branch merged into integration branch** (feature-grouped mode)
- [ ] **Temp merge worktree removed** (feature-grouped mode)
- [ ] PR created (single-issue mode only; feature-grouped mode skips PR)
- [ ] DevBoard status updated ("In Review" for single-issue, "Testing" for feature-grouped)
- [ ] **Sub-branch worktree removed** (feature-grouped mode)
- [ ] Remaining open issues reported (feature-grouped mode)
- [ ] (Follow-up) Issue created for Tier 2 integration tests if applicable

---

## Related Documentation

- [Worktree Workflow Guide](../docs/guides/worktree-workflow.md)
- [Test Tier Strategy](../docs/guides/test-tier-strategy.md)
