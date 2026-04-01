MODEL_HEALTH_SCHEMA = {
    "model": "z-ai/glm-4.5-air:free",
    "status": "healthy|degraded|circuit_open",
    "consecutive_errors": 0,
    "last_error_time": 1711891200,
    "circuit_open_until": 1711891380,
    "backoff_multiplier": 0.0,
}

# Formula comment: backoff_sec = 180 * (2 ** backoff_multiplier)
