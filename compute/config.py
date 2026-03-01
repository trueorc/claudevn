"""Configuration management for ClaudeVN Compute Infrastructure (v1.0).

This is the v1.0 architecture where compute is lightweight infrastructure
that spawns Claude Code CLI instances for work execution.
"""

import logging
import os
import socket
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ComputeConfig(BaseModel):
    """Configuration for compute infrastructure (v1.0)."""

    # Server settings
    host: str = Field(default="0.0.0.0", description="Bind host")
    port: int = Field(default=8003, description="Bind port")

    # Instance identity
    instance_id: Optional[str] = Field(default=None, description="Unique compute infrastructure ID")
    instance_name: Optional[str] = Field(default=None, description="Human-readable instance name")

    # Serving component connection
    serving_url: str = Field(default="http://localhost:8002", description="Serving component URL")
    api_key: str = Field(default="", description="API key for authentication with Serving")

    # Capabilities (advertised to Serving)
    capabilities: str = Field(default="coding,testing,documentation", description="Comma-separated capabilities")

    # Resources (advertised to Serving)
    resources_cpu: int = Field(default=4, description="CPU cores available")
    resources_memory: str = Field(default="16gb", description="Memory available")

    # Workspace and Claude CLI
    workspace_path: str = Field(default="./data/workspace", description="Workspace directory for Claude Code instances")
    claude_cli_path: Optional[str] = Field(default=None, description="Path to claude CLI (auto-detected if not set)")

    # Serving repository (for AI inspection during decomposition/characterization)
    serving_repo_url: Optional[str] = Field(
        default=None,
        description="Git URL of the serving repo — cloned once to ~/.claudevn/repos/serving/ and pulled on every task start so compute workers can inspect serving code"
    )

    # Credential monitoring
    credentials_path: str = Field(
        default="~/.claude/.credentials.json",
        description="Path to Claude OAuth credentials file"
    )
    credential_check_interval: int = Field(
        default=3600, description="Seconds between credential health checks"
    )
    credential_expiry_warning_days: int = Field(
        default=7, description="Days before expiry to emit warning"
    )

    # Authentication
    auth_mode: str = Field(
        default="serving",
        description="Auth mode: serving (fetch from serving), local (mount), or external (own)"
    )
    serving_auth_url: str = Field(
        default="",
        description="URL of Serving's auth API for credential fetching (derived from serving_url if not set)"
    )

    # SSE client settings
    sse_reconnect_delay: int = Field(default=5, description="SSE initial reconnect delay in seconds")
    sse_max_reconnect_delay: int = Field(default=60, description="SSE maximum reconnect delay in seconds")

    # TLS verification (set to false for self-signed certs in local testing)
    tls_verify: bool = Field(default=True, description="Verify TLS certificates for HTTPS connections")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_file: Optional[str] = Field(default="./logs/compute.log", description="Log file path")

    model_config = ConfigDict(
        env_prefix="CLAUDEVN_",
        case_sensitive=False,
    )


