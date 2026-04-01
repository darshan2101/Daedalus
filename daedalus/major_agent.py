"""
daedalus/major_agent.py
Major Agent runtime — assesses task complexity, routes to direct execution
or sub-agent fragmentation via LocalCoordinator.
"""

import asyncio
import json
from typing import Optional
from rich.console import Console

from daedalus.state import AgentSpec, StepResult, RunState
from daedalus.sub_agent import run_agent_task

console = Console()

# ── Complexity Assessment Prompt ──────────────────────────────────────────────

COMPLEXITY_PROMPT = """You are a task complexity assessor. Given a task description, determine if it should be fragmented into sub-tasks or executed directly.

TASK: {task}
OUTPUT TYPE: {output_type}
TASK LENGTH: {task_len} characters

Rules for fragmentation:
- Fragment if the task has 3+ distinct deliverables (e.g. "build backend, auth, and database schema")
- Fragment if the task description exceeds 1500 characters
- DO NOT fragment if the task is focused on a single component
- DO NOT fragment if depth would exceed {max_depth}

Output ONLY valid JSON:
{{
  "should_fragment": true/false,
  "reason": "<one sentence explanation>",
  "sub_tasks": [
    {{
      "task": "<sub-task description>",
      "specialist": "<coder|reasoner|drafter|creative|fast|researcher>"
    }}
  ]
}}

If should_fragment is false, sub_tasks should be an empty list.
"""


class MajorAgent:
    """
    Wraps a single major agent task. Decides whether to:
    1. Execute directly via run_agent_task (simple tasks)
    2. Fragment into sub-agents via LocalCoordinator (complex tasks)
    """

    def __init__(self, spec: AgentSpec, config: dict, state: RunState):
        self.spec = spec
        self.config = config
        self.state = state
        self.run_id = state["run_id"]
        self.max_depth = config.get("runtime", {}).get("max_recursion_depth", 5)

    async def run(self) -> StepResult:
        """
        Main entry point:
        1. Assess complexity
        2. Route to direct or fragment
        3. Return StepResult
        """
        aid = self.spec["agent_id"]
        depth = self.spec.get("depth", 0)

        # If already at max depth, always execute directly
        if depth >= self.max_depth - 1:
            return await self._execute_direct()

        # Assess complexity
        should_fragment, sub_tasks = await self._assess_complexity()

        if should_fragment and sub_tasks:
            console.print(f"  [bold cyan]↳ {aid} fragmenting into {len(sub_tasks)} sub-agents[/]")
            return await self._fragment_and_run(sub_tasks)
        else:
            return await self._execute_direct()

    async def _assess_complexity(self) -> tuple[bool, list]:
        """
        LLM call to determine if the task should be fragmented.
        Returns (should_fragment: bool, sub_tasks: list).
        """
        task = self.spec["task"]
        depth = self.spec.get("depth", 0)

        # Quick heuristic: very short tasks are never fragmented
        if len(task) < 800:
            return False, []
        
        # Check config to allow disabling fragmentation entirely for speed
        if not self.config.get("runtime", {}).get("allow_fragmentation", True):
            return False, []

        try:
            raw = await _call_complexity_llm(
                task=task,
                output_type=self.spec.get("output_type", "code"),
                task_len=len(task),
                max_depth=self.max_depth - depth,
            )

            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            parsed = json.loads(raw)
            should_fragment = parsed.get("should_fragment", False)
            sub_tasks = parsed.get("sub_tasks", [])

            if should_fragment:
                console.print(
                    f"  [dim]Complexity: FRAGMENT — {parsed.get('reason', 'complex task')}[/]"
                )
            else:
                console.print(f"  [dim]Complexity: DIRECT — {parsed.get('reason', 'simple task')}[/]")

            return should_fragment, sub_tasks

        except Exception as e:
            console.print(f"  [dim]Complexity assessment failed ({e}), defaulting to DIRECT[/]")
            return False, []

    async def _execute_direct(self) -> StepResult:
        """Execute the task directly via the existing run_agent_task bridge."""
        return await run_agent_task(
            self.run_id, self.spec, self.config, self.state
        )

    async def _fragment_and_run(self, sub_tasks: list) -> StepResult:
        """
        Fragment into sub-agents using LocalCoordinator.
        Falls back to direct execution if LocalCoordinator fails.
        """
        try:
            from daedalus.local_coordinator import LocalCoordinator
            local_coord = LocalCoordinator(self.spec, self.config, self.state)
            return await local_coord.run_sub_tasks(sub_tasks)
        except Exception as e:
            console.print(f"  [yellow]⚠ Fragmentation failed ({e}), falling back to direct[/]")
            return await self._execute_direct()


async def _call_complexity_llm(task: str, output_type: str, task_len: int, max_depth: int) -> str:
    """Call LLM for complexity assessment. Isolated for mocking in tests."""
    from kimiflow.agents import _call_with_fallback
    from models import REASONER_MODELS

    prompt = COMPLEXITY_PROMPT.format(
        task=task, output_type=output_type,
        task_len=task_len, max_depth=max_depth,
    )

    def _do():
        return _call_with_fallback(
            REASONER_MODELS,
            "You assess task complexity for decomposition.",
            prompt,
            temperature=0.1,
        )
    return await asyncio.to_thread(_do)
