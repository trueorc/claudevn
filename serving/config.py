"""Configuration management for Serving Component."""

import os
import sys
from typing import Optional, List
from pydantic import BaseModel, Field


def is_test_environment() -> bool:
    """Detect if running in a test environment.

    Checks for common test environment indicators:
    - PYTEST_CURRENT_TEST: Set by pytest during test runs
    - TESTING: Explicit testing flag
    - pytest in sys.modules: pytest has been imported

    Returns:
        True if running in a test environment, False otherwise.
    """
    return (
        os.getenv("PYTEST_CURRENT_TEST") is not None or
        os.getenv("TESTING", "").lower() == "true" or
        "pytest" in sys.modules
    )


class ServerConfig(BaseModel):
    """Server configuration."""
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8002, description="Server port")
    api_version: str = Field(default="v1", description="API version")
    log_level: str = Field(default="INFO", description="Logging level")
    cors_origins: str = Field(default="*", description="CORS origins (comma-separated)")


class StorageConfig(BaseModel):
    """Storage configuration."""
    storage_path: str = Field(default="./data/serving", description="Base storage path")
    cache_path: Optional[str] = Field(None, description="Cache path (defaults to storage_path/cache)")
    datastore_path: Optional[str] = Field(None, description="Datastore path (defaults to storage_path/datastore)")
    cache_default_ttl: int = Field(default=300, description="Default cache TTL in seconds")


class HealthMonitorConfig(BaseModel):
    """Health monitoring configuration."""
    check_interval: int = Field(default=30, description="Health check interval in seconds")
    degraded_threshold: int = Field(default=60, description="Seconds before marking degraded")
    offline_threshold: int = Field(default=90, description="Seconds before marking offline")
    max_failed_checks: int = Field(default=3, description="Max failed checks before action")
    auto_deregister: bool = Field(default=False, description="Auto-deregister failed instances")


class WorkTimeoutConfig(BaseModel):
    """Work timeout and stuck-work detection configuration."""
    timeout_minutes: int = Field(default=30, description="Minutes before work is considered stuck")
    check_interval: int = Field(default=60, description="Seconds between stuck-work checks")
    max_retries: int = Field(default=0, description="Maximum retries before marking as FAILED (0 = no retries)")
    enabled: bool = Field(default=True, description="Enable stuck-work detection")


class SessionConfig(BaseModel):
    """Session management configuration."""
    enable_persistence: bool = Field(default=True, description="Enable session persistence")
    session_timeout: int = Field(default=3600, description="Session timeout in seconds")