def load_config() -> ComputeConfig:
    """Load configuration from environment variables.

    Uses CLAUDEVN_* prefix for environment variables (v1.0 architecture).

    Returns:
        ComputeConfig instance
    """
    # Load from environment
    config = ComputeConfig(
        host=os.getenv("CLAUDEVN_HOST", os.getenv("COMPUTE_HOST", "0.0.0.0")),
        port=int(os.getenv("CLAUDEVN_PORT", os.getenv("COMPUTE_PORT", "8003"))),
        instance_id=os.getenv("CLAUDEVN_COMPUTE_ID", os.getenv("COMPUTE_INSTANCE_ID")),
        instance_name=os.getenv("CLAUDEVN_COMPUTE_NAME", os.getenv("COMPUTE_INSTANCE_NAME")),
        serving_url=os.getenv("CLAUDEVN_SERVING_URL", os.getenv("SERVING_URL", "http://localhost:8002")),
        api_key=os.getenv("CLAUDEVN_API_KEY", ""),
        capabilities=os.getenv("CLAUDEVN_CAPABILITIES", "coding,testing,documentation"),
        resources_cpu=int(os.getenv("CLAUDEVN_RESOURCES_CPU", "4")),
        resources_memory=os.getenv("CLAUDEVN_RESOURCES_MEMORY", "16gb"),
        workspace_path=os.getenv("CLAUDEVN_WORKSPACE_PATH", os.getenv("WORKSPACE_PATH", "./data/workspace")),
        claude_cli_path=os.getenv("CLAUDEVN_CLAUDE_CLI_PATH"),
        serving_repo_url=os.getenv("CLAUDEVN_SERVING_REPO_URL"),
        credentials_path=os.getenv("CLAUDEVN_CREDENTIALS_PATH", "~/.claude/.credentials.json"),
        credential_check_interval=int(os.getenv("CLAUDEVN_CREDENTIAL_CHECK_INTERVAL", "3600")),
        credential_expiry_warning_days=int(os.getenv("CLAUDEVN_CREDENTIAL_EXPIRY_WARNING_DAYS", "7")),
        auth_mode=os.getenv("COMPUTE_AUTH_MODE", "serving"),
        # Derive auth URL from serving_url when not explicitly set
        serving_auth_url=os.getenv(
            "CLAUDEVN_SERVING_AUTH_URL",
            f"{os.getenv('CLAUDEVN_SERVING_URL', os.getenv('SERVING_URL', 'http://localhost:8002')).rstrip('/')}/api/v1/auth",
        ),
        tls_verify=os.getenv("TLS_VERIFY", "true").lower() in ("true", "1", "yes"),
        sse_reconnect_delay=int(os.getenv("CLAUDEVN_SSE_RECONNECT_DELAY", "5")),
        sse_max_reconnect_delay=int(os.getenv("CLAUDEVN_SSE_MAX_RECONNECT_DELAY", "60")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("COMPUTE_LOG_FILE", "./logs/compute.log"),
    )

    # Generate instance ID if not provided
    if not config.instance_id:
        hostname = socket.gethostname()
        config.instance_id = f"compute-{hostname}-{config.port}"

    # Generate instance name if not provided
    if not config.instance_name:
        hostname = socket.gethostname()
        config.instance_name = f"Compute on {hostname}"

    # Warn if serving_url uses plain HTTP on a non-local address
    _warn_insecure_url(config.serving_url, "CLAUDEVN_SERVING_URL")
    _warn_insecure_url(config.serving_auth_url, "CLAUDEVN_SERVING_AUTH_URL")

    # Validate hostname consistency between serving_url and serving_auth_url
    _validate_auth_url_consistency(config.serving_url, config.serving_auth_url)

    return config


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "serving"}


def _warn_insecure_url(url: str, var_name: str) -> None:
    """Emit a warning if the URL uses plain HTTP to a non-local host."""
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.hostname not in _LOCAL_HOSTS:
        logger.warning(
            "SECURITY: %s uses plain HTTP (%s). "
            "API keys and credentials will be sent in cleartext. "
            "Use HTTPS for internet-facing deployments — see deploy/cloud/ for Caddy TLS setup.",
            var_name,
            url,
        )


def _validate_auth_url_consistency(serving_url: str, auth_url: str) -> None:
    """Warn if serving_auth_url points to a different host than serving_url.

    This catches misconfigurations where serving_url is overridden for remote
    access but serving_auth_url still points to a Docker-internal hostname.
    """
    serving_host = urlparse(serving_url).hostname
    auth_host = urlparse(auth_url).hostname

    if serving_host and auth_host and serving_host != auth_host:
        logger.error(
            "CLAUDEVN_SERVING_AUTH_URL host (%s) differs from CLAUDEVN_SERVING_URL host (%s). "
            "Auth URL should usually be derived from SERVING_URL. "
            "Credential fetching will likely fail for remote compute nodes. "
            "Either set CLAUDEVN_SERVING_AUTH_URL explicitly or leave it unset to auto-derive.",
            auth_host,
            serving_host,
        )


def get_version() -> str:
    """Get version from VERSION file.
    
    Returns:
        Version string
    """
    try:
        version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
        with open(version_file, "r") as f:
            return f.read().strip()
    except Exception:
        return "0.1.5"

