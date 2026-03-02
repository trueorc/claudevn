"""Tests for Cognito configuration."""

import os
import pytest
from unittest.mock import patch
from config import ServingConfig, CognitoConfig


class TestCognitoConfigDefaults:
    """Test CognitoConfig default values."""

    def test_default_auth_mode(self):
        config = CognitoConfig()
        assert config.auth_mode == "bypass"

    def test_default_user_pool_id(self):
        config = CognitoConfig()
        assert config.user_pool_id == ""

    def test_default_app_client_id(self):
        config = CognitoConfig()
        assert config.app_client_id == ""

    def test_default_region(self):
        config = CognitoConfig()
        assert config.region == "us-east-1"

    def test_default_admin_enabled(self):
        config = CognitoConfig()
        assert config.admin_enabled is False


class TestCognitoConfigFromEnv:
    """Test CognitoConfig loading from environment variables."""

    @patch.dict(os.environ, {
        "AUTH_MODE": "cognito",
        "COGNITO_USER_POOL_ID": "us-east-1_TestPool",
        "COGNITO_APP_CLIENT_ID": "test-client-id-123",
        "COGNITO_REGION": "us-west-2",
        "COGNITO_ADMIN_ENABLED": "true",
    }, clear=False)
    def test_loads_all_cognito_env_vars(self):
        config = ServingConfig.from_env()
        assert config.cognito.auth_mode == "cognito"
        assert config.cognito.user_pool_id == "us-east-1_TestPool"
        assert config.cognito.app_client_id == "test-client-id-123"
        assert config.cognito.region == "us-west-2"
        assert config.cognito.admin_enabled is True

    @patch.dict(os.environ, {}, clear=False)
    def test_defaults_to_bypass_mode(self):
        # Remove cognito vars if they exist
        env_copy = os.environ.copy()
        for key in ["AUTH_MODE", "COGNITO_USER_POOL_ID", "COGNITO_APP_CLIENT_ID",
                     "COGNITO_REGION", "COGNITO_ADMIN_ENABLED"]:
            env_copy.pop(key, None)

        with patch.dict(os.environ, env_copy, clear=True):
            config = ServingConfig.from_env()
            assert config.cognito.auth_mode == "bypass"
            assert config.cognito.user_pool_id == ""
            assert config.cognito.app_client_id == ""

    @patch.dict(os.environ, {
        "AUTH_MODE": "cognito",
        "COGNITO_USER_POOL_ID": "us-east-1_Pool123",
        "COGNITO_APP_CLIENT_ID": "client456",
    }, clear=False)
    def test_partial_cognito_config(self):
        config = ServingConfig.from_env()
        assert config.cognito.auth_mode == "cognito"
        assert config.cognito.user_pool_id == "us-east-1_Pool123"
        assert config.cognito.app_client_id == "client456"
        assert config.cognito.region == "us-east-1"  # default
        assert config.cognito.admin_enabled is False  # default


class TestServingConfigIncludesCognito:
    """Test that ServingConfig properly includes CognitoConfig."""

    def test_serving_config_has_cognito_field(self):
        config = ServingConfig()
        assert hasattr(config, 'cognito')
        assert isinstance(config.cognito, CognitoConfig)

    def test_cognito_config_serialization(self):
        config = CognitoConfig(
            auth_mode="cognito",
            user_pool_id="us-east-1_Test",
            app_client_id="test-client",
            region="eu-west-1",
            admin_enabled=True,
        )
        data = config.model_dump()
        assert data["auth_mode"] == "cognito"
        assert data["user_pool_id"] == "us-east-1_Test"
        assert data["app_client_id"] == "test-client"
        assert data["region"] == "eu-west-1"
        assert data["admin_enabled"] is True
