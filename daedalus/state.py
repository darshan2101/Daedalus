from typing import TypedDict, Optional

class AgentSpec(TypedDict):
    agent_id:       str          # uuid4 short e.g. "ag_a1b2"
    task:           str          # Full task description for this agent
    output_type:    str          # code | docs | design | research
    threshold:      float        # From config per output_type (planner can tighten)
    dependencies:   list[str]    # agent_ids this must wait for
    depth:          int          # 0 = major, 1+ = sub
    parent_id:      Optional[str]
    specialist:     str          # coder|reasoner|drafter|creative|fast|researcher

class StepResult(TypedDict):
    agent_id:       str
    task:           str
    result:         str
    score:          float
    iterations:     int
    frozen:         bool

class BrokenInterface(TypedDict):
    agent_a:        str          # agent_id
    agent_b:        str          # agent_id
    description:    str          # what is broken between them
    attempt:        int          # which repair attempt

class RunState(TypedDict):
    # ── Identity
    run_id:               str    # uuid4 e.g. "run_a1b2c3d4"
    goal:                 str
    preset:               str    # saas | default | research | ...

    # ── Planner output
    plan:                 str
    agent_specs:          list[AgentSpec]
    dep_graph:            dict[str, list[str]]  # {agent_id: [dep_ids]}
    output_type:          str    # dominant output type for the run

    # ── Execution tracking
    agent_results:        dict[str, StepResult]   # {agent_id: StepResult}
    frozen_agents:        list[str]               # agent_ids that passed

    # ── Combined output
    combined_result:      str
    output_path:          str
    combined_score:       float
    broken_interfaces:    list[BrokenInterface]

    # ── Iteration control
    system_iteration:     int    # 0-based, max = max_system_iterations
    repair_attempts:      int    # surgical attempts in current system iteration

    # ── Meta
    current_step:         str    # planner|executing|evaluating|repairing|done
    errors:               list[str]
