# Eternal

An autonomous agent orchestration system built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI (`claude -p`). A Python daemon manages three types of AI agents that communicate through the filesystem and build a continuously-updating knowledge base.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   DAEMON (Python)                    │
│                                                      │
│  ┌─────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │ Orchestrator │  │ Task Agents│  │Eternal Agents│ │
│  │ (interval +  │  │ (on-demand │  │(loop forever │ │
│  │  event wake) │  │  one-shot) │  │ self-paced)  │ │
│  └─────────────┘  └────────────┘  └──────────────┘ │
│         │               │                │          │
│         ▼               ▼                ▼          │
│  ┌──────────────────────────────────────────────┐   │
│  │          FILESYSTEM + SQLite                  │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Agent Types

| Type | Lifecycle | Purpose |
|---|---|---|
| **Orchestrator** | Wakes on timer + events, decides, exits | Coordination, task creation, oversight, self-evaluation |
| **Task Agents** | Spawn, execute, write result, exit | One-shot jobs: fetch news, organize, summarize, or ad-hoc |
| **Eternal Agents** | Loop forever, LIFETIME.md persists | Continuous research — each maintains a lifetime record |

## Key Concepts

- **`soul.md`** — The orchestrator's character, values, and personality. Not task-specific.
- **`mission.md`** — Current objectives. What the system is doing right now.
- **`LIFETIME.md`** — Each eternal agent's entire persistent existence. When a cycle ends, anything not written here is gone forever.
- **Ad-hoc agents** — The orchestrator can spawn custom agents with inline system prompts, no template needed.
- **File-based communication** — Agents create tasks by writing YAML files. The daemon handles execution.

## Eternal Agents

- **tech-scout** — Monitors the broad technology landscape: startups, funding, products, trends
- **ai-researcher** — Deep-dives into AI/ML: papers, models, benchmarks, tools, open-source
- **ai-business** — Tracks AI business: deals, valuations, market dynamics, competitive landscape

## Setup

Requires [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) and Python 3.12+.

```bash
# Clone
git clone https://github.com/Ngenome/eternal.git
cd eternal

# Install dependencies
uv sync

# Run
uv run python daemon.py
```

Dashboard at `http://localhost:7777`.

## Running as a Service

```bash
# With auto-restart wrapper
./start.sh

# Or with systemd (edit paths in the service file first)
cp eternal.service ~/.config/systemd/user/
systemctl --user enable eternal
systemctl --user start eternal
```

## File Structure

```
eternal/
├── soul.md              # Orchestrator character & values
├── mission.md           # Current objectives
├── ARCHITECTURE.md      # System self-documentation
├── daemon.py            # Core daemon
├── db.py                # SQLite layer
├── web.py               # Dashboard (FastAPI)
├── config.yaml          # Configuration
├── agents/
│   ├── orchestrator.md  # Orchestrator system prompt
│   ├── templates/       # Task agent templates
│   └── eternal/         # Eternal agents (LIFETIME.md, template, config)
├── tasks/               # pending/ → running/ → completed/ or failed/
├── output/              # All agent output, organized by category & date
├── state/               # Orchestrator memory, evaluations, system state
└── logs/                # Orchestrator log, event history
```

## License

MIT
