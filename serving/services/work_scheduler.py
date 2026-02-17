"""Multi-bucket priority scheduler for work dispatch.

Provides priority-ordered work item selection across task type buckets.
Used by the WorkDispatcher to decide what to assign next when computes
are available.

Bucket priority (highest to lowest):
  1. decomposition  — Unblocks all downstream characterization + execution
  2. characterization — Unblocks issue creation and execution ordering
  3. execution       — BucketTree-ordered work items (execution internals
                       are governed by the BucketTree and planner profile;
                       this scheduler only provides the top-level ordering
                       between task type categories)

Design reference: GitHub issue #874, §2 Multi-Bucket Priority Scheduler
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BucketCategory(str, Enum):
    """Top-level task type categories, ordered by priority."""
    DECOMPOSITION = "decomposition"
    CHARACTERIZATION = "characterization"
    EXECUTION = "execution"


@dataclass
class SchedulerResult:
    """Result of a scheduler selection cycle."""
    bucket: BucketCategory
    items: List[Any]  # Task objects (CharacterizationTask, DecompositionTask, or WorkItem)
    skipped_buckets: List[BucketCategory]


class WorkScheduler:
    """Multi-bucket priority scheduler.

    Selects the next batch of work items across priority buckets given a
    count of available idle computes.

    The execution bucket internals (BucketTree ordering, planner profiles,
    etc.) are handled by the WorkOrchestrator — this scheduler only queries
    the top-level category priority.
    """

    def select_next(
        self,
        decomp_queue: List[Any],
        char_queue: List[Any],
        idle_count: int,
    ) -> SchedulerResult:
        """Select the next batch of items to assign.

        Iterates buckets in priority order and fills up to idle_count items
        from the highest-priority non-empty bucket. Mixed-bucket batches
        (e.g., 1 char + 1 execution) are supported: if a bucket is exhausted
        before filling the batch, the scheduler moves to the next bucket.

        Args:
            decomp_queue: Pending DecompositionTask objects
            char_queue: Pending CharacterizationTask objects
            idle_count: Number of idle computes available

        Returns:
            SchedulerResult with the selected items and skipped buckets
        """
        if idle_count <= 0:
            return SchedulerResult(
                bucket=BucketCategory.DECOMPOSITION,
                items=[],
                skipped_buckets=[],
            )

        selected: List[Any] = []
        first_bucket: Optional[BucketCategory] = None
        skipped: List[BucketCategory] = []

        # Priority bucket iteration
        buckets = [
            (BucketCategory.DECOMPOSITION, decomp_queue),
            (BucketCategory.CHARACTERIZATION, char_queue),
            # Execution is handled externally by WorkOrchestrator
        ]

        for category, queue in buckets:
            remaining_slots = idle_count - len(selected)
            if remaining_slots <= 0:
                break

            if not queue:
                skipped.append(category)
                continue

            # Take up to remaining_slots items from this bucket
            batch = queue[:remaining_slots]
            if batch:
                if first_bucket is None:
                    first_bucket = category
                selected.extend(batch)

        return SchedulerResult(
            bucket=first_bucket or BucketCategory.EXECUTION,
            items=selected,
            skipped_buckets=skipped,
        )

    def describe_bucket_state(
        self,
        decomp_queue: List[Any],
        char_queue: List[Any],
        idle_count: int,
    ) -> Dict[str, Any]:
        """Return a human-readable description of current scheduling state."""
        return {
            "idle_computes": idle_count,
            "decomp_pending": len(decomp_queue),
            "char_pending": len(char_queue),
            "priority_order": [b.value for b in BucketCategory],
        }
