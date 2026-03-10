"""Eternal Dashboard — FastAPI web server for monitoring the agent system."""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import db

BASE_DIR = Path(__file__).parent.resolve()
app = FastAPI(title="Eternal Dashboard")

# ---------------------------------------------------------------------------
# API endpoints
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
    for fname in ["memory.md", "discoveries.md", "sleep.yaml"]:
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
# Dashboard HTML
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eternal Dashboard</title>
<style>
  :root {
    --bg: #0a0a0f; --surface: #12121a; --border: #1e1e2e;
    --text: #c8c8d8; --dim: #666680; --accent: #7c6cf0;
    --green: #4ade80; --red: #f87171; --yellow: #fbbf24; --blue: #60a5fa;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace; background: var(--bg); color: var(--text); padding: 20px; font-size: 13px; }
  h1 { color: var(--accent); font-size: 18px; margin-bottom: 4px; }
  .subtitle { color: var(--dim); font-size: 11px; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .card h3 { font-size: 11px; color: var(--dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .card .value { font-size: 28px; font-weight: bold; }
  .card .value.green { color: var(--green); }
  .card .value.red { color: var(--red); }
  .card .value.yellow { color: var(--yellow); }
  .card .value.blue { color: var(--blue); }
  .section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .section h2 { font-size: 13px; color: var(--accent); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; color: var(--dim); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; padding: 6px 8px; border-bottom: 1px solid var(--border); }
  td { padding: 8px; border-bottom: 1px solid var(--border); font-size: 12px; }
  tr:hover { background: rgba(124, 108, 240, 0.05); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase; }
  .badge.running { background: rgba(96, 165, 250, 0.2); color: var(--blue); }
  .badge.completed { background: rgba(74, 222, 128, 0.2); color: var(--green); }
  .badge.failed { background: rgba(248, 113, 113, 0.2); color: var(--red); }
  .badge.sleeping { background: rgba(251, 191, 36, 0.2); color: var(--yellow); }
  .badge.idle { background: rgba(102, 102, 128, 0.2); color: var(--dim); }
  .badge.timeout { background: rgba(248, 113, 113, 0.2); color: var(--red); }
  .eternal-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 8px; cursor: pointer; transition: border-color 0.2s; }
  .eternal-card:hover { border-color: var(--accent); }
  .eternal-card h3 { font-size: 14px; color: var(--text); margin-bottom: 4px; }
  .eternal-card .meta { color: var(--dim); font-size: 11px; line-height: 1.6; }
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 100; justify-content: center; align-items: center; }
  .modal-overlay.active { display: flex; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; max-width: 800px; width: 90%; max-height: 80vh; overflow-y: auto; }
  .modal h2 { color: var(--accent); margin-bottom: 16px; }
  .modal pre { background: var(--bg); padding: 12px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; font-size: 11px; line-height: 1.5; max-height: 400px; overflow-y: auto; }
  .modal .close { float: right; cursor: pointer; color: var(--dim); font-size: 18px; }
  .modal .close:hover { color: var(--text); }
  .refresh-indicator { position: fixed; top: 10px; right: 10px; color: var(--dim); font-size: 10px; }
  .pulse { animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
  .empty { color: var(--dim); font-style: italic; padding: 20px; text-align: center; }
</style>
</head>
<body>

<h1>ETERNAL</h1>
<p class="subtitle">Agent Orchestration System</p>

<div class="refresh-indicator"><span class="pulse">&#9679;</span> Live — refreshing every 5s</div>

<div class="grid" id="stats"></div>

<div class="section">
  <h2>Eternal Agents</h2>
  <div id="eternal-agents"></div>
</div>

<div class="section">
  <h2>Currently Running</h2>
  <div id="running"></div>
</div>

<div class="section">
  <h2>Recent Runs</h2>
  <div id="runs"></div>
</div>

<div class="section">
  <h2>Event Log</h2>
  <div id="events"></div>
</div>

<div class="modal-overlay" id="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <span class="close" onclick="closeModal()">&times;</span>
    <div id="modal-content"></div>
  </div>
</div>

<script>
function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function timeAgo(iso) {
  if (!iso) return '—';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return Math.floor(diff) + 's ago';
  if (diff < 3600) return Math.floor(diff/60) + 'm ago';
  if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
  return Math.floor(diff/86400) + 'd ago';
}

function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '...' : (s || '—'); }

async function fetchJSON(url) {
  const r = await fetch(url);
  return r.json();
}

async function refresh() {
  try {
    const [status, runs, events] = await Promise.all([
      fetchJSON('/api/status'),
      fetchJSON('/api/runs?limit=30'),
      fetchJSON('/api/events?limit=50'),
    ]);

    // Stats cards
    const s = status.stats;
    document.getElementById('stats').innerHTML = `
      <div class="card"><h3>Running</h3><div class="value blue">${s.running}</div></div>
      <div class="card"><h3>Completed</h3><div class="value green">${s.completed}</div></div>
      <div class="card"><h3>Failed</h3><div class="value red">${s.failed}</div></div>
      <div class="card"><h3>Total Runs</h3><div class="value">${s.total}</div></div>
    `;

    // Eternal agents
    const ea = status.eternal_agents;
    if (ea.length === 0) {
      document.getElementById('eternal-agents').innerHTML = '<div class="empty">No eternal agents configured</div>';
    } else {
      document.getElementById('eternal-agents').innerHTML = ea.map(a => `
        <div class="eternal-card" onclick="showEternal('${a.name}')">
          <h3>${a.name} ${badge(a.status || 'idle')}</h3>
          <div class="meta">
            ${a.sleep_until ? 'Wakes: ' + timeAgo(a.sleep_until).replace('ago','').trim() + ' from now' : ''}
            ${a.last_cycle_end ? '&nbsp;&middot;&nbsp; Last cycle: ' + timeAgo(a.last_cycle_end) : ''}
            ${a.memory_size_bytes ? '&nbsp;&middot;&nbsp; Memory: ' + (a.memory_size_bytes/1024).toFixed(1) + 'KB' : ''}
            ${a.latest_discovery ? '<br>Latest: ' + truncate(a.latest_discovery, 120) : ''}
          </div>
        </div>
      `).join('');
    }

    // Running agents
    const running = status.running;
    if (running.length === 0) {
      document.getElementById('running').innerHTML = '<div class="empty">No agents currently running</div>';
    } else {
      document.getElementById('running').innerHTML = `<table>
        <tr><th>Agent</th><th>Type</th><th>Task</th><th>Started</th></tr>
        ${running.map(r => `<tr>
          <td>${r.agent_name}</td><td>${r.agent_type}</td>
          <td>${r.task_id || '—'}</td><td>${timeAgo(r.started_at)}</td>
        </tr>`).join('')}
      </table>`;
    }

    // Recent runs
    if (runs.length === 0) {
      document.getElementById('runs').innerHTML = '<div class="empty">No runs yet</div>';
    } else {
      document.getElementById('runs').innerHTML = `<table>
        <tr><th>Agent</th><th>Type</th><th>Status</th><th>Summary</th><th>Started</th><th>Duration</th></tr>
        ${runs.map(r => {
          let dur = '—';
          if (r.started_at && r.finished_at) {
            const ms = new Date(r.finished_at) - new Date(r.started_at);
            dur = ms < 60000 ? Math.floor(ms/1000) + 's' : Math.floor(ms/60000) + 'm ' + Math.floor((ms%60000)/1000) + 's';
          }
          return `<tr onclick="showRun('${r.run_id}')" style="cursor:pointer">
            <td>${r.agent_name}</td><td>${r.agent_type}</td>
            <td>${badge(r.status)}</td><td>${truncate(r.summary, 80)}</td>
            <td>${timeAgo(r.started_at)}</td><td>${dur}</td>
          </tr>`;
        }).join('')}
      </table>`;
    }

    // Events
    if (events.length === 0) {
      document.getElementById('events').innerHTML = '<div class="empty">No events yet</div>';
    } else {
      document.getElementById('events').innerHTML = `<table>
        <tr><th>Time</th><th>Type</th><th>Agent</th><th>Summary</th></tr>
        ${events.map(e => `<tr>
          <td>${timeAgo(e.created_at)}</td><td>${e.event_type}</td>
          <td>${e.agent_name || '—'}</td><td>${truncate(e.summary, 100)}</td>
        </tr>`).join('')}
      </table>`;
    }
  } catch (e) {
    console.error('Refresh failed:', e);
  }
}

async function showEternal(name) {
  const data = await fetchJSON('/api/eternal/' + name);
  document.getElementById('modal-content').innerHTML = `
    <h2>${name}</h2>
    <h3 style="color:var(--dim);margin:12px 0 6px">Memory</h3>
    <pre>${data.memory_md || '(empty)'}</pre>
    <h3 style="color:var(--dim);margin:12px 0 6px">Discoveries</h3>
    <pre>${data.discoveries_md || '(none yet)'}</pre>
    <h3 style="color:var(--dim);margin:12px 0 6px">Sleep</h3>
    <pre>${data.sleep_yaml || '(no sleep data)'}</pre>
  `;
  document.getElementById('modal-overlay').classList.add('active');
}

async function showRun(runId) {
  // For now just show the run details from the runs list
  const runs = await fetchJSON('/api/runs?limit=100');
  const run = runs.find(r => r.run_id === runId);
  if (!run) return;
  document.getElementById('modal-content').innerHTML = `
    <h2>Run: ${run.agent_name}</h2>
    <table>
      <tr><td style="color:var(--dim)">Run ID</td><td>${run.run_id}</td></tr>
      <tr><td style="color:var(--dim)">Type</td><td>${run.agent_type}</td></tr>
      <tr><td style="color:var(--dim)">Status</td><td>${badge(run.status)}</td></tr>
      <tr><td style="color:var(--dim)">Exit Code</td><td>${run.exit_code ?? '—'}</td></tr>
      <tr><td style="color:var(--dim)">Started</td><td>${run.started_at}</td></tr>
      <tr><td style="color:var(--dim)">Finished</td><td>${run.finished_at || '—'}</td></tr>
      <tr><td style="color:var(--dim)">Summary</td><td>${run.summary || '—'}</td></tr>
      <tr><td style="color:var(--dim)">Output</td><td>${run.output_path || '—'}</td></tr>
    </table>
    ${run.prompt_preview ? '<h3 style="color:var(--dim);margin:12px 0 6px">Prompt Preview</h3><pre>' + run.prompt_preview + '</pre>' : ''}
  `;
  document.getElementById('modal-overlay').classList.add('active');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>""";
