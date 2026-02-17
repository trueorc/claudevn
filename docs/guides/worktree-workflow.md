# Git Worktree Workflow Guide

**Version**: 1.0.0
**Last Updated**: January 2026
**Audience**: Compute Instances (Claude Code)

---

## Overview

ClaudeVN v1.0 uses Git worktrees to enable compute instances to:
- Maintain a read-only reference to `main` branch
- Work on feature branches without constant switching
- Resolve conflicts by comparing branches side-by-side

This guide explains how compute instances should set up and use worktrees.

---

## What is a Git Worktree?

A worktree is an additional working directory linked to the same Git repository. Instead of switching branches (which changes files in place), worktrees let you have multiple branches checked out simultaneously in different directories.

```
/workspace/
├── repo/               # Main clone (bare or with default branch)
├── main/               # Worktree: tracks origin/main
└── active/             # Worktree: current working branch
```

---

## Initial Setup

### Step 1: Clone the Repository

```bash
# Clone as a regular repo (not bare - we need a working directory)
git clone git@serving:/home/git/repos/{project}.git /workspace/repo
cd /workspace/repo
```

### Step 2: Create Main Worktree

The `main` worktree provides a read-only reference to the latest main branch.

```bash
# Create worktree for main branch
git worktree add /workspace/main main

# This creates:
# /workspace/main/  <- Contains files from main branch
```

### Step 3: Create Active Worktree

The `active` worktree is where you do actual work.

```bash
# Create worktree with a placeholder branch
git worktree add /workspace/active -b placeholder

# Or create with your first feature branch
git worktree add /workspace/active -b f/initial-task/compute-001
```

### Verify Setup

```bash
git worktree list
# Output:
# /workspace/repo    abc1234 [main]
# /workspace/main    abc1234 [main]
# /workspace/active  def5678 [f/initial-task/compute-001]
```

---

## Daily Workflow

### Starting a New Task

```bash
# 1. Update main reference
cd /workspace/main
git pull origin main

# 2. Go to active worktree
cd /workspace/active

# 3. Ensure we're on latest main
git checkout main
git pull origin main

# 4. Create feature branch
git checkout -b f/my-task/compute-001

# 5. Start working!
```

### Working on a Task

```bash
cd /workspace/active

# Make changes...
# Edit files, write code, etc.

# Stage changes
git add src/feature.py tests/test_feature.py

# Commit with descriptive message
git commit -m "Add user authentication endpoint

- Implement POST /api/auth/login
- Add JWT token generation
- Include bcrypt password hashing"

# Continue working, commit often...
```

### Pushing Your Work

```bash
cd /workspace/active

# Push to remote (first time creates the remote branch)
git push -u origin f/my-task/compute-001

# Subsequent pushes
git push
```

### Referencing Main While Working

Need to see how something is done in main? No need to switch branches:

```bash
# Your work is in /workspace/active
# Main branch is always available in /workspace/main

# Example: Check how auth is currently implemented
cat /workspace/main/src/auth/handler.py

# Compare your changes to main
diff /workspace/main/src/auth/handler.py /workspace/active/src/auth/handler.py

# Or use git diff
git diff main -- src/auth/handler.py
```

### Submitting for Review

```bash
cd /workspace/active

# Ensure all changes are committed
git status

# Push final changes
git push

# Signal ready for review (via MCP tool)
# claudevn_request_review(branch="f/my-task/compute-001")
```

---

## Conflict Resolution

When Serving reports a merge conflict, you need to rebase your branch onto the latest main.

### Step 1: Update Main Reference

```bash
cd /workspace/main
git pull origin main
```

### Step 2: Rebase Your Branch

```bash
cd /workspace/active

# Fetch latest from remote
git fetch origin

# Rebase onto main
git rebase origin/main
```

### Step 3: Resolve Conflicts

If conflicts occur:

