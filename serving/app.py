"""
FastAPI application for ClaudeVN Serving Component.
"""

import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import get_config
from middleware.rate_limiter import (
    RateLimiter,
    RateLimitMiddleware,
    set_rate_limiter,
    get_rate_limiter,
)

from storage.registry_storage import RegistryStorage
from storage.cache_backend import FilesystemCache, set_cache_backend
from storage.data_provider import FilesystemDataProvider, set_data_provider
from services.registry_service import ComputeRegistry, set_compute_registry
from services.marketplace_registry import MarketplaceRegistry, set_marketplace_registry
from services.health_monitor import start_health_monitoring, stop_health_monitoring
from services.work_orchestrator import (
    start_work_orchestration, stop_work_orchestration, get_work_orchestrator
)
from services.work_dispatcher import start_work_dispatcher, stop_work_dispatcher
from services.reconciliation_manager import (
    start_reconciliation_manager, stop_reconciliation_manager
)
from api import compute
from api import marketplaces
from api import skills
from api import agents
from api import facilitated_sessions
from api import tasks
from api import pipelines
from api import process_maps
from api import logs
from api import observability
from api import cache
from api import git
from api import work_map
from api import spawner
from api import projects
from api import orchestrator
from api import slim_claude_code
from api import characterization
from api import specialization
from api import conflicts
from api import decision_traces
from api import plan_summary
from api import profile_presets
from api import notifications
from api import unified_directives
from api import feedback
from api import auth
# MCP server for compute communication
from mcp import get_router
# Marketplace HTTP client (marketplace is a separate service on port 8003)
from services.marketplace_client import (
    MarketplaceClient,
    get_marketplace_client,
    set_marketplace_client
)
# Work Map service for task allocation
from services.work_map_service import WorkMapService, set_work_map_service, get_work_map_service
from services.goal_service import set_goal_service
from services.project_service import ProjectService, set_project_service
# Release service for release management
from services.release_service import ReleaseService, set_release_service
# Goal Comment service for goal conversation threads
from services.goal_comment_service import (
    GoalCommentService,
    set_goal_comment_service,
    get_goal_comment_service
)
# Comment Rollup service for batch comment processing
from services.comment_rollup_service import (
    CommentRollupService,
    set_comment_rollup_service,
    get_comment_rollup_service
)
# Compute Spawner for Claude Code instances
from services.compute_spawner import ComputeSpawner, set_compute_spawner
# SSE connection manager for compute event push
from services.sse_connection_manager import (
    SSEConnectionManager,
    get_sse_connection_manager,
    set_sse_connection_manager
)
# Claude auth service for serving-centric OAuth
from services.claude_auth_service import (
    ClaudeAuthService,
    set_claude_auth_service,
    get_claude_auth_service,
)
# Version from central VERSION file
from claudevn_shared.version import get_version


# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Service Dependencies:
    ---------------------
    Services are categorized as REQUIRED or OPTIONAL based on whether the
    serving component can function in a degraded mode without them.

    REQUIRED services (raise on failure - application cannot start):
    - Storage (registry_storage): Core persistence for compute/marketplace registrations
    - Cache (cache_backend): Performance-critical caching for API responses
    - Data Provider: Session persistence and blob storage
    - Compute Registry: Core service for tracking compute instances
    - Marketplace Registry: Core service for tracking marketplace connections
    - Health Monitor: Critical for detecting degraded/offline instances
    - Marketplace Client: HTTP client for external marketplace service
    - Work Map Service: Task allocation and dependency tracking
    - Project Service: Project management and configuration
    - Compute Spawner: Claude Code instance lifecycle management

    OPTIONAL services (log warning, continue in degraded mode):
    - Redis: Only needed for Git PR queue features; work map uses in-memory fallback
    - Rate Limiter: API rate limiting; disabled if initialization fails
    - SSH Git Server: Only needed for compute Git push/pull; can be disabled
    - SSE Connection Manager: Real-time event push; not critical for core operation
    - Work Orchestrator: Auto-spawning of compute instances; can be disabled

    See serving/README.md "Service Dependencies" section for detailed documentation.
    """
    # Startup
    logger.info("Starting ClaudeVN Serving Component...")
    
    # =========================================================================
    # REQUIRED: Storage Backend
    # Core persistence layer for compute/marketplace registrations.
    # Without storage, no registrations can be persisted or recovered.
    # =========================================================================
    storage_path = os.getenv('STORAGE_PATH', './data/serving')
    try:
        registry_storage = RegistryStorage(storage_path)
        logger.info(f"Initialized registry storage at {storage_path}")
    except Exception as e:
        logger.error(f"Failed to initialize storage: {e}")
        raise

    # =========================================================================
    # REQUIRED: Cache Backend
    # Performance-critical caching for API responses and temporary state.
    # Many services depend on caching for acceptable performance.
    # =========================================================================
    try:
        cache_path = os.getenv('CACHE_PATH', f'{storage_path}/cache')
        cache_backend = FilesystemCache(cache_path)
        set_cache_backend(cache_backend)
        logger.info(f"Initialized cache backend at {cache_path}")
    except Exception as e:
        logger.error(f"Failed to initialize cache: {e}")
        raise

    # =========================================================================
    # REQUIRED: Data Provider
    # General storage for sessions, blobs, and artifacts.
    # Session persistence and data storage depend on this service.
    # =========================================================================
    try:
        datastore_path = os.getenv('DATASTORE_PATH', f'{storage_path}/datastore')
        data_provider = FilesystemDataProvider(datastore_path)
        set_data_provider(data_provider)
        logger.info(f"Initialized data provider at {datastore_path}")
        
        # Enable session persistence
        from broker.session_context import set_session_data_provider
        set_session_data_provider(data_provider)
        logger.info("Session persistence enabled")
    except Exception as e:
        logger.error(f"Failed to initialize data provider: {e}")
        raise

    # =========================================================================
    # REQUIRED: Compute Registry
    # Core service for tracking and managing compute instances.
    # Without this, no compute orchestration is possible.
    # =========================================================================
    try:
        compute_registry = ComputeRegistry(storage_backend=registry_storage)
        await compute_registry.initialize()  # Load from storage
        set_compute_registry(compute_registry)
        logger.info("Compute registry initialized")
    except Exception as e:
        logger.error(f"Failed to initialize compute registry: {e}")
        raise

    # =========================================================================
    # REQUIRED: Marketplace Registry
    # Core service for tracking marketplace connections.
    # Required for multi-marketplace agent discovery and coordination.
    # =========================================================================
    try:
        marketplace_registry = MarketplaceRegistry(storage_backend=registry_storage)
        await marketplace_registry.initialize()  # Load from storage
        set_marketplace_registry(marketplace_registry)
        logger.info("Marketplace registry initialized")
    except Exception as e:
        logger.error(f"Failed to initialize marketplace registry: {e}")
        raise

    # =========================================================================
    # REQUIRED: Health Monitoring
    # Monitors compute/marketplace health and updates status.
    # Critical for detecting degraded/offline instances and preventing
    # task routing to unhealthy instances.
    # =========================================================================
    try:
        check_interval = int(os.getenv('HEALTH_CHECK_INTERVAL', '30'))
        degraded_threshold = int(os.getenv('DEGRADED_THRESHOLD', '60'))
        offline_threshold = int(os.getenv('OFFLINE_THRESHOLD', '90'))
        max_failed_checks = int(os.getenv('MAX_FAILED_CHECKS', '3'))
        auto_deregister = os.getenv('AUTO_DEREGISTER', 'false').lower() == 'true'
        
        await start_health_monitoring(
            compute_registry=compute_registry,
            marketplace_registry=marketplace_registry,
            check_interval=check_interval,
            degraded_threshold=degraded_threshold,
            offline_threshold=offline_threshold,
            max_failed_checks=max_failed_checks,
            auto_deregister=auto_deregister
        )
        logger.info("Health monitoring started")
    except Exception as e:
        logger.error(f"Failed to start health monitoring: {e}")
        raise

    # =========================================================================
    # REQUIRED: Marketplace HTTP Client
    # HTTP client for communicating with the external marketplace service.
    # The client itself must initialize successfully, but the marketplace
    # service being unreachable is tolerated (uses fallback mode).
    # =========================================================================
    try:
        marketplace_url = os.getenv('MARKETPLACE_URL', 'http://localhost:8003')
        cache_ttl = int(os.getenv('MARKETPLACE_CACHE_TTL', '300'))
        marketplace_client = MarketplaceClient(
            base_url=marketplace_url,
            cache_ttl=cache_ttl
        )
        set_marketplace_client(marketplace_client)

        # Verify marketplace is reachable (non-blocking - will use fallback if unavailable)
        try:
            health = await marketplace_client.health_check()
            logger.info(f"Marketplace service connected at {marketplace_url}")
        except Exception as e:
            logger.warning(f"Marketplace service not reachable at {marketplace_url}: {e}. Using fallback mode.")
    except Exception as e:
        logger.error(f"Failed to initialize marketplace client: {e}")
        raise

    # =========================================================================
    # OPTIONAL: Redis Connection
    # Used for Git PR queue features and distributed state.
    # If unavailable, the work map service uses in-memory storage as fallback.
    # Git PR queue features will be disabled without Redis.
    # =========================================================================
    redis_client = None
    try:
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', '6379'))
        from git.redis_client import get_redis, RedisClient, set_redis_client
        redis_conn = await get_redis()
        redis_client = RedisClient(redis_conn)
        set_redis_client(redis_client)
        logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
    except Exception as e:
        from git.redis_client import set_redis_client
        set_redis_client(None)
        logger.warning(f"Redis not available: {e}. Git PR queue features disabled.")

    # =========================================================================
    # OPTIONAL: MCP Auth Key Persistence
    # Loads compute API keys from Redis so they survive Serving restarts.
    # =========================================================================
    try:
        from mcp.auth import set_auth_redis, initialize_from_redis
        set_auth_redis(redis_client)
        await initialize_from_redis()
        logger.info("MCP auth key persistence initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize MCP auth persistence: {e}")

    # =========================================================================
    # OPTIONAL: Rate Limiter
    # API rate limiting to protect against abuse and overload.
    # Can be disabled via RATE_LIMIT_ENABLED=false.
    # If initialization fails, rate limiting is disabled.
    # =========================================================================
    try:
        config = get_config()
        rate_limiter = RateLimiter(
            config=config.rate_limit,
            redis_client=redis_client,
        )
        set_rate_limiter(rate_limiter)
        if config.rate_limit.enabled:
            logger.info(
                f"Rate limiter initialized (default={config.rate_limit.default_requests_per_minute}/min, "
                f"compute={config.rate_limit.compute_requests_per_minute}/min)"
            )
        else:
            logger.info("Rate limiter disabled via RATE_LIMIT_ENABLED=false")
    except Exception as e:
        logger.warning(f"Failed to initialize rate limiter: {e}. Rate limiting disabled.")

    # =========================================================================
    # OPTIONAL: Git Token Service
    # Manages authentication tokens for Git Smart HTTP access.
    # Replaces SSH key-based authentication with token-based auth.
    # =========================================================================
    try:
        from git.git_token_service import GitTokenService, set_git_token_service
        git_token_service = GitTokenService(redis_client=redis_client)
        set_git_token_service(git_token_service)
        logger.info("Git token service initialized")
    except Exception as e:
        from git.git_token_service import set_git_token_service
        set_git_token_service(None)
        logger.warning(f"Git token service not available: {e}. Git auth disabled.")

    # =========================================================================
    # OPTIONAL: Migrate existing repos to enable HTTP push
    # Ensures http.receivepack=true is set on all bare repos.
    # =========================================================================
    try:
        from git.repo_manager import RepoManager
        repo_mgr = RepoManager()
        for project in repo_mgr.list_repos():
            repo_path = repo_mgr._repo_path(project)
            import subprocess as _sp
            _sp.run(
                ["git", "-C", str(repo_path), "config", "http.receivepack", "true"],
                capture_output=True
            )
        logger.info("Migrated existing repos for HTTP push support")
    except Exception as e:
        logger.debug(f"Repo migration check: {e}")

    # =========================================================================
    # REQUIRED: Work Map Service
    # Task allocation, dependency tracking, and work distribution.
    # Core to the orchestration workflow; uses Redis if available,
    # falls back to in-memory storage otherwise.
    # =========================================================================
    try:
        work_map_service = WorkMapService(redis_client=redis_client)
        await work_map_service.initialize()
        set_work_map_service(work_map_service)
        set_goal_service(work_map_service._goal_service)
        logger.info("Work map service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize work map service: {e}")
        raise

    # =========================================================================
    # OPTIONAL: Planner Profile Service
    # Constructs and maintains planner operating profiles from goals,
    # worker feedback, and resource conditions. Degrades gracefully
    # if Redis unavailable.
    # =========================================================================
    try:
        from services.planner_profile_service import (
            PlannerProfileService,
            set_planner_profile_service,
        )
        planner_profile_service = PlannerProfileService(redis_client=redis_client)
        await planner_profile_service.initialize()
        set_planner_profile_service(planner_profile_service)
        logger.info("Planner profile service initialized")
    except Exception as e:
        logger.warning(f"Planner profile service initialization failed: {e}. Profile features degraded.")

    # =========================================================================
    # OPTIONAL: Bucket Tree Store + Reorganization Service
    # Provides Redis-backed bucket tree persistence and dynamic
    # reorganization when planner profiles shift.
    # Degrades gracefully if unavailable.
    # =========================================================================
    try:
        from services.bucket_tree_store import BucketTreeStore, set_bucket_tree_store
        bucket_tree_store = BucketTreeStore(redis_client=redis_client)
        set_bucket_tree_store(bucket_tree_store)
        logger.info("Bucket tree store initialized")
    except Exception as e:
        logger.warning(f"Bucket tree store initialization failed: {e}. Bucket tree features degraded.")

    try:
        from services.bucket_reorganization_service import (
            BucketReorganizationService,
            set_bucket_reorganization_service,
        )
        reorg_service = BucketReorganizationService(redis_client=redis_client)
        await reorg_service.initialize()
        set_bucket_reorganization_service(reorg_service)
        logger.info("Bucket reorganization service initialized")
    except Exception as e:
        logger.warning(f"Bucket reorganization service initialization failed: {e}. Reorganization degraded.")

    # =========================================================================
    # OPTIONAL: Feedback Aggregation Service
    # Collects worker feedback signals (blockers, challenges, requirements),
    # detects patterns, and triggers planner profile updates.
    # Degrades gracefully if unavailable.
    # =========================================================================
    try:
        from services.feedback_aggregation_service import (
            FeedbackAggregationService,
            set_feedback_aggregation_service,
        )
        feedback_service = FeedbackAggregationService(redis_client=redis_client)
        await feedback_service.initialize()
        set_feedback_aggregation_service(feedback_service)
        logger.info("Feedback aggregation service initialized")
    except Exception as e:
        logger.warning(f"Feedback aggregation service initialization failed: {e}. Feedback loop degraded.")

    # =========================================================================
    # OPTIONAL: Characterization Service
    # Translates raw tasks into characterized work with ontology tags and
    # meaning assessments. Degrades gracefully if Redis unavailable.
    # =========================================================================
    try:
        from services.characterization_service import (
            CharacterizationService,
            set_characterization_service,
        )
        char_service = CharacterizationService(redis_client=redis_client)
        await char_service.initialize()
        set_characterization_service(char_service)
        logger.info("Characterization service initialized")
    except Exception as e:
        logger.warning(f"Characterization service initialization failed: {e}. Characterization features degraded.")

    # =========================================================================
    # OPTIONAL: Conflict Detection Service
    # Detects and manages planner-level conflicts across four categories.
    # Degrades gracefully if unavailable.
    # =========================================================================
    try:
        from services.conflict_detection_service import (
            ConflictDetectionService,
            set_conflict_detection_service,
        )
        conflict_service = ConflictDetectionService(redis_client=redis_client)
        set_conflict_detection_service(conflict_service)
        logger.info("Conflict detection service initialized")
    except Exception as e:
        logger.warning(f"Conflict detection service initialization failed: {e}. Conflict features degraded.")

    # =========================================================================
    # OPTIONAL: Release Service
    # Manages releases for grouping issues by version/milestone.
    # Degrades gracefully if Redis unavailable.
    # =========================================================================
    try:
        release_service = ReleaseService(redis_client=redis_client)
        await release_service.initialize()
        set_release_service(release_service)
        logger.info("Release service initialized")
    except Exception as e:
        logger.warning(f"Release service initialization failed: {e}. Release features degraded.")

    # =========================================================================
    # REQUIRED: Goal Comment Service
    # Manages goal conversation threads and comment evaluation status.
    # Uses Redis if available, falls back to in-memory storage otherwise.
    # =========================================================================
    try:
        goal_comment_service = GoalCommentService(redis_client=redis_client)
        await goal_comment_service.initialize()
        # Connect to goals reference for bi-directional status updates
        goal_comment_service.set_goals_reference(work_map_service._goal_service._goals)
        set_goal_comment_service(goal_comment_service)
        logger.info("Goal comment service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize goal comment service: {e}")
        raise

    # =========================================================================
    # OPTIONAL: Comment Rollup Service
    # Batches rapid comment submissions for efficient evaluation.
    # Not critical - if unavailable, comments are evaluated individually.
    # =========================================================================
    rollup_service = None
    try:
        rollup_window = int(os.getenv('ROLLUP_WINDOW_SECONDS', '30'))
        quiet_period = int(os.getenv('ROLLUP_QUIET_PERIOD_SECONDS', '10'))
        rollup_enabled = os.getenv('ROLLUP_ENABLED', 'true').lower() == 'true'

        from models.work_map import RollupConfig
        rollup_config = RollupConfig(
            rollup_window_seconds=rollup_window,
            quiet_period_seconds=quiet_period,
            enabled=rollup_enabled
        )
        rollup_service = CommentRollupService(
            redis_client=redis_client,
            config=rollup_config
        )
        await rollup_service.initialize()
        set_comment_rollup_service(rollup_service)
        # Wire rollup → evaluation callback so batch evaluation actually fires
        eval_service = work_map_service._evaluation_service
        async def _rollup_evaluation_callback(goal_id: str, comment_ids: list) -> None:
            await eval_service.evaluate_batch(goal_id)
        rollup_service.set_evaluation_callback(_rollup_evaluation_callback)

        if rollup_enabled:
            logger.info(f"Comment rollup service initialized (window={rollup_window}s, quiet={quiet_period}s)")
        else:
            logger.info("Comment rollup service initialized but disabled via ROLLUP_ENABLED=false")
    except Exception as e:
        logger.warning(f"Comment rollup service not available: {e}. Comments will be evaluated individually.")

    # =========================================================================
    # REQUIRED: Project Service
    # Project management, configuration, and repository tracking.
    # Essential for multi-project orchestration workflows.
    # =========================================================================
    try:
        project_service = ProjectService(redis_client=redis_client)
        await project_service.initialize()
        # Wire up work items reference for activity calculation
        project_service.set_work_items_reference(lambda: work_map_service._work_items)
        set_project_service(project_service)
        logger.info("Project service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize project service: {e}")
        raise

    # =========================================================================
    # OPTIONAL: Specialization Service
    # Worker specialization boundary management for domain-aware assignment.
    # =========================================================================
    try:
        from services.specialization_service import (
            SpecializationService,
            set_specialization_service,
        )
        spec_service = SpecializationService(redis_client=redis_client)
        set_specialization_service(spec_service)
        logger.info("Specialization service initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize specialization service: {e}")

    # =========================================================================
    # OPTIONAL: Decision Trace Service
    # Records decision traceability entries for planning decisions.
    # Degrades gracefully if unavailable.
    # =========================================================================
    try:
        from services.decision_trace_service import (
            DecisionTraceService,
            set_decision_trace_service,
        )
        decision_trace_service = DecisionTraceService(redis_client=redis_client)
        set_decision_trace_service(decision_trace_service)
        logger.info("Decision trace service initialized")
    except Exception as e:
        logger.warning(f"Decision trace service initialization failed: {e}. Traceability features degraded.")

    # =========================================================================
    # OPTIONAL: Planner Focus Service
    # Aggregates planner profile, goals, and issues into focus summaries
    # and goal alignment views. Stateless — no persistence needed.
    # =========================================================================
    try:
        from services.planner_focus_service import (
            PlannerFocusService,
            set_planner_focus_service,
        )
        planner_focus_svc = PlannerFocusService()
        set_planner_focus_service(planner_focus_svc)
        logger.info("Planner focus service initialized")
    except Exception as e:
        logger.warning(f"Planner focus service initialization failed: {e}. Focus views degraded.")

    # =========================================================================
    # OPTIONAL: Notification Service
    # In-memory notification feed for system event alerts in the UI.
    # =========================================================================
    try:
        from services.notification_service import (
            NotificationService,
            set_notification_service,
        )
        notification_svc = NotificationService()
        set_notification_service(notification_svc)
        logger.info("Notification service initialized")
    except Exception as e:
        logger.warning(f"Notification service initialization failed: {e}.")

    # =========================================================================
    # OPTIONAL: Directive Service
    # Interprets and applies user topology directives to planner profiles.
    # Degrades gracefully if unavailable.
    # =========================================================================
    try:
        from services.directive_service import (
            DirectiveService,
            set_directive_service,
        )
        directive_svc = DirectiveService(redis_client=redis_client)
        set_directive_service(directive_svc)
        logger.info("Directive service initialized")
    except Exception as e:
        logger.warning(f"Directive service initialization failed: {e}.")

    # =========================================================================
    # OPTIONAL: Unified Directive Service
    # Merges goal creation and priority-shift directives into a single
    # entry point with intent classification.  Degrades gracefully.
    # =========================================================================
    try:
        from services.unified_directive_service import (
            UnifiedDirectiveService,
            set_unified_directive_service,
        )
        unified_directive_svc = UnifiedDirectiveService(redis_client=redis_client)
        set_unified_directive_service(unified_directive_svc)
        logger.info("Unified directive service initialized")
    except Exception as e:
        logger.warning(f"Unified directive service initialization failed: {e}.")

    # =========================================================================
    # OPTIONAL: Issue Evaluation Service
    # Post-completion review of issues for success/failure determination.
    # Creates follow-up issues for partial/failed outcomes.
    # =========================================================================
    try:
        from services.issue_evaluation_service import (
            IssueEvaluationService,
            set_issue_evaluation_service,
        )
        from services.issue_ops_service import get_issue_ops_service
        issue_eval_service = IssueEvaluationService(
            issue_ops_service=get_issue_ops_service()
        )
        await issue_eval_service.start()
        set_issue_evaluation_service(issue_eval_service)
        logger.info("Issue evaluation service initialized")
    except Exception as e:
        logger.warning(f"Issue evaluation service initialization failed: {e}.")

    # =========================================================================
    # REQUIRED: Compute Spawner
    # Claude Code instance lifecycle management (spawn, monitor, terminate).
    # Core to the compute orchestration workflow.
    # =========================================================================
    try:
        workspaces_path = os.getenv('WORKSPACES_PATH', f'{storage_path}/workspaces')
        compute_spawner = ComputeSpawner(
            serving_url=os.getenv('SERVING_PUBLIC_URL', 'http://localhost:8002'),
            workspaces_path=workspaces_path
        )
        await compute_spawner.initialize()
        set_compute_spawner(compute_spawner)
        logger.info(f"Compute spawner initialized (workspaces: {workspaces_path})")
    except Exception as e:
        logger.error(f"Failed to initialize compute spawner: {e}")
        raise

    # =========================================================================
    # OPTIONAL: SSE Connection Manager
    # Server-Sent Events for real-time event push to compute instances.
    # Not critical for core operation; compute can poll for updates instead.
    # =========================================================================
    sse_manager = None
    try:
        keepalive_interval = int(os.getenv('SSE_KEEPALIVE_INTERVAL', '30'))
        sse_manager = SSEConnectionManager(keepalive_interval=keepalive_interval)
        await sse_manager.start()
        set_sse_connection_manager(sse_manager)
        logger.info(f"SSE connection manager started (keepalive: {keepalive_interval}s)")
    except Exception as e:
        logger.error(f"Failed to initialize SSE connection manager: {e}")
        # Don't raise - SSE is not critical for startup

    # =========================================================================
    # Claude Auth Service
    # Manages Claude API tokens for serving-centric authentication.
    # Tokens are stored in Redis. Compute containers fetch tokens from
    # this service instead of mounting host ~/.claude volumes.
    # Always enabled — checks for existing tokens on startup and shows
    # the setup page if none are found.
    # =========================================================================
    try:
        claude_auth_service = ClaudeAuthService(redis_client=redis_client)
        await claude_auth_service.initialize()
        # Wire SSE broadcast for credentials_refresh events
        if sse_manager:
            claude_auth_service.set_broadcast_callback(sse_manager.broadcast_event)
            claude_auth_service.set_send_event_callback(sse_manager.send_event)
        set_claude_auth_service(claude_auth_service)
        logger.info("Claude auth service initialized (Redis-backed token storage)")
    except Exception as e:
        set_claude_auth_service(None)
        logger.warning(f"Claude auth service initialization failed: {e}. Auth features disabled.")

    # =========================================================================
    # OPTIONAL: Token Re-push on Compute Reconnect
    # When a compute reconnects via SSE, check if it has a stored token
    # and re-push it so the compute can re-authorize immediately.
    # =========================================================================
    if sse_manager and claude_auth_service:
        async def _on_compute_reconnect_auth(compute_id: str) -> None:
            """Re-push stored token and sync registry auth_status when compute reconnects."""
            try:
                auth_svc = get_claude_auth_service()
                if not auth_svc:
                    return
                pushed = await auth_svc.push_token_to_compute(compute_id)
                if pushed:
                    # Sync registry auth_status so the UI reflects the real state
                    from models.compute import ComputeAuthStatus
                    from services.registry_service import get_compute_registry
                    reg = get_compute_registry()
                    if reg:
                        token_data = auth_svc._tokens.get(compute_id, {})
                        expires_at_str = token_data.get("expires_at")
                        expires_at = (
                            datetime.fromisoformat(expires_at_str)
                            if expires_at_str else None
                        )
                        await reg.update_auth_status(
                            compute_id,
                            ComputeAuthStatus.AUTHORIZED,
                            auth_expires_at=expires_at,
                        )
                        logger.info(f"Synced registry auth_status for {compute_id} to AUTHORIZED on reconnect")
            except Exception as e:
                logger.debug(f"Token re-push on reconnect for {compute_id}: {e}")

        sse_manager.on_connect(_on_compute_reconnect_auth)
        logger.info("Token re-push on reconnect handler registered")

    # =========================================================================
    # OPTIONAL: Git Token Provisioning for Compute Lifecycle
    # Generates and delivers Git HTTP tokens when compute instances connect
    # via SSE, enabling them to clone/push Git repos. Revokes on disconnect.
    # =========================================================================
    if sse_manager:
        try:
            from git.git_token_service import get_git_token_service

            async def _on_compute_connect_git(compute_id: str) -> None:
                """Generate and deliver Git token when compute connects."""
                try:
                    token_svc = get_git_token_service()
                    if not token_svc:
                        return
                    token = await token_svc.create_compute_token(compute_id)
                    await sse_manager.send_event(compute_id, "git_token_provisioned", {
                        "token": token,
                        "compute_id": compute_id,
                    })
                    logger.info(f"Git token provisioned for {compute_id}")
                except Exception as e:
                    logger.error(f"Failed to provision Git token for {compute_id}: {e}")

            async def _on_compute_disconnect_git(compute_id: str) -> None:
                """Revoke Git token when compute disconnects."""
                try:
                    token_svc = get_git_token_service()
                    if not token_svc:
                        return
                    await token_svc.revoke_compute_token(compute_id)
                    logger.info(f"Git token revoked for {compute_id}")
                except Exception as e:
                    logger.warning(f"Failed to revoke Git token for {compute_id}: {e}")

            sse_manager.on_connect(_on_compute_connect_git)
            sse_manager.on_disconnect(_on_compute_disconnect_git)
            logger.info("Git token provisioning handlers registered")
        except Exception as e:
            logger.warning(f"Git token provisioning not available: {e}")

    # =========================================================================
    # OPTIONAL: Work Dispatcher (event-driven)
    # Replaces polling-based task dispatch with asyncio.Event signals.
    # Triggered by compute idle events and work availability signals.
    # =========================================================================
    try:
        dispatcher_enabled = os.getenv('DISPATCHER_ENABLED', 'true').lower() == 'true'
        if dispatcher_enabled:
            await start_work_dispatcher()
            logger.info("Work dispatcher started (event-driven dispatch)")

            # Trigger dispatch when a new compute connects via SSE
            if sse_manager:
                async def _on_compute_connect_dispatch(compute_id: str) -> None:
                    try:
                        from services.work_dispatcher import get_work_dispatcher
                        get_work_dispatcher().trigger(
                            reason=f"new_compute_connected:{compute_id}"
                        )
                    except Exception:
                        pass

                sse_manager.on_connect(_on_compute_connect_dispatch)
                logger.info("Dispatcher hooked to SSE on_connect event")
        else:
            logger.info("Work dispatcher disabled via DISPATCHER_ENABLED=false")
    except Exception as e:
        logger.warning(f"Failed to start work dispatcher: {e}. Falling back to polling-only dispatch.")

    # =========================================================================
    # OPTIONAL: Reconciliation Manager
    # Periodic safety net (45s) that catches stuck items, orphaned tasks,
    # and consistency issues missed by the event-driven dispatch path.
    # =========================================================================
    try:
        reconcile_enabled = os.getenv('RECONCILIATION_ENABLED', 'true').lower() == 'true'
        reconcile_interval = int(os.getenv('RECONCILIATION_INTERVAL_SECONDS', '45'))
        if reconcile_enabled:
            await start_reconciliation_manager(check_interval=reconcile_interval)
            logger.info(
                f"Reconciliation manager started (interval={reconcile_interval}s)"
            )
        else:
            logger.info("Reconciliation manager disabled via RECONCILIATION_ENABLED=false")
    except Exception as e:
        logger.warning(f"Failed to start reconciliation manager: {e}")

    # =========================================================================
    # OPTIONAL: Work Orchestrator
    # Automatic polling and spawning of compute instances for pending work.
    # Can be disabled via ORCHESTRATOR_ENABLED=false for manual control.
    # Without this, work must be manually assigned and spawned.
    # =========================================================================
    try:
        orchestrator_poll_interval = int(os.getenv('ORCHESTRATOR_POLL_INTERVAL', '10'))
        orchestrator_max_spawns = int(os.getenv('ORCHESTRATOR_MAX_CONCURRENT_SPAWNS', '5'))
        orchestrator_max_retries = int(os.getenv('ORCHESTRATOR_MAX_RETRIES', '3'))
        orchestrator_retry_delay = int(os.getenv('ORCHESTRATOR_RETRY_DELAY', '30'))
        orchestrator_enabled = os.getenv('ORCHESTRATOR_ENABLED', 'true').lower() == 'true'

        # Work timeout configuration
        timeout_minutes = int(os.getenv('WORK_TIMEOUT_MINUTES', '30'))
        timeout_check_interval = int(os.getenv('WORK_TIMEOUT_CHECK_INTERVAL', '60'))
        timeout_max_retries = int(os.getenv('WORK_TIMEOUT_MAX_RETRIES', '3'))
        timeout_enabled = os.getenv('WORK_TIMEOUT_ENABLED', 'true').lower() == 'true'

        if orchestrator_enabled:
            await start_work_orchestration(
                poll_interval=orchestrator_poll_interval,
                max_concurrent_spawns=orchestrator_max_spawns,
                max_retries=orchestrator_max_retries,
                retry_delay=orchestrator_retry_delay,
                timeout_minutes=timeout_minutes,
                timeout_check_interval=timeout_check_interval,
                timeout_max_retries=timeout_max_retries,
                timeout_enabled=timeout_enabled
            )
            timeout_status = f"timeout={timeout_minutes}m" if timeout_enabled else "timeout=disabled"
            logger.info(
                f"Work orchestrator started "
                f"(poll_interval={orchestrator_poll_interval}s, "
                f"max_spawns={orchestrator_max_spawns}, "
                f"{timeout_status})"
            )
        else:
            logger.info("Work orchestrator disabled via ORCHESTRATOR_ENABLED=false")
    except Exception as e:
        logger.error(f"Failed to start work orchestrator: {e}")
        # Don't raise - orchestrator is not critical for startup

    logger.info("Serving component started successfully")

    yield
    
    # Shutdown
    logger.info("Shutting down Serving component...")

    # Stop reconciliation manager
    try:
        await stop_reconciliation_manager()
        logger.info("Reconciliation manager stopped")
    except Exception as e:
        logger.debug(f"Reconciliation manager cleanup: {e}")

    # Stop work dispatcher
    try:
        await stop_work_dispatcher()
        logger.info("Work dispatcher stopped")
    except Exception as e:
        logger.debug(f"Work dispatcher cleanup: {e}")

    # Stop work orchestrator
    try:
        await stop_work_orchestration()
        logger.info("Work orchestrator stopped")
    except Exception as e:
        logger.debug(f"Work orchestrator cleanup: {e}")

    # Stop compute instances
    try:
        from services.compute_spawner import get_compute_spawner
        spawner = get_compute_spawner()
        await spawner.shutdown()
        logger.info("Compute instances stopped")
    except Exception as e:
        logger.debug(f"Compute spawner cleanup: {e}")

    # Stop Claude auth service
    try:
        auth_svc = get_claude_auth_service()
        if auth_svc:
            await auth_svc.shutdown()
            logger.info("Claude auth service stopped")
    except Exception as e:
        logger.debug(f"Claude auth service cleanup: {e}")

    # Stop SSE connection manager
    try:
        sse_mgr = get_sse_connection_manager()
        if sse_mgr:
            await sse_mgr.stop()
            logger.info("SSE connection manager stopped")
    except Exception as e:
        logger.debug(f"SSE manager cleanup: {e}")

    # Stop issue evaluation service
    try:
        from services.issue_evaluation_service import get_issue_evaluation_service
        await get_issue_evaluation_service().stop()
        logger.info("Issue evaluation service stopped")
    except Exception:
        pass

    # Stop comment rollup service
    try:
        rollup_svc = get_comment_rollup_service()
        if rollup_svc:
            await rollup_svc.shutdown()
            logger.info("Comment rollup service stopped")
    except Exception as e:
        logger.debug(f"Comment rollup service cleanup: {e}")

    # Stop health monitoring
    try:
        await stop_health_monitoring()
        logger.info("Health monitoring stopped")
    except Exception as e:
        logger.error(f"Error stopping health monitoring: {e}")

    # Close Redis connection
    try:
        from git.redis_client import close_redis
        await close_redis()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.debug(f"Redis cleanup: {e}")

    logger.info("Serving component stopped")


# Create FastAPI app
app = FastAPI(
    title="ClaudeVN Serving Component",
    description="Central orchestration hub for coordinating agent execution",
    version=get_version(),
    lifespan=lifespan
)


# Configure CORS
cors_origins = os.getenv('CORS_ORIGINS', '*')
if cors_origins == '*':
    origins = ["*"]
else:
    origins = [origin.strip() for origin in cors_origins.split(',')]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)


# Include routers with /api/v1 prefix
API_VERSION = os.getenv('API_VERSION', 'v1')
api_prefix = f"/api/{API_VERSION}"

app.include_router(compute.router, prefix=api_prefix)
app.include_router(marketplaces.router, prefix=api_prefix)
app.include_router(skills.router, prefix=api_prefix)
app.include_router(agents.router, prefix=api_prefix)
app.include_router(facilitated_sessions.router, prefix=api_prefix)
app.include_router(tasks.router, prefix=api_prefix)
app.include_router(pipelines.router, prefix=api_prefix)
app.include_router(process_maps.router, prefix=api_prefix)
app.include_router(logs.router, prefix=api_prefix)
app.include_router(cache.router, prefix=api_prefix)
app.include_router(git.router, prefix=api_prefix)
app.include_router(work_map.router, prefix=api_prefix)
app.include_router(work_map.goals_router, prefix=api_prefix)
app.include_router(work_map.issues_router, prefix=api_prefix)
app.include_router(work_map.releases_router, prefix=api_prefix)
app.include_router(work_map.workmap_router, prefix=api_prefix)
app.include_router(spawner.router, prefix=api_prefix)
app.include_router(projects.router, prefix=api_prefix)
app.include_router(orchestrator.router, prefix=api_prefix)
app.include_router(slim_claude_code.router, prefix=api_prefix)
app.include_router(characterization.router, prefix=api_prefix)
app.include_router(conflicts.router, prefix=api_prefix)
app.include_router(feedback.router, prefix=api_prefix)
app.include_router(specialization.router, prefix=api_prefix)
app.include_router(plan_summary.router, prefix=api_prefix)
app.include_router(profile_presets.router, prefix=api_prefix)
app.include_router(notifications.router, prefix=api_prefix)
app.include_router(unified_directives.router, prefix=api_prefix)
app.include_router(auth.router, prefix=api_prefix)
app.include_router(get_router(), prefix=api_prefix)
app.include_router(decision_traces.router)  # Already has /api/v1 in router prefix
# Note: Skill marketplace is a separate service on port 8003 - use MarketplaceClient
app.include_router(observability.router)  # Already has /api/v1 in router prefix

# Git Smart HTTP backend (mounted at /git/ for clean clone URLs)
from git.http_backend import router as git_http_router
app.include_router(git_http_router)


# Health check endpoint
@app.get(f"{api_prefix}/health")
async def health_check():
    """Health check endpoint."""
    from services.registry_service import get_compute_registry
    from services.marketplace_registry import get_marketplace_registry
    
    compute_registry = get_compute_registry()
    marketplace_registry = get_marketplace_registry()
    
    compute_stats = compute_registry.get_stats()
    marketplace_stats = marketplace_registry.get_stats()
    
    # Get skill marketplace stats (via HTTP client to separate service)
    try:
        marketplace_client = get_marketplace_client()
        marketplace_health = await marketplace_client.health_check()
        skill_stats = {
            "total_skills": marketplace_health.get("skills_count", 0),
            "total_tools": marketplace_health.get("tools_count", 0),
            "status": "connected"
        }
    except Exception:
        skill_stats = {"total_skills": 0, "total_tools": 0, "status": "unavailable"}

    # Get spawner stats
    from services.compute_spawner import get_compute_spawner
    try:
        spawner = get_compute_spawner()
        spawner_result = await spawner.list_instances()
        spawner_stats = {
            "total_instances": spawner_result.total,
            "by_state": spawner_result.by_state
        }
    except Exception:
        spawner_stats = {"total_instances": 0, "by_state": {}}

    # Get work map stats
    from services.work_map_service import get_work_map_service
    try:
        work_map_svc = get_work_map_service()
        work_stats = await work_map_svc.get_stats()
        issue_stats = await work_map_svc.get_issue_stats()
        goal_list = await work_map_svc.list_goals()
        work_map_stats = {
            "total_work": work_stats.total,
            "by_status": work_stats.by_status,
            "goals": {
                "total": goal_list.total,
                "by_status": goal_list.by_status
            },
            "issues": {
                "total": issue_stats.total,
                "ready": issue_stats.ready_count,
                "in_progress": issue_stats.in_progress_count,
                "blocked": issue_stats.blocked_count
            }
        }
    except Exception:
        work_map_stats = {"total_work": 0, "by_status": {}, "goals": {}, "issues": {}}

    # Get orchestrator stats
    try:
        orch = get_work_orchestrator()
        orchestrator_stats = orch.get_stats() if orch else {"running": False}
    except Exception:
        orchestrator_stats = {"running": False}

    # Get rate limiter stats
    try:
        rate_limiter = get_rate_limiter()
        rate_limit_stats = rate_limiter.get_metrics() if rate_limiter else {"enabled": False}
    except Exception:
        rate_limit_stats = {"enabled": False}

    # Get Redis health status
    from git.redis_client import get_redis_client
    try:
        redis_client = get_redis_client()
        if redis_client:
            redis_health = await redis_client.health_check()
            redis_stats = {
                "connected": redis_health.get("connected", False),
                "response_time_ms": redis_health.get("response_time_ms"),
                "error": redis_health.get("error")
            }
        else:
            redis_stats = {"connected": False, "error": "Redis client not initialized"}
    except Exception as e:
        redis_stats = {"connected": False, "error": str(e)}

    # Get Claude auth status
    try:
        auth_svc = get_claude_auth_service()
        claude_auth_stats = auth_svc.get_status() if auth_svc else {"enabled": False}
    except Exception:
        claude_auth_stats = {"enabled": False}

    return {
        "status": "healthy",
        "service": "serving",
        "version": get_version(),
        "claude_auth": claude_auth_stats,
        "redis": redis_stats,
        "compute_registry": {
            "total_instances": compute_stats["total_instances"],
            "by_status": compute_stats["by_status"]
        },
        "marketplace_registry": {
            "total_marketplaces": marketplace_stats["total_marketplaces"],
            "by_status": marketplace_stats["by_status"]
        },
        "skill_registry": {
            "total_skills": skill_stats.get("total_skills", 0),
            "total_tools": skill_stats.get("total_tools", 0)
        },
        "compute_spawner": spawner_stats,
        "work_map": work_map_stats,
        "work_orchestrator": orchestrator_stats,
        "rate_limiter": rate_limit_stats
    }


# Serve frontend static files if they exist
frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists() and frontend_dist.is_dir():
    # Mount static files (CSS, JS, images)
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")
    
    # Serve index.html for all non-API routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend or return JSON info for root."""
        # If accessing root without any path, serve frontend
        if not full_path or full_path == "/":
            index_file = frontend_dist / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            # Fallback to JSON info if frontend not built
            return {
                "service": "ClaudeVN Serving Component",
                "version": "0.2.0",
                "status": "running",
                "api_docs": "/docs",
                "api_version": API_VERSION,
                "note": "Frontend not built. Run: cd frontend && npm install && npm run build"
            }
        
        # Serve static files from dist root (e.g. logo PNGs, favicon)
        static_file = frontend_dist / full_path
        if static_file.exists() and static_file.is_file() and frontend_dist in static_file.resolve().parents:
            return FileResponse(static_file)

        # For any other path, serve index.html for client-side routing
        if not full_path.startswith(("api/", "docs", "openapi.json", "redoc")):
            index_file = frontend_dist / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
        
        # If we get here, it's a 404
        return {"error": "Not found"}
    
    logger.info(f"Frontend static files mounted from: {frontend_dist}")
