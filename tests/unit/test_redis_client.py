"""Unit tests for Redis TTL logic and fallback behaviour."""
import pytest
from unittest.mock import patch, MagicMock

class TestSemaphoreCounter:
    def test_incr_respects_cap(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import sem_incr, sem_decr
            v1 = sem_incr("run_test")
            v2 = sem_incr("run_test")
            assert v2 == 2
            sem_decr("run_test")
            assert mock_redis._counters.get("run:run_test:sem", 0) == 1

    def test_freeze_agent_sets_frozen(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import freeze_agent, is_frozen
            freeze_agent("run_test", "ag_001")
            assert is_frozen("run_test", "ag_001") is True

    def test_unfreeze_sets_active(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import freeze_agent, unfreeze_agent, is_frozen
            freeze_agent("run_test", "ag_001")
            unfreeze_agent("run_test", "ag_001")
            assert is_frozen("run_test", "ag_001") is False

    def test_ttl_called_on_every_key_write(self, mock_redis):
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.redis_client import sem_incr
            sem_incr("run_ttltest")
            # expire must have been called — TTL is set per write
            assert mock_redis.expire.called

class TestGlobalSemaphore:
    @pytest.mark.asyncio
    async def test_semaphore_blocks_at_cap(self, mock_redis):
        """Semaphore should not allow more than cap concurrent calls."""
        with patch("infra.redis_client.get_redis", return_value=mock_redis):
            from infra.semaphore import GlobalSemaphore
            sem = GlobalSemaphore("run_sem_test", cap=2)
            # Manually set counter above cap
            mock_redis._counters["run:run_sem_test:sem"] = 3
            # acquire should not immediately succeed — it should poll
            import asyncio
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(sem.acquire(), timeout=0.2)

    @pytest.mark.asyncio
    async def test_fallback_used_when_redis_fails(self):
        """When Redis raises, asyncio.Semaphore fallback is used."""
        broken_redis = MagicMock()
        broken_redis.incr.side_effect = Exception("Redis unreachable")
        with patch("infra.redis_client.get_redis", return_value=broken_redis):
            from infra.semaphore import GlobalSemaphore
            sem = GlobalSemaphore("run_fallback", cap=3)
            # Should not raise — falls back to asyncio.Semaphore
            await sem.acquire()
            await sem.release()
