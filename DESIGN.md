# Eternal — Agent Orchestration System

## Overview

Eternal is a file-based agent orchestration system built on top of Claude Code CLI (`claude -p`). A Python daemon manages the lifecycle of three types of agents — an orchestrator, task agents, and eternal agents — all communicating through the filesystem.

No GUI (yet). No database (files are the database). No MCP servers (yet). Terminal-first.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        DAEMON (Python)                       │
│                                                               │
│  Manages three agent types:                                   │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │ Orchestrator │  │ Task Agents  │  │ Eternal Agents    │    │
│  │ (interval +  │  │ (on-demand,  │  │ (loop forever,   │    │
│  │  event wake) │  │  from queue) │  │  self-paced)     │    │
│  └─────────────┘  └──────────────┘  └──────────────────┘    │
│         │                │                    │               │
│         │ writes tasks   │ writes results     │ writes memory │
│         ▼                ▼                    ▼               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              FILESYSTEM (the shared state)            │    │
│  │  tasks/pending/  output/  state/  agents/eternal/    │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Agent Types

| Type | Lifecycle | Purpose | Examples |
|---|---|---|---|
| **Orchestrator** | Wakes on interval + events, makes decisions, exits | Coordination, task creation, oversight | Singleton |
| **Task agents** | Spawn, execute one task, write result, exit | Discrete work items | News fetcher, organizer, summarizer |
| **Eternal agents** | Run in a loop forever, sleep between cycles | Continuous research, monitoring | Tech scout, algorithm researcher |

---

## Component 1: The Daemon (`daemon.py`)

### Responsibilities

- Watch `tasks/pending/` for new task YAML files (using `watchdog` or `inotifywait`)
- Spawn `claude -p` sub-agents for each new task
- Track running processes: `{task_id: {pid, started_at, agent_template}}`
- When a PID exits:
  - Read the result file's YAML frontmatter for `status`
  - Move task from `running/` to `completed/` or `failed/`
  - Update `state/running.json`
  - If `wake_on_complete: true` OR status is `error/failed` -> queue orchestrator wake
- Run orchestrator on a configurable interval (e.g. every 30 min)
- Ensure only ONE orchestrator runs at a time (mutex lock via `orchestrator.lock`)
- Before waking orchestrator, generate `state/prompt.md` (cheap summary of current state)
- Manage a wake queue — reasons to wake the orchestrator, bundled into the next prompt
- Manage eternal agent sleep/wake cycles
- Watch for interrupt files written to eternal agent directories

### Edge Cases

| Scenario | Resolution |
|---|---|
| Orchestrator is running when a wake is needed | Queue it. Deliver after current run exits. |
| Multiple wakes queue up | Batch them into one orchestrator prompt. |
| Sub-agent hangs | Configurable timeout per task. Daemon kills PID after timeout, marks as `failed`, reason: `timeout`. |
| Daemon itself crashes | On startup, scan `tasks/running/` — any task there with no live PID is marked `failed: daemon_restart`. |
| Max concurrent sub-agents exceeded | Configurable in `config.yaml`. Default: 3. Tasks stay in `pending/` until a slot opens. |
| Orchestrator writes invalid YAML | Daemon validates schema before accepting. Invalid files moved to `tasks/failed/` with reason. |

### Startup Sequence

1. Load `config.yaml`
2. Create all directories if missing
3. Scan `tasks/running/` — check each PID:
   - PID alive -> continue tracking
   - PID dead -> mark as `failed: daemon_restart`, move to `failed/`
4. Load `state/running.json`
5. Start file watcher on `tasks/pending/`
6. Start orchestrator timer
7. Start eternal agent loops
8. Run initial orchestrator wake (so it can assess state)

### Graceful Shutdown (SIGTERM/SIGINT)

1. Stop accepting new tasks
2. Wait for running sub-agents (with timeout)
3. Write current state to `state/running.json`
4. Any still-running agents: note in running.json for next startup

