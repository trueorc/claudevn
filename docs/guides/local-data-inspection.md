# Local Data Directory Inspection

By default, serving data (Git repos, SSH keys, workspaces) lives inside Docker named volumes, requiring `docker exec` to inspect. You can bind-mount the data directory locally for easier access during development.

## Setup

Create a `docker-compose.override.yml` in the project root (already in `.gitignore`):

```yaml
services:
  serving:
    volumes:
      - ./data/serving:/app/data
```

Then restart:

```bash
docker compose down && docker compose up -d
```

The `./data/serving/` directory will appear locally with:

```
data/serving/
  repos/          # Git bare repositories (one per project)
  ssh_keys/       # Compute SSH keys
  workspaces/     # Compute worktree workspaces
  claude-credentials  # Claude API credentials (preserved across purges)
```

## Inspecting Git Repos

```bash
# List repos
ls data/serving/repos/

# View branches in a project repo
git -C data/serving/repos/<project>.git branch -a

# View commit log for a branch
git -C data/serving/repos/<project>.git log --oneline <branch>

# View diff between branch and main
git -C data/serving/repos/<project>.git diff main..<branch>
```

## Notes

- The `docker-compose.override.yml` is automatically merged by Docker Compose (no extra flags needed)
- If switching from named volumes to bind-mount, existing data in the named volume will **not** be copied. Start fresh or manually copy data first
- Claude credentials stored in `data/serving/claude-credentials` persist across container restarts
- The override file is in `.gitignore` so it won't be committed
