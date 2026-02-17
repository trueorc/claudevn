#!/usr/bin/env python3
"""
Migration script to install Git hooks on existing bare repositories.

This script ensures all bare repositories have the latest ClaudeVN Git hooks
installed (pre-receive and post-receive). It is idempotent and safe to run
multiple times.

Usage:
    python scripts/migrate_hooks.py [--repos-path PATH] [--dry-run]

Examples:
    # Run migration with default config
    python scripts/migrate_hooks.py

    # Preview what would be done without making changes
    python scripts/migrate_hooks.py --dry-run

    # Use custom repos path
    python scripts/migrate_hooks.py --repos-path /custom/path/to/repos
"""

import argparse
import sys
from pathlib import Path

# Add serving directory to path for imports
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SERVING_DIR = PROJECT_ROOT / "serving"
sys.path.insert(0, str(SERVING_DIR))

from git.repo_manager import RepoManager
from config import get_config, GitConfig


def main():
    parser = argparse.ArgumentParser(
        description="Install Git hooks on all existing bare repositories"
    )
    parser.add_argument(
        "--repos-path",
        type=str,
        help="Path to bare repositories directory (default: from config)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be done without making changes"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output"
    )
    args = parser.parse_args()

    # Get repos path
    if args.repos_path:
        config = GitConfig(repos_path=args.repos_path)
    else:
        config = get_config().git

    repos_path = Path(config.repos_path)

    print(f"Git Hook Migration Script")
    print(f"=" * 50)
    print(f"Repos path: {repos_path}")
    print()

    if not repos_path.exists():
        print(f"ERROR: Repos path does not exist: {repos_path}")
        sys.exit(1)

    # Create repo manager
    repo_manager = RepoManager(config=config)

    # List all repos
    repos = repo_manager.list_repos()

    if not repos:
        print("No repositories found.")
        sys.exit(0)

    print(f"Found {len(repos)} repositories")
    print()

    if args.dry_run:
        print("DRY RUN - No changes will be made")
        print()

    # Track results
    success_count = 0
    failed_count = 0
    results = []

    for project in repos:
        # Check current hook status
        try:
            hook_status = repo_manager.verify_hooks(project)
        except Exception as e:
            print(f"  ERROR: Could not check hooks for {project}: {e}")
            failed_count += 1
            results.append((project, "error", str(e)))
            continue

        if hook_status["hooks_installed"]:
            if args.verbose:
                print(f"  [OK] {project} - hooks already installed")
            success_count += 1
            results.append((project, "already_installed", None))
            continue

        # Install hooks
        if args.dry_run:
            print(f"  [DRY RUN] {project} - would install hooks")
            results.append((project, "would_install", None))
        else:
            try:
                repo_manager.install_hooks(project)
                print(f"  [INSTALLED] {project}")
                success_count += 1
                results.append((project, "installed", None))
            except Exception as e:
                print(f"  [FAILED] {project}: {e}")
                failed_count += 1
                results.append((project, "failed", str(e)))

    # Print summary
    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"Total repositories: {len(repos)}")

    if args.dry_run:
        would_install = sum(1 for r in results if r[1] == "would_install")
        already_ok = sum(1 for r in results if r[1] == "already_installed")
        print(f"Already have hooks: {already_ok}")
        print(f"Would install hooks: {would_install}")
    else:
        print(f"Successfully processed: {success_count}")
        print(f"Failed: {failed_count}")

    if failed_count > 0:
        print()
        print("Failed repositories:")
        for project, status, error in results:
            if status in ("failed", "error"):
                print(f"  - {project}: {error}")
        sys.exit(1)

    print()
    print("Migration complete!")


if __name__ == "__main__":
    main()