class RedisConfig(BaseModel):
    """Redis configuration."""
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")
    key_prefix: str = Field(default="claudevn:", description="Key prefix for all Redis keys")

    @property
    def url(self) -> str:
        """Get Redis URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class GitConfig(BaseModel):
    """Git infrastructure configuration."""
    repos_path: str = Field(default="./data/repos", description="Path to bare Git repositories")
    ssh_keys_path: str = Field(default="./data/ssh_keys", description="Path to SSH keys for external repo auth")
    hook_redis_notify: bool = Field(default=True, description="Enable Redis notifications from Git hooks")


class MarketplaceConfig(BaseModel):
    """Marketplace connection configuration for multi-network support."""
    url: str = Field(default="http://localhost:8003", description="Marketplace service URL")
    api_key: Optional[str] = Field(default=None, description="API key for marketplace authentication")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds for skill data")
    fallback_skills: List[str] = Field(
        default=["code-implementation", "bug-investigation"],
        description="Default skills to use when marketplace is unavailable"
    )


class CognitoConfig(BaseModel):
    """Authentication configuration (supports cognito, local, and bypass modes)."""
    auth_mode: str = Field(default="bypass", description="Auth mode: 'cognito', 'local', or 'bypass'")
    user_pool_id: str = Field(default="", description="Cognito User Pool ID")
    app_client_id: str = Field(default="", description="Cognito App Client ID")
    region: str = Field(default="us-east-1", description="AWS region for Cognito")
    admin_enabled: bool = Field(default=False, description="Enable admin user management endpoints")
    local_users_file: str = Field(default="users.local", description="Path to local users credential file (AUTH_MODE=local)")


class AutoDrainConfig(BaseModel):
    """Auto-drain configuration for idle managed compute instances."""
    enabled: bool = Field(default=True, description="Enable auto-drain of idle managed instances")
    check_interval_seconds: int = Field(default=60, description="Seconds between idle checks")
    idle_grace_period_minutes: int = Field(default=5, description="Minutes idle before drain starts")


class QualityGateConfig(BaseModel):
    """Quality gate configuration for PR validation."""
    enabled: bool = Field(default=True, description="Enable quality gates for auto-merge")
    syntax_check: bool = Field(default=True, description="Run syntax/import validation on changed Python files")
    test_gate: bool = Field(default=True, description="Run test suite before merge")
    startup_smoke_test: bool = Field(default=False, description="Run application startup smoke test")
    config_completeness: bool = Field(default=False, description="Validate config completeness")
    timeout_seconds: int = Field(default=300, description="Timeout for quality gate execution")


class DockerImageMapping(BaseModel):
    """Maps a Docker image to the capabilities it provides."""
    image: str = Field(..., description="Docker image name:tag")
    capabilities: List[str] = Field(default_factory=list, description="Capabilities provided by this image")


class DockerProvisionerConfig(BaseModel):
    """Docker provisioner configuration."""
    enabled: bool = Field(default=False, description="Enable Docker provisioner")
    socket: str = Field(default="/var/run/docker.sock", description="Docker socket path")
    network: str = Field(default="claudevn-network", description="Docker network for compute containers")
    serving_url: str = Field(default="http://serving:8002", description="Serving URL for compute containers")
    container_prefix: str = Field(default="claudevn-managed-", description="Prefix for managed container names")
    image_mappings: List[DockerImageMapping] = Field(default_factory=list, description="Image-to-capability mappings")
    default_image: str = Field(default="trueorc/compute-base:latest", description="Fallback image when no specific mapping matches")


class NetworkCapacityConfig(BaseModel):
    """Network capacity configuration."""
    max_compute_instances: int = Field(
        default=0, description="Maximum compute instances (0 = unlimited)"
    )


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""
    enabled: bool = Field(default=True, description="Enable rate limiting")
    default_requests_per_minute: int = Field(
        default=60, description="Default requests per minute for endpoints"
    )
    compute_requests_per_minute: int = Field(
        default=120, description="Requests per minute for /compute/* endpoints"
    )
    work_requests_per_minute: int = Field(
        default=60, description="Requests per minute for /work/* endpoints"
    )
    pr_requests_per_minute: int = Field(
        default=30, description="Requests per minute for /pr/* endpoints"
    )
    burst_multiplier: float = Field(
        default=1.5, description="Multiplier for burst capacity above rate limit"
    )


class ServingConfig(BaseModel):
    """Complete serving component configuration."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    health_monitor: HealthMonitorConfig = Field(default_factory=HealthMonitorConfig)
    work_timeout: WorkTimeoutConfig = Field(default_factory=WorkTimeoutConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    marketplace: MarketplaceConfig = Field(default_factory=MarketplaceConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    network_capacity: NetworkCapacityConfig = Field(default_factory=NetworkCapacityConfig)
    cognito: CognitoConfig = Field(default_factory=CognitoConfig)
    docker_provisioner: DockerProvisionerConfig = Field(default_factory=DockerProvisionerConfig)
    auto_drain: AutoDrainConfig = Field(default_factory=AutoDrainConfig)
    quality_gate: QualityGateConfig = Field(default_factory=QualityGateConfig)
    demo_mode: bool = Field(default=False, description="Demo mode - blocks real compute execution")

    @classmethod
    def from_env(cls) -> "ServingConfig":
        """Load configuration from environment variables."""
        
        # Server config
        server = ServerConfig(
            host=os.getenv("SERVING_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVING_PORT", "8002")),
            api_version=os.getenv("API_VERSION", "v1"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            cors_origins=os.getenv("CORS_ORIGINS", "*")
        )
        
        # Storage config
        storage_path = os.getenv("STORAGE_PATH", "./data/serving")
        storage = StorageConfig(
            storage_path=storage_path,
            cache_path=os.getenv("CACHE_PATH", f"{storage_path}/cache"),
            datastore_path=os.getenv("DATASTORE_PATH", f"{storage_path}/datastore"),
            cache_default_ttl=int(os.getenv("CACHE_DEFAULT_TTL", "300"))
        )
        
        # Health monitor config
        health_monitor = HealthMonitorConfig(
            check_interval=int(os.getenv("HEALTH_CHECK_INTERVAL", "30")),
            degraded_threshold=int(os.getenv("DEGRADED_THRESHOLD", "60")),
            offline_threshold=int(os.getenv("OFFLINE_THRESHOLD", "90")),
            max_failed_checks=int(os.getenv("MAX_FAILED_CHECKS", "3")),
            auto_deregister=os.getenv("AUTO_DEREGISTER", "false").lower() == "true"
        )
        
        # Session config
        session = SessionConfig(
            enable_persistence=os.getenv("SESSION_PERSISTENCE", "true").lower() == "true",
            session_timeout=int(os.getenv("SESSION_TIMEOUT", "3600"))
        )

        # Redis config
        redis = RedisConfig(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
            key_prefix=os.getenv("REDIS_KEY_PREFIX", "claudevn:")
        )

        # Git config
        git = GitConfig(
            repos_path=os.getenv("GIT_REPOS_PATH", f"{storage_path}/repos"),
            ssh_keys_path=os.getenv("GIT_SSH_KEYS_PATH", f"{storage_path}/ssh_keys"),
            hook_redis_notify=os.getenv("GIT_HOOK_REDIS_NOTIFY", "true").lower() == "true",
        )

        # Work timeout config
        work_timeout = WorkTimeoutConfig(
            timeout_minutes=int(os.getenv("WORK_TIMEOUT_MINUTES", "30")),
            check_interval=int(os.getenv("WORK_TIMEOUT_CHECK_INTERVAL", "60")),
            max_retries=int(os.getenv("WORK_TIMEOUT_MAX_RETRIES", "3")),
            enabled=os.getenv("WORK_TIMEOUT_ENABLED", "true").lower() == "true"
        )

        # Marketplace config
        fallback_skills_str = os.getenv("MARKETPLACE_FALLBACK_SKILLS", "code-implementation,bug-investigation")
        fallback_skills = [s.strip() for s in fallback_skills_str.split(",") if s.strip()]
        marketplace = MarketplaceConfig(
            url=os.getenv("MARKETPLACE_URL", "http://localhost:8003"),
            api_key=os.getenv("MARKETPLACE_API_KEY"),
            cache_ttl=int(os.getenv("MARKETPLACE_CACHE_TTL", "300")),
            fallback_skills=fallback_skills
        )

        # Rate limit config
        # Auto-disable rate limiting in test environments unless explicitly enabled
        rate_limit_enabled_env = os.getenv("RATE_LIMIT_ENABLED")
        if rate_limit_enabled_env is not None:
            # Explicit configuration takes precedence
            rate_limit_enabled = rate_limit_enabled_env.lower() == "true"
        else:
            # Auto-disable in test environments, enable otherwise
            rate_limit_enabled = not is_test_environment()

        rate_limit = RateLimitConfig(
            enabled=rate_limit_enabled,
            default_requests_per_minute=int(os.getenv("RATE_LIMIT_DEFAULT_RPM", "60")),
            compute_requests_per_minute=int(os.getenv("RATE_LIMIT_COMPUTE_RPM", "120")),
            work_requests_per_minute=int(os.getenv("RATE_LIMIT_WORK_RPM", "60")),
            pr_requests_per_minute=int(os.getenv("RATE_LIMIT_PR_RPM", "30")),
            burst_multiplier=float(os.getenv("RATE_LIMIT_BURST_MULTIPLIER", "1.5"))
        )

        # Network capacity config
        network_capacity = NetworkCapacityConfig(
            max_compute_instances=int(os.getenv("MAX_COMPUTE_INSTANCES", "0")),
        )

        # Auth config (cognito, local, or bypass)
        cognito = CognitoConfig(
            auth_mode=os.getenv("AUTH_MODE", "bypass"),
            user_pool_id=os.getenv("COGNITO_USER_POOL_ID", ""),
            app_client_id=os.getenv("COGNITO_APP_CLIENT_ID", ""),
            region=os.getenv("COGNITO_REGION", "us-east-1"),
            admin_enabled=os.getenv("COGNITO_ADMIN_ENABLED", "false").lower() == "true",
            local_users_file=os.getenv("LOCAL_USERS_FILE", "users.local"),
        )

        demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"

        # Docker provisioner config
        import json as _json
        docker_image_mappings_raw = os.getenv("DOCKER_PROVISIONER_IMAGES", "")
        docker_image_mappings = []
        if docker_image_mappings_raw:
            try:
                docker_image_mappings = [
                    DockerImageMapping(**m)
                    for m in _json.loads(docker_image_mappings_raw)
                ]
            except Exception:
                pass
        docker_provisioner = DockerProvisionerConfig(
            enabled=os.getenv("DOCKER_PROVISIONER_ENABLED", "false").lower() == "true",
            socket=os.getenv("DOCKER_PROVISIONER_SOCKET", "/var/run/docker.sock"),
            network=os.getenv("DOCKER_PROVISIONER_NETWORK", "claudevn-network"),
            serving_url=os.getenv("SERVING_PUBLIC_URL", "http://serving:8002"),
            container_prefix=os.getenv("DOCKER_PROVISIONER_PREFIX", "claudevn-managed-"),
            image_mappings=docker_image_mappings,
            default_image=os.getenv("DOCKER_PROVISIONER_DEFAULT_IMAGE", "trueorc/compute-base:latest"),
        )

        # Auto-drain config
        auto_drain = AutoDrainConfig(
            enabled=os.getenv("AUTO_DRAIN_ENABLED", "true").lower() == "true",
            check_interval_seconds=int(os.getenv("AUTO_DRAIN_CHECK_INTERVAL", "60")),
            idle_grace_period_minutes=int(os.getenv("AUTO_DRAIN_GRACE_PERIOD", "5")),
        )

        return cls(
            server=server,
            storage=storage,
            health_monitor=health_monitor,
            work_timeout=work_timeout,
            session=session,
            redis=redis,
            git=git,
            marketplace=marketplace,
            rate_limit=rate_limit,
            network_capacity=network_capacity,
            cognito=cognito,
            docker_provisioner=docker_provisioner,
            auto_drain=auto_drain,
            demo_mode=demo_mode
        )


# Global config instance
_config: Optional[ServingConfig] = None


def get_config() -> ServingConfig:
    """Get the global configuration instance.
    
    Returns:
        ServingConfig instance
    """
    global _config
    
    if _config is None:
        _config = ServingConfig.from_env()
    
    return _config


def reload_config() -> ServingConfig:
    """Reload configuration from environment.
    
    Returns:
        New ServingConfig instance
    """
    global _config
    _config = ServingConfig.from_env()
    return _config