### Wake Queue

The daemon maintains an in-memory list:

```python
wake_queue: list[WakeEvent] = []

@dataclass
class WakeEvent:
    type: str          # TASK_COMPLETED, TASK_FAILED, SCHEDULED, BUDGET_WARNING
    task_id: str | None
    summary: str
    timestamp: datetime
```

When it's time to wake the orchestrator:
1. Check `orchestrator.lock` — if orchestrator is running, keep queuing
2. Build `state/prompt.md` from: wake_queue + running.json + recent history + eternal agent status
3. Clear the queue
4. Spawn orchestrator
5. Write PID to `orchestrator.lock`
6. On orchestrator exit, remove lock, check if new wakes queued during run

---

## Component 2: The Orchestrator

### Invocation

```bash
claude -p \
  --system-prompt "$(cat agents/orchestrator.md)" \
  --allowedTools "Read,Write,Edit,Glob,Grep" \
  "$(cat state/orchestrator_memory.md)

---

$(cat state/prompt.md)"
```

The orchestrator's persistent memory comes first in the prompt. The ephemeral status (built by daemon) comes after the separator.

### What the Orchestrator Reads

- `state/orchestrator_memory.md` — its own persistent memory (loaded into prompt automatically)
- `state/prompt.md` — pre-built by daemon, contains current status (see format below)
- `state/todo.yaml` — persistent task queue (if it needs to check full list)
- Specific output files — only if it needs to make decisions about content

### What the Orchestrator Writes

- `tasks/pending/*.yaml` — new tasks to spawn
- `state/todo.yaml` — updated priorities
- `state/orchestrator_memory.md` — anything it wants to remember across runs
- `agents/eternal/{name}/interrupt.md` — to wake an eternal agent early
- `logs/orchestrator_log.md` — appends a one-line summary of what it did

### What the Orchestrator Does NOT Do

- Call Bash to spawn agents directly (daemon handles all spawning)
- Make network requests (sub-agents do that)
- Read every output file (reads pre-built summaries instead)
- Know about dollar budgets (only time budgets)

### System Prompt Requirements (`agents/orchestrator.md`)

The system prompt must instruct the orchestrator to:

1. Read the status information provided in the prompt
2. Make decisions about what tasks to create
3. Monitor eternal agents and interrupt them if needed
4. Before exiting, ALWAYS:
   - Check `tasks/pending/` to confirm new tasks were written correctly
   - Check if anything new appeared while it was working
   - Write a one-line summary to `logs/orchestrator_log.md`
5. Use `state/orchestrator_memory.md` for long-term memory:
   - Append or edit anything it wants to remember
   - Keep it compact and reorganize when it grows
   - This file is loaded into every session automatically

### `state/prompt.md` Format (built by daemon)

```markdown
## Current Time
2026-03-10T14:30:00

## Wake Reason
- SCHEDULED: Regular 30-minute interval check
- TASK_COMPLETED: fetch-techcrunch-20260310 — "Fetched 12 articles, 3 funding rounds"
- TASK_FAILED: fetch-hackernews-20260310 — "Timeout after 5 minutes"

## Currently Running Task Agents (2)
- organize-news-20260310 | started 3 min ago | timeout: 10 min
- fetch-theverge-20260310 | started 1 min ago | timeout: 10 min

## Recently Completed (last 2 hours)
- fetch-techcrunch-20260310 | completed 2 min ago | "12 articles fetched"
- summarize-morning-20260310 | completed 45 min ago | "Morning digest created"

## Eternal Agents (2 active)

### tech-scout
- Status: SLEEPING (wakes in 45 min)
- Last cycle: 12 min ago
- Latest discovery: "New paper on transformer efficiency from Google"
- Memory size: 2.4KB

### algo-researcher
- Status: RUNNING (cycle started 8 min ago)
- Last discovery: "Found that radix sort outperforms quicksort for our data distribution"
- Memory size: 5.1KB

## Pending Tasks (0)
(none)
```

