#!/usr/bin/env python3
"""ClaudeVN Demo Data CLI.

Populates the system with realistic demo data organized in phases:
  Phase 1 - Foundation: Project, Git infrastructure, Auth (completed)
  Phase 2 - Execution: Dispatcher, Conflict resolution (mostly done)
  Phase 3 - Growth:    Marketplace, Frontend, active work (in-flight)

Usage:
  python -m demo_data                          # Populate all phases
  python -m demo_data --phase 1                # Phase 1 only
  python -m demo_data --phase 1,2              # Phases 1 and 2
  python -m demo_data --clear --populate       # Full reset
  python -m demo_data --status                 # Show counts
  python -m demo_data --delete                 # Delete ALL data
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
SCRIPT_DIR = Path(__file__).parent.parent  # scripts/
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from demo_data.cli import (
    clear_demo_data,
    clear_goals,
    clear_projects,
    clear_skills,
    clear_work,
    create_default_project,
    delete_all_data,
    get_status,
    populate_goals,
    populate_projects,
    populate_skills,
    populate_work,
    refresh_data,
)


def parse_phases(phase_str: str) -> list[int]:
    """Parse comma-separated phase numbers."""
    phases = []
    for p in phase_str.split(","):
        p = p.strip()
        if p.isdigit() and 1 <= int(p) <= 3:
            phases.append(int(p))
        else:
            print(f"Warning: Invalid phase '{p}' (must be 1, 2, or 3)")
    return sorted(set(phases)) if phases else [1, 2, 3]


def main():
    parser = argparse.ArgumentParser(
        prog="demo_data",
        description="""
ClaudeVN Demo Data Script

Populates the system with realistic demo data organized in phases:
  Phase 1 - Foundation: Project setup, Git infrastructure, Auth system
  Phase 2 - Execution:  Event-driven dispatcher, Conflict resolution
  Phase 3 - Growth:     Skill marketplace, Frontend, active in-flight work

Data is based on the real ClaudeVN project history.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                             Populate all phases
  %(prog)s --phase 1                   Only foundation data
  %(prog)s --phase 1,2                 Foundation + execution
  %(prog)s --populate --projects       Only populate projects
  %(prog)s --clear --goals             Clear only goals
  %(prog)s --refresh --work            Refresh work items
  %(prog)s --status                    Show current data counts
  %(prog)s --clear --populate          Full reset (clear then populate)
  %(prog)s --dry-run --clear           Preview what would be deleted
  %(prog)s --delete                    Delete ALL data
  %(prog)s --delete --start            Delete everything, create default project

