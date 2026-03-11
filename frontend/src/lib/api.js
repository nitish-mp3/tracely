/**
 * Tracely REST API client — all backend communication goes through here.
 * Uses native fetch with relative URLs for HA ingress compatibility.
 */

/** Detect the base path (handles HA ingress proxy). */
function getBasePath() {
  const path = window.location.pathname;
  const match = path.match(/^(\/api\/hassio_ingress\/[^/]+)/);
  return match ? match[1] : '';
}

const BASE = getBasePath();

async function request(endpoint, options = {}) {
  const url = `${BASE}${endpoint}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ─── Events ────────────────────────────────────────────

export async function getEvents(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  }
  const query = qs.toString();
  return request(`/api/events${query ? '?' + query : ''}`);
}

export async function getEvent(id) {
  return request(`/api/events/${encodeURIComponent(id)}`);
}

export async function bookmarkEvent(id, note = '') {
  return request(`/api/events/${encodeURIComponent(id)}/bookmark`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
}

// ─── Search ────────────────────────────────────────────

export async function searchEvents(q, limit = 50, offset = 0, extraParams = {}) {
  const qs = new URLSearchParams({ q, limit, offset });
  for (const [k, v] of Object.entries(extraParams)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  }
  return request(`/api/search?${qs}`);
}

// ─── Trees ─────────────────────────────────────────────

export async function getTrees() {
  return request('/api/trees');
}

// ─── Entities ──────────────────────────────────────────

export async function getEntities() {
  return request('/api/entities');
}

export async function getEntityHistory(entityId, limit = 100) {
  const qs = new URLSearchParams({ limit });
  return request(`/api/entities/${encodeURIComponent(entityId)}/history?${qs}`);
}

// ─── Health ────────────────────────────────────────────

export async function getHealth() {
  return request('/health');
}

// ─── Stats ──────────────────────────────────────────────

export async function getStats() {
  return request('/api/stats');
}

// ─── System Health ──────────────────────────────────────

export async function getSystemHealth() {
  return request('/api/system');
}

// ─── SSE stream (global singleton with robust reconnection) ─

let _sseSource = null;
let _sseReconnectTimer = null;
let _sseRetryDelay = 1000;
let _sseStopped = false;
let _sseListeners = new Set();
let _sseStatusListeners = new Set();

function _sseConnect() {
  if (_sseStopped) return;
  const url = `${BASE}/api/events/stream`;
  _sseSource = new EventSource(url);

  _sseSource.onopen = () => {
    _sseRetryDelay = 1000;
    _sseStatusListeners.forEach(fn => fn('connected'));
  };

  _sseSource.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data);
      _sseListeners.forEach(fn => fn(event));
    } catch { /* skip invalid */ }
  };

  _sseSource.onerror = () => {
    if (_sseStopped) return;
    _sseSource.close();
    _sseStatusListeners.forEach(fn => fn('reconnecting'));
    _sseReconnectTimer = setTimeout(() => {
      _sseRetryDelay = Math.min(_sseRetryDelay * 1.5, 30000);
      _sseConnect();
    }, _sseRetryDelay);
  };
}

function _handleVisibility() {
  if (!document.hidden && _sseSource && _sseSource.readyState === EventSource.CLOSED) {
    _sseConnect();
  }
}
document.addEventListener('visibilitychange', _handleVisibility);

// Auto-start SSE on module load
_sseConnect();

/**
 * Subscribe to SSE events. Returns unsubscribe function.
 * This is a global singleton — SSE connection stays alive
 * regardless of component lifecycle.
 */
export function subscribeEvents(onEvent, onStatus) {
  _sseListeners.add(onEvent);
  if (onStatus) {
    _sseStatusListeners.add(onStatus);
    // Report current status immediately
    if (_sseSource) {
      onStatus(_sseSource.readyState === EventSource.OPEN ? 'connected' : 'reconnecting');
    }
  }

  return () => {
    _sseListeners.delete(onEvent);
    if (onStatus) _sseStatusListeners.delete(onStatus);
  };
}
