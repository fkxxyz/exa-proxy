"""主入口：FastAPI + 自定义 MCP 代理 + Key 管理 API"""

from __future__ import annotations

import html
import json
import logging
import os
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn

from .api import create_api_router
from .executor import ExecutionAbortedError, ProxyExecutor
from .key_manager import KeyManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)
security = HTTPBasic()


def create_admin_auth():
    username = os.getenv("EXA_PROXY_ADMIN_USERNAME", "admin")
    password = os.getenv("EXA_PROXY_ADMIN_PASSWORD", "admin")

    def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
        valid_username = secrets.compare_digest(credentials.username, username)
        valid_password = secrets.compare_digest(credentials.password, password)

        if not (valid_username and valid_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )

        return credentials.username

    return require_admin


def render_admin_page(stats: dict, keys: list[dict]) -> str:
    def mask_key(raw: str) -> str:
        if len(raw) <= 12:
            return raw
        return f"{raw[:8]}...{raw[-4:]}"

    def is_cooling_down(key: dict) -> bool:
        cooldown_until = key.get("cooldown_until")
        if not cooldown_until or not key.get("enabled", False):
            return False
        try:
            from datetime import datetime, timezone

            cooldown_time = datetime.fromisoformat(cooldown_until)
            return cooldown_time > datetime.now(timezone.utc)
        except ValueError:
            return False

    def status_label(key: dict) -> tuple[str, str]:
        if not key.get("enabled", False):
            return "Disabled", "status-disabled"
        if is_cooling_down(key):
            return "Cooldown", "status-cooldown"
        return "Available", "status-available"

    def success_rate(key: dict) -> str:
        total = key["stats"].get("total_requests", 0)
        success = key["stats"].get("success_count", 0)
        if total == 0:
            return "--"
        return f"{(success / total) * 100:.0f}%"

    def overall_success_rate() -> str:
        total = stats.get("total_requests", 0)
        success = stats.get("total_success", 0)
        if total == 0:
            return "--"
        return f"{(success / total) * 100:.0f}%"

    card_items = [
        ("Total Keys", stats["total_keys"], "Configured API keys"),
        ("Enabled Keys", stats["enabled_keys"], "Ready for routing"),
        ("Available Keys", stats["available_keys"], "Healthy and selectable"),
        ("In Cooldown", stats["in_cooldown"], "Temporarily unavailable"),
        ("Total Requests", stats["total_requests"], "Processed via proxy"),
        ("Success Rate", overall_success_rate(), "Overall request health"),
    ]

    cards = "".join(
        (
            '<section class="stat-card">'
            f'<div class="stat-label">{html.escape(label)}</div>'
            f'<div class="stat-value">{html.escape(str(value))}</div>'
            f'<div class="stat-meta">{html.escape(meta)}</div>'
            "</section>"
        )
        for label, value, meta in card_items
    )

    if keys:
        rows = []
        for key in keys:
            label, status_class = status_label(key)
            rows.append(
                '<tr class="data-row">'
                f'<td><div class="name-cell">{html.escape(key["name"])}</div><div class="subtle">{html.escape(key["id"])}</div></td>'
                f"<td><code>{html.escape(mask_key(key['key']))}</code></td>"
                f'<td><span class="status-pill {status_class}">{html.escape(label)}</span></td>'
                f"<td>{'Enabled' if key['enabled'] else 'Disabled'}</td>"
                f'<td class="num">{key["stats"]["total_requests"]}</td>'
                f'<td class="num">{html.escape(success_rate(key))}</td>'
                f"<td>{html.escape(key['stats'].get('last_used_at') or 'Never')}</td>"
                f"<td>{html.escape(key.get('cooldown_until') or '-')}</td>"
                "<td>"
                f'<div class="actions">'
                f'<button class="action-btn" data-action="edit" data-key-id="{html.escape(key["id"])}">Edit</button>'
                f'<button class="action-btn" data-action="toggle" data-key-id="{html.escape(key["id"])}">{"Disable" if key["enabled"] else "Enable"}</button>'
                f'<button class="action-btn" data-action="reset" data-key-id="{html.escape(key["id"])}">Reset</button>'
                f'<button class="action-btn danger" data-action="delete" data-key-id="{html.escape(key["id"])}">Delete</button>'
                "</div>"
                "</td>"
                "</tr>"
            )
        rows_html = "".join(rows)
        empty_state_class = "empty-state hidden"
    else:
        rows_html = ""
        empty_state_class = "empty-state"

    initial_state = json.dumps({"stats": stats, "keys": keys}, ensure_ascii=False)

    return f"""
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Exa Proxy Admin</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #0b1220;
        --panel: #111827;
        --panel-2: #0f172a;
        --panel-3: #172033;
        --border: #23304a;
        --text: #f8fafc;
        --muted: #94a3b8;
        --green: #22c55e;
        --amber: #f59e0b;
        --red: #ef4444;
        --blue: #60a5fa;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        background: radial-gradient(circle at top, #13203b 0%, var(--bg) 42%);
        color: var(--text);
        font-family: "Fira Sans", "Inter", system-ui, sans-serif;
      }}
      code, .stat-value, .name-cell {{ font-family: "Fira Code", "JetBrains Mono", monospace; }}
      .shell {{ max-width: 1400px; margin: 0 auto; padding: 32px 20px 48px; }}
      .hero {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 24px; }}
      .hero h1 {{ margin: 0; font-size: 32px; line-height: 1.1; }}
      .hero p {{ margin: 10px 0 0; color: var(--muted); max-width: 720px; }}
      .top-actions {{ display: flex; gap: 12px; align-items: center; }}
      .ghost-link {{ color: var(--muted); text-decoration: none; font-size: 14px; }}
      .primary-btn, .action-btn, .secondary-btn {{
        border: 1px solid transparent;
        border-radius: 12px;
        cursor: pointer;
        transition: background-color .18s ease, border-color .18s ease, transform .18s ease;
      }}
      .primary-btn {{
        background: linear-gradient(135deg, #2563eb, #22c55e);
        color: white;
        padding: 12px 18px;
        font-weight: 700;
        box-shadow: 0 10px 30px rgba(37, 99, 235, 0.25);
      }}
      .primary-btn:hover, .secondary-btn:hover, .action-btn:hover {{ transform: translateY(-1px); }}
      .stats-grid {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; margin-bottom: 22px; }}
      .stat-card {{
        background: linear-gradient(180deg, rgba(17,24,39,.96), rgba(15,23,42,.9));
        border: 1px solid rgba(96,165,250,.12);
        border-radius: 18px;
        padding: 18px;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 18px 40px rgba(2,6,23,.28);
      }}
      .stat-label {{ color: var(--muted); font-size: 13px; margin-bottom: 14px; text-transform: uppercase; letter-spacing: .08em; }}
      .stat-value {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
      .stat-meta {{ color: #cbd5e1; font-size: 13px; }}
      .panel {{
        background: linear-gradient(180deg, rgba(17,24,39,.98), rgba(15,23,42,.94));
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 20px;
        box-shadow: 0 24px 70px rgba(2, 6, 23, .38);
      }}
      .toolbar {{ display: flex; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; }}
      .toolbar-left {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
      .search, .select, .field {{
        background: rgba(15,23,42,.92);
        color: var(--text);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 11px 14px;
        min-height: 44px;
      }}
      .search {{ min-width: 240px; }}
      .secondary-btn {{
        background: rgba(15,23,42,.92);
        color: var(--text);
        border-color: var(--border);
        padding: 10px 14px;
      }}
      .table-wrap {{ overflow-x: auto; }}
      table {{ width: 100%; border-collapse: separate; border-spacing: 0 12px; }}
      th {{ text-align: left; font-size: 12px; color: var(--muted); font-weight: 700; padding: 0 12px 8px; text-transform: uppercase; letter-spacing: .08em; }}
      td {{ background: rgba(15,23,42,.72); border-top: 1px solid rgba(51,65,85,.78); border-bottom: 1px solid rgba(51,65,85,.78); padding: 16px 12px; vertical-align: middle; }}
      td:first-child {{ border-left: 1px solid rgba(51,65,85,.78); border-top-left-radius: 16px; border-bottom-left-radius: 16px; }}
      td:last-child {{ border-right: 1px solid rgba(51,65,85,.78); border-top-right-radius: 16px; border-bottom-right-radius: 16px; }}
      .data-row:hover td {{ background: rgba(23,32,51,.92); }}
      .subtle {{ color: var(--muted); font-size: 12px; margin-top: 6px; }}
      .status-pill {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 7px 10px; font-size: 12px; font-weight: 700; border: 1px solid transparent; }}
      .status-available {{ color: #bbf7d0; background: rgba(34,197,94,.15); border-color: rgba(34,197,94,.35); }}
      .status-cooldown {{ color: #fde68a; background: rgba(245,158,11,.14); border-color: rgba(245,158,11,.3); }}
      .status-disabled {{ color: #cbd5e1; background: rgba(148,163,184,.14); border-color: rgba(148,163,184,.24); }}
      .num {{ font-variant-numeric: tabular-nums; }}
      .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
      .action-btn {{ background: rgba(17,24,39,.88); color: var(--text); border-color: rgba(71,85,105,.68); padding: 8px 10px; font-size: 13px; }}
      .action-btn.danger {{ color: #fecaca; border-color: rgba(239,68,68,.35); background: rgba(127,29,29,.18); }}
      .empty-state {{ border: 1px dashed rgba(96,165,250,.24); border-radius: 18px; padding: 48px 18px; text-align: center; color: var(--muted); background: rgba(15,23,42,.45); }}
      .hidden {{ display: none !important; }}
      .modal-backdrop {{ position: fixed; inset: 0; background: rgba(2,6,23,.72); display: flex; align-items: center; justify-content: center; padding: 20px; }}
      .modal {{ width: min(560px, 100%); background: linear-gradient(180deg, #101827, #0f172a); border: 1px solid var(--border); border-radius: 22px; box-shadow: 0 24px 80px rgba(2,6,23,.48); }}
      .modal-head, .modal-body, .modal-foot {{ padding: 20px 22px; }}
      .modal-head {{ border-bottom: 1px solid rgba(51,65,85,.7); display: flex; justify-content: space-between; gap: 16px; align-items: center; }}
      .modal-title {{ margin: 0; font-size: 20px; }}
      .modal-copy {{ margin: 8px 0 0; color: var(--muted); font-size: 14px; }}
      .modal-body {{ display: grid; gap: 14px; }}
      .label {{ display: grid; gap: 8px; color: #dbeafe; font-size: 14px; }}
      .check {{ display: flex; gap: 10px; align-items: center; color: var(--text); }}
      .modal-foot {{ border-top: 1px solid rgba(51,65,85,.7); display: flex; justify-content: flex-end; gap: 10px; }}
      .toast {{ position: fixed; right: 18px; bottom: 18px; background: rgba(15,23,42,.95); border: 1px solid rgba(96,165,250,.25); color: var(--text); border-radius: 14px; padding: 14px 16px; min-width: 220px; box-shadow: 0 18px 40px rgba(2,6,23,.35); }}
      .toast.error {{ border-color: rgba(239,68,68,.3); color: #fecaca; }}
      @media (max-width: 1200px) {{ .stats-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
      @media (max-width: 820px) {{ .stats-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .hero {{ flex-direction: column; }} }}
      @media (max-width: 640px) {{ .stats-grid {{ grid-template-columns: 1fr; }} .shell {{ padding-inline: 14px; }} .toolbar-left, .top-actions, .actions {{ width: 100%; }} .search, .select, .secondary-btn, .primary-btn {{ width: 100%; }} }}
    </style>
  </head>
  <body>
    <main class=\"shell\">
      <header class=\"hero\">
        <div>
          <h1>Exa Proxy Admin</h1>
          <p>Deep-dark operations dashboard for Exa API key management. Add, edit, enable, disable, reset cooldown, and monitor request health without leaving the current FastAPI service.</p>
        </div>
        <div class=\"top-actions\">
          <a class=\"ghost-link\" href=\"/mcp\" target=\"_blank\" rel=\"noreferrer\">Open /mcp</a>
          <button id=\"open-create\" class=\"primary-btn\" type=\"button\">Add Key</button>
        </div>
      </header>

      <section class=\"stats-grid\">{cards}</section>

      <section class=\"panel\">
        <div class=\"toolbar\">
          <div class=\"toolbar-left\">
            <input id=\"search\" class=\"search\" type=\"search\" placeholder=\"Search keys\" />
            <select id=\"status-filter\" class=\"select\">
              <option value=\"all\">All statuses</option>
              <option value=\"available\">Available</option>
              <option value=\"cooldown\">Cooldown</option>
              <option value=\"disabled\">Disabled</option>
            </select>
          </div>
          <button id=\"refresh\" class=\"secondary-btn\" type=\"button\">Refresh</button>
        </div>

        <div id=\"empty-state\" class=\"{empty_state_class}\">No API keys added yet</div>

        <div class=\"table-wrap\">
          <table id=\"keys-table\">
            <thead>
              <tr>
                <th>Name</th>
                <th>API Key</th>
                <th>Status</th>
                <th>Enabled</th>
                <th>Requests</th>
                <th>Success Rate</th>
                <th>Last Used</th>
                <th>Cooldown Until</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id=\"keys-body\">{rows_html}</tbody>
          </table>
        </div>
      </section>
    </main>

    <div id=\"modal-backdrop\" class=\"modal-backdrop hidden\" role=\"dialog\" aria-modal=\"true\">
      <div class=\"modal\">
        <div class=\"modal-head\">
          <div>
            <h2 id=\"modal-title\" class=\"modal-title\">Create Key</h2>
            <p id=\"modal-copy\" class=\"modal-copy\">Add a new Exa key to the pool.</p>
          </div>
          <button id=\"close-modal\" class=\"secondary-btn\" type=\"button\">Close</button>
        </div>
        <form id=\"key-form\">
          <div class=\"modal-body\">
            <input id=\"key-id\" type=\"hidden\" />
            <label class=\"label\">Display name
              <input id=\"name\" class=\"field\" name=\"name\" placeholder=\"primary / backup / personal\" required />
            </label>
            <label class=\"label\">API key
              <input id=\"api-key\" class=\"field\" name=\"key\" placeholder=\"exa_...\" />
            </label>
            <label class=\"check\">
              <input id=\"enabled\" type=\"checkbox\" checked />
              <span>Enabled for routing</span>
            </label>
          </div>
          <div class=\"modal-foot\">
            <button class=\"secondary-btn\" type=\"button\" id=\"cancel-modal\">Cancel</button>
            <button class=\"primary-btn\" type=\"submit\" id=\"submit-modal\">Save Changes</button>
          </div>
        </form>
      </div>
    </div>

    <div id=\"toast\" class=\"toast hidden\"></div>

    <script>
      const initialState = {initial_state};
      const searchInput = document.getElementById('search');
      const statusFilter = document.getElementById('status-filter');
      const refreshButton = document.getElementById('refresh');
      const openCreateButton = document.getElementById('open-create');
      const keysBody = document.getElementById('keys-body');
      const emptyState = document.getElementById('empty-state');
      const modalBackdrop = document.getElementById('modal-backdrop');
      const closeModalButton = document.getElementById('close-modal');
      const cancelModalButton = document.getElementById('cancel-modal');
      const form = document.getElementById('key-form');
      const keyIdInput = document.getElementById('key-id');
      const nameInput = document.getElementById('name');
      const keyInput = document.getElementById('api-key');
      const enabledInput = document.getElementById('enabled');
      const modalTitle = document.getElementById('modal-title');
      const modalCopy = document.getElementById('modal-copy');
      const submitButton = document.getElementById('submit-modal');
      const toast = document.getElementById('toast');

      let state = initialState;

      function escapeHtml(value) {{
        return String(value)
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#39;');
      }}

      function maskKey(value) {{
        if (!value) return '';
        return value.length <= 12 ? value : `${{value.slice(0, 8)}}...${{value.slice(-4)}}`;
      }}

      function isCooldown(key) {{
        return Boolean(key.enabled && key.cooldown_until && new Date(key.cooldown_until) > new Date());
      }}

      function statusLabel(key) {{
        if (!key.enabled) return {{ text: 'Disabled', className: 'status-disabled' }};
        if (isCooldown(key)) return {{ text: 'Cooldown', className: 'status-cooldown' }};
        return {{ text: 'Available', className: 'status-available' }};
      }}

      function successRate(key) {{
        const total = key.stats.total_requests || 0;
        const success = key.stats.success_count || 0;
        if (!total) return '--';
        return `${{Math.round((success / total) * 100)}}%`;
      }}

      function showToast(message, kind = 'info') {{
        toast.textContent = message;
        toast.className = `toast ${{kind === 'error' ? 'error' : ''}}`;
        setTimeout(() => toast.classList.add('hidden'), 2200);
      }}

      function openModal(mode, key = null) {{
        modalBackdrop.classList.remove('hidden');
        if (mode === 'create') {{
          modalTitle.textContent = 'Create Key';
          modalCopy.textContent = 'Add a new Exa key to the pool.';
          submitButton.textContent = 'Create Key';
          keyIdInput.value = '';
          nameInput.value = '';
          keyInput.value = '';
          keyInput.disabled = false;
          keyInput.required = true;
          enabledInput.checked = true;
        }} else if (key) {{
          modalTitle.textContent = 'Edit Key';
          modalCopy.textContent = 'Update display name and routing state.';
          submitButton.textContent = 'Save Changes';
          keyIdInput.value = key.id;
          nameInput.value = key.name || '';
          keyInput.value = maskKey(key.key);
          keyInput.disabled = true;
          keyInput.required = false;
          enabledInput.checked = Boolean(key.enabled);
        }}
      }}

      function closeModal() {{
        modalBackdrop.classList.add('hidden');
      }}

      function renderRows() {{
        const query = searchInput.value.trim().toLowerCase();
        const filter = statusFilter.value;
        const rows = state.keys.filter((key) => {{
          const status = statusLabel(key).text.toLowerCase();
          const matchesQuery = !query || key.name.toLowerCase().includes(query) || key.id.toLowerCase().includes(query) || maskKey(key.key).toLowerCase().includes(query);
          const matchesFilter = filter === 'all' || status === filter;
          return matchesQuery && matchesFilter;
        }});

        keysBody.innerHTML = rows.map((key) => {{
          const status = statusLabel(key);
          return `
            <tr class="data-row">
              <td><div class="name-cell">${{escapeHtml(key.name)}}</div><div class="subtle">${{escapeHtml(key.id)}}</div></td>
              <td><code>${{escapeHtml(maskKey(key.key))}}</code></td>
              <td><span class="status-pill ${{status.className}}">${{status.text}}</span></td>
              <td>${{key.enabled ? 'Enabled' : 'Disabled'}}</td>
              <td class="num">${{key.stats.total_requests}}</td>
              <td class="num">${{successRate(key)}}</td>
              <td>${{escapeHtml(key.stats.last_used_at || 'Never')}}</td>
              <td>${{escapeHtml(key.cooldown_until || '-')}}</td>
              <td>
                <div class="actions">
                  <button class="action-btn" data-action="edit" data-key-id="${{key.id}}">Edit</button>
                  <button class="action-btn" data-action="toggle" data-key-id="${{key.id}}">${{key.enabled ? 'Disable' : 'Enable'}}</button>
                  <button class="action-btn" data-action="reset" data-key-id="${{key.id}}">Reset</button>
                  <button class="action-btn danger" data-action="delete" data-key-id="${{key.id}}">Delete</button>
                </div>
              </td>
            </tr>
          `;
        }}).join('');

        emptyState.classList.toggle('hidden', rows.length !== 0);
      }}

      function updateStats(stats) {{
        const values = document.querySelectorAll('.stat-value');
        values[0].textContent = stats.total_keys;
        values[1].textContent = stats.enabled_keys;
        values[2].textContent = stats.available_keys;
        values[3].textContent = stats.in_cooldown;
        values[4].textContent = stats.total_requests;
        values[5].textContent = stats.total_requests ? `${{Math.round((stats.total_success / stats.total_requests) * 100)}}%` : '--';
      }}

      async function refreshData() {{
        const [statsResponse, keysResponse] = await Promise.all([
          fetch('/api/keys/stats'),
          fetch('/api/keys'),
        ]);
        if (!statsResponse.ok || !keysResponse.ok) {{
          throw new Error('Failed to refresh admin dashboard');
        }}
        state = {{
          stats: await statsResponse.json(),
          keys: await keysResponse.json(),
        }};
        updateStats(state.stats);
        renderRows();
      }}

      async function submitForm(event) {{
        event.preventDefault();
        const isEditing = Boolean(keyIdInput.value);
        const payload = {{ name: nameInput.value.trim(), enabled: enabledInput.checked }};

        let url = '/api/keys';
        let method = 'POST';

        if (!isEditing) {{
          payload.key = keyInput.value.trim();
        }} else {{
          url = `/api/keys/${{keyIdInput.value}}`;
          method = 'PUT';
        }}

        const response = await fetch(url, {{
          method,
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});

        if (!response.ok) {{
          const error = await response.text();
          showToast(error || 'Save failed', 'error');
          return;
        }}

        closeModal();
        await refreshData();
        showToast(isEditing ? 'Key updated' : 'Key created');
      }}

      async function handleActionClick(event) {{
        const button = event.target.closest('[data-action]');
        if (!button) return;
        const keyId = button.dataset.keyId;
        const action = button.dataset.action;
        const key = state.keys.find((item) => item.id === keyId);
        if (!key) return;

        if (action === 'edit') {{
          openModal('edit', key);
          return;
        }}

        if (action === 'toggle') {{
          const response = await fetch(`/api/keys/${{keyId}}`, {{
            method: 'PUT',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ name: key.name, enabled: !key.enabled }}),
          }});
          if (!response.ok) {{
            showToast('Failed to update key state', 'error');
            return;
          }}
          await refreshData();
          showToast(key.enabled ? 'Key disabled' : 'Key enabled');
          return;
        }}

        if (action === 'reset') {{
          const response = await fetch(`/api/keys/${{keyId}}/reset`, {{ method: 'POST' }});
          if (!response.ok) {{
            showToast('Failed to reset cooldown', 'error');
            return;
          }}
          await refreshData();
          showToast('Cooldown reset');
          return;
        }}

        if (action === 'delete') {{
          const confirmed = window.confirm(`Delete key "${{key.name}}"? This cannot be undone.`);
          if (!confirmed) return;
          const response = await fetch(`/api/keys/${{keyId}}`, {{ method: 'DELETE' }});
          if (!response.ok) {{
            showToast('Failed to delete key', 'error');
            return;
          }}
          await refreshData();
          showToast('Key deleted');
        }}
      }}

      openCreateButton.addEventListener('click', () => openModal('create'));
      closeModalButton.addEventListener('click', closeModal);
      cancelModalButton.addEventListener('click', closeModal);
      modalBackdrop.addEventListener('click', (event) => {{ if (event.target === modalBackdrop) closeModal(); }});
      refreshButton.addEventListener('click', async () => {{ try {{ await refreshData(); showToast('Dashboard refreshed'); }} catch (error) {{ showToast(error.message, 'error'); }} }});
      form.addEventListener('submit', submitForm);
      keysBody.addEventListener('click', handleActionClick);
      searchInput.addEventListener('input', renderRows);
      statusFilter.addEventListener('change', renderRows);
      renderRows();
    </script>
  </body>
</html>
"""


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    # 配置
    storage_path = Path(os.getenv("EXA_PROXY_STORAGE", "./data/keys.json"))
    upstream_url = os.getenv("EXA_PROXY_UPSTREAM", "https://mcp.exa.ai/mcp")
    host = os.getenv("EXA_PROXY_HOST", "127.0.0.1")
    port = int(os.getenv("EXA_PROXY_PORT", "8080"))

    # 初始化 key manager
    key_manager = KeyManager(storage_path)
    logger.info(f"Loaded {len(key_manager.list_keys())} keys from {storage_path}")

    # 初始化代理执行器
    executor = ProxyExecutor(key_manager, upstream_url)

    # 创建 FastAPI app
    app = FastAPI(title="Exa Proxy", version="0.2.0")

    admin_auth = create_admin_auth()

    # 挂载 key 管理 API
    api_router = create_api_router(key_manager, auth_dependency=admin_auth)
    app.include_router(api_router)

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(_: str = Depends(admin_auth)) -> HTMLResponse:
        """简易管理页面"""
        html = render_admin_page(
            key_manager.get_stats(),
            [key.to_dict() for key in key_manager.list_keys()],
        )
        return HTMLResponse(content=html)

    @app.get("/health")
    def health_check():
        """健康检查"""
        stats = key_manager.get_stats()
        return {
            "status": "ok",
            "available_keys": stats["available_keys"],
            "total_keys": stats["total_keys"],
        }

    @app.api_route("/mcp", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_mcp(request: Request) -> Response:
        """MCP 代理端点：智能选择 key 并转发请求"""
        method = request.method
        path = ""  # 空路径，因为 upstream_base_url 已经包含 /mcp
        headers = dict(request.headers)
        body = await request.body()

        async def should_abort() -> bool:
            return await request.is_disconnected()

        # 移除 Host header 避免冲突
        headers.pop("host", None)

        try:
            status, resp_headers, resp_body = await executor.execute(
                method=method,
                path=path,
                headers=headers,
                body=body if body else None,
                should_abort=should_abort,
            )

            # 处理 SSE 响应
            content_type = resp_headers.get("content-type", "")
            if "text/event-stream" in content_type:

                async def stream_generator():
                    yield resp_body

                return StreamingResponse(
                    stream_generator(),
                    status_code=status,
                    headers=resp_headers,
                    media_type="text/event-stream",
                )

            # 普通响应
            return Response(
                content=resp_body,
                status_code=status,
                headers=resp_headers,
            )

        except ExecutionAbortedError as e:
            logger.info(f"Proxy request aborted: {e}")
            return Response(status_code=499)

        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return Response(
                content=str(e),
                status_code=503,
            )

    return app


def main():
    """启动服务器"""
    host = os.getenv("EXA_PROXY_HOST", "127.0.0.1")
    port = int(os.getenv("EXA_PROXY_PORT", "8080"))

    app = create_app()
    logger.info(f"Starting Exa Proxy on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
