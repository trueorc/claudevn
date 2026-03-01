"""Unit tests for compute SSE registration authentication (#80).

Tests the _verify_registration_token function that guards the /connect endpoint.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.compute import _verify_registration_token


class TestVerifyRegistrationToken:
    """Tests for _verify_registration_token."""

    def test_no_token_configured_allows_any(self):
        """When COMPUTE_REGISTRATION_TOKEN is not set, any request passes."""
        with patch.dict(os.environ, {}, clear=True):
            # No Authorization header — should pass
            _verify_registration_token(None)
            # With Authorization — should also pass
            _verify_registration_token("Bearer some-token")

    def test_valid_token_passes(self):
        """Correct Bearer token passes validation."""
        with patch.dict(os.environ, {"COMPUTE_REGISTRATION_TOKEN": "troc_test123"}):
            _verify_registration_token("Bearer troc_test123")

    def test_missing_auth_header_rejected(self):
        """Missing Authorization header is rejected when token is configured."""
        with patch.dict(os.environ, {"COMPUTE_REGISTRATION_TOKEN": "troc_test123"}):
            with pytest.raises(HTTPException) as exc_info:
                _verify_registration_token(None)
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["code"] == "MISSING_AUTH"

    def test_non_bearer_auth_rejected(self):
        """Non-Bearer Authorization is rejected."""
        with patch.dict(os.environ, {"COMPUTE_REGISTRATION_TOKEN": "troc_test123"}):
            with pytest.raises(HTTPException) as exc_info:
                _verify_registration_token("Basic dXNlcjpwYXNz")
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["code"] == "INVALID_AUTH"

    def test_wrong_token_rejected(self):
        """Wrong Bearer token is rejected."""
        with patch.dict(os.environ, {"COMPUTE_REGISTRATION_TOKEN": "troc_test123"}):
            with pytest.raises(HTTPException) as exc_info:
                _verify_registration_token("Bearer troc_wrong")
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["code"] == "INVALID_TOKEN"

    def test_auth_bypass_skips_validation(self):
        """MCP_AUTH_BYPASS=true skips token validation."""
        with patch.dict(os.environ, {
            "COMPUTE_REGISTRATION_TOKEN": "troc_test123",
            "MCP_AUTH_BYPASS": "true",
        }):
            # No auth at all — should pass due to bypass
            _verify_registration_token(None)

    def test_empty_token_env_treated_as_unset(self):
        """Empty COMPUTE_REGISTRATION_TOKEN is treated as not configured."""
        with patch.dict(os.environ, {"COMPUTE_REGISTRATION_TOKEN": ""}):
            _verify_registration_token(None)
