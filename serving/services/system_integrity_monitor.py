"""System Integrity Monitor — active agent that sweeps the full pipeline for anomalies.

Replaces ReconciliationManager with broader cross-cutting state machine validation.
Detects inconsistencies where work, issues, PRs, and goals fall out of sync,
attempts remediation through existing service methods, and emits notifications
when things are stuck. No more silent hangs.

Checks (run every sweep cycle):
  1. Merged branches with un-finalized work items
  2. Issues stuck after all work items completed
  3. Goals not finalized when all issues are done
  4. PRs stuck in CONFLICT (resolved) or APPROVED (not merging)
  5. Stale high-progress work on disconnected computes
  6. Pipeline stalls (READY issues or PENDING work with idle computes)
  7. Orphaned work assigned to disconnected computes
  8. Failed work items whose parent issue is still IN_PROGRESS
  9. Goals stuck in PLANNING (decomposition may have failed)
  10. Failed issues whose work PR is actually merged (recover to DONE)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Module-level singleton
_monitor: Optional["SystemIntegrityMonitor"] = None

# Cooldown seconds per check type — how long to wait before re-attempting
# remediation on the same entity
COOLDOWNS = {
    "merged_not_finalized": 120,
    "stuck_issue": 180,
    "stuck_goal": 300,
    "stuck_pr_conflict": 180,
    "stuck_pr_approved": 120,
    "stale_high_progress": 300,
    "pipeline_stall": 120,
    "orphaned_work": 120,
    "failed_work_impact": 180,
    "stuck_planning_goal": 300,
    "failed_issue_merged_pr": 120,
}

# How many consecutive detections before escalating notification to ERROR
ESCALATION_THRESHOLD = 3

# Clean up tracker entries after this many seconds of no re-detection
TRACKER_CLEANUP_SECONDS = 1800  # 30 minutes


@dataclass
class AnomalyResult:
    """Detected anomaly with remediation context."""
    check_type: str
    entity_type: str  # "work", "issue", "goal", "pr"
    entity_id: str
    project_id: Optional[str]
    description: str
    remediation_action: Optional[str]  # method name or None for notify-only
    context: Dict[str, Any] = field(default_factory=dict)


def get_system_integrity_monitor() -> "SystemIntegrityMonitor":
    global _monitor
    if _monitor is None:
        raise RuntimeError(
            "SystemIntegrityMonitor not initialized. "
            "Call start_system_integrity_monitor() first."
        )
    return _monitor


def set_system_integrity_monitor(monitor: "SystemIntegrityMonitor") -> None:
    global _monitor
    _monitor = monitor


class SystemIntegrityMonitor:
    """Background agent that sweeps the system for state machine inconsistencies."""

    def __init__(self, check_interval: int = 60) -> None:
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Throttling: "{check_type}:{entity_id}" -> tracking info
        self._attempt_tracker: Dict[str, Dict[str, Any]] = {}

        self._stats: Dict[str, Any] = {
            "cycles": 0,
            "anomalies_detected": 0,
            "anomalies_remediated": 0,
            "anomalies_failed": 0,
            "active_anomalies": 0,
            "last_sweep_duration_ms": 0,
            "last_sweep_at": None,
            "by_check_type": {k: {"detected": 0, "remediated": 0, "failed": 0}
                              for k in COOLDOWNS},
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._sweep_loop(), name="system-integrity-monitor"
        )
        logger.info(
            f"SystemIntegrityMonitor started (interval={self.check_interval}s)"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SystemIntegrityMonitor stopped")

    def is_running(self) -> bool:
        return self._running

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "running": self._running,
            "active_anomalies": len(self._attempt_tracker),
        }

    # =========================================================================
    # Main Loop
    # =========================================================================

    async def _sweep_loop(self) -> None:
        logger.debug("SystemIntegrityMonitor loop started")
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                if not self._running:
                    break
                await self._run_sweep()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Integrity] Sweep error: {e}", exc_info=True)
        logger.debug("SystemIntegrityMonitor loop exited")

    async def _run_sweep(self) -> None:
        start = time.monotonic()
        all_anomalies: List[AnomalyResult] = []

        # Run all checks — each is wrapped to not break the sweep on failure
        for check_fn in (
            self._check_merged_not_finalized,
            self._check_stuck_issues,
            self._check_stuck_goals,
            self._check_stuck_prs,
            self._check_stale_high_progress,
            self._check_pipeline_stall,
            self._check_orphaned_work,
            self._check_failed_work_impact,
            self._check_stuck_planning_goals,
            self._check_failed_issue_merged_pr,
        ):
            try:
                results = await check_fn()
                all_anomalies.extend(results)
            except Exception as e:
                logger.error(f"[Integrity] Check {check_fn.__name__} failed: {e}")

        self._stats["anomalies_detected"] += len(all_anomalies)

        for anomaly in all_anomalies:
            tracker_key = f"{anomaly.check_type}:{anomaly.entity_id}"

            if self._should_throttle(tracker_key, anomaly.check_type):
                continue

            self._record_attempt(tracker_key)
            consecutive = self._attempt_tracker[tracker_key]["attempt_count"]

            # Update per-check stats
            check_stats = self._stats["by_check_type"].get(anomaly.check_type)
            if check_stats:
                check_stats["detected"] += 1

            if anomaly.remediation_action:
                success = await self._attempt_remediation(anomaly)
                if success:
                    self._stats["anomalies_remediated"] += 1
                    if check_stats:
                        check_stats["remediated"] += 1
                    logger.info(f"[Integrity] Remediated: {anomaly.description}")
                    self._notify_success(anomaly)
                    # Clean tracker on success — anomaly resolved
                    self._attempt_tracker.pop(tracker_key, None)
                else:
                    self._stats["anomalies_failed"] += 1
                    if check_stats:
                        check_stats["failed"] += 1
                    self._notify_failure(anomaly, consecutive)
            else:
                # Notification-only anomaly
                self._notify_failure(anomaly, consecutive)

        self._cleanup_tracker()

        elapsed_ms = (time.monotonic() - start) * 1000
        self._stats["cycles"] += 1
        self._stats["last_sweep_duration_ms"] = round(elapsed_ms, 1)
        self._stats["last_sweep_at"] = datetime.now(timezone.utc).isoformat()

        if all_anomalies:
            logger.info(
                f"[Integrity] Sweep #{self._stats['cycles']}: "
                f"{len(all_anomalies)} anomalies detected "
                f"({elapsed_ms:.0f}ms)"
            )

    # =========================================================================
    # Throttling
    # =========================================================================

    def _should_throttle(self, tracker_key: str, check_type: str) -> bool:
        entry = self._attempt_tracker.get(tracker_key)
        if not entry:
            return False
        cooldown = COOLDOWNS.get(check_type, 120)
        elapsed = (datetime.now(timezone.utc) - entry["last_attempt"]).total_seconds()
        return elapsed < cooldown

    def _record_attempt(self, tracker_key: str) -> None:
        now = datetime.now(timezone.utc)
        if tracker_key in self._attempt_tracker:
            self._attempt_tracker[tracker_key]["last_attempt"] = now
            self._attempt_tracker[tracker_key]["attempt_count"] += 1
        else:
            self._attempt_tracker[tracker_key] = {
                "first_seen": now,
                "last_attempt": now,
                "attempt_count": 1,
            }

    def _cleanup_tracker(self) -> None:
        now = datetime.now(timezone.utc)
        stale_keys = [
            k for k, v in self._attempt_tracker.items()
            if (now - v["last_attempt"]).total_seconds() > TRACKER_CLEANUP_SECONDS
        ]
        for k in stale_keys:
            del self._attempt_tracker[k]

    # =========================================================================
    # Notification
    # =========================================================================

    def _notify_success(self, anomaly: AnomalyResult) -> None:
        """Notify that an anomaly was detected AND successfully remediated."""
        try:
            from services.notification_service import get_notification_service
            from models.notification import NotificationLevel, NotificationCategory

            notification_service = get_notification_service()
            if not notification_service:
                return

            notification_service.emit(
                title=f"[Integrity] Auto-fixed: {anomaly.entity_type}",
                message=f"Detected and resolved: {anomaly.description}",
                level=NotificationLevel.SUCCESS,
                category=NotificationCategory.SYSTEM,
                project_id=anomaly.project_id,
                entity_id=anomaly.entity_id,
            )
        except Exception as e:
            logger.debug(f"[Integrity] Could not emit success notification: {e}")

    def _notify_failure(self, anomaly: AnomalyResult, consecutive: int) -> None:
        """Notify that an anomaly was detected but could NOT be remediated."""
        try:
            from services.notification_service import get_notification_service
            from models.notification import NotificationLevel, NotificationCategory

            notification_service = get_notification_service()
            if not notification_service:
                return

            level = (
                NotificationLevel.ERROR
                if consecutive >= ESCALATION_THRESHOLD
                else NotificationLevel.WARNING
            )

            action_note = (
                " Manual intervention required."
                if consecutive >= ESCALATION_THRESHOLD
                else " Will retry."
            )

            notification_service.emit(
                title=f"[Integrity] Cannot resolve: {anomaly.entity_type}",
                message=f"{anomaly.description}.{action_note}",
                level=level,
                category=NotificationCategory.SYSTEM,
                project_id=anomaly.project_id,
                entity_id=anomaly.entity_id,
            )
        except Exception as e:
            logger.debug(f"[Integrity] Could not emit failure notification: {e}")

    # =========================================================================
    # Remediation
    # =========================================================================

    async def _attempt_remediation(self, anomaly: AnomalyResult) -> bool:
        try:
            action = anomaly.remediation_action
            ctx = anomaly.context

            if action == "finalize_work":
                return await self._remediate_finalize_work(
                    anomaly.entity_id, ctx
                )
            elif action == "finalize_issue":
                return await self._remediate_finalize_issue(anomaly.entity_id)
            elif action == "check_goal_completion":
                return await self._remediate_goal_completion(anomaly.entity_id)
            elif action == "requeue_merge":
                return await self._remediate_requeue_merge(
                    ctx.get("project"), ctx.get("branch")
                )
            elif action == "process_merge_queue":
                return await self._remediate_process_merge_queue(ctx.get("project"))
            elif action == "trigger_dispatch":
                return await self._remediate_trigger_dispatch()
            elif action == "requeue_orphaned":
                return await self._remediate_requeue_orphaned(anomaly.entity_id)
            elif action == "fail_parent_issue":
                return await self._remediate_fail_parent_issue(
                    anomaly.entity_id, ctx
                )
            elif action == "fail_stuck_planning_goal":
                return await self._remediate_fail_stuck_planning_goal(
                    anomaly.entity_id
                )
            elif action == "recover_failed_issue":
                return await self._remediate_recover_failed_issue(
                    anomaly.entity_id, ctx
                )
            else:
                logger.warning(f"[Integrity] Unknown remediation: {action}")
                return False

        except Exception as e:
            logger.error(
                f"[Integrity] Remediation failed for "
                f"{anomaly.entity_type} {anomaly.entity_id}: {e}"
            )
            return False

    async def _remediate_finalize_work(
        self, work_id: str, ctx: Dict[str, Any]
    ) -> bool:
        from services.work_map_service import get_work_map_service
        from models.work_map import WorkStatus

        wm = get_work_map_service()
        work = wm._work_items.get(work_id)
        if not work:
            return False

        if work.status == WorkStatus.IN_PROGRESS:
            await wm.complete_work(
                work_id,
                {"auto_completed": True, "reason": "integrity_monitor_merged_branch"},
                trigger_cascade=False,
            )

        result = await wm.finalize_work(work_id)
        return result is not None

    async def _remediate_finalize_issue(self, issue_id: str) -> bool:
        from services.work_map_service import get_work_map_service

        wm = get_work_map_service()
        await wm._issue_service.finalize_issue(issue_id, trigger_cascade=True)
        return True

    async def _remediate_goal_completion(self, goal_id: str) -> bool:
        from services.work_map_service import get_work_map_service

        wm = get_work_map_service()
        await wm._goal_service.check_goal_completion(goal_id)
        return True

    async def _remediate_requeue_merge(
        self, project: Optional[str], branch: Optional[str]
    ) -> bool:
        if not project or not branch:
            return False
        from api.git import get_pr_service
        from git.pr_service import PRStatus

        pr_service = get_pr_service()
        await pr_service.update_status(project, branch, PRStatus.PENDING)
        results = await pr_service.process_merge_queue(project)
        return len(results) > 0

    async def _remediate_process_merge_queue(self, project: Optional[str]) -> bool:
        if not project:
            return False
        from api.git import get_pr_service

        pr_service = get_pr_service()
        await pr_service.process_merge_queue(project)
        return True

    async def _remediate_trigger_dispatch(self) -> bool:
        from services.work_dispatcher import get_work_dispatcher

        dispatcher = get_work_dispatcher()
        dispatcher.trigger(reason="integrity_pipeline_stall")
        return True

    async def _remediate_requeue_orphaned(self, work_id: str) -> bool:
        from services.work_map_service import get_work_map_service

        wm = get_work_map_service()
        result = await wm.mark_work_timed_out(work_id, max_retries=3)
        return result is not None

    async def _remediate_fail_parent_issue(
        self, issue_id: str, ctx: Dict[str, Any]
    ) -> bool:
        """Mark an issue as FAILED when its work items have all failed."""
        from services.work_map_service import get_work_map_service
        from models.work_map import IssueStatus

        wm = get_work_map_service()
        await wm._issue_service.update_issue_status(
            issue_id, IssueStatus.FAILED
        )
        return True

    async def _remediate_fail_stuck_planning_goal(self, goal_id: str) -> bool:
        """Mark a stuck PLANNING goal as FAILED so the user knows decomposition stalled."""
        from services.work_map_service import get_work_map_service
        from models.work_map import GoalStatus

        wm = get_work_map_service()
        goal = wm._goals.get(goal_id)
        if not goal:
            return False
        goal.status = GoalStatus.FAILED
        await wm._goal_service._save_goal_to_redis(goal)
        return True

    async def _remediate_recover_failed_issue(
        self, issue_id: str, ctx: Dict[str, Any]
    ) -> bool:
        """Recover a FAILED issue whose work is actually merged.

        Transitions FAILED → IN_PROGRESS → IMPLEMENTED → DONE (with cascade).
        Each step follows the valid transition table.
        """
        from services.work_map_service import get_work_map_service
        from models.work_map import IssueStatus

        wm = get_work_map_service()

        # FAILED → IN_PROGRESS (valid transition)
        result = await wm._issue_service.update_issue_status(
            issue_id, IssueStatus.IN_PROGRESS,
            reason="integrity_monitor: PR is merged, recovering from FAILED"
        )
        if not result:
            return False

        # Finalize: IN_PROGRESS → IMPLEMENTED → DONE + cascade
        result = await wm._issue_service.finalize_issue(
            issue_id, trigger_cascade=True
        )
        # finalize_issue expects IMPLEMENTED, but we're at IN_PROGRESS.
        # So transition to IMPLEMENTED first, then finalize.
        if not result:
            result = await wm._issue_service.update_issue_status(
                issue_id, IssueStatus.IMPLEMENTED,
                reason="integrity_monitor: work merged, advancing to IMPLEMENTED"
            )
            if result:
                result = await wm._issue_service.finalize_issue(
                    issue_id, trigger_cascade=True
                )

        return result is not None

    # =========================================================================
    # Anomaly Checks
    # =========================================================================

    def _resolve_git_project_name(self, project_id: str) -> str:
        """Resolve project_id to git repo name (e.g. proj_abc -> proj_abc_repo_def)."""
        try:
            from api.compute import _resolve_git_project_name
            return _resolve_git_project_name(project_id)
        except Exception:
            return project_id

    async def _check_merged_not_finalized(self) -> List[AnomalyResult]:
        """Check 1: Work items whose PR is MERGED but status is still active."""
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from api.git import get_pr_service
            from git.pr_service import PRStatus
            from models.work_map import WorkStatus

            wm = get_work_map_service()
            pr_service = get_pr_service()

            for status in (WorkStatus.IN_PROGRESS, WorkStatus.IMPLEMENTED):
                try:
                    result = await wm.list_work(status=status, limit=100)
                except Exception:
                    continue
                for work in result.items:
                    if not work.branch_name or not work.project_id:
                        continue
                    try:
                        git_project = self._resolve_git_project_name(
                            work.project_id
                        )
                        pr = await pr_service.get_pr(
                            git_project, work.branch_name
                        )
                        if pr and pr.status == PRStatus.MERGED:
                            anomalies.append(AnomalyResult(
                                check_type="merged_not_finalized",
                                entity_type="work",
                                entity_id=work.work_id,
                                project_id=work.project_id,
                                description=(
                                    f"Work {work.work_id} is {status.value} "
                                    f"but branch {work.branch_name} is already merged"
                                ),
                                remediation_action="finalize_work",
                                context={"branch": work.branch_name},
                            ))
                    except Exception:
                        continue
        except RuntimeError:
            pass  # Service not initialized
        return anomalies

    async def _check_stuck_issues(self) -> List[AnomalyResult]:
        """Check 2: Issues stuck in active status when all work is completed."""
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from models.work_map import IssueStatus, WorkStatus

            wm = get_work_map_service()

            for status in (IssueStatus.IN_PROGRESS, IssueStatus.IMPLEMENTED):
                try:
                    result = await wm.list_issues(status=status, limit=100)
                except Exception:
                    continue
                for issue in result.items:
                    # Find all work items for this issue
                    issue_work = [
                        w for w in wm._work_items.values()
                        if w.issue_id == issue.issue_id
                    ]
                    if not issue_work:
                        continue
                    if all(w.status == WorkStatus.COMPLETED for w in issue_work):
                        anomalies.append(AnomalyResult(
                            check_type="stuck_issue",
                            entity_type="issue",
                            entity_id=issue.issue_id,
                            project_id=getattr(issue, 'project_id', None),
                            description=(
                                f"Issue {issue.issue_id} is {status.value} but all "
                                f"{len(issue_work)} work item(s) are completed"
                            ),
                            remediation_action="finalize_issue",
                        ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_stuck_goals(self) -> List[AnomalyResult]:
        """Check 3: Goals still IN_PROGRESS when all issues are DONE."""
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from models.work_map import GoalStatus, IssueStatus

            wm = get_work_map_service()
            goals_result = await wm.list_goals(status=GoalStatus.IN_PROGRESS)

            for goal in goals_result.items:
                issues = await wm.get_goal_issues(goal.goal_id)
                if not issues:
                    continue
                if all(i.status == IssueStatus.DONE for i in issues):
                    anomalies.append(AnomalyResult(
                        check_type="stuck_goal",
                        entity_type="goal",
                        entity_id=goal.goal_id,
                        project_id=getattr(goal, 'project_id', None),
                        description=(
                            f"Goal {goal.goal_id} is in_progress but all "
                            f"{len(issues)} issues are done"
                        ),
                        remediation_action="check_goal_completion",
                    ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_stuck_prs(self) -> List[AnomalyResult]:
        """Check 4: PRs stuck in CONFLICT (resolved) or APPROVED (not merging)."""
        anomalies: List[AnomalyResult] = []
        try:
            from api.git import get_pr_service
            from git.pr_service import PRStatus
            from services.work_map_service import get_work_map_service

            pr_service = get_pr_service()
            wm = get_work_map_service()

            # Get unique project IDs from active work, resolve to git names
            raw_project_ids = set()
            for status_val in ("in_progress", "implemented", "assigned", "pending"):
                try:
                    from models.work_map import WorkStatus
                    ws = WorkStatus(status_val)
                    result = await wm.list_work(status=ws, limit=100)
                    for w in result.items:
                        if w.project_id:
                            raw_project_ids.add(w.project_id)
                except Exception:
                    continue

            for raw_project_id in raw_project_ids:
                project_id = self._resolve_git_project_name(raw_project_id)
                try:
                    prs = await pr_service.list_prs(project_id)
                except Exception:
                    continue

                for pr in prs:
                    # 4a: CONFLICT but actually mergeable
                    if pr.status == PRStatus.CONFLICT:
                        try:
                            check = await pr_service.check_mergeable(
                                project_id, pr.branch
                            )
                            if check.get("mergeable"):
                                anomalies.append(AnomalyResult(
                                    check_type="stuck_pr_conflict",
                                    entity_type="pr",
                                    entity_id=f"{project_id}/{pr.branch}",
                                    project_id=project_id,
                                    description=(
                                        f"PR {pr.branch} is marked CONFLICT "
                                        f"but branch is actually mergeable"
                                    ),
                                    remediation_action="requeue_merge",
                                    context={
                                        "project": project_id,
                                        "branch": pr.branch,
                                    },
                                ))
                        except Exception:
                            continue

                    # 4b: APPROVED for >5 minutes but not merged
                    elif pr.status == PRStatus.APPROVED:
                        approved_at = getattr(pr, 'updated_at', None)
                        if approved_at:
                            if isinstance(approved_at, str):
                                approved_at = datetime.fromisoformat(approved_at)
                            age = (
                                datetime.now(timezone.utc) - approved_at
                            ).total_seconds()
                            if age > 300:  # 5 minutes
                                anomalies.append(AnomalyResult(
                                    check_type="stuck_pr_approved",
                                    entity_type="pr",
                                    entity_id=f"{project_id}/{pr.branch}",
                                    project_id=project_id,
                                    description=(
                                        f"PR {pr.branch} has been APPROVED for "
                                        f"{int(age)}s but not merged"
                                    ),
                                    remediation_action="process_merge_queue",
                                    context={"project": project_id},
                                ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_stale_high_progress(self) -> List[AnomalyResult]:
        """Check 5: Work at >=90% progress with no activity, compute disconnected."""
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from services.sse_connection_manager import get_sse_connection_manager
            from models.work_map import WorkStatus

            wm = get_work_map_service()
            sse_manager = get_sse_connection_manager()
            connected_ids = {c.compute_id for c in sse_manager.list_connections()}

            result = await wm.list_work(status=WorkStatus.IN_PROGRESS, limit=100)
            now = datetime.now(timezone.utc)

            for work in result.items:
                progress = getattr(work, 'progress_percent', 0) or 0
                if progress < 90:
                    continue

                last_activity = getattr(work, 'last_activity_at', None)
                if last_activity:
                    if isinstance(last_activity, str):
                        last_activity = datetime.fromisoformat(last_activity)
                    stale_seconds = (now - last_activity).total_seconds()
                    if stale_seconds < 900:  # 15 minutes
                        continue
                else:
                    continue

                if work.assigned_to and work.assigned_to not in connected_ids:
                    anomalies.append(AnomalyResult(
                        check_type="stale_high_progress",
                        entity_type="work",
                        entity_id=work.work_id,
                        project_id=work.project_id,
                        description=(
                            f"Work {work.work_id} at {progress}% progress, "
                            f"no activity for {int(stale_seconds)}s, "
                            f"compute {work.assigned_to} disconnected"
                        ),
                        remediation_action=None,  # Notify only
                    ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_pipeline_stall(self) -> List[AnomalyResult]:
        """Check 6: READY issues or PENDING work with idle computes but nothing moving."""
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from services.sse_connection_manager import get_sse_connection_manager
            from models.work_map import WorkStatus, IssueStatus

            wm = get_work_map_service()
            sse_manager = get_sse_connection_manager()

            idle_count = sum(
                1 for c in sse_manager.list_connections() if c.status == "idle"
            )
            if idle_count == 0:
                return anomalies

            # Check for PENDING work items
            pending_result = await wm.list_work(
                status=WorkStatus.PENDING, limit=1
            )
            if pending_result.items:
                anomalies.append(AnomalyResult(
                    check_type="pipeline_stall",
                    entity_type="system",
                    entity_id="pending_work_idle_compute",
                    project_id=None,
                    description=(
                        f"{idle_count} idle compute(s) with pending work "
                        f"items — dispatch may have stalled"
                    ),
                    remediation_action="trigger_dispatch",
                ))
                return anomalies

            # Check for READY issues with no active work
            ready_result = await wm.list_issues(
                status=IssueStatus.READY, limit=10
            )
            if ready_result.items:
                active_count = 0
                for status in (WorkStatus.PENDING, WorkStatus.ASSIGNED,
                               WorkStatus.IN_PROGRESS):
                    try:
                        r = await wm.list_work(status=status, limit=1)
                        active_count += len(r.items)
                    except Exception:
                        continue

                if active_count == 0:
                    anomalies.append(AnomalyResult(
                        check_type="pipeline_stall",
                        entity_type="system",
                        entity_id="ready_issues_no_work",
                        project_id=None,
                        description=(
                            f"{len(ready_result.items)} READY issue(s) but "
                            f"no active work items — pipeline stalled"
                        ),
                        remediation_action="trigger_dispatch",
                    ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_orphaned_work(self) -> List[AnomalyResult]:
        """Check 7: Work assigned to computes that are no longer connected."""
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from services.sse_connection_manager import get_sse_connection_manager
            from models.work_map import WorkStatus

            wm = get_work_map_service()
            sse_manager = get_sse_connection_manager()
            connected_ids = {c.compute_id for c in sse_manager.list_connections()}

            for status in (WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS):
                try:
                    result = await wm.list_work(status=status, limit=100)
                except Exception:
                    continue
                for work in result.items:
                    if work.assigned_to and work.assigned_to not in connected_ids:
                        anomalies.append(AnomalyResult(
                            check_type="orphaned_work",
                            entity_type="work",
                            entity_id=work.work_id,
                            project_id=work.project_id,
                            description=(
                                f"Work {work.work_id} ({status.value}) assigned "
                                f"to disconnected compute {work.assigned_to}"
                            ),
                            remediation_action="requeue_orphaned",
                        ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_failed_work_impact(self) -> List[AnomalyResult]:
        """Check 8: Issues stuck IN_PROGRESS when all work items are FAILED.

        When work fails but the parent issue isn't updated, the issue blocks
        downstream work indefinitely. This detects the gap and marks the
        parent issue as FAILED so the system can move on.
        """
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from models.work_map import IssueStatus, WorkStatus

            wm = get_work_map_service()

            for status in (IssueStatus.IN_PROGRESS, IssueStatus.IMPLEMENTED):
                try:
                    result = await wm.list_issues(status=status, limit=100)
                except Exception:
                    continue
                for issue in result.items:
                    issue_work = [
                        w for w in wm._work_items.values()
                        if w.issue_id == issue.issue_id
                    ]
                    if not issue_work:
                        continue
                    # All work items are terminal but at least one is FAILED
                    # (i.e., not all COMPLETED — that's _check_stuck_issues)
                    terminal = all(
                        w.status in (WorkStatus.COMPLETED, WorkStatus.FAILED)
                        for w in issue_work
                    )
                    has_failed = any(
                        w.status == WorkStatus.FAILED for w in issue_work
                    )
                    if terminal and has_failed:
                        failed_count = sum(
                            1 for w in issue_work if w.status == WorkStatus.FAILED
                        )
                        anomalies.append(AnomalyResult(
                            check_type="failed_work_impact",
                            entity_type="issue",
                            entity_id=issue.issue_id,
                            project_id=getattr(issue, 'project_id', None),
                            description=(
                                f"Issue {issue.issue_id} is {status.value} but "
                                f"{failed_count}/{len(issue_work)} work item(s) "
                                f"failed — issue should be marked FAILED"
                            ),
                            remediation_action="fail_parent_issue",
                        ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_failed_issue_merged_pr(self) -> List[AnomalyResult]:
        """Check 10: FAILED issues whose work branch is actually merged.

        This catches the scenario where work completed and merged but the
        work item timed out or failed for unrelated reasons, leaving the
        issue stuck at FAILED while the code is on main. The fix recovers
        the issue to DONE and triggers the dependency cascade to unblock
        downstream work.
        """
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from api.git import get_pr_service
            from git.pr_service import PRStatus
            from models.work_map import IssueStatus

            wm = get_work_map_service()
            pr_service = get_pr_service()

            result = await wm.list_issues(status=IssueStatus.FAILED, limit=100)
            for issue in result.items:
                # Find all work items for this issue
                issue_work = [
                    w for w in wm._work_items.values()
                    if w.issue_id == issue.issue_id
                ]
                if not issue_work:
                    continue

                # Check if ANY work item's branch has a merged PR
                has_merged_pr = False
                merged_branch = None
                for work in issue_work:
                    if not work.branch_name or not work.project_id:
                        continue
                    try:
                        git_project = self._resolve_git_project_name(
                            work.project_id
                        )
                        pr = await pr_service.get_pr(
                            git_project, work.branch_name
                        )
                        if pr and pr.status == PRStatus.MERGED:
                            has_merged_pr = True
                            merged_branch = work.branch_name
                            break
                    except Exception:
                        continue

                if has_merged_pr:
                    anomalies.append(AnomalyResult(
                        check_type="failed_issue_merged_pr",
                        entity_type="issue",
                        entity_id=issue.issue_id,
                        project_id=getattr(issue, 'project_id', None),
                        description=(
                            f"Issue {issue.issue_id} is FAILED but branch "
                            f"{merged_branch} is merged — recovering to DONE"
                        ),
                        remediation_action="recover_failed_issue",
                        context={"branch": merged_branch},
                    ))
        except RuntimeError:
            pass
        return anomalies

    async def _check_stuck_planning_goals(self) -> List[AnomalyResult]:
        """Check 9: Goals stuck in PLANNING for too long.

        If decomposition fails silently (compute crash, timeout, error),
        the goal stays in PLANNING forever. After 15 minutes with no
        issues created, mark as FAILED.
        """
        anomalies: List[AnomalyResult] = []
        try:
            from services.work_map_service import get_work_map_service
            from models.work_map import GoalStatus

            wm = get_work_map_service()
            goals_result = await wm.list_goals(status=GoalStatus.PLANNING)
            now = datetime.now(timezone.utc)

            for goal in goals_result.items:
                # Check how long it's been in PLANNING
                created_at = getattr(goal, 'created_at', None)
                if not created_at:
                    continue
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                age_seconds = (now - created_at).total_seconds()

                if age_seconds < 900:  # 15 minutes grace period
                    continue

                # Verify no issues have been created
                issues = await wm.get_goal_issues(goal.goal_id)
                if issues:
                    continue  # Decomposition produced issues, probably transitioning

                anomalies.append(AnomalyResult(
                    check_type="stuck_planning_goal",
                    entity_type="goal",
                    entity_id=goal.goal_id,
                    project_id=getattr(goal, 'project_id', None),
                    description=(
                        f"Goal {goal.goal_id} stuck in PLANNING for "
                        f"{int(age_seconds / 60)}m with no issues created"
                    ),
                    remediation_action="fail_stuck_planning_goal",
                ))
        except RuntimeError:
            pass
        return anomalies


# =========================================================================
# Module-level helpers
# =========================================================================

async def start_system_integrity_monitor(
    check_interval: int = 60,
) -> SystemIntegrityMonitor:
    """Create, register, and start the SystemIntegrityMonitor singleton."""
    monitor = SystemIntegrityMonitor(check_interval=check_interval)
    set_system_integrity_monitor(monitor)
    await monitor.start()
    return monitor


async def stop_system_integrity_monitor() -> None:
    """Stop the SystemIntegrityMonitor singleton if running."""
    global _monitor
    if _monitor and _monitor.is_running():
        await _monitor.stop()
