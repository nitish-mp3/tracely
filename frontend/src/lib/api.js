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
  const {
    timeoutMs = 15000,
    headers: customHeaders = {},
    ...fetchOptions
  } = options;

  const url = `${BASE}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let res;
  try {
    res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...customHeaders },
      signal: controller.signal,
      ...fetchOptions,
    });
  } catch (err) {
    if (err && err.name === 'AbortError') {
      throw new Error(`API timeout after ${timeoutMs}ms for ${endpoint}`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

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

export async function getLifecycleEvents(limit = 100) {
  const qs = new URLSearchParams({ limit });
  return request(`/api/lifecycle?${qs}`);
}

export async function getNetworkDevices(scan = false) {
  return request(`/api/network-devices${scan ? '?scan=true' : ''}`, {
    timeoutMs: scan ? 30000 : 15000,
  });
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

// ─── KNX ───────────────────────────────────────────────

export async function getKnxTelegrams(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  }
  return request(`/api/knx/telegrams${qs.toString() ? '?' + qs : ''}`);
}

export async function getKnxActivity(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  }
  return request(`/api/knx/activity${qs.toString() ? '?' + qs : ''}`);
}

export async function getProtocolActivity(protocol, params = {}) {
  const qs = new URLSearchParams({ protocol });
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  }
  return request(`/api/protocol/activity?${qs}`);
}

export async function getKnxGroupAddresses(limit = 200) {
  return request(`/api/knx/group-addresses?limit=${limit}`);
}

export async function getKnxFlow(groupAddress, aroundTs, windowMs = 5000) {
  const qs = new URLSearchParams({ window_ms: windowMs });
  if (aroundTs) qs.set('around', aroundTs);
  return request(`/api/knx/flow/${encodeURIComponent(groupAddress)}?${qs}`);
}

// KNX SSE (separate singleton from the main events SSE)
let _knxSseSource = null;
let _knxSseReconnectTimer = null;
let _knxSseRetryDelay = 1000;
let _knxSseStopped = false;
let _knxSseListeners = new Set();

function _knxSseConnect() {
  if (_knxSseStopped) return;
  const url = `${BASE}/api/knx/stream`;
  _knxSseSource = new EventSource(url);
  _knxSseSource.onmessage = (msg) => {
    try {
      const tg = JSON.parse(msg.data);
      _knxSseListeners.forEach(fn => fn(tg));
    } catch { /* skip */ }
  };
  _knxSseSource.onerror = () => {
    if (_knxSseStopped) return;
    _knxSseSource.close();
    _knxSseReconnectTimer = setTimeout(() => {
      _knxSseRetryDelay = Math.min(_knxSseRetryDelay * 1.5, 30000);
      _knxSseConnect();
    }, _knxSseRetryDelay);
  };
}

/** Subscribe to live KNX telegrams. Returns unsubscribe fn. */
export function subscribeKnxEvents(onTelegram) {
  if (_knxSseListeners.size === 0) {
    _knxSseConnect(); // lazy-start
  }
  _knxSseListeners.add(onTelegram);
  return () => {
    _knxSseListeners.delete(onTelegram);
    if (_knxSseListeners.size === 0 && _knxSseSource) {
      _knxSseStopped = true;
      _knxSseSource.close();
      _knxSseSource = null;
      _knxSseStopped = false; // allow re-start next time
    }
  };
}

// ─── Alerts / Notifications ────────────────────────────

export async function getAlerts(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  }
  return request(`/api/alerts${qs.toString() ? '?' + qs : ''}`);
}

export async function getAlertCounts() {
  return request('/api/alerts/counts');
}

export async function acknowledgeAlert(alertId) {
  return request(`/api/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
    method: 'POST',
  });
}

export async function acknowledgeAllAlerts() {
  return request('/api/alerts/acknowledge-all', { method: 'POST' });
}

export async function getOfflineDevices() {
  return request('/api/devices/offline');
}

// Alert SSE (separate singleton)
let _alertSseSource = null;
let _alertSseReconnectTimer = null;
let _alertSseRetryDelay = 1000;
let _alertSseStopped = false;
let _alertSseListeners = new Set();

function _alertSseConnect() {
  if (_alertSseStopped) return;
  const url = `${BASE}/api/alerts/stream`;
  _alertSseSource = new EventSource(url);
  _alertSseSource.onmessage = (msg) => {
    try {
      const alert = JSON.parse(msg.data);
      _alertSseListeners.forEach(fn => fn(alert));
    } catch { /* skip */ }
  };
  _alertSseSource.onerror = () => {
    if (_alertSseStopped) return;
    _alertSseSource.close();
    _alertSseReconnectTimer = setTimeout(() => {
      _alertSseRetryDelay = Math.min(_alertSseRetryDelay * 1.5, 30000);
      _alertSseConnect();
    }, _alertSseRetryDelay);
  };
}

/** Subscribe to live alert events. Returns unsubscribe fn. */
export function subscribeAlerts(onAlert) {
  if (_alertSseListeners.size === 0) {
    _alertSseConnect();
  }
  _alertSseListeners.add(onAlert);
  return () => {
    _alertSseListeners.delete(onAlert);
    if (_alertSseListeners.size === 0 && _alertSseSource) {
      _alertSseStopped = true;
      _alertSseSource.close();
      _alertSseSource = null;
      _alertSseStopped = false;
    }
  };
}

// ─── Supervisor ────────────────────────────────────────

export async function getSupervisorInfo() {
  return request('/api/supervisor');
}

// ─── Incidents ─────────────────────────────────────────

export async function getIncidents(params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  }
  return request(`/api/incidents${qs.toString() ? '?' + qs : ''}`);
}

export async function getLogs(limit = 200) {
  return request(`/api/logs?limit=${limit}`);
}
