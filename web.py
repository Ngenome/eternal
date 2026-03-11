"""Eternal Dashboard — FastAPI web server for monitoring the agent system."""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import db

BASE_DIR = Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Eternal Dashboard")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Reference to daemon instance (set by daemon.py at startup)
_daemon = None

def set_daemon(daemon):
    global _daemon
    _daemon = daemon

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text()

# ---------------------------------------------------------------------------
# API — Status & Monitoring
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    stats = db.get_stats()
    running = db.get_running_agents()
    eternal = db.get_eternal_agents()
    return {"stats": stats, "running": running, "eternal_agents": eternal}

@app.get("/api/runs")
def api_runs(limit: int = 50):
    return db.get_recent_runs(limit)

@app.get("/api/events")
def api_events(limit: int = 100):
    return db.get_recent_events(limit)

@app.get("/api/eternal/{name}")
def api_eternal_detail(name: str):
    agent_dir = BASE_DIR / "agents" / "eternal" / name
    result = {"name": name}
    for fname in ["LIFETIME.md", "discoveries.md", "sleep.yaml"]:
        fpath = agent_dir / fname
        result[fname.replace(".", "_")] = fpath.read_text() if fpath.exists() else ""
    return result

@app.get("/api/file")
def api_file(path: str):
    """Read any file relative to BASE_DIR."""
    fpath = (BASE_DIR / path).resolve()
    if not str(fpath).startswith(str(BASE_DIR)):
        return JSONResponse({"error": "path traversal"}, 403)
    if not fpath.exists():
        return JSONResponse({"error": "not found"}, 404)
    return {"path": path, "content": fpath.read_text()[:50000]}

# ---------------------------------------------------------------------------
# API — Notes
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    title: str
    content: str
    category: str = ""
    tags: str = ""

@app.post("/api/notes")
def api_create_note(note: NoteCreate):
    note_id = db.insert_note(note.title, note.content, note.category, note.tags)
    return {"id": note_id, "status": "created"}

@app.get("/api/notes")
def api_get_notes(status: str = None, limit: int = 50):
    return db.get_notes(status=status, limit=limit)

@app.get("/api/notes/{note_id}")
def api_get_note(note_id: int):
    note = db.get_note(note_id)
    if not note:
        return JSONResponse({"error": "not found"}, 404)
    return note

# ---------------------------------------------------------------------------
# API — Threads (Chat Sessions)
# ---------------------------------------------------------------------------

class ThreadCreate(BaseModel):
    title: str = "New Thread"

class MessageCreate(BaseModel):
    content: str

@app.post("/api/threads")
def api_create_thread(body: ThreadCreate = ThreadCreate()):
    thread_id = str(uuid.uuid4())[:8]
    db.create_thread(thread_id, body.title)
    return {"id": thread_id, "title": body.title, "status": "active"}

@app.get("/api/threads")
def api_get_threads(status: str = None, limit: int = 50):
    return db.get_threads(status=status, limit=limit)

@app.get("/api/threads/{thread_id}")
def api_get_thread(thread_id: str):
    thread = db.get_thread(thread_id)
    if not thread:
        return JSONResponse({"error": "not found"}, 404)
    return thread

@app.get("/api/threads/{thread_id}/messages")
def api_get_thread_messages(thread_id: str, limit: int = 200):
    thread = db.get_thread(thread_id)
    if not thread:
        return JSONResponse({"error": "not found"}, 404)
    return db.get_thread_messages(thread_id, limit)

@app.post("/api/threads/{thread_id}/messages")
def api_send_message(thread_id: str, body: MessageCreate, background_tasks: BackgroundTasks):
    thread = db.get_thread(thread_id)
    if not thread:
        return JSONResponse({"error": "not found"}, 404)

    # Store user message
    msg_id = db.insert_thread_message(thread_id, "user", body.content)

    # Auto-title on first message
    if thread["title"] == "New Thread":
        first_line = body.content.split('\n')[0].strip()
        title = first_line[:60] + ('...' if len(first_line) > 60 else '')
        db.update_thread(thread_id, title=title)

    # Spawn chat agent in background
    background_tasks.add_task(run_chat_agent, thread_id, body.content)

    return {"message_id": msg_id, "status": "sent"}

