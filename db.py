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

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT '',
            status TEXT DEFAULT 'new',       -- new, processing, processed, archived
            key_points TEXT,                 -- JSON array, filled by summarizer
            summary TEXT,                    -- filled by summarizer
            tags TEXT DEFAULT '',            -- comma-separated
            created_at TEXT NOT NULL,
            processed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(status);
        CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at);

        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Thread',
            status TEXT DEFAULT 'active',  -- active, archived
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS thread_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL REFERENCES threads(id),
            role TEXT NOT NULL,           -- 'user' or 'assistant'
            content_full TEXT NOT NULL,   -- raw complete content
            content_compressed TEXT,      -- summarized version, NULL until compressed
            metadata TEXT DEFAULT '{}',   -- JSON: tool_calls, files_modified, etc.
            token_estimate INTEGER DEFAULT 0,
            is_compressed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_thread_messages_thread ON thread_messages(thread_id);
        CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status);
        CREATE INDEX IF NOT EXISTS idx_threads_updated ON threads(updated_at);
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

# -- Notes --

def insert_note(title: str, content: str, category: str = "", tags: str = "") -> int:
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO notes (title, content, category, tags, status, created_at) VALUES (?, ?, ?, ?, 'new', ?)",
        (title, content, category, tags, now)
    )
    conn.commit()
    note_id = cur.lastrowid
    conn.close()
    return note_id

def update_note_status(note_id: int, status: str, summary: str = None, key_points: str = None):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    if summary is not None and key_points is not None:
        conn.execute(
            "UPDATE notes SET status=?, summary=?, key_points=?, processed_at=? WHERE id=?",
            (status, summary, key_points, now, note_id)
        )
    else:
        conn.execute("UPDATE notes SET status=? WHERE id=?", (status, note_id))
    conn.commit()
    conn.close()

def get_notes(status: str = None, limit: int = 50) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM notes WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_note(note_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_new_notes() -> list[dict]:
    """Get notes with status 'new' that haven't been processed yet."""
    return get_notes(status="new")

# -- Threads --

def create_thread(thread_id: str, title: str = "New Thread") -> str:
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO threads (id, title, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
        (thread_id, title, now, now)
    )
    conn.commit()
    conn.close()
    return thread_id

def get_threads(status: str = None, limit: int = 50) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM threads WHERE status=? ORDER BY updated_at DESC LIMIT ?", (status, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM threads ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_thread(thread_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_thread(thread_id: str, **kwargs):
    conn = get_conn()
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [thread_id]
    conn.execute(f"UPDATE threads SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()

def insert_thread_message(thread_id: str, role: str, content: str, metadata: dict = None) -> int:
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata or {})
    token_est = len(content) // 4
    cur = conn.execute(
        "INSERT INTO thread_messages (thread_id, role, content_full, metadata, token_estimate, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (thread_id, role, content, meta_json, token_est, now)
    )
    # Update thread's updated_at
    conn.execute("UPDATE threads SET updated_at=? WHERE id=?", (now, thread_id))
    conn.commit()
    msg_id = cur.lastrowid
    conn.close()
    return msg_id

def get_thread_messages(thread_id: str, limit: int = 200) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM thread_messages WHERE thread_id=? ORDER BY id ASC LIMIT ?", (thread_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_thread_context_size(thread_id: str) -> int:
    """Get total token estimate for a thread."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(token_estimate), 0) as total FROM thread_messages WHERE thread_id=?", (thread_id,)
    ).fetchone()
    conn.close()
    return row[0]

def compress_thread_message(msg_id: int, compressed: str):
    conn = get_conn()
    conn.execute(
        "UPDATE thread_messages SET content_compressed=?, is_compressed=1 WHERE id=?",
        (compressed, msg_id)
    )
    conn.commit()
    conn.close()

def get_uncompressed_messages(thread_id: str, limit: int = 50) -> list[dict]:
    """Get oldest uncompressed messages for a thread (candidates for compression)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM thread_messages WHERE thread_id=? AND is_compressed=0 ORDER BY id ASC LIMIT ?",
        (thread_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_full_message(msg_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM thread_messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# -- Stats --

def get_stats() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='completed'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='failed'").fetchone()[0]
    running = conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='running'").fetchone()[0]
    conn.close()
    return {"total": total, "completed": completed, "failed": failed, "running": running}
