import os
from upstash_redis import Redis

_redis: Redis | None = None

def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis(
            url=os.getenv("UPSTASH_REDIS_REST_URL"),
            token=os.getenv("UPSTASH_REDIS_REST_TOKEN"),
        )
    return _redis

def register_key(run_id: str, key: str, ttl: int):
    """Register a key and set its TTL. Called after every key creation."""
    get_redis().sadd(f"run:{run_id}:_keys", key)
    get_redis().expire(key, ttl)
    get_redis().expire(f"run:{run_id}:_keys", ttl)

def expire_run(run_id: str, ttl_hours: int):
    """Called at run completion — refresh TTL on all tracked keys."""
    ttl = ttl_hours * 3600
    keys = get_redis().smembers(f"run:{run_id}:_keys") or set()
    for key in keys:
        get_redis().expire(key, ttl)
    get_redis().expire(f"run:{run_id}:_keys", ttl)

def sem_incr(run_id: str, ttl_hours: int = 48) -> int:
    key = f"run:{run_id}:sem"
    val = get_redis().incr(key)
    register_key(run_id, key, ttl_hours * 3600)
    return val

def sem_decr(run_id: str) -> int:
    return get_redis().decr(f"run:{run_id}:sem")

def sem_get(run_id: str)  -> int:
    return int(get_redis().get(f"run:{run_id}:sem") or 0)

def freeze_agent(run_id: str, agent_id: str, ttl_hours: int = 48):
    key = f"run:{run_id}:modules"
    get_redis().hset(key, agent_id, "frozen")
    register_key(run_id, key, ttl_hours * 3600)

def unfreeze_agent(run_id: str, agent_id: str, ttl_hours: int = 48):
    key = f"run:{run_id}:modules"
    get_redis().hset(key, agent_id, "active")
    register_key(run_id, key, ttl_hours * 3600)

def is_frozen(run_id: str, agent_id: str) -> bool:
    return get_redis().hget(f"run:{run_id}:modules", agent_id) == "frozen"

def incr_sys_iter(run_id: str, ttl_hours: int = 48) -> int:
    key = f"run:{run_id}:sys_iter"
    val = get_redis().incr(key)
    register_key(run_id, key, ttl_hours * 3600)
    return val

def incr_agent_iter(run_id: str, agent_id: str, ttl_hours: int = 48) -> int:
    key = f"run:{run_id}:agent:{agent_id}:iter"
    val = get_redis().incr(key)
    register_key(run_id, key, ttl_hours * 3600)
    return val

def set_agent_meta(run_id: str, agent_id: str, data: dict, ttl_hours: int = 48):
    key = f"run:{run_id}:agent:{agent_id}"
    get_redis().hset(key, data)
    register_key(run_id, key, ttl_hours * 3600)