Endpoints (must be running):
  Serving:     http://localhost:8002
  Marketplace: http://localhost:8003
        """,
    )

    # Action modes
    action_group = parser.add_argument_group("Actions")
    action_group.add_argument("--clear", action="store_true", help="Remove demo data")
    action_group.add_argument("--populate", action="store_true", help="Create demo data")
    action_group.add_argument("--refresh", action="store_true", help="Refresh timestamps on existing data")
    action_group.add_argument("--status", action="store_true", help="Show current data counts")
    action_group.add_argument("--delete", action="store_true", help="Delete ALL data (not just demo)")
    action_group.add_argument("--start", action="store_true", help="Create a default project")

    # Phase selection
    parser.add_argument(
        "--phase",
        type=str,
        default="1,2,3",
        help="Comma-separated phases to include (1,2,3). Default: all",
    )

    # Category filters
    cat_group = parser.add_argument_group("Category Filters")
    cat_group.add_argument("--projects", action="store_true", help="Only affect projects")
    cat_group.add_argument("--goals", action="store_true", help="Only affect goals")
    cat_group.add_argument("--work", action="store_true", help="Only affect work items and issues")
    cat_group.add_argument("--skills", action="store_true", help="Only affect skills")

    # Options
    opt_group = parser.add_argument_group("Options")
    opt_group.add_argument("--seed", type=int, default=None, help="Random seed for reproducible data")
    opt_group.add_argument("--count", type=int, default=0, help="Limit items per category")
    opt_group.add_argument("--serving-url", default="http://localhost:8002", help="Serving API URL")
    opt_group.add_argument("--marketplace-url", default="http://localhost:8003", help="Marketplace API URL")
    opt_group.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    opt_group.add_argument("-n", "--dry-run", action="store_true", help="Preview without making changes")

    args = parser.parse_args()
    phases = parse_phases(args.phase)

    # Determine categories
    categories = []
    if args.projects:
        categories.append("projects")
    if args.goals:
        categories.append("goals")
    if args.work:
        categories.append("work")
    if args.skills:
        categories.append("skills")

    # Default action: populate
    if not any([args.clear, args.populate, args.refresh, args.status, args.delete, args.start]):
        args.populate = True

    async def run():
        # Status check
        if args.status:
            print("\n=== ClaudeVN Demo Data Status ===")
            status = await get_status(args.serving_url, args.marketplace_url)

            print(f"\n  Serving ({args.serving_url}):")
            for key, val in status["serving"].items():
                print(f"    {key}: {val}")

            print(f"\n  Marketplace ({args.marketplace_url}):")
            for key, val in status["marketplace"].items():
                print(f"    {key}: {val}")

            if status["errors"]:
                print("\n  Errors:")
                for err in status["errors"]:
                    print(f"    {err}")

            print()
            return

        # Delete ALL data
        if args.delete:
            print("\n=== Deleting ALL Data ===")
            results = await delete_all_data(
                dry_run=args.dry_run,
                serving_url=args.serving_url,
                marketplace_url=args.marketplace_url,
            )
            print(f"\n  Deleted: {results}")

            if args.start:
                print("\n=== Creating Default Project ===")
                await create_default_project(
                    dry_run=args.dry_run,
                    serving_url=args.serving_url,
                )
            return

        # Start (create default project)
        if args.start and not args.clear and not args.populate:
            print("\n=== Creating Default Project ===")
            await create_default_project(
                dry_run=args.dry_run,
                serving_url=args.serving_url,
            )
            return

        # Clear demo data
        if args.clear:
            print("\n=== Clearing Demo Data ===")
            if not categories:
                results = await clear_demo_data(
                    phases=phases,
                    dry_run=args.dry_run,
                    serving_url=args.serving_url,
                    marketplace_url=args.marketplace_url,
                )
                print(f"\n  Cleared: {results}")
            else:
                if "projects" in categories:
                    count = await clear_projects(args.dry_run, args.verbose, args.serving_url)
                    print(f"  Cleared {count} projects")
                if "goals" in categories:
                    count = await clear_goals(args.dry_run, args.verbose, args.serving_url)
                    print(f"  Cleared {count} goals")
                if "work" in categories:
                    count = await clear_work(args.dry_run, args.verbose, args.serving_url)
                    print(f"  Cleared {count} work items/issues")
                if "skills" in categories:
                    count = await clear_skills(args.dry_run, args.verbose, args.marketplace_url)
                    print(f"  Cleared {count} skills")

        # Refresh data
        if args.refresh:
            print("\n=== Refreshing Demo Data ===")
            results = await refresh_data(
                categories=categories,
                dry_run=args.dry_run,
                verbose=args.verbose,
                serving_url=args.serving_url,
                marketplace_url=args.marketplace_url,
            )
            print(f"\n  Refreshed: {results}")
            return

        # Populate demo data
        if args.populate:
            phase_names = {1: "Foundation", 2: "Execution", 3: "Growth"}
            phase_str = ", ".join(f"{p} ({phase_names[p]})" for p in phases)
            print(f"\n=== Populating Demo Data [Phases: {phase_str}] ===")

            if not categories or "projects" in categories:
                count = await populate_projects(
                    phases=phases,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    count=args.count,
                    seed=args.seed,
                    serving_url=args.serving_url,
                )
                print(f"  Created {count} projects")

            if not categories or "goals" in categories:
                count = await populate_goals(
                    phases=phases,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    count=args.count,
                    seed=args.seed,
                    serving_url=args.serving_url,
                )
                print(f"  Created {count} goals")

            if not categories or "work" in categories:
                count = await populate_work(
                    phases=phases,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    count=args.count,
                    seed=args.seed,
                    serving_url=args.serving_url,
                )
                print(f"  Created {count} issues + work items")

            if not categories or "skills" in categories:
                count = await populate_skills(
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    count=args.count,
                    seed=args.seed,
                    marketplace_url=args.marketplace_url,
                )
                print(f"  Created {count} skills")

            print("\n  Done!")

    asyncio.run(run())


if __name__ == "__main__":
    main()
