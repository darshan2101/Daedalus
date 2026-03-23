# Project Brief: Daedalus Development (Ollama onwards)

This document summarizes the development progress and architectural decisions for the **Daedalus Orchestrator** depuis the integration of the Ollama suite.

## 1. Core Objectives
- Transition Daedalus from a linear script to a **hierarchical multi-agent system**.
- Implement a **self-healing "Repair Engine"** (Phase C).
- Introduce **formal routing** via LangGraph while maintaining a proven inline fallback.
- Enforce strict **mock-based unit testing** for speed and reliability.

## 2. Key Components Built (Ollama Onwards)

### **Phase C: Repair Engine** (`daedalus/repair.py`)
- **Function**: Automatically re-runs "weakest agents" if the system-level score falls below threshold (0.85).
- **Logic**: Unfreezes agents in Redis, increments iteration counts, and triggers a surgical re-run of only the failed/weak components.

### **M1: Merger Module** (`daedalus/merger.py`)
- **Function**: Detects and resolves "interface conflicts" between agents (e.g., Agent A expects `email` but Agent B produced `user_email`).
- **Resolution**: Uses an LLM to pick a "canonical" version and patches the non-canonical agent's output.

### **M2: Major Agent Wrapper** (`daedalus/major_agent.py`)
- **Function**: Adds a layer of "intelligence" before execution.
- **Complexity Assessment**: An LLM assesses the task description. If it's too complex (3+ deliverables or >1500 chars), it triggers **Sub-Agent Fragmentation**.
- **Guardrails**: Forced direct execution if at `max_recursion_depth`.

### **M3: Local Coordinator** (`daedalus/local_coordinator.py`)
- **Function**: Manages the recursive decomposition of a Major Agent's task.
- **Decomposition**: Spawns parallel sub-agents, executes them, and merges results (concatenation + averaged quality scores).

### **M4: LangGraph State Machine** (`daedalus/graph.py`)
- **Topology**: Formal `StateGraph` defining: `plan → execute → merge → aggregate → evaluate → repair (conditional loop)`.
- **Resume Flow**: A dedicated graph variant for resuming runs that skips the initial planning node.

## 3. Key Interactions & Decisions

- **Q: Should we defer LangGraph due to complexity?**
  - **A (User)**: No, implement it now. But provide a `config.yaml` toggle (`use_langgraph: true/false`) and ensure `main.py` can fall back to the inline `GlobalCoordinator` flow if the graph fails.
- **Q: How to handle testing for these complex modules?**
  - **A (User)**: Follow the `DAEDALUS_TESTING_ADDENDUM`. Use fast, mock-based unit tests. Avoid live LLM calls in the CI loop.
- **Decision**: Fixed a critical pre-existing bug in `tests/conftest.py` where the Redis `hset` mock didn't match the Upstash Redis API signature, resolving inherited test failures.

## 4. Configuration & Infrastructure
- **`config.yaml`**: Updated with `use_langgraph`, `max_parallel_sub`, and `max_recursion_depth`.
- **`main.py`**: Refactored to act as a router—initializing either the LangGraph flow or the inline flow based on configuration.
- **State Management**: Standardized on a shared `RunState` TypedDict and Redis-based "frozen agent" persistence for caching.

## 5. Current Status
- **Unit Tests**: **51 Passing / 0 Failing**.
- **Coverage**: Planner, Coordinator (Inline), Evaluator, Repair, Merger, MajorAgent, LocalCoordinator, and Graph routing logic are all verified.
- **Next Steps**: Low-priority items (Assembler, Reporter, 5-dim evaluation).

---
*Prepared for sync with Claude.ai instance.*
