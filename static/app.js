// ---------------------------------------------------------------------------
// Eternal Dashboard — app.js
// ---------------------------------------------------------------------------

// -- Utilities --

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function timeAgo(iso) {
  if (!iso) return '—';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return Math.floor(diff) + 's ago';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '...' : (s || '—'); }

async function fetchJSON(url) {
  const r = await fetch(url);
  return r.json();
}

// Simple markdown: code blocks, inline code, bold, italic, headers, lists
function renderMarkdown(text) {
  if (!text) return '';
  let html = text
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Headers
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    // Unordered lists
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    // Paragraphs (double newline)
    .replace(/\n\n/g, '</p><p>')
    // Single newlines within paragraphs
    .replace(/\n/g, '<br>');
  // Wrap loose <li> in <ul>
  html = html.replace(/(<li>.*?<\/li>)+/gs, '<ul>$&</ul>');
  return '<p>' + html + '</p>';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// -- Page navigation --

let currentPage = 'dashboard';

function showPage(page, btn) {
  currentPage = page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const threadSidebar = document.getElementById('thread-sidebar');
  if (page === 'chat') {
    threadSidebar.style.display = 'flex';
    refreshThreadList();
  } else {
    threadSidebar.style.display = 'none';
  }
}

// -- Modal --

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ============================================================================
// DASHBOARD
// ============================================================================

async function refreshDashboard() {
  if (currentPage !== 'dashboard') return;
  try {
    const [status, runs, events] = await Promise.all([
      fetchJSON('/api/status'),
      fetchJSON('/api/runs?limit=30'),
      fetchJSON('/api/events?limit=50'),
    ]);

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
            ${a.sleep_until ? 'Wakes: ' + timeAgo(a.sleep_until).replace('ago', '').trim() + ' from now' : ''}
            ${a.last_cycle_end ? '&middot; Last cycle: ' + timeAgo(a.last_cycle_end) : ''}
            ${a.memory_size_bytes ? '&middot; Memory: ' + (a.memory_size_bytes / 1024).toFixed(1) + 'KB' : ''}
            ${a.latest_discovery ? '<br>Latest: ' + truncate(a.latest_discovery, 120) : ''}
          </div>
        </div>
      `).join('');
    }

    // Running
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
            dur = ms < 60000 ? Math.floor(ms / 1000) + 's' : Math.floor(ms / 60000) + 'm ' + Math.floor((ms % 60000) / 1000) + 's';
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
    console.error('Dashboard refresh failed:', e);
  }
}

async function showEternal(name) {
  const data = await fetchJSON('/api/eternal/' + name);
  document.getElementById('modal-content').innerHTML = `
    <h2>${name}</h2>
    <h3 style="color:var(--dim);margin:12px 0 6px">LIFETIME Record</h3>
    <pre>${data.LIFETIME_md || '(empty)'}</pre>
    <h3 style="color:var(--dim);margin:12px 0 6px">Discoveries</h3>
    <pre>${data.discoveries_md || '(none yet)'}</pre>
    <h3 style="color:var(--dim);margin:12px 0 6px">Sleep</h3>
    <pre>${data.sleep_yaml || '(no sleep data)'}</pre>
  `;
  document.getElementById('modal-overlay').classList.add('active');
}

async function showRun(runId) {
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
    ${run.prompt_preview ? '<h3 style="color:var(--dim);margin:12px 0 6px">Prompt Preview</h3><pre>' + escapeHtml(run.prompt_preview) + '</pre>' : ''}
  `;
  document.getElementById('modal-overlay').classList.add('active');
}

// ============================================================================
// NOTES
// ============================================================================

let currentNoteTab = null;

async function submitNote() {
  const content = document.getElementById('note-content').value.trim();
  if (!content) return;
  const btn = document.querySelector('.note-form .btn');
  btn.disabled = true;
  try {
    const firstLine = content.split('\n')[0].trim();
    const title = firstLine.length > 60 ? firstLine.slice(0, 60) + '...' : firstLine;
    await fetch('/api/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content })
    });
    document.getElementById('note-content').value = '';
    refreshNotes();
  } finally { btn.disabled = false; }
}

function setNoteTab(status, el) {
  currentNoteTab = status;
  document.querySelectorAll('#page-notes .tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  refreshNotes();
}

async function refreshNotes() {
  if (currentPage !== 'notes') return;
  const url = currentNoteTab ? '/api/notes?status=' + currentNoteTab : '/api/notes';
  const notes = await fetchJSON(url);
  const el = document.getElementById('notes-list');
  if (notes.length === 0) {
    el.innerHTML = '<div class="empty">No notes yet</div>';
  } else {
    el.innerHTML = notes.map(n => `
      <div class="note-item" onclick="showNote(${n.id})">
        <h4>${escapeHtml(n.title)} ${badge(n.status)}</h4>
        <div class="note-meta">${timeAgo(n.created_at)} ${n.tags ? '&middot; ' + escapeHtml(n.tags) : ''} ${n.category ? '&middot; ' + escapeHtml(n.category) : ''}</div>
        <div class="note-preview">${escapeHtml(truncate(n.content, 150))}</div>
        ${n.summary ? '<div class="note-preview" style="color:var(--green);margin-top:4px">Summary: ' + escapeHtml(truncate(n.summary, 120)) + '</div>' : ''}
      </div>
    `).join('');
  }
}

async function showNote(id) {
  const n = await fetchJSON('/api/notes/' + id);
  if (!n) return;
  let kp = '';
  if (n.key_points) {
    try {
      const pts = JSON.parse(n.key_points);
      kp = '<ul>' + pts.map(p => '<li>' + escapeHtml(p) + '</li>').join('') + '</ul>';
    } catch (e) { kp = escapeHtml(n.key_points); }
  }
  document.getElementById('modal-content').innerHTML = `
    <h2>${escapeHtml(n.title)} ${badge(n.status)}</h2>
    <div style="color:var(--dim);font-size:11px;margin-bottom:12px">${n.created_at} ${n.tags ? '&middot; Tags: ' + escapeHtml(n.tags) : ''}</div>
    <h3 style="color:var(--dim);margin:12px 0 6px">Content</h3>
    <pre>${escapeHtml(n.content)}</pre>
    ${n.summary ? '<h3 style="color:var(--dim);margin:12px 0 6px">Summary</h3><pre>' + escapeHtml(n.summary) + '</pre>' : ''}
    ${kp ? '<h3 style="color:var(--dim);margin:12px 0 6px">Key Points</h3>' + kp : ''}
  `;
  document.getElementById('modal-overlay').classList.add('active');
}

// ============================================================================
// CHAT / THREADS
// ============================================================================

let currentThreadId = null;
let chatPollingInterval = null;
let isSending = false;

async function refreshThreadList() {
  try {
    const threads = await fetchJSON('/api/threads');
    const el = document.getElementById('thread-list');
    if (threads.length === 0) {
      el.innerHTML = '<div class="empty" style="padding:12px;font-size:11px">No threads yet</div>';
    } else {
      el.innerHTML = threads.map(t => `
        <div class="thread-item ${t.id === currentThreadId ? 'active' : ''}" onclick="openThread('${t.id}')">
          <div class="title">${escapeHtml(t.title)}</div>
          <div class="meta">${timeAgo(t.updated_at)} ${badge(t.status)}</div>
        </div>
      `).join('');
    }
  } catch (e) {
    console.error('Thread list refresh failed:', e);
  }
}

async function createThread() {
  try {
    const res = await fetch('/api/threads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    await refreshThreadList();
    openThread(data.id);
  } catch (e) {
    console.error('Failed to create thread:', e);
  }
}

async function openThread(threadId) {
  currentThreadId = threadId;
  document.getElementById('send-btn').disabled = false;
  document.getElementById('chat-input').focus();

  // Update sidebar selection
  document.querySelectorAll('.thread-item').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.thread-item').forEach(t => {
    if (t.onclick.toString().includes(threadId)) t.classList.add('active');
  });

  await refreshChatMessages();
  refreshThreadList();
}

async function refreshChatMessages() {
  if (!currentThreadId) return;
  try {
    const [thread, messages] = await Promise.all([
      fetchJSON('/api/threads/' + currentThreadId),
      fetchJSON('/api/threads/' + currentThreadId + '/messages'),
    ]);

    document.getElementById('chat-title').textContent = thread.title || 'Thread';

    const el = document.getElementById('chat-messages');
    if (messages.length === 0) {
      el.innerHTML = '<div class="chat-empty">Start the conversation — ask anything, give instructions, or tell the agents what to do</div>';
    } else {
      el.innerHTML = messages.map(m => renderMessage(m)).join('');
      // Scroll to bottom
      el.scrollTop = el.scrollHeight;
    }

    // Check if latest message is pending (assistant hasn't responded yet)
    const lastMsg = messages[messages.length - 1];
    const isPending = lastMsg && lastMsg.role === 'user' && messages.filter(m => m.role === 'assistant').length < messages.filter(m => m.role === 'user').length;
    if (isPending) {
      // Show typing indicator
      el.innerHTML += `
        <div class="message assistant message-pending">
          <div class="bubble">
            <div class="typing"><span></span><span></span><span></span></div>
            Working on it...
          </div>
        </div>
      `;
      el.scrollTop = el.scrollHeight;
    }

    // Update status
    const statusEl = document.getElementById('chat-status');
    const ctxSize = messages.reduce((sum, m) => sum + (m.token_estimate || 0), 0);
    statusEl.textContent = `${messages.length} messages · ~${Math.round(ctxSize / 1000)}k tokens`;
  } catch (e) {
    console.error('Chat refresh failed:', e);
  }
}

function renderMessage(msg) {
  const isUser = msg.role === 'user';
  let metadata = {};
  try { metadata = JSON.parse(msg.metadata || '{}'); } catch (e) {}

  let content = '';
  if (isUser) {
    content = `<div class="bubble">${renderMarkdown(escapeHtml(msg.content_full))}</div>`;
  } else {
    // Assistant: parse the response field from content_full
    let response = msg.content_full;
    let actionSummary = '';
    let toolsUsed = [];

    try {
      const parsed = JSON.parse(msg.content_full);
      response = parsed.response || msg.content_full;
      actionSummary = parsed.action_summary || '';
      toolsUsed = parsed.tools_used || [];
    } catch (e) {
      // Not JSON, just use raw content
    }

    content = `<div class="bubble">${renderMarkdown(escapeHtml(response))}</div>`;

    if (actionSummary && actionSummary !== 'No actions taken.') {
      const toolsHtml = toolsUsed.length > 0
        ? '<ul class="tools-list">' + toolsUsed.map(t =>
            `<li><strong>${escapeHtml(t.tool)}</strong>: ${escapeHtml(t.target || '')} ${t.detail ? '— ' + escapeHtml(t.detail) : ''}</li>`
          ).join('') + '</ul>'
        : '';
      content += `
        <div class="action-summary collapsed" onclick="this.classList.toggle('collapsed')">
          <span class="toggle">&#9656; Actions</span> ${escapeHtml(truncate(actionSummary, 80))}
          <div class="detail" style="margin-top:6px">
            <div>${escapeHtml(actionSummary)}</div>
            ${toolsHtml}
          </div>
        </div>
      `;
    }
  }

  const compressed = msg.is_compressed ? ' <span style="color:var(--yellow);font-size:9px">[compressed]</span>' : '';

  return `
    <div class="message ${isUser ? 'user' : 'assistant'}">
      ${content}
      <div class="meta-row">${timeAgo(msg.created_at)}${compressed}</div>
    </div>
  `;
}

function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 200) + 'px';
}

