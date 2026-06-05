import redis
import time
import logging
from dataclasses import dataclass

from config import settings

@dataclass
class RateLimitResult:
    allowed: bool
    user_id: str
    requests_made: int
    requests_limit: int
    requests_remaining: int
    window_seconds: int
    retry_after: int
    reason: str

class RateLimiter:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.limit = settings.RATE_LIMIT_REQUESTS
        self.window = settings.RATE_LIMIT_WINDOW_SECONDS
        self.logger.info(f"Rate limiter initialized: {self.limit} requests per {self.window}s")

    def _get_key(self, user_id: str) -> str:
        return f"rate_limit:{user_id}"

    def check_and_increment(self, user_id: str) -> RateLimitResult:
        key = self._get_key(user_id)
        now = time.time()
        window_start = now - self.window

        pipe = self.redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, self.window)
        results = pipe.execute()

        requests_made = results[2]
        allowed = requests_made <= self.limit
        requests_remaining = max(0, self.limit - requests_made)

        if allowed:
            retry_after = 0
            reason = f"Request allowed ({requests_made}/{self.limit} in window)"
        else:
            oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = int(oldest[0][1] + self.window - now) + 1
            else:
                retry_after = self.window
            reason = f"Rate limit exceeded. Retry after {retry_after}s"
            self.logger.warning(f"Rate limit exceeded for user: {user_id}, requests_made: {requests_made}")

        return RateLimitResult(
            allowed=allowed,
            user_id=user_id,
            requests_made=requests_made,
            requests_limit=self.limit,
            requests_remaining=requests_remaining,
            window_seconds=self.window,
            retry_after=retry_after,
            reason=reason
        )

    def is_allowed(self, user_id: str) -> bool:
        return self.check_and_increment(user_id).allowed

    def reset_user(self, user_id: str) -> bool:
        self.redis_client.delete(self._get_key(user_id))
        return True

    def get_usage(self, user_id: str) -> dict:
        key = self._get_key(user_id)
        now = time.time()
        window_start = now - self.window
        self.redis_client.zremrangebyscore(key, 0, window_start)
        count = self.redis_client.zcard(key)
        return {
            "user_id": user_id,
            "requests_made": count,
            "requests_limit": self.limit,
            "requests_remaining": max(0, self.limit - count),
            "window_seconds": self.window
        }

def safe_check(user_id: str, limiter: "RateLimiter") -> RateLimitResult:
    try:
        return limiter.check_and_increment(user_id)
    except Exception as e:
        limiter.logger.warning(f"Redis unavailable, failing open: {e}")
        return RateLimitResult(
            allowed=True,
            user_id=user_id,
            requests_made=0,
            requests_limit=limiter.limit,
            requests_remaining=limiter.limit,
            window_seconds=limiter.window,
            retry_after=0,
            reason="Rate limiter unavailable — request allowed"
        )

rate_limiter = RateLimiter()