---

## Component 3: Task Agents

### Invocation (by daemon)

```bash
claude -p \
  --system-prompt "$(cat agents/templates/{agent_type}.md)" \
  --allowedTools "{allowed_tools}" \
  "$(cat tasks/running/{task_id}.prompt.md)"
```

### Task YAML Schema (written by orchestrator to `tasks/pending/`)

```yaml
id: fetch-techcrunch-20260310-1400       # Unique ID
type: news-fetch                          # Descriptive type
agent: news-fetcher                       # Maps to template in agents/templates/
priority: normal                          # low | normal | high | critical
wake_on_complete: false                   # Wake orchestrator when done?
timeout_minutes: 10                       # Daemon kills after this
prompt: |                                 # What the agent should do
  Fetch today's articles from TechCrunch.
  Focus on startups, funding rounds, product launches.
output_path: output/news/2026-03-10/techcrunch.md
allowed_tools: "Read,Write,Glob,Grep,WebFetch,WebSearch"
depends_on: []                            # Task IDs that must complete first
```

### Daemon Enrichment (appended when task moves to `running/`)

```yaml
pid: 12345
started_at: 2026-03-10T14:00:03
```

### Daemon Enrichment (appended when task completes)

```yaml
finished_at: 2026-03-10T14:02:30
exit_code: 0
result_summary: "Fetched 12 articles..."   # Parsed from output frontmatter
```

### Task Prompt File (`tasks/running/{task_id}.prompt.md`)

Constructed by daemon from the task YAML:

```markdown
## Task
{prompt from task YAML}

## Output Instructions
Write your results to: {output_path}

Use this YAML frontmatter format at the top of your output file:
---
task_id: {task_id}
status: completed|failed|error
summary: "One sentence summary of what you did"
error_message: "Only if status is failed/error"
---

Then write your full output below the frontmatter.
```

### Agent Templates (`agents/templates/*.md`)

Each template defines:
- The agent's role and purpose
- What tools it needs (maps to `--allowedTools`)
- Output format expectations
- Quality standards

### Dependency Resolution

Tasks can have `depends_on: [task-id-1, task-id-2]`. The daemon:
- Keeps dependent tasks in `pending/` until dependencies resolve
- Checks before spawning: are all `depends_on` tasks in `completed/`?
- If a dependency fails -> mark dependent task as `failed: dependency_failed`

Example chain:
1. `fetch-techcrunch` (no deps)
2. `fetch-hackernews` (no deps)
3. `organize-news` (depends_on: fetch-techcrunch, fetch-hackernews)

---

## Component 4: Eternal Agents

### Lifecycle

```
┌──────────────────────────────────────────────────────────┐
│                    ETERNAL AGENT LOOP                      │
│                                                            │
│  1. Load memory file (agents/eternal/{name}/memory.md)     │
│     — this is its ENTIRE life, everything it knows         │
│                                                            │
│  2. Load any pending interrupt (interrupt.md)              │
│     — prepended to prompt if present                       │
│                                                            │
│  3. Run claude -p with:                                    │
│     - System prompt (template.md)                          │
│     - Memory file as context                               │
│     - "Continue your research from where you left off"     │
│     - Interrupt message if any                             │
│                                                            │
│  4. Agent does work, makes discoveries                     │
│     - Writes findings to output/{name}/                    │
│     - Can write to tasks/pending/ to spawn task agents     │
│                                                            │
│  5. Before exiting, agent MUST write:                      │
│     a. agents/eternal/{name}/memory.md (COMPACTED)         │
│        Replaces old memory entirely.                       │
│        ANYTHING NOT HERE IS GONE FOREVER.                  │
│     b. agents/eternal/{name}/discoveries.md (append)       │
│        One-line summaries for the orchestrator to scan.    │
│     c. agents/eternal/{name}/sleep.yaml                    │
│        { sleep_minutes: N, reason: "..." }                 │
│                                                            │
│  6. Process exits                                          │
│                                                            │
│  7. Daemon reads sleep.yaml                                │
│     - Waits N minutes (or until interrupted)               │
│     - Restarts at step 1                                   │
│                                                            │
│  INTERRUPT: Daemon can wake early if:                      │
│     - Someone writes to interrupt.md                       │
│     - A configured trigger file changes                    │
└──────────────────────────────────────────────────────────┘
```