```bash
# Git will stop and show conflicted files
git status
# Output:
# Unmerged paths:
#   both modified:   src/auth/handler.py

# Open the conflicted file and resolve
# Look for conflict markers: <<<<<<<, =======, >>>>>>>

# You can compare with main easily:
diff /workspace/main/src/auth/handler.py /workspace/active/src/auth/handler.py

# After resolving, stage the file
git add src/auth/handler.py

# Continue rebase
git rebase --continue
```

### Step 4: Push Updated Branch

```bash
# Force push is safe because it's your branch
git push --force-with-lease origin f/my-task/compute-001

# Signal ready for re-review
# claudevn_request_review(branch="f/my-task/compute-001")
```

---

## Multiple Tasks (Advanced)

If you need to work on multiple tasks simultaneously, create additional worktrees:

```bash
# Add worktree for second task
git worktree add /workspace/task-456 -b f/other-task/compute-001

# Now you have:
# /workspace/main/      <- main reference
# /workspace/active/    <- first task
# /workspace/task-456/  <- second task

# Switch between them by changing directories
cd /workspace/active      # Work on first task
cd /workspace/task-456    # Work on second task
```

### Cleanup Old Worktrees

```bash
# When done with a task, remove the worktree
git worktree remove /workspace/task-456

# Or if the directory was deleted manually:
git worktree prune
```

---

## Common Commands Reference

### Worktree Management

```bash
# List all worktrees
git worktree list

# Add new worktree
git worktree add <path> <branch>
git worktree add <path> -b <new-branch>  # Create new branch

# Remove worktree
git worktree remove <path>

# Clean up stale worktree references
git worktree prune
```

### Branch Operations (in active worktree)

```bash
# Create and switch to new branch
git checkout -b f/task-name/compute-001

# Switch to existing branch
git checkout f/other-task/compute-001

# Push new branch to remote
git push -u origin f/task-name/compute-001

# Push updates
git push

# Force push after rebase (safe for your branches)
git push --force-with-lease
```

### Keeping Up to Date

```bash
# Update main reference
cd /workspace/main && git pull origin main

# Update active branch with latest main
cd /workspace/active
git fetch origin
git rebase origin/main
```

### Comparing with Main

```bash
# See what you changed compared to main
git diff main

# See specific file difference
git diff main -- path/to/file.py

# Use the main worktree for side-by-side comparison
diff /workspace/main/file.py /workspace/active/file.py
```

---

## Best Practices

### DO

- **Keep main worktree read-only**: Never make changes in `/workspace/main`
- **Pull main before creating branches**: Start from latest main
- **Commit often**: Small, logical commits are easier to review
- **Write good commit messages**: Explain what and why
- **Push regularly**: Backup your work, enable visibility

### DON'T

- **Don't work directly on main**: Always create a feature branch
- **Don't force push to shared branches**: Only force push to your own branches
- **Don't delete the main worktree**: You need it for reference
- **Don't commit large generated files**: Add them to `.gitignore`

---

## Troubleshooting

### "fatal: 'main' is already checked out"

This happens when trying to checkout main in a worktree where it's already used.

```bash
# Solution: Use a different branch or update the existing main worktree
cd /workspace/main
git pull
```

### Worktree shows wrong branch

```bash
# Check worktree status
git worktree list

# If corrupted, remove and recreate
git worktree remove /workspace/active
git worktree add /workspace/active -b f/new-task/compute-001
```

### Merge conflicts during rebase

```bash
# See which files are conflicted
git status

# After resolving conflicts:
git add <resolved-files>
git rebase --continue

# If you want to abort and start over:
git rebase --abort
```

### Branch already exists on remote

```bash
# If the branch exists and you want to track it:
git checkout -b f/existing-task/compute-001 origin/f/existing-task/compute-001

# If you want to start fresh:
git push origin --delete f/old-branch/compute-001
git checkout -b f/old-branch/compute-001
```

---

## Related Documents

- [Git Infrastructure Design](../design/specifications/git-infrastructure.md)
- [v1.0 Architecture](../design/architecture/v1.0-architecture.md)
- [MCP Tools Specification](../design/specifications/mcp-tools.md)
