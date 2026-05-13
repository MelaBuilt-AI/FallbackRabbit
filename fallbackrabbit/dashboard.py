"""Web dashboard for FallbackRabbit — single-page UI for chain management and test visualization."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# ---------------------------------------------------------------------------
# Dashboard HTML (inline — zero external dependencies)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FallbackRabbit Dashboard</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --text: #e1e4ed;
    --text-dim: #8b8fa3;
    --primary: #6c5ce7;
    --primary-hover: #7c6ff7;
    --success: #00b894;
    --warning: #fdcb6e;
    --danger: #e17055;
    --info: #74b9ff;
    --radius: 8px;
    --font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  /* Layout */
  .app { display: flex; min-height: 100vh; }
  .sidebar {
    width: 260px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    padding: 20px 16px;
    flex-shrink: 0;
  }
  .main { flex: 1; padding: 24px; overflow-y: auto; }
  /* Sidebar */
  .logo { font-size: 20px; font-weight: 700; margin-bottom: 24px; display: flex; align-items: center; gap: 8px; }
  .logo span { color: var(--primary); }
  .nav-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px; border-radius: var(--radius);
    cursor: pointer; transition: background 0.15s; color: var(--text-dim);
    margin-bottom: 4px; font-size: 14px;
  }
  .nav-item:hover, .nav-item.active { background: rgba(108,92,231,0.12); color: var(--text); }
  .nav-item.active { color: var(--primary); font-weight: 600; }
  .nav-icon { font-size: 18px; width: 24px; text-align: center; }
  /* Header */
  .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  .page-title { font-size: 24px; font-weight: 700; }
  /* Cards */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 16px;
  }
  .card-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
  /* Stats */
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }
  .stat-value { font-size: 28px; font-weight: 700; }
  .stat-label { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
  /* Table */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); }
  th { color: var(--text-dim); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  td { color: var(--text); }
  tr:hover td { background: rgba(108,92,231,0.04); }
  /* Badges */
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 11px; font-weight: 600;
  }
  .badge-success { background: rgba(0,184,148,0.15); color: var(--success); }
  .badge-warning { background: rgba(253,203,110,0.15); color: var(--warning); }
  .badge-danger { background: rgba(225,112,85,0.15); color: var(--danger); }
  .badge-info { background: rgba(116,185,255,0.15); color: var(--info); }
  /* Buttons */
  .btn {
    padding: 8px 16px; border-radius: var(--radius); border: none;
    font-size: 13px; font-weight: 600; cursor: pointer;
    transition: all 0.15s; display: inline-flex; align-items: center; gap: 6px;
  }
  .btn-primary { background: var(--primary); color: white; }
  .btn-primary:hover { background: var(--primary-hover); }
  .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-outline:hover { border-color: var(--primary); color: var(--primary); }
  .btn-sm { padding: 4px 10px; font-size: 12px; }
  .btn-danger { background: var(--danger); color: white; }
  .btn-danger:hover { opacity: 0.9; }
  /* Forms */
  .form-group { margin-bottom: 16px; }
  .form-label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--text-dim); }
  .form-input {
    width: 100%; padding: 10px 12px; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--bg);
    color: var(--text); font-size: 14px;
  }
  .form-input:focus { outline: none; border-color: var(--primary); }
  textarea.form-input { min-height: 80px; resize: vertical; font-family: monospace; }
  /* Modal */
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  .modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 24px;
    width: 90%; max-width: 600px; max-height: 80vh; overflow-y: auto;
  }
  .modal-title { font-size: 18px; font-weight: 700; margin-bottom: 20px; }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
  /* Test progress */
  .progress-bar {
    height: 8px; background: var(--border); border-radius: 4px; overflow: hidden;
  }
  .progress-fill {
    height: 100%; background: var(--primary); border-radius: 4px;
    transition: width 0.3s;
  }
  .test-log {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-dim);
    max-height: 400px;
    overflow-y: auto;
    padding: 12px;
    background: var(--bg);
    border-radius: var(--radius);
  }
  .test-log .success { color: var(--success); }
  .test-log .fail { color: var(--danger); }
  .test-log .info { color: var(--info); }
  /* Empty state */
  .empty-state {
    text-align: center; padding: 60px 20px; color: var(--text-dim);
  }
  .empty-state .icon { font-size: 48px; margin-bottom: 16px; }
  /* Responsive */
  @media (max-width: 768px) {
    .sidebar { display: none; }
    .stats { grid-template-columns: repeat(2, 1fr); }
  }
  /* WS status */
  .ws-status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-dim); margin-top: 16px; }
  .ws-dot { width: 8px; height: 8px; border-radius: 50%; }
  .ws-dot.connected { background: var(--success); }
  .ws-dot.disconnected { background: var(--danger); }
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <nav class="sidebar">
    <div class="logo">🐰 <span>Fallback</span>Rabbit</div>
    <div class="nav-item active" data-page="overview">
      <span class="nav-icon">📊</span> Overview
    </div>
    <div class="nav-item" data-page="chains">
      <span class="nav-icon">🔗</span> Chains
    </div>
    <div class="nav-item" data-page="test">
      <span class="nav-icon">🧪</span> Test Runner
    </div>
    <div class="nav-item" data-page="export">
      <span class="nav-icon">📦</span> Export
    </div>
    <div class="ws-status">
      <div class="ws-dot disconnected" id="wsDot"></div>
      <span id="wsLabel">Disconnected</span>
    </div>
  </nav>

  <!-- Main Content -->
  <main class="main" id="mainContent">
    <!-- Pages rendered by JS -->
  </main>
</div>

<script>
const API = '';
let chains = [];
let ws = null;
let currentPage = 'overview';
let testResults = null;

// ---- API helpers ----
async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ---- WebSocket ----
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    document.getElementById('wsDot').className = 'ws-dot connected';
    document.getElementById('wsLabel').textContent = 'Connected';
  };
  ws.onclose = () => {
    document.getElementById('wsDot').className = 'ws-dot disconnected';
    document.getElementById('wsLabel').textContent = 'Disconnected';
    setTimeout(connectWS, 3000);
  };
  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleWSEvent(event);
  };
  ws.onerror = () => ws.close();
}

function handleWSEvent(event) {
  if (event.type === 'test_progress' && currentPage === 'test') {
    appendTestLog(event.data);
  }
  if (event.type === 'test_complete' && currentPage === 'test') {
    showTestComplete(event.data);
  }
  if (event.type === 'chain_created' || event.type === 'chain_deleted') {
    loadChains();
  }
}

// ---- Navigation ----
document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    el.classList.add('active');
    currentPage = el.dataset.page;
    renderPage();
  });
});

// ---- Load data ----
async function loadChains() {
  try {
    chains = await api('/chains');
  } catch { chains = []; }
  renderPage();
}

// ---- Pages ----
function renderPage() {
  const main = document.getElementById('mainContent');
  switch (currentPage) {
    case 'overview': renderOverview(main); break;
    case 'chains': renderChains(main); break;
    case 'test': renderTest(main); break;
    case 'export': renderExport(main); break;
  }
}

function renderOverview(el) {
  const totalChains = chains.length;
  const totalProviders = chains.reduce((s, c) => s + c.providers, 0);
  const totalRules = chains.reduce((s, c) => s + c.fallback_rules, 0);
  el.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Dashboard</h1>
    </div>
    <div class="stats">
      <div class="stat-card"><div class="stat-value">${totalChains}</div><div class="stat-label">Chains</div></div>
      <div class="stat-card"><div class="stat-value">${totalProviders}</div><div class="stat-label">Providers</div></div>
      <div class="stat-card"><div class="stat-value">${totalRules}</div><div class="stat-label">Fallback Rules</div></div>
      <div class="stat-card"><div class="stat-value" style="color:var(--success)">●</div><div class="stat-label">API Status</div></div>
    </div>
    <div class="card">
      <div class="card-title">Recent Chains</div>
      ${chains.length === 0 ? '<div class="empty-state"><div class="icon">🔗</div><p>No chains yet. Create one to get started!</p></div>' : `
      <div class="table-wrap"><table>
        <thead><tr><th>Name</th><th>Providers</th><th>Rules</th><th>ID</th></tr></thead>
        <tbody>${chains.map(c => `<tr><td>${c.name}</td><td>${c.providers}</td><td>${c.fallback_rules}</td><td><code>${c.chain_id}</code></td></tr>`).join('')}</tbody>
      </table></div>`}
    </div>
  `;
}

function renderChains(el) {
  el.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Chains</h1>
      <button class="btn btn-primary" onclick="showCreateChainModal()">+ New Chain</button>
    </div>
    <div id="chainsList"></div>
  `;
  renderChainsList();
}

async function renderChainsList() {
  const container = document.getElementById('chainsList');
  if (!container) return;
  if (chains.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="icon">🔗</div><p>No chains yet. Create one!</p></div>';
    return;
  }
  container.innerHTML = chains.map(c => `
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div class="card-title">${c.name}</div>
          <span class="badge badge-info">${c.providers} providers</span>
          <span class="badge badge-warning" style="margin-left:4px">${c.fallback_rules} rules</span>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-outline btn-sm" onclick="viewChain('${c.chain_id}')">View</button>
          <button class="btn btn-outline btn-sm btn-danger" onclick="deleteChain('${c.chain_id}')">Delete</button>
        </div>
      </div>
    </div>
  `).join('');
}

function showCreateChainModal() {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal">
      <div class="modal-title">Create New Chain</div>
      <div class="form-group">
        <label class="form-label">Chain Name</label>
        <input class="form-input" id="newChainName" placeholder="My Fallback Chain">
      </div>
      <div class="form-group">
        <label class="form-label">Providers (JSON array)</label>
        <textarea class="form-input" id="newChainProviders" placeholder='[{"name":"gpt-4","model_id":"gpt-4","api_base":"https://api.openai.com/v1","priority":1}]'></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Fallback Rules (JSON array, optional)</label>
        <textarea class="form-input" id="newChainRules" placeholder='[]'></textarea>
      </div>
      <div class="modal-actions">
        <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
        <button class="btn btn-primary" onclick="createChain()">Create</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}

async function createChain() {
  const name = document.getElementById('newChainName').value.trim();
  const providers = JSON.parse(document.getElementById('newChainProviders').value);
  const rules = JSON.parse(document.getElementById('newChainRules').value || '[]');
  if (!name || !providers.length) { alert('Name and providers required'); return; }
  try {
    await api('/chains', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, providers, fallback_rules: rules }),
    });
    document.querySelector('.modal-overlay').remove();
    await loadChains();
  } catch (e) { alert('Error: ' + e.message); }
}

async function viewChain(id) {
  try {
    const chain = await api(`/chains/${id}`);
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-title">${chain.name}</div>
        <div class="card-title">Providers</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Name</th><th>Model</th><th>Priority</th></tr></thead>
          <tbody>${chain.providers.map(p => `<tr><td>${p.name}</td><td>${p.model_id}</td><td>${p.priority}</td></tr>`).join('')}</tbody>
        </table></div>
        ${chain.fallback_rules && chain.fallback_rules.length ? `<div class="card-title" style="margin-top:16px">Fallback Rules</div><pre style="font-size:12px;color:var(--text-dim)">${JSON.stringify(chain.fallback_rules, null, 2)}</pre>` : ''}
        <div class="modal-actions">
          <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove()">Close</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  } catch (e) { alert('Error: ' + e.message); }
}

async function deleteChain(id) {
  if (!confirm('Delete this chain?')) return;
  try {
    await api(`/chains/${id}`, { method: 'DELETE' });
    await loadChains();
  } catch (e) { alert('Error: ' + e.message); }
}

function renderTest(el) {
  el.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Test Runner</h1>
    </div>
    <div class="card">
      <div class="card-title">Run Test</div>
      <div class="form-group">
        <label class="form-label">Select Chain</label>
        <select class="form-input" id="testChainId">
          <option value="">-- Select --</option>
          ${chains.map(c => `<option value="${c.chain_id}">${c.name}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Number of Prompts</label>
        <input class="form-input" id="testPromptCount" type="number" value="5" min="1" max="100">
      </div>
      <button class="btn btn-primary" onclick="runTest()">Run Test</button>
    </div>
    <div id="testOutput" style="display:none;">
      <div class="card">
        <div class="card-title">Test Progress</div>
        <div class="progress-bar" style="margin-bottom:12px"><div class="progress-fill" id="testProgress" style="width:0%"></div></div>
        <div class="test-log" id="testLog"></div>
      </div>
    </div>
    <div id="testResults" style="display:none;"></div>
  `;
}

async function runTest() {
  const chainId = document.getElementById('testChainId').value;
  const count = parseInt(document.getElementById('testPromptCount').value) || 5;
  if (!chainId) { alert('Select a chain'); return; }

  document.getElementById('testOutput').style.display = 'block';
  document.getElementById('testResults').style.display = 'none';
  document.getElementById('testProgress').style.width = '0%';
  document.getElementById('testLog').innerHTML = '';

  appendTestLog({ current: 0, total: count, provider: '-', success: true, latency_ms: 0 }, true);

  try {
    const result = await api(`/chains/${chainId}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompts: count }),
    });
    showTestResults(result);
  } catch (e) {
    appendTestLog({ error: e.message }, false, true);
  }
}

function appendTestLog(data, isStart = false, isError = false) {
  const log = document.getElementById('testLog');
  if (!log) return;
  if (isStart) {
    log.innerHTML += `<div class="info">🚀 Starting test: ${data.total} prompts</div>`;
    return;
  }
  if (isError) {
    log.innerHTML += `<div class="fail">❌ Error: ${data.error}</div>`;
    return;
  }
  const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
  document.getElementById('testProgress').style.width = pct + '%';
  const cls = data.success ? 'success' : 'fail';
  const icon = data.success ? '✅' : '❌';
  log.innerHTML += `<div class="${cls}">${icon} [${data.current}/${data.total}] ${data.provider} — ${data.latency_ms.toFixed(0)}ms</div>`;
  log.scrollTop = log.scrollHeight;
}

function showTestComplete(data) {
  const log = document.getElementById('testLog');
  if (!log) return;
  log.innerHTML += `<div class="info">🏁 Complete: ${data.successful}/${data.total} successful</div>`;
  document.getElementById('testProgress').style.width = '100%';
}

function showTestResults(report) {
  const el = document.getElementById('testResults');
  el.style.display = 'block';
  const summary = report.summary || 'Test completed';
  const successRate = report.results ? (report.results.filter(r => r.success).length / report.results.length * 100).toFixed(1) : '—';
  el.innerHTML = `
    <div class="card">
      <div class="card-title">Results</div>
      <div class="stats" style="margin-bottom:16px">
        <div class="stat-card"><div class="stat-value" style="color:var(--success)">${successRate}%</div><div class="stat-label">Success Rate</div></div>
        <div class="stat-card"><div class="stat-value">${report.results ? report.results.length : 0}</div><div class="stat-label">Prompts</div></div>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>#</th><th>Provider</th><th>Success</th><th>Latency</th></tr></thead>
        <tbody>${(report.results || []).map((r, i) => `<tr>
          <td>${i+1}</td><td>${r.provider || '—'}</td>
          <td><span class="badge ${r.success ? 'badge-success' : 'badge-danger'}">${r.success ? 'OK' : 'FAIL'}</span></td>
          <td>${(r.latency_ms || 0).toFixed(0)}ms</td>
        </tr>`).join('')}</tbody>
      </table></div>
    </div>
  `;
}

function renderExport(el) {
  el.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Export</h1>
    </div>
    <div class="card">
      <div class="card-title">Export Chain Config</div>
      <div class="form-group">
        <label class="form-label">Select Chain</label>
        <select class="form-input" id="exportChainId">
          <option value="">-- Select --</option>
          ${chains.map(c => `<option value="${c.chain_id}">${c.name}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Format</label>
        <select class="form-input" id="exportFormat">
          <option value="custom">Custom</option>
          <option value="litellm">LiteLLM</option>
          <option value="openrouter">OpenRouter</option>
          <option value="langchain">LangChain</option>
          <option value="haystack">Haystack</option>
        </select>
      </div>
      <button class="btn btn-primary" onclick="exportChain()">Export</button>
      <pre id="exportOutput" style="display:none;margin-top:16px;font-size:12px;color:var(--text-dim);background:var(--bg);padding:16px;border-radius:var(--radius);max-height:400px;overflow:auto;"></pre>
    </div>
  `;
}

async function exportChain() {
  const chainId = document.getElementById('exportChainId').value;
  const fmt = document.getElementById('exportFormat').value;
  if (!chainId) { alert('Select a chain'); return; }
  try {
    const result = await api(`/chains/${chainId}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format: fmt }),
    });
    const output = document.getElementById('exportOutput');
    output.style.display = 'block';
    output.textContent = JSON.stringify(result, null, 2);
  } catch (e) { alert('Error: ' + e.message); }
}

// ---- Init ----
loadChains();
connectWS();
</script>
</body>
</html>"""


def get_dashboard_html() -> str:
    """Return the dashboard HTML string."""
    return DASHBOARD_HTML


def mount_dashboard(app: FastAPI, *, prefix: str = "/dashboard") -> None:
    """Mount the dashboard UI on a FastAPI app.

    Args:
        app: FastAPI application.
        prefix: URL prefix for the dashboard. Defaults to /dashboard.
    """

    @app.get(prefix, response_class=HTMLResponse, tags=["dashboard"])
    async def dashboard_page():
        """Serve the FallbackRabbit dashboard UI."""
        return HTMLResponse(content=get_dashboard_html())

    @app.get(f"{prefix}/", response_class=HTMLResponse, tags=["dashboard"])
    async def dashboard_page_slash():
        """Serve the dashboard UI (trailing slash)."""
        return HTMLResponse(content=get_dashboard_html())
