import logging
import time
from typing import Optional, Tuple
import redis.asyncio as aioredis
from src.config import settings

logger = logging.getLogger("hag.redis")


class InMemoryFallbackStore:

    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}
        self._rate_limits: dict[str, list[float]] = {}
        self._nonces: dict[str, float] = {}

    def _cleanup(self):
        now = time.time()
        # Clean store
        expired_keys = [k for k, v in self._store.items() if v[1] < now]
        for k in expired_keys:
            del self._store[k]
        # Clean nonces
        expired_nonces = [k for k, exp in self._nonces.items() if exp < now]
        for k in expired_nonces:
            del self._nonces[k]

    async def set_otp(self, phone: str, otp: str, ttl: int = 300) -> bool:
        self._cleanup()
        expires_at = time.time() + ttl
        self._store[f"otp:{phone}"] = (otp, expires_at)
        return True

    async def get_otp(self, phone: str) -> Optional[str]:
        self._cleanup()
        key = f"otp:{phone}"
        val = self._store.get(key)
        if not val:
            return None
        otp, expires_at = val
        if time.time() > expires_at:
            del self._store[key]
            return None
        return otp

    async def delete_otp(self, phone: str) -> bool:
        key = f"otp:{phone}"
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def check_rate_limit(
        self, key: str, limit: int = 5, window: int = 3600
    ) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - window
        timestamps = [t for t in self._rate_limits.get(key, []) if t > cutoff]
        count = len(timestamps)
        if count >= limit:
            self._rate_limits[key] = timestamps
            return False, count
        timestamps.append(now)
        self._rate_limits[key] = timestamps
        return True, count + 1

    async def store_nonce(self, nonce: str, ttl: int = 300) -> bool:
        self._cleanup()
        expires_at = time.time() + ttl
        self._nonces[nonce] = expires_at
        return True

    async def consume_nonce(self, nonce: str) -> bool:
        self._cleanup()
        expires_at = self._nonces.get(nonce)
        if not expires_at:
            return False
        del self._nonces[nonce]
        return time.time() <= expires_at


class RedisClientManager:

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.fallback = InMemoryFallbackStore()
        self.use_fallback = False

    async def init_redis(self):
        try:
            url = settings.get_redis_url()
            client = aioredis.from_url(
                url, decode_responses=True, socket_timeout=2.0
            )
            await client.ping()
            self.redis = client
            self.use_fallback = False
            logger.info("Connected to Redis at %s", url)
        except Exception as e:
            logger.warning(
                "Redis connection failed (%s). Using in-memory store.", e
            )
            self.redis = None
            self.use_fallback = True

    async def close_redis(self):
        if self.redis:
            await self.redis.close()
            self.redis = None

    async def set_otp(self, phone: str, otp: str, ttl: int = 300) -> bool:
        if self.use_fallback or not self.redis:
            return await self.fallback.set_otp(phone, otp, ttl)
        try:
            key = f"otp:{phone}"
            await self.redis.set(key, otp, ex=ttl)
            return True
        except Exception as e:
            logger.error("Redis set_otp failed: %s. Using fallback.", e)
            return await self.fallback.set_otp(phone, otp, ttl)

    async def get_otp(self, phone: str) -> Optional[str]:
        if self.use_fallback or not self.redis:
            return await self.fallback.get_otp(phone)
        try:
            key = f"otp:{phone}"
            val = await self.redis.get(key)
            return str(val) if val is not None else None
        except Exception as e:
            logger.error("Redis get_otp failed: %s. Using fallback.", e)
            return await self.fallback.get_otp(phone)

    async def delete_otp(self, phone: str) -> bool:
        if self.use_fallback or not self.redis:
            return await self.fallback.delete_otp(phone)
        try:
            key = f"otp:{phone}"
            res = await self.redis.delete(key)
            return bool(res > 0)
        except Exception as e:
            logger.error("Redis delete_otp failed: %s. Using fallback.", e)
            return await self.fallback.delete_otp(phone)

    async def check_rate_limit(
        self, key: str, limit: int = 5, window: int = 3600
    ) -> Tuple[bool, int]:
        if self.use_fallback or not self.redis:
            return await self.fallback.check_rate_limit(key, limit, window)
        try:
            rate_key = f"ratelimit:{key}"
            pipe = self.redis.pipeline()
            now = time.time()
            cutoff = now - window
            pipe.zremrangebyscore(rate_key, 0, cutoff)
            pipe.zcard(rate_key)
            pipe.zadd(rate_key, {str(now): now})
            pipe.expire(rate_key, window)
            results = await pipe.execute()
            count = results[1]
            if count >= limit:
                return False, count
            return True, count + 1
        except Exception as e:
            logger.error("Redis check_rate_limit failed: %s. Using fallback.", e)
            return await self.fallback.check_rate_limit(key, limit, window)

    async def store_nonce(self, nonce: str, ttl: int = 300) -> bool:
        if self.use_fallback or not self.redis:
            return await self.fallback.store_nonce(nonce, ttl)
        try:
            key = f"nonce:{nonce}"
            await self.redis.set(key, "1", ex=ttl)
            return True
        except Exception as e:
            logger.error("Redis store_nonce failed: %s. Using fallback.", e)
            return await self.fallback.store_nonce(nonce, ttl)

    async def consume_nonce(self, nonce: str) -> bool:
        if self.use_fallback or not self.redis:
            return await self.fallback.consume_nonce(nonce)
        try:
            key = f"nonce:{nonce}"
            val = await self.redis.get(key)
            if not val:
                return False
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error("Redis consume_nonce failed: %s. Using fallback.", e)
            return await self.fallback.consume_nonce(nonce)


redis_client = RedisClientManager()
