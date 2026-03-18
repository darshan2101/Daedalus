"""
PHASE GATE — Week 7
Must pass before Phase 2 work begins.
"""
import pytest
from unittest.mock import patch, AsyncMock

# NOTE: These tests require the --resume feature in coordinator.py
# which is not yet implemented (Week 7).
# All tests are skipped until that module exists.

class TestWeek7ResumeGate:

    @pytest.mark.skip(reason="Resume not yet implemented (Week 7)")
    @pytest.mark.asyncio
    async def test_resume_skips_frozen_agents(self):
        pass

    @pytest.mark.skip(reason="Resume not yet implemented (Week 7)")
    @pytest.mark.asyncio
    async def test_resume_restores_prior_results(self):
        pass
