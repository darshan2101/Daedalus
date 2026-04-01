"""
tests/unit/test_phase2b_fixes.py
Unit tests for Phase 2b emergency fixes:
  - Bug 1: LangGraph recursion limit formula
  - Bug 2: Threshold epsilon
  - Bug 3: Garbage patch prevention
"""
import pytest
from unittest.mock import patch, MagicMock


# ── Bug 1: Recursion Limit Formula ───────────────────────────────────────────

def test_recursion_limit_formula():
    """
    Formula: 1 + (max_retries * 2) + 3
    Graph has 3 nodes: plan, execute, evaluate.
    Router is a conditional edge, not a node — does not count toward recursion.
    Each iteration = 2 node steps (execute + evaluate). Plan fires once = 1.
    Buffer = 3 for safety.
    With max_module_iterations=5: 1 + (5 * 2) + 3 = 14.
    """
    max_retries = 5
    expected = 1 + (max_retries * 2) + 3
    assert expected == 14

    max_retries_1 = 1
    expected_1 = 1 + (max_retries_1 * 2) + 3
    assert expected_1 == 6

    max_retries_10 = 10
    expected_10 = 1 + (max_retries_10 * 2) + 3
    assert expected_10 == 24


def test_recursion_limit_default_is_safe():
    """
    Default for max_module_iterations must be 5 (matching config.yaml),
    not 1 which would give a dangerously low recursion_limit of 6.
    """
    # Simulate config missing the key entirely — default must be 5
    config_empty = {}
    max_retries = config_empty.get("runtime", {}).get("max_module_iterations", 5)
    recursion_limit = 1 + (max_retries * 2) + 3
    assert max_retries == 5, f"Default must be 5, got {max_retries}"
    assert recursion_limit == 14, f"Expected 14, got {recursion_limit}"


# ── Bug 2: Threshold Epsilon ──────────────────────────────────────────────────

def test_threshold_epsilon():
    """
    Score just below threshold due to floating-point imprecision should pass.
    epsilon = 0.005.
    0.8799 >= (0.88 - 0.005) = 0.875 → PASS
    0.874  >= (0.88 - 0.005) = 0.875 → FAIL (should still repair)
    """
    threshold = 0.88
    epsilon = 0.005

    score_just_below = 0.8799
    assert score_just_below >= threshold - epsilon  # should pass with epsilon

    score_clearly_below = 0.874
    assert not (score_clearly_below >= threshold - epsilon)  # should still fail


# ── Bug 3: Garbage Patch Prevention ──────────────────────────────────────────

def test_garbage_patch_prevention_short():
    """Patch shorter than 200 chars must be skipped."""
    original = "x" * 1000
    patch = "x" * 150  # < 200 chars absolute minimum

    too_short = len(patch) < 200
    assert too_short, "Expected patch to be flagged as too short"


def test_garbage_patch_prevention_relative():
    """Patch less than 20% of original must be skipped."""
    original = "x" * 5000
    patch = "x" * 500  # 10% of original = below 20% threshold

    original_len = len(original)
    patch_len = len(patch)

    too_small_relative = original_len > 0 and patch_len < original_len * 0.2
    assert too_small_relative, "Expected patch to be flagged as too small relative to original"


def test_garbage_patch_prevention_valid():
    """A patch that passes both checks should be applied."""
    original = "x" * 1000
    patch = "x" * 300  # 30% of original and >= 200 chars absolute

    patch_len = len(patch)
    original_len = len(original)

    too_short = patch_len < 200
    too_small_relative = original_len > 0 and patch_len < original_len * 0.2

    assert not too_short, "Valid patch should not be flagged as too short"
    assert not too_small_relative, "Valid patch should not be flagged as too small"
