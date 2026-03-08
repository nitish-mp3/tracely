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

export async function searchEvents(q, limit = 50) {
  const qs = new URLSearchParams({ q, limit });
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

// ─── SSE stream (robust reconnection) ──────────────────

export function subscribeEvents(onEvent, onStatus) {
  let source = null;
  let reconnectTimer = null;
  let retryDelay = 1000;
  let stopped = false;

  function connect() {
    if (stopped) return;
    const url = `${BASE}/api/events/stream`;
    source = new EventSource(url);

    source.onopen = () => {
      retryDelay = 1000;
      if (onStatus) onStatus('connected');
    };

    source.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data);
        onEvent(event);
      } catch { /* skip invalid */ }
    };

    source.onerror = () => {
      if (stopped) return;
      source.close();
      if (onStatus) onStatus('reconnecting');
      reconnectTimer = setTimeout(() => {
        retryDelay = Math.min(retryDelay * 1.5, 30000);
        connect();
      }, retryDelay);
    };
  }

  connect();

  // Also reconnect when page becomes visible again
  function handleVisibility() {
    if (!document.hidden && source && source.readyState === EventSource.CLOSED) {
      connect();
    }
  }
  document.addEventListener('visibilitychange', handleVisibility);

  return () => {
    stopped = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (source) source.close();
    document.removeEventListener('visibilitychange', handleVisibility);
  };
}
