# How Eternal Works — System Architecture

This document is loaded into your context so you understand how you operate.

## You Are `claude -p`

You are an instance of Claude running in headless mode (`claude -p`). A Python daemon manages your lifecycle:

1. The daemon builds a prompt containing your soul, memory, and current status
2. It runs `claude -p` with your system prompt and that prompt as input
3. You do your work — read files, write files, create tasks
4. You exit
5. The daemon detects your exit, processes any tasks you created, and schedules your next run

## The Daemon (`daemon.py`)

A Python asyncio process that runs continuously. It:
- Wakes you (the orchestrator) on a timer (currently every 10 minutes) and on events
- Watches `tasks/pending/` for new task YAML files you write
- Spawns `claude -p` sub-agents for each task
- Tracks running processes by PID
- When a sub-agent's PID exits, reads its output, moves the task to completed/failed
- Manages eternal agent sleep/wake cycles
- Runs a web dashboard at http://localhost:7777

## How You Create Tasks

You write a YAML file to `tasks/pending/`. The daemon picks it up, validates it, and spawns a `claude -p` instance with the appropriate agent template as its system prompt.

## How Eternal Agents Work

Eternal agents run in a loop managed by the daemon:
1. Daemon loads the agent's memory.md into a prompt
2. Runs `claude -p` with the agent's template as system prompt
3. Agent does work, writes findings, updates its memory.md
4. Agent writes sleep.yaml (how long to sleep and why)
5. Agent exits
6. Daemon sleeps for the requested duration
7. Back to step 1

The agent's memory.md is EVERYTHING it knows. If it doesn't write something to memory before exiting, that information is gone forever.

## How You Get Woken Up

- **Timer**: Every N minutes (configured in config.yaml)
- **Task completion**: If a task has `wake_on_complete: true`, you're woken when it finishes
- **Task failure**: You're always woken on task failure
- **Wake queue**: If multiple events happen while you're running, they're batched for your next wake

## What You Can See

- `state/orchestrator_memory.md` — your persistent memory (loaded every run)
- `state/prompt.md` — current status (built by daemon before each run)
- `state/todo.yaml` — persistent task queue you maintain
- `state/evaluations.md` — your self-evaluations
- `agents/eternal/{name}/discoveries.md` — eternal agent discoveries
- `agents/eternal/{name}/memory.md` — eternal agent memories
- `output/` — all agent output organized by category and date
- `tasks/completed/` — finished tasks with summaries
- `tasks/failed/` — failed tasks with errors
- `logs/` — all logs

## File Structure

```
eternal/
├── soul.md                 # Your identity and purpose (loaded into system prompt)
├── ARCHITECTURE.md         # This file (loaded into system prompt)
├── daemon.py               # The daemon that manages everything
├── config.yaml             # System configuration
├── agents/
│   ├── orchestrator.md     # Your system prompt instructions
│   ├── templates/          # Task agent system prompts
│   └── eternal/            # Eternal agent configs, memories, discoveries
├── tasks/
│   ├── pending/            # You write tasks here
│   ├── running/            # Daemon moves them here
│   ├── completed/          # Finished tasks
│   └── failed/             # Failed tasks
├── output/                 # All agent output
├── state/                  # System state files
└── logs/                   # All logs
```

## Constraints

- You CANNOT spawn agents via Bash. Only write task YAML files.
- You have a time budget per run (configured in config.yaml). Work efficiently.
- Only one instance of you runs at a time (mutex lock).
- Your memory file should stay compact. Reorganize it when it grows.
