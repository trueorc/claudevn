"""Rate limiting middleware for FastAPI.

Implements a sliding window rate limiter using Redis for distributed state.
Falls back to in-memory rate limiting if Redis is unavailable.
"""

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import RateLimitConfig


logger = logging.getLogger(__name__)


@dataclass
class RateLimitMetrics:
    """Metrics for rate limiting."""
    total_requests: int = 0
    rate_limited_requests: int = 0
    requests_by_endpoint: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    rate_limits_by_endpoint: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RateLimitState:
    """State for a single rate limit bucket."""
    request_count: int = 0
    window_start: float = 0.0


class RateLimiter:
    """Rate limiter with Redis backend and in-memory fallback.

    Uses a sliding window algorithm for fair rate limiting.
    Supports different rate limits for different endpoint prefixes.
    """

    def __init__(
        self,
        config: RateLimitConfig,
        redis_client: Optional[object] = None,
    ):
        """Initialize rate limiter.

        Args:
            config: Rate limit configuration.
            redis_client: Optional Redis client for distributed rate limiting.
        """
        self.config = config
        self.redis_client = redis_client
        self._memory_state: Dict[str, RateLimitState] = {}
        self._metrics = RateLimitMetrics()
        self._window_size = 60  # 1 minute window

        # Build endpoint prefix -> rate limit mapping
        self._rate_limits: Dict[str, int] = {
            "/compute": config.compute_requests_per_minute,
            "/work": config.work_requests_per_minute,
            "/pr": config.pr_requests_per_minute,
            "/git": config.pr_requests_per_minute,  # Git ops same as PR
        }

        logger.info(
            f"Rate limiter initialized (enabled={config.enabled}, "
            f"default_rpm={config.default_requests_per_minute})"
        )

    def _get_rate_limit_for_path(self, path: str) -> int:
        """Get the rate limit for a given path.

        Args:
            path: The request path.

        Returns:
            Requests per minute limit for this path.
        """
        # Remove /api/v1 prefix if present
        if path.startswith("/api/"):
            parts = path.split("/", 3)
            if len(parts) >= 4:
                path = "/" + parts[3]

        # Check for matching prefix
        for prefix, limit in self._rate_limits.items():
            if path.startswith(prefix):
                return limit

        return self.config.default_requests_per_minute

    def _get_client_identifier(self, request: Request) -> str:
        """Extract client identifier from request.

        Uses X-Forwarded-For if behind proxy, otherwise client host.
        Also considers X-Compute-ID header for compute instances.

        Args:
            request: The incoming request.

        Returns:
            Client identifier string.
        """
        # Check for compute instance identifier
        compute_id = request.headers.get("X-Compute-ID")
        if compute_id:
            return f"compute:{compute_id}"

        # Check for forwarded IP (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain
            return f"ip:{forwarded.split(',')[0].strip()}"

        # Fall back to direct client
        if request.client:
            return f"ip:{request.client.host}"

        return "unknown"

    async def _check_redis(
        self,
        key: str,
        rate_limit: int,
        now: float,
    ) -> Tuple[bool, int, int]:
        """Check rate limit using Redis sliding window.

        Args:
            key: Rate limit key.
            rate_limit: Maximum requests per window.
            now: Current timestamp.

        Returns:
            Tuple of (is_allowed, remaining, retry_after).
        """
        window_start = now - self._window_size
        redis_key = f"claudevn:ratelimit:{key}"

        try:
            # Get the underlying Redis connection
            redis = self.redis_client._redis if hasattr(self.redis_client, '_redis') else self.redis_client

            # Remove old entries and count current window
            await redis.zremrangebyscore(redis_key, 0, window_start)
            current_count = await redis.zcard(redis_key)

            burst_limit = int(rate_limit * self.config.burst_multiplier)

            if current_count >= burst_limit:
                # Rate limited - calculate retry after
                oldest = await redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(self._window_size - (now - oldest[0][1])) + 1
                else:
                    retry_after = self._window_size
                return False, 0, retry_after

            # Add current request
            await redis.zadd(redis_key, {str(now): now})
            await redis.expire(redis_key, self._window_size + 10)

            remaining = burst_limit - current_count - 1
            return True, max(0, remaining), 0

        except Exception as e:
            logger.warning(f"Redis rate limit check failed: {e}, falling back to memory")
            return await self._check_memory(key, rate_limit, now)

    async def _check_memory(
        self,
        key: str,
        rate_limit: int,
        now: float,
    ) -> Tuple[bool, int, int]:
        """Check rate limit using in-memory state.

        Args:
            key: Rate limit key.
            rate_limit: Maximum requests per window.
            now: Current timestamp.

        Returns:
            Tuple of (is_allowed, remaining, retry_after).
        """
        state = self._memory_state.get(key)

        if state is None:
            state = RateLimitState(request_count=0, window_start=now)
            self._memory_state[key] = state

        # Reset window if expired
        if now - state.window_start >= self._window_size:
            state.request_count = 0
            state.window_start = now

        burst_limit = int(rate_limit * self.config.burst_multiplier)

        if state.request_count >= burst_limit:
            retry_after = int(self._window_size - (now - state.window_start)) + 1
            return False, 0, retry_after

        state.request_count += 1
        remaining = burst_limit - state.request_count
        return True, max(0, remaining), 0

    async def is_allowed(self, request: Request) -> Tuple[bool, int, int]:
        """Check if request is allowed under rate limit.

        Args:
            request: The incoming request.

        Returns:
            Tuple of (is_allowed, remaining, retry_after).
        """
        if not self.config.enabled:
            return True, -1, 0

        client_id = self._get_client_identifier(request)
        path = request.url.path
        rate_limit = self._get_rate_limit_for_path(path)

        # Create rate limit key combining client and endpoint prefix
        endpoint_prefix = path.split("/")[3] if path.count("/") >= 3 else "default"
        key = f"{client_id}:{endpoint_prefix}"

        now = time.time()

        # Update metrics
        self._metrics.total_requests += 1
        self._metrics.requests_by_endpoint[endpoint_prefix] += 1

        # Check rate limit
        if self.redis_client:
            is_allowed, remaining, retry_after = await self._check_redis(key, rate_limit, now)
        else:
            is_allowed, remaining, retry_after = await self._check_memory(key, rate_limit, now)

        if not is_allowed:
            self._metrics.rate_limited_requests += 1
            self._metrics.rate_limits_by_endpoint[endpoint_prefix] += 1

        return is_allowed, remaining, retry_after

    def get_metrics(self) -> Dict:
        """Get rate limiting metrics.

        Returns:
            Dictionary of rate limiting metrics.
        """
        return {
            "total_requests": self._metrics.total_requests,
            "rate_limited_requests": self._metrics.rate_limited_requests,
            "rate_limit_percentage": (
                round(self._metrics.rate_limited_requests / self._metrics.total_requests * 100, 2)
                if self._metrics.total_requests > 0 else 0
            ),
            "requests_by_endpoint": dict(self._metrics.requests_by_endpoint),
            "rate_limits_by_endpoint": dict(self._metrics.rate_limits_by_endpoint),
            "last_reset": self._metrics.last_reset.isoformat(),
        }

    def reset_metrics(self) -> None:
        """Reset rate limiting metrics."""
        self._metrics = RateLimitMetrics()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    async def dispatch(self, request: Request, call_next):
        """Process request through rate limiter.

        Args:
            request: The incoming request.
            call_next: Next middleware/handler in chain.

        Returns:
            Response from next handler or 429 if rate limited.
        """
        rate_limiter = get_rate_limiter()

        if rate_limiter is None:
            # Rate limiter not initialized, pass through
            return await call_next(request)

        # Skip rate limiting for health checks and docs
        path = request.url.path
        if path.endswith("/health") or path in ("/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        is_allowed, remaining, retry_after = await rate_limiter.is_allowed(request)

        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded for {request.client.host if request.client else 'unknown'} "
                f"on {path}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        if remaining >= 0:
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the global rate limiter instance.

    Returns:
        RateLimiter instance or None if not initialized.
    """
    return _rate_limiter


def set_rate_limiter(rate_limiter: RateLimiter) -> None:
    """Set the global rate limiter instance.

    Args:
        rate_limiter: RateLimiter instance to set.
    """
    global _rate_limiter
    _rate_limiter = rate_limiter
