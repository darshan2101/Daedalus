import time
import json
from typing import Dict, Any

class ModelHealthTracker:
    def __init__(self, redis_client):
        self.redis = redis_client

    def get_state(self, model: str) -> dict:
        key = f"model_state:{model}"
        try:
            state = self.redis.get(key)
            if state:
                return json.loads(state)
        except Exception as e:
            print(f"  [circuit_breaker] Redis get error: {e}")
            
        return self._default_state(model)

    def record_success(self, model: str) -> None:
        state = self.get_state(model)
        state["consecutive_errors"] = 0
        state["status"] = "healthy"
        state["backoff_multiplier"] = 0.0
        self._save_state(model, state)

    def record_error(self, model: str, error: str) -> dict:
        state = self.get_state(model)
        state["consecutive_errors"] += 1
        state["last_error_time"] = time.time()

        if state["consecutive_errors"] >= 3:
            # Open circuit with exponential backoff
            backoff_sec = 180 * (2 ** state["backoff_multiplier"])
            state["status"] = "circuit_open"
            state["circuit_open_until"] = time.time() + backoff_sec
            state["backoff_multiplier"] += 1.0
            print(f"  [circuit_breaker] {model} OPENED for {backoff_sec}s (attempt #{state['consecutive_errors']})")
        elif state["status"] == "degraded":
            # If we were degraded and failed again immediately, re-open circuit
            backoff_sec = 180 * (2 ** state["backoff_multiplier"])
            state["status"] = "circuit_open"
            state["circuit_open_until"] = time.time() + backoff_sec
            state["backoff_multiplier"] += 1.0
            print(f"  [circuit_breaker] {model} OPENED for {backoff_sec}s (degraded attempt)")

        self._save_state(model, state)
        return state

    def can_use_model(self, model: str) -> bool:
        state = self.get_state(model)
        if state["status"] == "circuit_open":
            if state.get("circuit_open_until") is not None and time.time() < state["circuit_open_until"]:
                return False
            else:
                # Window closed, try again
                state["status"] = "degraded"
                self._save_state(model, state)
                return True
        return True

    def _default_state(self, model: str) -> dict:
        return {
            "model": model,
            "status": "healthy",
            "consecutive_errors": 0,
            "last_error_time": None,
            "circuit_open_until": None,
            "backoff_multiplier": 0.0,
        }

    def _save_state(self, model: str, state: dict) -> None:
        key = f"model_state:{model}"
        try:
            self.redis.set(key, json.dumps(state), ex=86400)
        except Exception as e:
            print(f"  [circuit_breaker] Redis set error: {e}")

_health_tracker = None

def get_health_tracker() -> ModelHealthTracker:
    global _health_tracker
    if _health_tracker is None:
        from infra.redis_client import get_redis
        _health_tracker = ModelHealthTracker(get_redis())
    return _health_tracker
