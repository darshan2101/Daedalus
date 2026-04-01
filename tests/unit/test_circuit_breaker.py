import pytest
import time
import json
from daedalus.circuit_breaker import ModelHealthTracker

class MockRedis:
    def __init__(self):
        self.data = {}
        
    def get(self, key):
        return self.data.get(key)
        
    def set(self, key, value, ex=None):
        self.data[key] = value

def test_circuit_opens_after_3_errors():
    tracker = ModelHealthTracker(MockRedis())
    tracker.record_error("model_a", "timeout")
    tracker.record_error("model_a", "timeout")
    state = tracker.record_error("model_a", "timeout")
    
    assert state["status"] == "circuit_open"
    assert not tracker.can_use_model("model_a")

def test_circuit_stays_open_before_timeout(monkeypatch):
    tracker = ModelHealthTracker(MockRedis())
    for _ in range(3):
        tracker.record_error("model_b", "err")
        
    assert not tracker.can_use_model("model_b")
    
    # Fast forward time by a small amount
    current_time = time.time()
    monkeypatch.setattr(time, 'time', lambda: current_time + 10)
    assert not tracker.can_use_model("model_b")  # Still open

def test_exponential_backoff_escalates():
    tracker = ModelHealthTracker(MockRedis())
    
    # First trip (3 errors)
    for _ in range(3): tracker.record_error("model_c", "err")
    state1 = tracker.get_state("model_c")
    b1 = state1["circuit_open_until"] - state1["last_error_time"]
    assert b1 == 180
    
    # Manually reset to healthy and mock time passing so we aren't blocked,
    # but theoretically if we got another error while degraded, it should escalate.
    # The requirement is that backoff multiplier increments.
    # Let's say circuit closes after timeout, we try again, it's degraded, and fails again.
    state1["status"] = "degraded"
    state1["circuit_open_until"] = time.time() - 100
    tracker._save_state("model_c", state1)
    
    tracker.record_error("model_c", "err")
    state2 = tracker.get_state("model_c")
    b2 = state2["circuit_open_until"] - state2["last_error_time"]
    assert b2 == 360
    
    # Trip again
    state2["status"] = "degraded"
    state2["circuit_open_until"] = time.time() - 100
    tracker._save_state("model_c", state2)
    
    tracker.record_error("model_c", "err")
    state3 = tracker.get_state("model_c")
    b3 = state3["circuit_open_until"] - state3["last_error_time"]
    assert b3 == 720

def test_success_resets_error_counter():
    tracker = ModelHealthTracker(MockRedis())
    tracker.record_error("model_d", "err")
    tracker.record_error("model_d", "err")
    tracker.record_success("model_d")
    
    state = tracker.get_state("model_d")
    assert state["consecutive_errors"] == 0
    assert state["status"] == "healthy"
    assert state["backoff_multiplier"] == 0.0

def test_redis_schema():
    tracker = ModelHealthTracker(MockRedis())
    tracker.record_error("model_e", "err")
    
    raw = tracker.redis.get("model_state:model_e")
    assert raw is not None
    data = json.loads(raw)
    
    assert "model" in data
    assert "status" in data
    assert "consecutive_errors" in data
    assert "last_error_time" in data
    assert "circuit_open_until" in data
    assert "backoff_multiplier" in data