### The Memory File is Sacred

The system prompt for every eternal agent includes:

```
You are a long-running research agent. You operate in cycles — each cycle
you wake up, do work, then sleep.

YOUR MEMORY FILE IS YOUR ENTIRE LIFE. When you write your updated memory
before sleeping, anything you omit is lost permanently. There is no other
record. No backup. No recovery.

Before sleeping:
1. Write your updated memory.md — compact but NEVER discard important
   discoveries, insights, leads, or context. Compress ruthlessly but
   lose nothing of value.
2. Append a one-line discovery summary to discoveries.md
3. Write sleep.yaml with how long you want to sleep and why
```

### Eternal Agent File Structure

```
agents/eternal/{name}/
├── config.yaml        # Agent definition & settings
├── template.md        # System prompt
├── memory.md          # THE memory — compacted each cycle
├── discoveries.md     # Append-only one-liners
├── sleep.yaml         # How long to sleep (set by agent)
└── interrupt.md       # Write here to wake it early
```

### Eternal Agent Config

```yaml
name: tech-scout
description: "Researches tech news, startup ecosystem, emerging trends"
template: agents/eternal/tech-scout/template.md
default_sleep_minutes: 60
max_sleep_minutes: 360          # Don't let it sleep more than 6 hours
min_sleep_minutes: 5            # Don't let it spin too fast
timeout_minutes: 30             # Max time per cycle
allowed_tools: "Read,Write,Edit,Glob,Grep,WebFetch,WebSearch"

# What can interrupt this agent's sleep early
interrupt_on:
  - file: "agents/eternal/tech-scout/interrupt.md"
  - file: "output/news/*/breaking.md"
```

### Interrupt Mechanism

When the daemon detects a write to `interrupt.md`:

```markdown
from: orchestrator
reason: "New dataset arrived in output/data/ — re-evaluate your recommendations"
priority: high
```

Daemon behavior:
1. Agent is SLEEPING -> cancel sleep timer, restart cycle immediately with interrupt prepended to prompt
2. Agent is RUNNING -> cannot interrupt mid-run, queue it for the next cycle
3. Clear `interrupt.md` after delivering it

### Eternal Agent Invocation

```bash
claude -p \
  --system-prompt "$(cat agents/eternal/{name}/template.md)" \
  --allowedTools "{allowed_tools}" \
  "## Your Memory (everything you know)

$(cat agents/eternal/{name}/memory.md)

---

## Interrupt Message (if any)
$(cat agents/eternal/{name}/interrupt.md 2>/dev/null || echo 'None')

---

Continue your research from where you left off."
```

---

## Component 5: Configuration (`config.yaml`)

```yaml
orchestrator:
  interval_minutes: 30
  system_prompt: agents/orchestrator.md
  allowed_tools: "Read,Write,Edit,Glob,Grep"
  timeout_minutes: 15

agents:
  max_concurrent: 3
  default_timeout_minutes: 10

claude:
  permission_mode: "default"
  model: "sonnet"               # Cost-effective for sub-agents
  orchestrator_model: "sonnet"  # Can use a different model for orchestrator

paths:
  tasks_dir: tasks
  output_dir: output
  state_dir: state
  logs_dir: logs
  agents_dir: agents

wake_on:
  task_failed: true             # Always wake orchestrator on failure
  task_completed: false         # Only if task explicitly says so
```

Note: Dollar budgets are NOT exposed to any agent. The daemon can enforce spending limits internally via `--max-budget-usd` on each `claude -p` call, but agents only see time budgets (timeout_minutes).

