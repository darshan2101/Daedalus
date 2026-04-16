import pytest
from unittest.mock import AsyncMock
from daedalus.component_generator import ComponentGenerator

@pytest.fixture
def config():
    return {"max_module_iterations": 3}

@pytest.fixture
def module_spec():
    return {
        "name": "auth-gateway",
        "responsibility": "Validate JWT tokens",
        "success_criteria": ["TestValidJWT returns 200", "TestExpiredJWT returns 401"]
    }

@pytest.mark.asyncio
async def test_component_generator_success_path(config, module_spec):
    drafter_fn = AsyncMock(return_value="mock tests")
    coder_fn = AsyncMock(return_value="mock implementation")
    fast_fn = AsyncMock(return_value={"test_results": [], "feedback": "All tests passed"})
    evaluator_fn = AsyncMock(return_value={"score": 0.95})

    generator = ComponentGenerator(config, drafter_fn, coder_fn, fast_fn, evaluator_fn)

    result = await generator.generate_module(module_spec)

    assert result["status"] == "complete"
    assert result["score"] == 0.95

    drafter_fn.assert_not_called()           # drafter no longer used — coder writes tests
    assert coder_fn.call_count == 2          # once for test generation, once for implementation
    fast_fn.assert_called_once()
    evaluator_fn.assert_called_once()

@pytest.mark.asyncio
async def test_component_generator_failure_path_retries(config, module_spec):
    """Failure path (coder fails, loop retries)"""
    drafter_fn = AsyncMock(return_value="mock tests")
    # coder called 3 times: once for test gen, twice for impl (first fails, second passes)
    coder_fn = AsyncMock(side_effect=["mock go tests", "flawed implementation", "fixed implementation"])
    fast_fn = AsyncMock(side_effect=[
        {"test_results": [{"test": "mock_test", "error": "failed"}], "feedback": "mock_test failing: failed"},
        {"test_results": [], "feedback": "All tests passed"}
    ])
    evaluator_fn = AsyncMock(side_effect=[{"score": 0.5}, {"score": 0.9}])

    generator = ComponentGenerator(config, drafter_fn, coder_fn, fast_fn, evaluator_fn)

    result = await generator.generate_module(module_spec)

    assert result["status"] == "complete"
    assert result["score"] == 0.9

    assert drafter_fn.call_count == 0  # drafter no longer used — coder writes tests
    assert coder_fn.call_count == 3    # 1 test gen + 2 impl iterations
    assert fast_fn.call_count == 2
    assert evaluator_fn.call_count == 2

@pytest.mark.asyncio
async def test_component_generator_max_iteration_exit(config, module_spec):
    """Max iteration exit constraint check"""
    drafter_fn = AsyncMock(return_value="mock tests")
    coder_fn = AsyncMock(return_value="always flawed implementation")
    fast_fn = AsyncMock(return_value={"test_results": [{"test": "fail", "error": "failed"}], "feedback": "failing"})
    evaluator_fn = AsyncMock(return_value={"score": 0.4})

    generator = ComponentGenerator(config, drafter_fn, coder_fn, fast_fn, evaluator_fn)

    result = await generator.generate_module(module_spec)

    assert result["status"] == "partial"
    assert result["score"] == 0.4
    assert result.get("action") == "fix"

    assert drafter_fn.call_count == 0  # drafter no longer used
    assert coder_fn.call_count == 4    # 1 test gen + 3 impl iterations (max_iterations=3)
    assert fast_fn.call_count == 3
    assert evaluator_fn.call_count == 3
