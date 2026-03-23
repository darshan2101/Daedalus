# PROMPT FOR CLAUDE CODE — TESTING ADDENDUM INTEGRATION

Paste this entire prompt into Claude Code as a single message.

---

## Your Task

Read `DAEDALUS_TESTING_ADDENDUM.md` in full. Then integrate it into
`daedalus_master_plan.md` as **PART 13** without modifying any existing
content in the master plan.

Do the following steps in order:

---

### Step 1 — Append PART 13 to the master plan

Open `daedalus_master_plan.md` and append the full contents of
`DAEDALUS_TESTING_ADDENDUM.md` at the end of the file.
The master plan already ends at PART 12. Add a blank line separator then
paste PART 13 in full.

---

### Step 2 — Create the test directory structure

Create these empty files (with minimal valid content) so the structure exists:

```
tests/__init__.py
tests/conftest.py              ← paste the full conftest from PART 13.2
tests/unit/__init__.py
tests/unit/test_planner.py     ← paste from PART 13.3
tests/unit/test_coordinator.py ← paste from PART 13.3
tests/unit/test_evaluator.py   ← paste from PART 13.3
tests/unit/test_redis_client.py ← paste from PART 13.3
tests/unit/test_repair.py      ← paste from PART 13.3
tests/integration/__init__.py
tests/integration/test_week1_planner.py  ← paste from PART 13.4
tests/integration/test_week3_dag.py      ← paste from PART 13.4
tests/integration/test_week5_repair.py   ← paste from PART 13.4
tests/integration/test_week7_resume.py   ← paste from PART 13.4
tests/live/__init__.py
tests/live/.gitkeep
tests/health/__init__.py
tests/health/check.py          ← paste from PART 13.5
```

---

### Step 3 — Add pytest config

Create `pytest.ini` in the project root with this content:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
markers =
    live: marks tests that make real LLM API calls (deselect with -m "not live")
```

---

### Step 4 — Update requirements.txt

Add these lines to `requirements.txt` under a `# Testing` comment:

```
# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

### Step 5 — Install and verify

Run:
```bash
pip install pytest pytest-asyncio
```

Then run the unit tests that don't require any Daedalus modules yet
(they'll be skipped/collected as errors until those modules exist,
which is expected):

```bash
pytest tests/unit/ --collect-only
```

This should show all test files and test names being discovered without
import errors in the test infrastructure itself (conftest, fixtures).

---

### Step 6 — Run the health check

```bash
python tests/health/check.py
```

This will fail on checks that aren't set up yet (imports, config.yaml, etc.)
That is expected. Report which checks pass and which fail right now so we
know the current baseline.

---

### Step 7 — Confirm and report

Tell me:
1. That `daedalus_master_plan.md` now contains PART 13 at the end
2. The full list of test files created
3. Which health checks currently pass vs fail
4. Any import errors found during `--collect-only`

Do NOT start implementing any Daedalus modules yet. This step is
infrastructure only — getting the test scaffolding in place so every
subsequent implementation step can be verified immediately.

---

## Naming reminder

- Project root: `d:\Dev\Daedalus\`
- Never reference `testKimiClaw`
- Do not modify `pipeline.py`, `agents.py`, or `models.py`
