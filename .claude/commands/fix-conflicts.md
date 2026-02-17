# Fix Merge Conflicts Workflow

Resolve merge conflicts from a pull request strategically and safely.

## Arguments
- `$ARGUMENTS` - Pull request number (e.g., `123`)

## Workflow

### 1. Fetch PR Information

```bash
gh pr view $ARGUMENTS --json title,body,headRefName,baseRefName,files,mergeable,mergeStateStatus
```

Understand:
- **Head branch** - The feature branch with changes
- **Base branch** - Target branch (usually `main`)
- **Changed files** - What the PR modifies
- **Merge state** - Why it can't merge

### 2. Checkout and Update Branches

```bash
# Fetch latest from remote
git fetch origin

# Checkout the PR branch
gh pr checkout $ARGUMENTS

# Get current branch name
BRANCH=$(git branch --show-current)
```

### 3. Attempt Merge to Identify Conflicts

```bash
# Try merging base into head to see conflicts
git merge origin/main --no-commit --no-ff
```

If conflicts exist, Git will list them.

### 4. Analyze Conflict Types

For each conflicted file, determine the conflict type:

| Type | Description | Resolution Strategy |
|------|-------------|---------------------|
| **Content** | Both branches modified same lines | Manual merge - understand both changes |
| **Add/Add** | Both branches added file with same name | Keep one or merge contents |
| **Modify/Delete** | One branch modified, other deleted | Decide: keep modified or confirm delete |
| **Rename** | File renamed differently in each branch | Choose canonical name |

### 5. Resolve Each Conflict

**For Python files:**
- Check imports - may need both sets
- Service changes - ensure singleton pattern preserved
- Model changes - validate Pydantic v2 patterns
- Test changes - may need to merge test cases

**For React/JS files:**
- Component changes - preserve hook dependencies
- State changes - ensure consistency
- Import changes - deduplicate

**For each conflict:**
1. Open the file and find conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
2. Understand what each side intended
3. Write the correct merged result
4. Remove conflict markers
5. Stage the resolved file

```bash
# After resolving a file
git add {resolved-file}
```

### 6. Validate Resolution

**Run tests to ensure nothing broke:**

```bash
# Run unit tests
./scripts/run_unit_tests.sh -v

# Frontend tests (if JS files changed)
cd serving/frontend && npm test
```

**Check for:**
- [ ] All tests pass
- [ ] No syntax errors
- [ ] Imports resolve correctly
- [ ] No duplicate code accidentally introduced

### 7. Complete the Merge

```bash
# If all conflicts resolved and tests pass
git commit -m "merge: Resolve conflicts with main (#$ARGUMENTS)"
```

### 8. Push Resolution

```bash
git push origin $BRANCH
```

### 9. Verify PR Status

```bash
gh pr view $ARGUMENTS --json mergeable,mergeStateStatus,statusCheckRollup
```

Confirm:
- [ ] PR is now mergeable
- [ ] CI checks are running/passing

## Conflict Resolution Patterns

### Pattern: Service Method Signature Change

Both branches modified a service method differently.

**Resolution:**
1. Identify the intended functionality from each branch
2. Combine parameters if both are needed
3. Ensure backwards compatibility or update all callers
4. Update tests to cover combined behavior

### Pattern: Model Field Additions

Both branches added fields to the same Pydantic model.

**Resolution:**
1. Keep all new fields from both branches
2. Check for naming conflicts
3. Ensure `Field()` defaults are appropriate
4. Update any affected API routes

### Pattern: React Component Props

Both branches modified component props.

**Resolution:**
1. Merge prop definitions
2. Update PropTypes or JSDoc
3. Check all component usages
4. Update tests

### Pattern: Import Conflicts

Both branches added different imports.

**Resolution:**
1. Keep all necessary imports
2. Remove duplicates
3. Organize by convention (stdlib, third-party, local)
4. Remove unused imports

## Rollback if Needed

If resolution goes wrong:

```bash
# Abort the merge attempt
git merge --abort

# Or reset to before merge
git reset --hard origin/$BRANCH
```

## Checklist

- [ ] PR information fetched and understood
- [ ] Branches updated from remote
- [ ] Conflicts identified and categorized
- [ ] Each conflict resolved thoughtfully
- [ ] All tests pass after resolution
- [ ] Merge committed with descriptive message
- [ ] Changes pushed to remote
- [ ] PR verified as mergeable
