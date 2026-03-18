import asyncio
from typing import Optional
from infra.redis_client import sem_incr, sem_decr

class GlobalSemaphore:
    """
    Redis-backed global LLM call semaphore.
    Fallback to asyncio.Semaphore if Redis unreachable.
    """
    def __init__(self, run_id: str, cap: int, ttl_hours: int = 48):
        self.run_id = run_id
        self.cap    = cap
        self.ttl_hours = ttl_hours
        self._fallback = asyncio.Semaphore(cap)

    async def acquire(self):
        try:
            while True:
                # Upstash REST might have jitter, making async network calls in loop
                current = await asyncio.to_thread(sem_incr, self.run_id, self.ttl_hours)
                if current <= self.cap:
                    return
                await asyncio.to_thread(sem_decr, self.run_id)
                await asyncio.sleep(0.5)
        except Exception:
            await self._fallback.acquire()

    async def release(self):
        try:
            await asyncio.to_thread(sem_decr, self.run_id)
        except Exception:
            self._fallback.release()

    async def __aenter__(self): await self.acquire(); return self
    async def __aexit__(self, *_): await self.release()
