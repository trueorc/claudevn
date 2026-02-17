"""Unit tests for marketplace config.py."""

import pytest
from unittest.mock import patch
import uuid


class TestConfigInit:
    """Tests for Config initialization."""

    def test_config_default_values(self):
        """Config should have sensible defaults when no env vars set."""
        with patch.dict('os.environ', {}, clear=True):
            # Reset the global _config
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.host == '0.0.0.0'
            assert cfg.port == 8003
            assert cfg.skills_path == './skills'
            assert cfg.log_level == 'INFO'
            assert cfg.cors_origins == '*'
            assert cfg.api_version == 'v1'
            assert cfg.api_key is None
            assert cfg.require_auth is True
            assert cfg.serving_url is None
            assert cfg.register_on_startup is True
            assert cfg.heartbeat_interval == 60
            assert cfg.marketplace_name == 'ClaudeVN Marketplace'
            assert cfg.marketplace_id.startswith('marketplace-')
            assert cfg.agent_cache_max_size == 10000
            assert cfg.agent_cache_ttl == 86400
            assert cfg.git_repos_path == '/var/lib/claudevn/marketplace/repos'
            assert cfg.git_worktree_path == '/tmp/marketplace-worktree'
            assert cfg.git_enabled is True
            assert cfg.redis_host == 'localhost'
            assert cfg.redis_port == 6379
            assert cfg.redis_db == 0
            assert cfg.redis_key_prefix == 'claudevn:'

    def test_config_reads_environment_variables(self):
        """Config should read values from environment variables."""
        env_vars = {
            'MARKETPLACE_HOST': '127.0.0.1',
            'MARKETPLACE_PORT': '9000',
            'SKILLS_PATH': '/custom/skills',
            'LOG_LEVEL': 'debug',  # Test case insensitivity
            'CORS_ORIGINS': 'http://localhost:3000,http://localhost:8080',
            'API_VERSION': 'v2',
            'MARKETPLACE_API_KEY': 'secret-key-123',
            'MARKETPLACE_REQUIRE_AUTH': 'true',
            'SERVING_URL': 'http://serving:8002',
            'REGISTER_ON_STARTUP': 'false',
            'HEARTBEAT_INTERVAL': '120',
            'MARKETPLACE_NAME': 'Custom Marketplace',
            'MARKETPLACE_ID': 'custom-id-123',
            'AGENT_CACHE_MAX_SIZE': '5000',
            'AGENT_CACHE_TTL': '3600',
            'GIT_REPOS_PATH': '/custom/repos',
            'GIT_WORKTREE_PATH': '/custom/worktree',
            'GIT_STORAGE_ENABLED': 'false',
            'REDIS_HOST': 'redis-server',
            'REDIS_PORT': '6380',
            'REDIS_DB': '1',
            'REDIS_KEY_PREFIX': 'custom:',
        }

        with patch.dict('os.environ', env_vars, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.host == '127.0.0.1'
            assert cfg.port == 9000
            assert cfg.skills_path == '/custom/skills'
            assert cfg.log_level == 'DEBUG'  # Should be uppercased
            assert cfg.cors_origins == 'http://localhost:3000,http://localhost:8080'
            assert cfg.api_version == 'v2'
            assert cfg.api_key == 'secret-key-123'
            assert cfg.require_auth is True
            assert cfg.serving_url == 'http://serving:8002'
            assert cfg.register_on_startup is False
            assert cfg.heartbeat_interval == 120
            assert cfg.marketplace_name == 'Custom Marketplace'
            assert cfg.marketplace_id == 'custom-id-123'
            assert cfg.agent_cache_max_size == 5000
            assert cfg.agent_cache_ttl == 3600
            assert cfg.git_repos_path == '/custom/repos'
            assert cfg.git_worktree_path == '/custom/worktree'
            assert cfg.git_enabled is False
            assert cfg.redis_host == 'redis-server'
            assert cfg.redis_port == 6380
            assert cfg.redis_db == 1
            assert cfg.redis_key_prefix == 'custom:'

    def test_marketplace_id_generates_uuid_when_not_set(self):
        """marketplace_id should generate a UUID-based ID when not provided."""
        with patch.dict('os.environ', {}, clear=True):
            import config
            config._config = None

            cfg1 = config.Config()
            config._config = None
            cfg2 = config.Config()

            # Both should start with prefix
            assert cfg1.marketplace_id.startswith('marketplace-')
            assert cfg2.marketplace_id.startswith('marketplace-')
            # But should have different UUIDs
            assert cfg1.marketplace_id != cfg2.marketplace_id
            # Should be 8 hex chars after prefix
            assert len(cfg1.marketplace_id.split('-')[1]) == 8


class TestCorsOriginsList:
    """Tests for cors_origins_list property."""

    def test_cors_origins_list_returns_wildcard(self):
        """cors_origins_list should return ['*'] when cors_origins is '*'."""
        with patch.dict('os.environ', {'CORS_ORIGINS': '*'}, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.cors_origins_list == ["*"]

    def test_cors_origins_list_parses_comma_separated(self):
        """cors_origins_list should split on commas and strip whitespace."""
        with patch.dict('os.environ', {'CORS_ORIGINS': 'http://localhost:3000, http://localhost:8080 , http://example.com'}, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.cors_origins_list == [
                'http://localhost:3000',
                'http://localhost:8080',
                'http://example.com'
            ]

    def test_cors_origins_list_handles_single_origin(self):
        """cors_origins_list should handle a single origin."""
        with patch.dict('os.environ', {'CORS_ORIGINS': 'http://localhost:3000'}, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.cors_origins_list == ['http://localhost:3000']


class TestGetConfig:
    """Tests for get_config singleton function."""

    def test_get_config_returns_singleton(self):
        """get_config should return the same instance on repeated calls."""
        with patch.dict('os.environ', {}, clear=True):
            import config
            config._config = None

            cfg1 = config.get_config()
            cfg2 = config.get_config()

            assert cfg1 is cfg2

    def test_get_config_creates_instance_if_none(self):
        """get_config should create a new Config if _config is None."""
        with patch.dict('os.environ', {}, clear=True):
            import config
            config._config = None

            cfg = config.get_config()

            assert cfg is not None
            assert isinstance(cfg, config.Config)


class TestLoadApiKeys:
    """Tests for _load_api_keys method."""

    def test_load_all_api_keys(self):
        """All three named API keys should be loaded when set."""
        env_vars = {
            'SERVING_API_KEY': 'serving-key-abc',
            'ADMIN_API_KEY': 'admin-key-def',
            'MARKETPLACE_API_KEY': 'marketplace-key-ghi',
        }
        with patch.dict('os.environ', env_vars, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.api_keys == {
                'serving': 'serving-key-abc',
                'admin': 'admin-key-def',
                'default': 'marketplace-key-ghi',
            }

    def test_load_partial_api_keys(self):
        """Only keys that are set should be included in api_keys dict."""
        env_vars = {
            'SERVING_API_KEY': 'serving-key-only',
        }
        with patch.dict('os.environ', env_vars, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.api_keys == {'serving': 'serving-key-only'}
            assert 'admin' not in cfg.api_keys
            assert 'default' not in cfg.api_keys

    def test_load_no_api_keys_returns_empty_dict(self):
        """No keys configured should return an empty dict."""
        with patch.dict('os.environ', {}, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.api_keys == {}

    def test_load_two_of_three_api_keys(self):
        """Two out of three keys set should load only those two."""
        env_vars = {
            'ADMIN_API_KEY': 'admin-key-xyz',
            'MARKETPLACE_API_KEY': 'default-key-xyz',
        }
        with patch.dict('os.environ', env_vars, clear=True):
            import config
            config._config = None

            cfg = config.Config()

            assert cfg.api_keys == {
                'admin': 'admin-key-xyz',
                'default': 'default-key-xyz',
            }
            assert 'serving' not in cfg.api_keys


class TestRequireAuthParsing:
    """Tests for require_auth boolean parsing."""

    def test_require_auth_true_by_default(self):
        """require_auth should be True when not set (secure by default)."""
        with patch.dict('os.environ', {}, clear=True):
            import config
            config._config = None

            cfg = config.Config()
            assert cfg.require_auth is True

    def test_require_auth_true_when_set(self):
        """require_auth should be True when set to 'true'."""
        with patch.dict('os.environ', {'MARKETPLACE_REQUIRE_AUTH': 'true'}, clear=True):
            import config
            config._config = None

            cfg = config.Config()
            assert cfg.require_auth is True

    def test_require_auth_false_when_set_to_false(self):
        """require_auth should be False when explicitly set to 'false'."""
        with patch.dict('os.environ', {'MARKETPLACE_REQUIRE_AUTH': 'false'}, clear=True):
            import config
            config._config = None

            cfg = config.Config()
            assert cfg.require_auth is False

    def test_require_auth_case_insensitive(self):
        """require_auth should handle case insensitivity."""
        with patch.dict('os.environ', {'MARKETPLACE_REQUIRE_AUTH': 'TRUE'}, clear=True):
            import config
            config._config = None

            cfg = config.Config()
            assert cfg.require_auth is True

        with patch.dict('os.environ', {'MARKETPLACE_REQUIRE_AUTH': 'True'}, clear=True):
            config._config = None

            cfg = config.Config()
            assert cfg.require_auth is True
