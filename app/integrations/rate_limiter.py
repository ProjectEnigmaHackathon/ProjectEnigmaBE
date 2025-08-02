"""
Rate Limiter

Implements rate limiting for API calls to prevent exceeding service limits.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .exceptions import (
    ConfluenceRateLimitError,
    GitHubRateLimitError,
    JiraRateLimitError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for a service."""

    requests_per_minute: int
    requests_per_hour: int
    burst_allowance: int = 5  # Allow burst requests
    backoff_factor: float = 2.0  # Exponential backoff multiplier
    max_retries: int = 3


@dataclass
class RateLimitState:
    """Current rate limit state for a service."""

    requests_this_minute: deque = field(default_factory=deque)
    requests_this_hour: deque = field(default_factory=deque)
    last_request_time: float = 0
    retry_count: int = 0
    next_allowed_time: float = 0


class RateLimiter:
    """Rate limiter for API requests with exponential backoff."""

    # Default rate limits for each service
    DEFAULT_CONFIGS = {
        "jira": RateLimitConfig(
            requests_per_minute=60, requests_per_hour=1000, burst_allowance=10
        ),
        "github": RateLimitConfig(
            requests_per_minute=60, requests_per_hour=5000, burst_allowance=10
        ),
        "confluence": RateLimitConfig(
            requests_per_minute=60, requests_per_hour=1000, burst_allowance=5
        ),
    }

    def __init__(self, custom_configs: Optional[Dict[str, RateLimitConfig]] = None):
        self.configs = self.DEFAULT_CONFIGS.copy()
        if custom_configs:
            self.configs.update(custom_configs)

        self.states: Dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _cleanup_old_requests(self, state: RateLimitState, current_time: float):
        """Remove requests older than tracking window."""
        # Clean up requests older than 1 minute
        minute_cutoff = current_time - 60
        while (
            state.requests_this_minute and state.requests_this_minute[0] < minute_cutoff
        ):
            state.requests_this_minute.popleft()

        # Clean up requests older than 1 hour
        hour_cutoff = current_time - 3600
        while state.requests_this_hour and state.requests_this_hour[0] < hour_cutoff:
            state.requests_this_hour.popleft()

    def _check_rate_limits(
        self, service: str, state: RateLimitState, current_time: float
    ) -> Optional[float]:
        """
        Check if request would exceed rate limits.

        Returns:
            Optional[float]: Wait time in seconds if rate limited, None if OK
        """
        config = self.configs[service]

        # Check minute limit
        if len(state.requests_this_minute) >= config.requests_per_minute:
            oldest_request = state.requests_this_minute[0]
            wait_time = 60 - (current_time - oldest_request)
            if wait_time > 0:
                return wait_time

        # Check hour limit
        if len(state.requests_this_hour) >= config.requests_per_hour:
            oldest_request = state.requests_this_hour[0]
            wait_time = 3600 - (current_time - oldest_request)
            if wait_time > 0:
                return wait_time

        # Check if we need to wait due to previous rate limiting
        if current_time < state.next_allowed_time:
            return state.next_allowed_time - current_time

        return None

    def _calculate_backoff_delay(self, service: str, retry_count: int) -> float:
        """Calculate exponential backoff delay."""
        config = self.configs[service]
        base_delay = 1.0  # 1 second base delay
        delay = base_delay * (config.backoff_factor**retry_count)

        # Add jitter to prevent thundering herd
        import random

        jitter = random.uniform(0.1, 0.3) * delay

        return min(delay + jitter, 300)  # Max 5 minute delay

    async def acquire(self, service: str, endpoint: Optional[str] = None) -> None:
        """
        Acquire permission to make an API request.

        Args:
            service: Service name (jira, github, confluence)
            endpoint: Optional endpoint identifier for more granular limiting

        Raises:
            RateLimitError: If maximum retries exceeded
        """
        if service not in self.configs:
            logger.warning(f"No rate limit config for service: {service}")
            return

        async with self._locks[service]:
            state = self.states[service]
            current_time = time.time()

            # Clean up old requests
            self._cleanup_old_requests(state, current_time)

            # Check if we need to wait
            wait_time = self._check_rate_limits(service, state, current_time)

            if wait_time:
                state.retry_count += 1
                config = self.configs[service]

                if state.retry_count > config.max_retries:
                    # Reset retry count for next attempt
                    state.retry_count = 0

                    # Raise appropriate rate limit error
                    if service == "jira":
                        raise JiraRateLimitError(retry_after=int(wait_time))
                    elif service == "github":
                        raise GitHubRateLimitError(retry_after=int(wait_time))
                    elif service == "confluence":
                        raise ConfluenceRateLimitError(retry_after=int(wait_time))
                    else:
                        raise RateLimitError(service, retry_after=int(wait_time))

                # Calculate backoff delay
                backoff_delay = self._calculate_backoff_delay(
                    service, state.retry_count
                )
                total_delay = max(wait_time, backoff_delay)

                logger.info(
                    f"Rate limited for {service}. "
                    f"Waiting {total_delay:.2f}s (attempt {state.retry_count}/{config.max_retries})"
                )

                # Set next allowed time
                state.next_allowed_time = current_time + total_delay

                # Wait for the calculated delay
                await asyncio.sleep(total_delay)

                # Recursive call after waiting
                await self.acquire(service, endpoint)
                return

            # Request is allowed, record it
            current_time = time.time()
            state.requests_this_minute.append(current_time)
            state.requests_this_hour.append(current_time)
            state.last_request_time = current_time
            state.retry_count = 0  # Reset retry count on successful request

            logger.debug(f"Rate limiter: Allowed request to {service}")

    def update_from_headers(self, service: str, headers: Dict[str, Any]):
        """
        Update rate limit state from API response headers.

        Args:
            service: Service name
            headers: Response headers containing rate limit info
        """
        state = self.states[service]
        current_time = time.time()

        # GitHub rate limit headers
        if service == "github":
            remaining = headers.get("X-RateLimit-Remaining")
            reset_time = headers.get("X-RateLimit-Reset")

            if remaining is not None and int(remaining) == 0 and reset_time:
                # Rate limited, set next allowed time
                state.next_allowed_time = float(reset_time)
                logger.warning(f"GitHub rate limit exceeded. Reset at {reset_time}")

        # JIRA rate limit headers (if available)
        elif service == "jira":
            retry_after = headers.get("Retry-After")
            if retry_after:
                state.next_allowed_time = current_time + float(retry_after)
                logger.warning(f"JIRA rate limit exceeded. Retry after {retry_after}s")

        # Confluence rate limit headers (if available)
        elif service == "confluence":
            retry_after = headers.get("Retry-After")
            if retry_after:
                state.next_allowed_time = current_time + float(retry_after)
                logger.warning(
                    f"Confluence rate limit exceeded. Retry after {retry_after}s"
                )

    def get_status(self, service: str) -> Dict[str, Any]:
        """Get current rate limit status for a service."""
        if service not in self.states:
            return {"status": "no_requests"}

        state = self.states[service]
        config = self.configs[service]
        current_time = time.time()

        # Clean up old requests for accurate counts
        self._cleanup_old_requests(state, current_time)

        return {
            "service": service,
            "requests_this_minute": len(state.requests_this_minute),
            "requests_this_hour": len(state.requests_this_hour),
            "minute_limit": config.requests_per_minute,
            "hour_limit": config.requests_per_hour,
            "retry_count": state.retry_count,
            "next_allowed_time": state.next_allowed_time,
            "rate_limited": current_time < state.next_allowed_time,
            "time_until_allowed": max(0, state.next_allowed_time - current_time),
        }

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get rate limit status for all services."""
        return {service: self.get_status(service) for service in self.configs.keys()}

    def reset_service(self, service: str):
        """Reset rate limit state for a service."""
        if service in self.states:
            self.states[service] = RateLimitState()
            logger.info(f"Reset rate limit state for {service}")

    def reset_all(self):
        """Reset rate limit state for all services."""
        self.states.clear()
        logger.info("Reset all rate limit states")


# Global rate limiter instance
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter


async def rate_limited_request(service: str, endpoint: Optional[str] = None):
    """
    Context manager for rate-limited API requests.

    Usage:
        async with rate_limited_request("github", "/repos"):
            # Make API request here
            pass
    """
    rate_limiter = get_rate_limiter()
    await rate_limiter.acquire(service, endpoint)
