"""Configuration management for Marketplace service."""

import os
import uuid
from typing import Optional


class Config:
    """Configuration settings for the Marketplace service."""

    def __init__(self):
        self.host = os.getenv('MARKETPLACE_HOST', '0.0.0.0')
        self.port = int(os.getenv('MARKETPLACE_PORT', 8003))
        self.skills_path = os.getenv('SKILLS_PATH', './skills')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.cors_origins = os.getenv('CORS_ORIGINS', '*')
        self.api_version = os.getenv('API_VERSION', 'v1')
        # Authentication settings (enabled by default for production safety)
        self.require_auth = os.getenv('MARKETPLACE_REQUIRE_AUTH', 'true').lower() == 'true'
        self.api_key = os.getenv('MARKETPLACE_API_KEY')
        self.api_keys = self._load_api_keys()

        # Registration with Serving
        self.serving_url = os.getenv('SERVING_URL')  # e.g., "http://serving:8002"
        self.register_on_startup = os.getenv('REGISTER_ON_STARTUP', 'true').lower() == 'true'
        self.heartbeat_interval = int(os.getenv('HEARTBEAT_INTERVAL', '60'))
        self.marketplace_name = os.getenv('MARKETPLACE_NAME', 'ClaudeVN Marketplace')
        self.marketplace_id = os.getenv('MARKETPLACE_ID', f"marketplace-{uuid.uuid4().hex[:8]}")

        # Agent cache settings
        self.agent_cache_max_size = int(os.getenv('AGENT_CACHE_MAX_SIZE', '10000'))
        self.agent_cache_ttl = int(os.getenv('AGENT_CACHE_TTL', '86400'))  # 24 hours default

        # Git-backed storage settings
        self.git_repos_path = os.getenv('GIT_REPOS_PATH', '/var/lib/claudevn/marketplace/repos')
        self.git_worktree_path = os.getenv('GIT_WORKTREE_PATH', '/tmp/marketplace-worktree')
        self.git_enabled = os.getenv('GIT_STORAGE_ENABLED', 'true').lower() == 'true'

        # Redis settings (for optional indexing)
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_db = int(os.getenv('REDIS_DB', '0'))
        self.redis_key_prefix = os.getenv('REDIS_KEY_PREFIX', 'claudevn:')

    def _load_api_keys(self) -> dict:
        """Load named API keys from environment variables.

        Supports multiple keys for different clients:
          SERVING_API_KEY, ADMIN_API_KEY, MARKETPLACE_API_KEY
        """
        keys = {}
        key_mappings = {
            'serving': 'SERVING_API_KEY',
            'admin': 'ADMIN_API_KEY',
            'default': 'MARKETPLACE_API_KEY',
        }
        for name, env_var in key_mappings.items():
            value = os.getenv(env_var)
            if value:
                keys[name] = value
        return keys

    @property
    def cors_origins_list(self):
        """Parse CORS origins into a list."""
        if self.cors_origins == '*':
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(',')]


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
