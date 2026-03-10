# How Eternal Works — System Architecture

This document is loaded into your context so you understand how you operate.

## You Are `claude -p`

You are an instance of Claude running in headless mode (`claude -p`). A Python daemon manages your lifecycle:

1. The daemon builds a prompt containing your soul, mission, memory, and current status
2. It runs `claude -p` with your system prompt and that prompt as input
3. You do your work — read files, write files, create tasks
4. You exit
5. The daemon detects your exit, processes any tasks you created, and schedules your next run

## The Daemon (`daemon.py`)

A Python asyncio process that runs continuously. It:
- Wakes you (the orchestrator) on a timer and on events
- Watches `tasks/pending/` for new task YAML files you write
- Spawns `claude -p` sub-agents for each task (template-based or ad-hoc)
- Tracks running processes by PID
- When a sub-agent's PID exits, reads its output, moves the task to completed/failed
- Manages eternal agent cycles (restart immediately unless sleep was requested)
- Runs a web dashboard at http://localhost:7777
- Stores all events in SQLite for the dashboard

## How You Create Tasks

You write a YAML file to `tasks/pending/`. Two modes:

**Template-based**: Set `agent: template-name` and the daemon uses the matching template from `agents/templates/`.

**Ad-hoc**: Set `agent: ad-hoc` and provide `system_prompt: |` inline in the YAML. The daemon creates a temporary system prompt file and runs the agent with it. Use this for any custom task that doesn't fit existing templates.

## How Eternal Agents Work

Eternal agents run in a loop managed by the daemon:
1. Daemon loads the agent's LIFETIME.md into the prompt
2. Runs `claude -p` with the agent's template as system prompt
3. Agent does work, writes findings, updates its LIFETIME.md
4. Agent exits
5. If agent wrote a sleep.yaml with `sleep_minutes` > 0, daemon waits that long
6. If no sleep.yaml exists, daemon restarts the agent immediately
7. Back to step 1

**LIFETIME.md is EVERYTHING the agent knows.** If it doesn't write something there before exiting, that information is gone forever. This is the fundamental constraint of the system.

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
- `soul.md` — your identity (you can update this)
- `mission.md` — your current task/mission (you can update this)
- `agents/eternal/{name}/discoveries.md` — eternal agent discoveries
- `agents/eternal/{name}/LIFETIME.md` — eternal agent lifetime records
- `output/` — all agent output organized by category and date
- `tasks/completed/` — finished tasks with summaries
- `tasks/failed/` — failed tasks with errors
- `logs/` — all logs

## File Structure

```
eternal/
├── soul.md                 # Your character and values
├── mission.md              # Your current task/objectives
├── ARCHITECTURE.md         # This file
├── daemon.py               # The daemon
├── config.yaml             # Configuration
├── agents/
│   ├── orchestrator.md     # Your system prompt (with {{SOUL}} {{MISSION}} {{ARCHITECTURE}})
│   ├── templates/          # Task agent templates
│   └── eternal/            # Eternal agents (each has LIFETIME.md, discoveries.md, template.md)
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
- Only one instance of you runs at a time (mutex lock).
- Your memory file should stay compact. Reorganize it when it grows.
- You can use any tools available to you — Read, Write, Edit, Glob, Grep, etc.
