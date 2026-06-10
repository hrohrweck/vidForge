import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.config import get_settings

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class RateLimiter:
    def __init__(self, times: int, seconds: int) -> None:
        self.times = times
        self.seconds = seconds

    async def _get_key(self, request: Request, user_id: Optional[str] = None) -> str:
        if user_id is not None:
            return f"rate_limit:user:{user_id}"
        client_ip = request.client.host if request.client else "unknown"
        return f"rate_limit:ip:{client_ip}"

    async def is_allowed(self, key: str) -> bool:
        redis = await get_redis()
        now = time.time()
        window_start = now - self.seconds

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        _, count = await pipe.execute()

        if count >= self.times:
            return False

        pipe = redis.pipeline()
        pipe.zadd(key, {str(int(now * 1000)): now})
        pipe.expire(key, self.seconds)
        await pipe.execute()
        return True

    async def get_retry_after(self, key: str) -> int:
        redis = await get_redis()
        now = time.time()

        oldest = await redis.zrange(key, 0, 0, withscores=True)
        if not oldest:
            return self.seconds

        oldest_ts = oldest[0][1]
        retry_after = int(oldest_ts + self.seconds - now)
        return max(1, retry_after)

    async def __call__(self, request: Request) -> None:
        key = await self._get_key(request)
        if not await self.is_allowed(key):
            retry_after = await self.get_retry_after(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )


class AuthenticatedRateLimiter(RateLimiter):
    async def __call__(self, request: Request) -> None:
        from jose import JWTError, jwt

        from app.config import get_settings

        settings = get_settings()
        user_id = None

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
                user_id = payload.get("sub")
            except JWTError:
                pass

        if not user_id:
            token = request.cookies.get("vidforge_token")
            if token:
                try:
                    payload = jwt.decode(
                        token, settings.secret_key, algorithms=[settings.algorithm]
                    )
                    user_id = payload.get("sub")
                except JWTError:
                    pass

        key = await self._get_key(request, user_id=user_id)
        if not await self.is_allowed(key):
            retry_after = await self.get_retry_after(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
