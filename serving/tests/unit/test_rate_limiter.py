"""Unit tests for rate limiting middleware."""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from config import RateLimitConfig
from middleware.rate_limiter import (
    RateLimiter,
    RateLimitMiddleware,
    RateLimitMetrics,
    RateLimitState,
    get_rate_limiter,
    set_rate_limiter,
)


@pytest.fixture
def rate_limit_config():
    """Create a test rate limit configuration."""
    return RateLimitConfig(
        enabled=True,
        default_requests_per_minute=10,
        compute_requests_per_minute=20,
        work_requests_per_minute=15,
        pr_requests_per_minute=5,
        burst_multiplier=1.5,
    )


@pytest.fixture
def rate_limit_config_disabled():
    """Create a disabled rate limit configuration."""
    return RateLimitConfig(enabled=False)


@pytest.fixture
def rate_limiter(rate_limit_config):
    """Create a rate limiter without Redis (memory-only)."""
    return RateLimiter(config=rate_limit_config, redis_client=None)


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = MagicMock(spec=Request)
    request.url.path = "/api/v1/compute/register"
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


@pytest.fixture
def app_with_rate_limiting(rate_limiter):
    """Create a FastAPI app with rate limiting middleware."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    set_rate_limiter(rate_limiter)

    @app.get("/api/v1/compute/status")
    async def compute_status():
        return {"status": "ok"}

    @app.get("/api/v1/work/list")
    async def work_list():
        return {"items": []}

    @app.get("/api/v1/pr/queue")
    async def pr_queue():
        return {"queue": []}

    @app.get("/api/v1/health")
    async def health():
        return {"healthy": True}

    return app


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RateLimitConfig()
        assert config.enabled is True
        assert config.default_requests_per_minute == 60
        assert config.compute_requests_per_minute == 120
        assert config.work_requests_per_minute == 60
        assert config.pr_requests_per_minute == 30
        assert config.burst_multiplier == 1.5

    def test_custom_values(self, rate_limit_config):
        """Test custom configuration values."""
        assert rate_limit_config.default_requests_per_minute == 10
        assert rate_limit_config.compute_requests_per_minute == 20


class TestRateLimiterInit:
    """Tests for RateLimiter initialization."""

    def test_init_without_redis(self, rate_limit_config):
        """Test initialization without Redis client."""
        limiter = RateLimiter(config=rate_limit_config, redis_client=None)
        assert limiter.config == rate_limit_config
        assert limiter.redis_client is None

    def test_init_with_redis(self, rate_limit_config):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        limiter = RateLimiter(config=rate_limit_config, redis_client=mock_redis)
        assert limiter.redis_client == mock_redis

    def test_rate_limits_mapping(self, rate_limiter):
        """Test that endpoint rate limits are mapped correctly."""
        assert rate_limiter._rate_limits["/compute"] == 20
        assert rate_limiter._rate_limits["/work"] == 15
        assert rate_limiter._rate_limits["/pr"] == 5
        assert rate_limiter._rate_limits["/git"] == 5  # Same as PR


class TestGetRateLimitForPath:
    """Tests for path-based rate limit resolution."""

    def test_compute_endpoint(self, rate_limiter):
        """Test rate limit for compute endpoints."""
        assert rate_limiter._get_rate_limit_for_path("/api/v1/compute/register") == 20

    def test_work_endpoint(self, rate_limiter):
        """Test rate limit for work endpoints."""
        assert rate_limiter._get_rate_limit_for_path("/api/v1/work/items") == 15

    def test_pr_endpoint(self, rate_limiter):
        """Test rate limit for PR endpoints."""
        assert rate_limiter._get_rate_limit_for_path("/api/v1/pr/queue") == 5

    def test_git_endpoint(self, rate_limiter):
        """Test rate limit for git endpoints."""
        assert rate_limiter._get_rate_limit_for_path("/api/v1/git/repos") == 5

    def test_unknown_endpoint(self, rate_limiter):
        """Test rate limit for unknown endpoints falls back to default."""
        assert rate_limiter._get_rate_limit_for_path("/api/v1/other/endpoint") == 10


class TestGetClientIdentifier:
    """Tests for client identification."""

    def test_compute_id_header(self, rate_limiter, mock_request):
        """Test identification by X-Compute-ID header."""
        mock_request.headers = {"X-Compute-ID": "compute-123"}
        identifier = rate_limiter._get_client_identifier(mock_request)
        assert identifier == "compute:compute-123"

    def test_forwarded_for_header(self, rate_limiter, mock_request):
        """Test identification by X-Forwarded-For header."""
        mock_request.headers = {"X-Forwarded-For": "192.168.1.100, 10.0.0.1"}
        identifier = rate_limiter._get_client_identifier(mock_request)
        assert identifier == "ip:192.168.1.100"

    def test_direct_client(self, rate_limiter, mock_request):
        """Test identification by direct client IP."""
        mock_request.headers = {}
        identifier = rate_limiter._get_client_identifier(mock_request)
        assert identifier == "ip:127.0.0.1"

    def test_no_client_info(self, rate_limiter, mock_request):
        """Test identification when no client info available."""
        mock_request.headers = {}
        mock_request.client = None
        identifier = rate_limiter._get_client_identifier(mock_request)
        assert identifier == "unknown"


class TestMemoryRateLimiting:
    """Tests for in-memory rate limiting."""

    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self, rate_limiter, mock_request):
        """Test that requests under the limit are allowed."""
        is_allowed, remaining, retry_after = await rate_limiter.is_allowed(mock_request)
        assert is_allowed is True
        assert remaining >= 0
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_blocks_request_over_limit(self, rate_limit_config):
        """Test that requests over the limit are blocked."""
        # Use very low limits for testing
        config = RateLimitConfig(
            enabled=True,
            default_requests_per_minute=2,
            compute_requests_per_minute=2,
            work_requests_per_minute=2,
            pr_requests_per_minute=2,
            burst_multiplier=1.0,  # No burst
        )
        limiter = RateLimiter(config=config, redis_client=None)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/compute/status"
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        # First two requests should be allowed
        is_allowed1, _, _ = await limiter.is_allowed(mock_request)
        is_allowed2, _, _ = await limiter.is_allowed(mock_request)
        assert is_allowed1 is True
        assert is_allowed2 is True

        # Third request should be blocked
        is_allowed3, remaining, retry_after = await limiter.is_allowed(mock_request)
        assert is_allowed3 is False
        assert remaining == 0
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_burst_capacity(self, rate_limit_config):
        """Test that burst capacity allows extra requests."""
        config = RateLimitConfig(
            enabled=True,
            default_requests_per_minute=2,
            compute_requests_per_minute=2,
            work_requests_per_minute=2,
            pr_requests_per_minute=2,
            burst_multiplier=2.0,  # 2x burst
        )
        limiter = RateLimiter(config=config, redis_client=None)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/compute/status"
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        # Should allow up to 4 requests (2 * 2.0 burst)
        allowed_count = 0
        for _ in range(5):
            is_allowed, _, _ = await limiter.is_allowed(mock_request)
            if is_allowed:
                allowed_count += 1

        assert allowed_count == 4  # 2 * 2.0 = 4 burst capacity

    @pytest.mark.asyncio
    async def test_disabled_rate_limiting(self, rate_limit_config_disabled):
        """Test that disabled rate limiting allows all requests."""
        limiter = RateLimiter(config=rate_limit_config_disabled, redis_client=None)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/compute/status"
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        # All requests should be allowed
        for _ in range(100):
            is_allowed, remaining, retry_after = await limiter.is_allowed(mock_request)
            assert is_allowed is True
            assert remaining == -1  # -1 indicates disabled
            assert retry_after == 0


class TestMetrics:
    """Tests for rate limiter metrics."""

    @pytest.mark.asyncio
    async def test_metrics_tracked(self, rate_limiter, mock_request):
        """Test that metrics are tracked correctly."""
        # Make some requests
        for _ in range(3):
            await rate_limiter.is_allowed(mock_request)

        metrics = rate_limiter.get_metrics()
        assert metrics["total_requests"] == 3
        assert "compute" in metrics["requests_by_endpoint"]

    @pytest.mark.asyncio
    async def test_rate_limited_requests_tracked(self):
        """Test that rate-limited requests are tracked."""
        config = RateLimitConfig(
            enabled=True,
            default_requests_per_minute=1,
            compute_requests_per_minute=1,
            work_requests_per_minute=1,
            pr_requests_per_minute=1,
            burst_multiplier=1.0,
        )
        limiter = RateLimiter(config=config, redis_client=None)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/compute/status"
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        # First allowed, second blocked
        await limiter.is_allowed(mock_request)
        await limiter.is_allowed(mock_request)

        metrics = limiter.get_metrics()
        assert metrics["rate_limited_requests"] == 1
        assert metrics["rate_limit_percentage"] == 50.0

    def test_reset_metrics(self, rate_limiter):
        """Test metrics reset."""
        rate_limiter._metrics.total_requests = 100
        rate_limiter.reset_metrics()
        metrics = rate_limiter.get_metrics()
        assert metrics["total_requests"] == 0


class TestRateLimitMiddleware:
    """Tests for the rate limiting middleware."""

    def test_health_endpoint_bypasses_rate_limit(self, app_with_rate_limiting):
        """Test that health endpoint bypasses rate limiting."""
        client = TestClient(app_with_rate_limiting)

        # Make many requests to health endpoint
        for _ in range(50):
            response = client.get("/api/v1/health")
            assert response.status_code == 200

    def test_rate_limit_headers_in_response(self, app_with_rate_limiting):
        """Test that rate limit headers are added to responses."""
        client = TestClient(app_with_rate_limiting)
        response = client.get("/api/v1/compute/status")

        assert response.status_code == 200
        assert "X-RateLimit-Remaining" in response.headers

    def test_429_response_on_rate_limit(self):
        """Test 429 response when rate limit exceeded."""
        config = RateLimitConfig(
            enabled=True,
            default_requests_per_minute=1,
            compute_requests_per_minute=1,
            work_requests_per_minute=1,
            pr_requests_per_minute=1,
            burst_multiplier=1.0,
        )
        limiter = RateLimiter(config=config, redis_client=None)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)
        set_rate_limiter(limiter)

        @app.get("/api/v1/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        # First request should succeed
        response1 = client.get("/api/v1/test")
        assert response1.status_code == 200

        # Second request should be rate limited
        response2 = client.get("/api/v1/test")
        assert response2.status_code == 429
        assert "Retry-After" in response2.headers
        assert response2.json()["detail"] == "Rate limit exceeded"

    def test_no_rate_limiter_passthrough(self):
        """Test that requests pass through when no rate limiter is set."""
        set_rate_limiter(None)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)

        @app.get("/api/v1/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        # All requests should succeed
        for _ in range(10):
            response = client.get("/api/v1/test")
            assert response.status_code == 200


class TestGlobalRateLimiter:
    """Tests for global rate limiter getter/setter."""

    def test_set_and_get_rate_limiter(self, rate_limiter):
        """Test setting and getting the global rate limiter."""
        set_rate_limiter(rate_limiter)
        assert get_rate_limiter() == rate_limiter

    def test_get_none_when_not_set(self):
        """Test that None is returned when rate limiter not set."""
        set_rate_limiter(None)
        assert get_rate_limiter() is None