---

## Component 6: File Structure (Complete)

```
eternal/
├── daemon.py                          # Process manager
├── config.yaml                        # All configuration
├── DESIGN.md                          # This file
│
├── agents/
│   ├── orchestrator.md                # Orchestrator system prompt
│   ├── templates/                     # Task agent templates
│   │   ├── news-fetcher.md
│   │   ├── organizer.md
│   │   └── summarizer.md
│   └── eternal/                       # Eternal agents
│       ├── tech-scout/
│       │   ├── config.yaml
│       │   ├── template.md
│       │   ├── memory.md
│       │   ├── discoveries.md
│       │   ├── sleep.yaml
│       │   └── interrupt.md
│       └── algo-researcher/
│           └── ...
│
├── tasks/
│   ├── pending/                       # Orchestrator writes here
│   │   └── {task_id}.yaml
│   ├── running/                       # Daemon moves here + adds PID
│   │   ├── {task_id}.yaml
│   │   └── {task_id}.prompt.md
│   ├── completed/                     # Done tasks + result summary
│   │   └── {task_id}.yaml
│   └── failed/                        # Failed tasks + error info
│       └── {task_id}.yaml
│
├── output/                            # Where agents write results
│   ├── news/
│   │   └── 2026-03-10/
│   │       ├── techcrunch.md
│   │       └── organized/
│   └── {eternal_agent_name}/
│       └── ...
│
├── state/
│   ├── prompt.md                      # Built by daemon each orchestrator run
│   ├── orchestrator_memory.md         # Orchestrator's persistent memory
│   ├── running.json                   # {task_id: {pid, started, type}}
│   ├── todo.yaml                      # Persistent task queue
│   └── orchestrator.lock              # PID file for mutex
│
└── logs/
    ├── orchestrator_log.md            # Orchestrator appends one-liners
    ├── history.jsonl                  # Every agent run (daemon appends)
    └── errors.log                     # Daemon errors
```

---

## Communication Flow

```
Orchestrator (claude -p)          Daemon (Python)           Sub-agents (claude -p)
       │                              │                           │
       │ writes task.yaml             │                           │
       │ to tasks/pending/            │                           │
       │─────────────────────────────>│                           │
       │                              │ inotify detects new file  │
       │                              │ validates YAML schema     │
       │                              │ checks depends_on         │
       │                              │ moves to tasks/running/   │
       │                              │ builds prompt.md for task │
       │                              │ spawns claude -p ─────────>│
       │                              │                           │ does work
       │                              │                           │ writes result
       │                              │                           │ exits
       │                              │<──── PID exited ──────────│
       │                              │ reads result frontmatter  │
       │                              │ moves to tasks/completed/ │
       │                              │ updates running.json      │
       │                              │ appends to history.jsonl  │
       │                              │                           │
       │  (if wake_on_complete:true   │                           │
       │   or task failed)            │                           │
       │<─── daemon builds prompt.md  │                           │
       │     and spawns orchestrator  │                           │
       │                              │                           │
       │  reads orchestrator_memory   │                           │
       │  reads prompt.md             │                           │
       │  decides next steps          │                           │
       │  writes new tasks / memory   │                           │
       │  exits                       │                           │
       └──────────────────────────────┘
```

---

## Build Order

1. `daemon.py` — core loop, task agent spawning, file watching
2. `config.yaml` — with sensible defaults
3. Eternal agent loop — sleep/wake/memory cycle in daemon
4. `agents/orchestrator.md` — system prompt
5. First eternal agent: `tech-scout` — news/tech research
6. First task template: `news-fetcher` — on-demand fetching
7. Smoke test end-to-end

---

## Future (Not in Scope Now)

- GUI / web dashboard for monitoring
- MCP server integration for richer tool access
- SQLite for structured history queries
- Remote deployment
- Multi-machine coordination
