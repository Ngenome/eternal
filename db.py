"""SQLite database for Eternal — tracks all agent runs, tasks, and events."""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "eternal.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT UNIQUE,
            agent_type TEXT NOT NULL,       -- 'orchestrator', 'task', 'eternal'
            agent_name TEXT NOT NULL,
            task_id TEXT,
            status TEXT DEFAULT 'running',  -- running, completed, failed, timeout
            exit_code INTEGER,
            summary TEXT,
            prompt_preview TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            output_path TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            agent_name TEXT,
            task_id TEXT,
            summary TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS eternal_agents (
            name TEXT PRIMARY KEY,
            status TEXT DEFAULT 'idle',     -- idle, running, sleeping
            current_run_id TEXT,
            last_cycle_end TEXT,
            sleep_until TEXT,
            sleep_reason TEXT,
            memory_size_bytes INTEGER,
            latest_discovery TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_runs(status);
        CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_type, agent_name);
        CREATE INDEX IF NOT EXISTS idx_runs_started ON agent_runs(started_at);
        CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
    """)
    conn.commit()
    conn.close()

# -- Agent runs --

def insert_run(run_id: str, agent_type: str, agent_name: str, task_id: str = None, prompt_preview: str = "") -> int:
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO agent_runs (run_id, agent_type, agent_name, task_id, status, started_at, prompt_preview) VALUES (?, ?, ?, ?, 'running', ?, ?)",
        (run_id, agent_type, agent_name, task_id, now, prompt_preview[:500])
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id

def finish_run(run_id: str, status: str, exit_code: int, summary: str = "", output_path: str = ""):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE agent_runs SET status=?, exit_code=?, summary=?, finished_at=?, output_path=? WHERE run_id=?",
        (status, exit_code, summary, now, output_path, run_id)
    )
    conn.commit()
    conn.close()

def get_recent_runs(limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_running_agents() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_runs WHERE status='running' ORDER BY started_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -- Events --

def insert_event(event_type: str, summary: str, agent_name: str = "", task_id: str = "", details: str = ""):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO events (event_type, agent_name, task_id, summary, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (event_type, agent_name, task_id, summary, details, now)
    )
    conn.commit()
    conn.close()

def get_recent_events(limit: int = 100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -- Eternal agents --

def upsert_eternal_agent(name: str, **kwargs):
    conn = get_conn()
    # Check if exists
    row = conn.execute("SELECT name FROM eternal_agents WHERE name=?", (name,)).fetchone()
    if row:
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [name]
        conn.execute(f"UPDATE eternal_agents SET {sets} WHERE name=?", vals)
    else:
        kwargs["name"] = name
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" for _ in kwargs)
        conn.execute(f"INSERT INTO eternal_agents ({cols}) VALUES ({placeholders})", list(kwargs.values()))
    conn.commit()
    conn.close()

def get_eternal_agents() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM eternal_agents ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -- Stats --

def get_stats() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='completed'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='failed'").fetchone()[0]
    running = conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='running'").fetchone()[0]
    conn.close()
    return {"total": total, "completed": completed, "failed": failed, "running": running}