@app.get("/api/threads/{thread_id}/context-size")
def api_thread_context_size(thread_id: str):
    return {"token_estimate": db.get_thread_context_size(thread_id)}

# ---------------------------------------------------------------------------
# Chat agent runner (runs in background)
# ---------------------------------------------------------------------------

async def _run_chat_agent_async(thread_id: str, user_message: str):
    """Build context from thread history and spawn claude -p."""
    import yaml

    messages = db.get_thread_messages(thread_id)
    model = "sonnet"
    timeout = 10

    # Load config if daemon is available
    if _daemon:
        model = _daemon.config.get("claude", {}).get("model", "sonnet")
        timeout = _daemon.config.get("agents", {}).get("default_timeout_minutes", 10)

    # Build conversation context
    context_parts = []
    total_chars = 0
    CONTEXT_BUDGET = 120000  # ~30k tokens

    # Walk messages newest-first to prioritize recent context
    for msg in reversed(messages):
        # Use compressed version if available, otherwise full
        content = msg.get("content_compressed") or msg["content_full"]
        role_label = "USER" if msg["role"] == "user" else "ASSISTANT"

        entry = f"[{role_label} — msg #{msg['id']}]\n{content}\n"
        if total_chars + len(entry) > CONTEXT_BUDGET:
            context_parts.append(f"[... {len(messages) - len(context_parts)} older messages truncated — agent can query full history via message IDs ...]\n")
            break
        context_parts.append(entry)
        total_chars += len(entry)

    context_parts.reverse()
    conversation_history = "\n---\n".join(context_parts)

    # Build the prompt
    prompt = f"""## Conversation History

{conversation_history}

---

## New Message from User

{user_message}

---

Respond with valid JSON as specified in your system prompt. Remember: your action_summary is what persists across sessions — be thorough."""

    # System prompt
    template_path = BASE_DIR / "agents" / "templates" / "chat-session.md"
    if not template_path.exists():
        # Fallback if template missing
        db.insert_thread_message(thread_id, "assistant", json.dumps({
            "response": "Chat session template not found. Please ensure agents/templates/chat-session.md exists.",
            "action_summary": "No actions taken.",
            "tools_used": [],
            "files_modified": [],
            "needs_followup": False
        }))
        return

    # Remove CLAUDECODE env to allow nested sessions
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    cmd = [
        "claude", "-p",
        "--system-prompt", template_path.read_text(),
        "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash",
        "--model", model,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=timeout * 60,
        )

        output = stdout.decode() if stdout else ""

        # Try to parse as JSON, store raw if not
        try:
            parsed = json.loads(output)
            metadata = {
                "action_summary": parsed.get("action_summary", ""),
                "tools_used": parsed.get("tools_used", []),
                "files_modified": parsed.get("files_modified", []),
                "needs_followup": parsed.get("needs_followup", False),
                "exit_code": proc.returncode,
            }
        except json.JSONDecodeError:
            parsed = None
            metadata = {"raw_output": True, "exit_code": proc.returncode}

        # Store assistant message
        db.insert_thread_message(
            thread_id, "assistant",
            output if output else json.dumps({"response": "(no output)", "action_summary": "No actions taken.", "tools_used": [], "files_modified": [], "needs_followup": False}),
            metadata=metadata,
        )

        # Log to events
        summary = ""
        if parsed:
            summary = parsed.get("response", "")[:100]
        db.insert_event("CHAT_RESPONSE", f"Thread {thread_id}: {summary}", agent_name="chat-session")

    except asyncio.TimeoutError:
        db.insert_thread_message(
            thread_id, "assistant",
            json.dumps({
                "response": f"Request timed out after {timeout} minutes.",
                "action_summary": "Timed out.",
                "tools_used": [],
                "files_modified": [],
                "needs_followup": True
            }),
            metadata={"timeout": True},
        )
    except Exception as e:
        db.insert_thread_message(
            thread_id, "assistant",
            json.dumps({
                "response": f"Error running chat agent: {str(e)}",
                "action_summary": f"Error: {str(e)}",
                "tools_used": [],
                "files_modified": [],
                "needs_followup": False
            }),
            metadata={"error": str(e)},
        )


def run_chat_agent(thread_id: str, user_message: str):
    """Sync wrapper to run async chat agent from BackgroundTasks."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run_chat_agent_async(thread_id, user_message))
    finally:
        loop.close()
