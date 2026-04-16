import pytest
from daedalus.test_validator import TestValidator

GO_PASS_FIXTURE = """=== RUN   TestValidJWT
--- PASS: TestValidJWT (0.00s)
PASS
coverage: 92.0% of statements
"""

GO_FAIL_FIXTURE = """=== RUN   TestExpiredJWT
    auth_test.go:45: expected 401, got 200
--- FAIL: TestExpiredJWT (0.01s)
FAIL
coverage: 87.5% of statements
"""

GO_PANIC_FIXTURE = """panic: runtime error: invalid memory address or nil pointer dereference
goroutine 1 [running]:
main.TestCrash()
FAIL
"""

@pytest.fixture
def validator():
    return TestValidator()

def test_get_coverage_success(validator):
    cov = validator.get_coverage(GO_PASS_FIXTURE)
    assert cov == 92.0

def test_get_coverage_missing_returns_sentinel(validator):
    cov = validator.get_coverage(GO_PANIC_FIXTURE)
    assert cov == -1.0

def test_extract_failures_empty_on_success(validator):
    failures = validator.extract_failures(GO_PASS_FIXTURE)
    assert len(failures) == 0

def test_extract_failures_catches_standard_failure(validator):
    failures = validator.extract_failures(GO_FAIL_FIXTURE)
    assert len(failures) == 1
    assert failures[0]["test"] == "TestExpiredJWT"
    assert "expected 401, got 200" in failures[0]["error"]

def test_extract_failures_catches_panic(validator):
    failures = validator.extract_failures(GO_PANIC_FIXTURE)
    assert len(failures) == 1
    assert "panic: runtime error" in failures[0]["error"]

from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
@patch("daedalus.test_validator.asyncio.create_subprocess_shell")
async def test_validate_module_executes_subproc_and_parses(mock_shell, validator):
    """Verifies validate_module runs shell and maps output to dict schema."""
    
    # Mock subprocess return object
    process_mock = AsyncMock()
    # communicate() returns (stdout, stderr) as bytes
    process_mock.communicate.return_value = (GO_FAIL_FIXTURE.encode('utf-8'), b"")
    process_mock.returncode = 1
    mock_shell.return_value = process_mock

    # Run the validation
    res = await validator.validate_module("testmod", "test.go", "impl.go")
    
    # Assert Subprocess execution format
    assert mock_shell.called
    cmd = mock_shell.call_args[0][0]
    assert "go test" in cmd
    
    # Assert dictionary mapping
    assert res["status"] == "failing"
    assert res["coverage"] == 87.5
    assert len(res["test_results"]) == 1
    assert res["test_results"][0]["test"] == "TestExpiredJWT"
    assert "expected 401, got 200" in res["test_results"][0]["error"]
    
    # Feedback string should contain failing info
    assert "TestExpiredJWT" in res["feedback"]
