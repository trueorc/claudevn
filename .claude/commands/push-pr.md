# Push PR

Create a Pull Request for a feature integration branch, automatically associating all related issues so they close on merge.

## Arguments
- `$ARGUMENTS` - The feature name (from `feature:*` label) or integration branch name
  - Examples: `user-identity`, `feat/safe-clone`, `feature:user-identity`

## Workflow

### 1. Resolve the Integration Branch

Parse the argument to determine the integration branch:

```bash
ARG="$ARGUMENTS"

# Strip "feature:" prefix if present
FEATURE_NAME="${ARG#feature:}"

# If it already looks like a branch name (contains /), use as-is
if [[ "$FEATURE_NAME" == */* ]]; then
    INTEGRATION_BRANCH="$FEATURE_NAME"
    # Extract feature name from branch for label lookup
    FEATURE_LABEL_NAME="${FEATURE_NAME#feat/}"
else
    INTEGRATION_BRANCH="feat/${FEATURE_NAME}"
    FEATURE_LABEL_NAME="$FEATURE_NAME"
fi
```

### 2. Verify the Branch Exists

```bash
git fetch origin "$INTEGRATION_BRANCH"
```

If it doesn't exist, report an error and stop.

### 3. Find All Associated Issues

Find issues tied to this feature using two methods:

**Method A: Feature label** (preferred)
```bash
FEATURE_ISSUES=$(gh issue list \
  --repo trueorc/claudevn \
  --label "feature:${FEATURE_LABEL_NAME}" \
  --state all \
  --json number,title,state \
  --jq '.')
```

**Method B: Git log** (fallback — scan commits on the integration branch for issue references)
```bash
# Get commits on integration branch not on main
COMMIT_ISSUES=$(git log origin/main..origin/"$INTEGRATION_BRANCH" --oneline \
  | grep -oP '#\d+' \
  | sort -u)
```

Combine both sources, deduplicate by issue number.

### 4. Verify All Issues are Complete

Check that all associated issues have their work merged into the integration branch. Report status:

```
Feature: {FEATURE_LABEL_NAME}
Branch:  {INTEGRATION_BRANCH}

Associated Issues:
  #42  [closed] Add user login endpoint
  #43  [closed] Add session management
  #44  [open]   Add password reset flow   ⚠️ still open

Commits on branch: {count}
```

If any issues are still open, warn the user and ask whether to proceed. Open issues will still be listed in the PR body with `Closes` keywords — they will auto-close when the PR merges.

### 5. Build the PR Body

Construct the PR body with `Closes #N` for every associated issue. GitHub auto-closes issues with these keywords on merge.

```
## Summary
Brief description synthesized from the associated issue titles.

## Issues
Closes #42
Closes #43
Closes #44

## Changes
- List key changes pulled from commit messages on the integration branch

## Testing
- [ ] All Tier 1 unit tests passing
- [ ] Feature tested end-to-end
```

### 6. Build the PR Title

Synthesize from the feature name and issue titles:
```
feat: {Feature description} (#{first_issue}, #{second_issue}, ...)
```

Keep under 72 characters. If too many issues, use:
```
feat: {Feature description} ({N} issues)
```

### 7. Create the PR

```bash
gh pr create \
  --repo trueorc/claudevn \
  --head "$INTEGRATION_BRANCH" \
  --base main \
  --title "$PR_TITLE" \
  --body "$PR_BODY"
```

If a PR already exists for this branch, update it instead:
```bash
EXISTING_PR=$(gh pr list --repo trueorc/claudevn --head "$INTEGRATION_BRANCH" --json number --jq '.[0].number')
if [ -n "$EXISTING_PR" ]; then
    gh pr edit "$EXISTING_PR" --title "$PR_TITLE" --body "$PR_BODY"
fi
```

### 8. Update Project Board

Set all associated issues to "In Review":
```bash
for ISSUE_NUM in $ALL_ISSUE_NUMBERS; do
    ITEM_ID=$(gh api graphql -f query="{ repository(owner: \"trueorc\", name: \"claudevn\") { issue(number: $ISSUE_NUM) { projectItems(first: 1) { nodes { id } } } } }" --jq '.data.repository.issue.projectItems.nodes[0].id')

    if [ -n "$ITEM_ID" ] && [ "$ITEM_ID" != "null" ]; then
        gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"PVT_kwDOD6FTDM4BQFhJ\" itemId: \"$ITEM_ID\" fieldId: \"PVTSSF_lADOD6FTDM4BQFhJzg-Tsck\" value: { singleSelectOptionId: \"4cc61d42\" } }) { projectV2Item { id } } }"
    fi
done
```

### 9. Report

```
PR created/updated: <URL>
Branch: {INTEGRATION_BRANCH} → main

Issues associated ({count}):
  Closes #42 — Add user login endpoint
  Closes #43 — Add session management
  Closes #44 — Add password reset flow

Board: All issues set to "In Review"

When this PR is merged, GitHub will automatically close all listed issues.
```

## Rules

- ALWAYS use `Closes #N` (not `Fixes` or `Resolves`) for consistency
- Every issue found via label OR commit history gets a `Closes` line
- If no issues are found, warn the user — a feature PR without issue associations defeats the purpose
- Never force-push or modify the integration branch content — this command only creates/updates the PR
- Ask for confirmation before creating the PR, showing the title, body preview, and issue list