async function sendMessage() {
  if (isSending || !currentThreadId) return;
  const input = document.getElementById('chat-input');
  const content = input.value.trim();
  if (!content) return;

  isSending = true;
  input.value = '';
  input.style.height = 'auto';
  document.getElementById('send-btn').disabled = true;

  try {
    await fetch(`/api/threads/${currentThreadId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    });

    // Immediately refresh to show user message + pending state
    await refreshChatMessages();

    // Poll for assistant response
    startPollingForResponse();
  } catch (e) {
    console.error('Failed to send message:', e);
  }
}

function startPollingForResponse() {
  // Poll every 2s until we get the assistant response
  if (chatPollingInterval) clearInterval(chatPollingInterval);
  chatPollingInterval = setInterval(async () => {
    const messages = await fetchJSON(`/api/threads/${currentThreadId}/messages`);
    const userCount = messages.filter(m => m.role === 'user').length;
    const assistantCount = messages.filter(m => m.role === 'assistant').length;

    if (assistantCount >= userCount) {
      // Response received
      clearInterval(chatPollingInterval);
      chatPollingInterval = null;
      isSending = false;
      document.getElementById('send-btn').disabled = false;
      await refreshChatMessages();
    } else {
      // Still waiting, refresh to update typing indicator
      await refreshChatMessages();
    }
  }, 2000);
}

// ============================================================================
// INIT
// ============================================================================

refreshDashboard();
setInterval(() => {
  if (currentPage === 'dashboard') refreshDashboard();
  if (currentPage === 'notes') refreshNotes();
  if (currentPage === 'chat' && !isSending) refreshThreadList();
}, 5000);
