---
name: kanvas
description: Plan and track work on the project's Kanvas board (kanvas.json), which you share with a human who approves and reviews tasks. Use when the user mentions the board, Kanvas, tasks, planning, "what's next", or a task ID such as DV-03.
---

# Kanvas

The board is `kanvas.json` at the project root. Change it only through the CLI that sits next to this file; the CLI enforces the workflow and keeps the file valid:

```bash
python .agents/skills/kanvas/kanvas.py <command>
```

Use `python3` where `python` is missing. Never edit `kanvas.json` by hand. The human watches the board in a browser (`kanvas.py serve`), where your changes appear within a second.

## Workflow

```
proposed -> todo -> doing -> review -> done
```

| State | Moved there by | Meaning |
|-------|----------------|---------|
| proposed | you (`propose`, `batch`) | An idea waiting for human approval |
| todo | the human | Approved. Shown as **blocked** while a dependency is unfinished |
| doing | you (`start`) | In progress |
| review | you (`finish`, with a summary) | Waiting for the human to check it |
| done | the human | Accepted |

You may propose tasks and groups, start ready tasks, finish or pause tasks in progress, add notes and add dependencies. Approving proposals, marking tasks done, editing and deleting belong to the human; ask for them in the conversation.

### YOLO

The human can put a task under **YOLO** in the board. That covers the task and everything it depends on, directly or indirectly; the CLI marks covered tasks `(YOLO)`. For covered tasks:

- proposals count as approved, so `ready` lists them and `start` accepts them;
- `finish` moves the task straight to done, with your summary as a note, and the tasks waiting on it unblock.

Only the human can turn YOLO on or off. Linking extra work into a YOLO chain with `depend` puts it under YOLO too, so do that only for work the human clearly asked for.

## Session protocol

1. **Read the board:** `status`. Tell the user what waits for review, what is ready, what is blocked and what is proposed.
2. **Pick a task:** if the user named one, `show ID`. Otherwise `ready`; when several tasks are ready, ask which one to take.
3. **Start it:** `start ID -m "Plan: ..."`. Read the description and every note. A note starting with "Sent back:" is review feedback you must address.
4. **Work.** Record findings with `note ID "..."`. Propose any extra work you discover with `propose`, linking it with `--deps`.
5. **Finish:** `finish ID -m "..."` with what changed, where, and how you verified it. Tell the user the task is ready for review, then stop. Start the next task only when asked. Under YOLO the task is done instead of waiting for review, and you may go on with the next ready `(YOLO)` task without asking; stop when none is left and summarize what you did.

To stop halfway, run `pause ID -m "Where I left off and why"`.

## Planning

When asked to plan a project, interview the user briefly, then propose the whole plan in one batch:

```bash
python .agents/skills/kanvas/kanvas.py batch <<'EOF'
{
  "groups": ["Research", "Backend"],
  "tasks": [
    {"title": "Compare weather APIs", "group": "Research", "desc": "Free tier, hourly data, caching terms"},
    {"title": "Fetch forecasts", "group": "Backend", "deps": ["Compare weather APIs"]}
  ]
}
EOF
```

`deps` takes task IDs or the titles of earlier tasks in the same batch. A batch is all or nothing. Everything arrives as proposals; ask the human to approve them in the board.

Keep tasks small enough to finish in one session, give each a clear outcome in `desc`, and use groups for areas of work (Research, Backend, Docs). A group's ID prefix starts every task ID in it (`RS-01`).

## Commands

| Command | Purpose |
|---------|---------|
| `status` | Overview: doing, review, ready, blocked, proposed, problems |
| `ready` | Tasks you can start now |
| `show ID` | Details, dependencies, notes |
| `list [STATE or GROUP]` | Tasks by group; filter by state (`ready`, `blocked`, ...) or group |
| `blocked` | Blocked tasks and what they wait on |
| `start ID [-m NOTE]` | todo -> doing (also proposals under YOLO) |
| `finish ID -m SUMMARY` | doing -> review, or done under YOLO (the summary is required) |
| `pause ID [-m NOTE]` | doing -> todo |
| `note ID TEXT` | Append a note |
| `propose GROUP TITLE [DESC] [--deps ID ...]` | New proposal; use `-` as GROUP for none |
| `add-group NAME [--prefix XX]` | New group |
| `batch` | Many groups and proposals from JSON on stdin |
| `depend ID ON [ON ...]` | ID waits for the others (cycles are rejected) |
| `check` | Validate the board |

Notes record your name: pass `--as claude` or set `KANVAS_AGENT=claude`.

## Long or non-ASCII text

Commands that take text also accept `--stdin` and `--file PATH`, which read UTF-8 on every platform. Use a heredoc for multi-line summaries:

```bash
python .agents/skills/kanvas/kanvas.py finish DV-03 --stdin <<'EOF'
Added retries with exponential backoff (src/fetch.py).
- 3 attempts, then the cached forecast is served as stale
- 6 new tests; the suite passes
EOF
```

In PowerShell, write the text to a file and pass `--file summary.md`.

## When a command fails

The CLI exits with a non-zero code and an `Error:` line explaining the rule, for example "DV-04 is blocked by unfinished DV-02". Follow the message, or ask the human. Editing the file to get around a rule breaks the human's trust in the board.