else:
    # Frontend not built - provide JSON endpoint
    @app.get("/")
    def root():
        """Root endpoint with service information."""
        return {
            "service": "ClaudeVN Serving Component",
            "version": "0.2.0",
            "status": "running",
            "api_docs": "/docs",
            "api_version": API_VERSION,
            "frontend": "not_built",
            "instructions": "To build frontend: cd frontend && npm install && npm run build"
        }
    
    logger.warning(f"Frontend not found at: {frontend_dist}. API-only mode.")


@app.get("/api")
def api_info():
    """API version information."""
    marketplace_url = os.getenv('MARKETPLACE_URL', 'http://localhost:8003')
    return {
        "version": API_VERSION,
        "endpoints": {
            "compute": f"{api_prefix}/compute",
            "marketplaces": f"{api_prefix}/marketplaces",
            "sessions": f"{api_prefix}/sessions",
            "git": f"{api_prefix}/git",
            "mcp": f"{api_prefix}/mcp",
            "health": f"{api_prefix}/health"
        },
        "external_services": {
            "skills_marketplace": f"{marketplace_url}/api/v1/skills"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv('SERVING_HOST', '0.0.0.0')
    port = int(os.getenv('SERVING_PORT', 8002))
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=True,
        log_level=os.getenv('LOG_LEVEL', 'info').lower()
    )

