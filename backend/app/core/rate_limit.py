"""
Distributed Sliding-Window Rate Limiter for Dukaanly.
Supports Redis-backed atomic sliding window (using Lua script) with
graceful, thread-safe in-memory fallback when Redis is unavailable.
"""

from collections import defaultdict
import ipaddress
import logging
import time
import uuid
from typing import Callable, Dict, List, Optional, Tuple
from fastapi import Request
import redis.asyncio as redis

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Atomic sliding-window rate limit script in Lua
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]
local clear_before = now - window

-- 1. Remove expired timestamps outside the sliding window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

-- 2. Count requests currently in the sliding window
local current_requests = redis.call('ZCARD', key)

if current_requests < max_requests then
    -- 3. Add this request with timestamp as score
    redis.call('ZADD', key, now, member)
    -- Expire key after window + 2 seconds to prevent memory leaks
    redis.call('EXPIRE', key, math.ceil(window) + 2)
    return {1, 0}
else
    -- Request rejected: find oldest item in window to calculate retry_after
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest and #oldest >= 2 then
        local oldest_time = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(window - (now - oldest_time)))
    end
    return {0, retry_after}
end
"""


class RateLimiter:
    """
    Sliding-window rate limiter.
    Uses Redis sorted sets for atomic distributed rate limiting across API workers.
    Falls back gracefully to process-local in-memory sliding window if Redis is unavailable.
    """

    def __init__(
        self,
        prefix: str,
        requests_per_window: Optional[int] = None,
        limit_getter: Optional[Callable[[], int]] = None,
        window_seconds: float = 60.0,
        fail_closed: bool = False,
    ):
        self.prefix = prefix
        self._requests_per_window = requests_per_window
        self._limit_getter = limit_getter
        self.window_seconds = window_seconds
        self.fail_closed = fail_closed
        self._local_history: Dict[str, List[float]] = defaultdict(list)
        self._script = None

    @property
    def requests_per_minute(self) -> int:
        """Alias for compatibility with existing tests and diagnostics."""
        return self.requests_per_window

    @property
    def requests_per_window(self) -> int:
        if self._limit_getter is not None:
            return self._limit_getter()
        return self._requests_per_window or 10

    def _make_key(self, identifier: str) -> str:
        return f"rl:{self.prefix}:{identifier}"

    async def check_and_record(self, identifier: str) -> Tuple[bool, Optional[float]]:
        """
        Check if an attempt is permitted and record it.
        Returns: (allowed: bool, retry_after_seconds: Optional[float])
        """
        try:
            client = await get_redis_client()
            if client is not None:
                if self._script is None or getattr(self._script, "redis", None) != client:
                    self._script = client.register_script(SLIDING_WINDOW_LUA)
                now = time.time()
                member = f"{now}:{uuid.uuid4().hex[:8]}"
                key = self._make_key(identifier)
                res = await self._script(
                    keys=[key],
                    args=[str(now), str(self.window_seconds), str(self.requests_per_window), member],
                )
                allowed = bool(res[0] == 1)
                retry_after = float(res[1]) if res[1] > 0 else None
                return allowed, retry_after
        except Exception as exc:
            if (
                self.fail_closed
                or getattr(settings, "RATE_LIMIT_FAIL_CLOSED", False)
                or (
                    getattr(settings, "RATE_LIMIT_AUTH_FAIL_CLOSED", False)
                    and self.prefix.startswith("auth_")
                )
            ):
                logger.warning(
                    "Redis rate limiter unavailable for '%s' (%s). Fail-closed mode active.",
                    self.prefix,
                    exc.__class__.__name__,
                )
                return False, self.window_seconds

            logger.warning(
                "Redis rate limiter unavailable for '%s' (%s). Falling back to in-memory limiter.",
                self.prefix,
                exc.__class__.__name__,
            )

        # Fallback to process-local sliding window (endpoint never silently becomes unlimited)
        return self.check_and_record_local(identifier)

    def check_and_record_local(self, identifier: str) -> Tuple[bool, Optional[float]]:
        """Synchronous in-memory sliding window check and record."""
        now = time.time()
        clear_before = now - self.window_seconds
        timestamps = [t for t in self._local_history[identifier] if t > clear_before]
        if len(timestamps) >= self.requests_per_window:
            oldest = timestamps[0]
            retry_after = max(1.0, round(self.window_seconds - (now - oldest), 1))
            self._local_history[identifier] = timestamps
            return False, retry_after

        timestamps.append(now)
        self._local_history[identifier] = timestamps
        return True, None

    async def reset(self, identifier: Optional[str] = None) -> None:
        """Reset rate limit history for a specific identifier or all identifiers in this namespace."""
        self._script = None
        self.reset_local(identifier)
        try:
            client = await get_redis_client()
            if client is not None:
                if identifier:
                    await client.delete(self._make_key(identifier))
                else:
                    pattern = f"rl:{self.prefix}:*"
                    cursor = 0
                    while True:
                        cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                        if keys:
                            await client.delete(*keys)
                        if cursor == 0:
                            break
        except Exception:
            pass

    def reset_local(self, identifier: Optional[str] = None) -> None:
        """Reset local in-memory history."""
        if identifier:
            self._local_history.pop(identifier, None)
        else:
            self._local_history.clear()


def is_ip_trusted_proxy(ip_str: str, trusted_proxies: str) -> bool:
    """Check if an IP address matches the trusted proxy whitelist or CIDR ranges."""
    if not ip_str or not trusted_proxies:
        return False
    if trusted_proxies.strip() == "*":
        return True
    try:
        addr = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False

    for entry in trusted_proxies.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                net = ipaddress.ip_network(entry, strict=False)
                if addr in net:
                    return True
            else:
                trusted_addr = ipaddress.ip_address(entry)
                if addr == trusted_addr:
                    return True
        except ValueError:
            continue
    return False


def get_client_ip(request: Request) -> str:
    """
    Extract verified client IP address respecting trusted proxy configuration.
    If the direct connection peer is NOT a trusted proxy, forwarding headers
    (X-Forwarded-For, X-Real-IP) are rejected to prevent IP spoofing attacks.
    """
    peer_ip = "127.0.0.1"
    if request.client and request.client.host:
        peer_ip = request.client.host.strip()

    trusted_proxies = getattr(
        settings,
        "TRUSTED_PROXIES",
        "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
    )

    # If peer is NOT a trusted proxy, forwarding headers are untrusted
    if not is_ip_trusted_proxy(peer_ip, trusted_proxies):
        return peer_ip

    # Peer is a trusted proxy: parse forwarding headers
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        for candidate in reversed(ips):
            if not is_ip_trusted_proxy(candidate, trusted_proxies):
                return candidate
        if ips:
            return ips[0]

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    return peer_ip


# Singletons configured with dynamic settings lookups
login_ip_rate_limiter = RateLimiter(
    prefix="auth_login_ip",
    limit_getter=lambda: settings.AUTH_RATE_LIMIT_LOGIN_PER_MINUTE,
    window_seconds=60.0,
)

login_email_rate_limiter = RateLimiter(
    prefix="auth_login_email",
    limit_getter=lambda: settings.AUTH_RATE_LIMIT_LOGIN_ACCOUNT_PER_MINUTE,
    window_seconds=60.0,
)

register_rate_limiter = RateLimiter(
    prefix="auth_register_ip",
    limit_getter=lambda: settings.AUTH_RATE_LIMIT_REGISTER_PER_MINUTE,
    window_seconds=60.0,
)

refresh_rate_limiter = RateLimiter(
    prefix="auth_refresh_ip",
    limit_getter=lambda: getattr(settings, "AUTH_RATE_LIMIT_REFRESH_PER_MINUTE", 30),
    window_seconds=60.0,
)

checkout_rate_limiter = RateLimiter(
    prefix="order_checkout",
    limit_getter=lambda: settings.CHECKOUT_RATE_LIMIT_PER_MINUTE,
    window_seconds=60.0,
)

image_upload_rate_limiter = RateLimiter(
    prefix="image_upload",
    limit_getter=lambda: 30,
    window_seconds=60.0,
)

ai_chat_rate_limiter = RateLimiter(
    prefix="ai_chat_user",
    limit_getter=lambda: settings.AI_RATE_LIMIT_PER_MINUTE,
    window_seconds=60.0,
)

rider_offers_rate_limiter = RateLimiter(
    prefix="rider_offers",
    limit_getter=lambda: 120,
    window_seconds=60.0,
)

ALL_RATE_LIMITERS: List[RateLimiter] = [
    login_ip_rate_limiter,
    login_email_rate_limiter,
    register_rate_limiter,
    refresh_rate_limiter,
    checkout_rate_limiter,
    image_upload_rate_limiter,
    ai_chat_rate_limiter,
    rider_offers_rate_limiter,
]


async def reset_all_rate_limiters() -> None:
    """Reset all application rate limiters (e.g. between test runs)."""
    for limiter in ALL_RATE_LIMITERS:
        await limiter.reset()
    try:
        from app.api.routes.ai import ai_user_rate_limiter
        ai_user_rate_limiter.reset()
    except Exception:
        pass
