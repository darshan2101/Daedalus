# Daedalus Claude Project — Setup Guide

## Step 1: Project Instructions (paste into "Project Instructions" field)

Copy the FULL contents of `00_project_instructions.md` into the
**Project Instructions** box in your Daedalus Claude project settings.
This loads on every chat — keep it tight, no fluff.

---

## Step 2: Upload These 4 Files to Project Knowledge

Upload in this order (most critical first):

| File | Purpose |
|------|---------|
| `01_architecture.md` | Phases, state shapes, execution paths |
| `02_infra_models.md` | MongoDB, Redis, LLM chains, env vars |
| `03_config.md` | config.yaml reference, CLI flags |
| `04_decisions_issues.md` | Why decisions were made, known bugs |

**Upload as `.md` files, not HTML.** HTML burns ~2x more KB space.

---

## Step 3: Chat Naming Convention

Name each chat by the exact scope of work. Examples:
- `repair.py — sentinel score bug`
- `graph.py — resume node refactor`
- `evaluator — weight config integration`
- `sub_agent — retry backoff implementation`

One task per chat. When done: extract decisions into `04_decisions_issues.md` and re-upload.

---

## Step 4: Prompt Patterns to Use

**Bug fix:**
```
Bug: [paste error + traceback]
File: daedalus/repair.py
Fix only the affected function.
```

**Implementation:**
```
Add [X] to [file]. No explanation.
```

**Review:**
```
Review [function name] in [file]. Flag logic issues only. No style notes.
```

**Context dump before ending chat:**
```
Summarize: what we changed, decisions made, open issues.
Max 150 words. Bullet points.
```

---

## Step 5: Maintenance Rhythm

After every meaningful chat:
1. Paste the summary into `04_decisions_issues.md` under "Active Development Areas"
2. Re-upload the updated file to project knowledge (delete old, upload new)
3. Start a fresh chat for the next task

This keeps the KB as the persistent brain — not the chat history.

---

## File Token Budget Estimate

| File | Est. Tokens |
|------|------------|
| 00_project_instructions.md | ~600 |
| 01_architecture.md | ~700 |
| 02_infra_models.md | ~650 |
| 03_config.md | ~500 |
| 04_decisions_issues.md | ~800 |
| **Total KB load** | **~3,250** |

Leaves ~196,750 of 200,000 token KB budget for actual chat work.
