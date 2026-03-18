"""Unit tests for GlobalCoordinator — topological sort only, no I/O."""
import pytest

# NOTE: GlobalCoordinator is not yet implemented (Week 3-4).
# These tests will be runnable once daedalus/coordinator.py exists.
# For now they are placeholder stubs that pytest --collect-only can discover.

class TestTopologicalSort:
    @pytest.mark.skip(reason="GlobalCoordinator not yet implemented (Week 3-4)")
    def test_no_deps_is_single_wave(self):
        pass

    @pytest.mark.skip(reason="GlobalCoordinator not yet implemented (Week 3-4)")
    def test_linear_chain_is_sequential_waves(self):
        pass

    @pytest.mark.skip(reason="GlobalCoordinator not yet implemented (Week 3-4)")
    def test_saas_pattern_produces_three_waves(self):
        pass

    @pytest.mark.skip(reason="GlobalCoordinator not yet implemented (Week 3-4)")
    def test_empty_graph_returns_empty_waves(self):
        pass
