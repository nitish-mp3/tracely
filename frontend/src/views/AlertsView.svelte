<script>
  import { onMount, onDestroy } from 'svelte';
  import { getAlerts, getAlertCounts, acknowledgeAlert, acknowledgeAllAlerts, getOfflineDevices, subscribeAlerts } from '../lib/api.js';
  import { addToast } from '../stores/config.js';

  let alerts = [];
  let total = 0;
  let counts = { total: 0, unread: 0, critical_unread: 0 };
  let offlineDevices = [];
  let loading = true;
  let error = null;
  let page = 1;
  const limit = 30;

  let filter = 'all'; // all | unread | critical | warning | info
  let unsubscribe = null;
  let refreshInterval = null;

  onMount(async () => {
    await loadAll();
    unsubscribe = subscribeAlerts(handleLiveAlert);
    refreshInterval = setInterval(refreshCounts, 30000);
  });

  onDestroy(() => {
    if (unsubscribe) unsubscribe();
    if (refreshInterval) clearInterval(refreshInterval);
  });

  async function loadAll() {
    loading = true;
    error = null;
    try {
      // Don't let counts/offline failures block the main alert list
      const [alertResult] = await Promise.allSettled([loadAlerts(), refreshCounts(), loadOffline()]);
      if (alertResult.status === 'rejected') {
        error = alertResult.reason?.message || 'Failed to load alerts';
      }
    } catch (e) {
      error = e.message;
    }
    loading = false;
  }

  async function loadAlerts() {
    const params = { page, limit };
    if (filter === 'unread') params.acknowledged = false;
    else if (filter === 'critical') params.severity = 'critical';
    else if (filter === 'warning') params.severity = 'warning';
    else if (filter === 'info') params.severity = 'info';

    const data = await getAlerts(params);
    alerts = data.items || [];
    total = data.total || 0;
  }

  async function refreshCounts() {
    try {
      counts = await getAlertCounts();
    } catch { /* silent */ }
  }

  async function loadOffline() {
    try {
      const data = await getOfflineDevices();
      offlineDevices = data.devices || [];
    } catch { /* silent */ }
  }

  function handleLiveAlert(alert) {
    alerts = [alert, ...alerts].slice(0, limit);
    counts = { ...counts, total: counts.total + 1, unread: counts.unread + 1 };
    if (alert.severity === 'critical') {
      counts.critical_unread = (counts.critical_unread || 0) + 1;
    }
  }

  async function handleAcknowledge(id) {
    try {
      await acknowledgeAlert(id);
      alerts = alerts.map(a => a.id === id ? { ...a, acknowledged: true } : a);
      await refreshCounts();
    } catch (e) {
      addToast('Failed to acknowledge: ' + e.message, 'error');
    }
  }

  async function handleAcknowledgeAll() {
    try {
      await acknowledgeAllAlerts();
      alerts = alerts.map(a => ({ ...a, acknowledged: true }));
      await refreshCounts();
      addToast('All alerts acknowledged', 'success');
    } catch (e) {
      addToast('Failed: ' + e.message, 'error');
    }
  }

  function handleFilterChange(f) {
    filter = f;
    page = 1;
    loadAlerts();
  }

  function handlePageChange(dir) {
    page += dir;
    if (page < 1) page = 1;
    loadAlerts();
  }

  function formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function severityColor(sev) {
    if (sev === 'critical') return 'var(--color-error)';
    if (sev === 'warning') return 'var(--color-warning)';
    return 'var(--color-info)';
  }

  function severityBg(sev) {
    if (sev === 'critical') return 'var(--color-error-soft)';
    if (sev === 'warning') return 'var(--color-warning-soft)';
    return 'var(--color-info-soft)';
  }

  $: totalPages = Math.max(1, Math.ceil(total / limit));
</script>

<section class="alerts-view" aria-label="Alerts & Notifications">
  {#if loading}
    <div class="loading-state">
      <div class="spinner" />
      <span>Loading alerts…</span>
    </div>
  {:else if error}
    <div class="error-state">
      <h3>Failed to load</h3>
      <p>{error}</p>
      <button class="retry-btn" on:click={loadAll}>Retry</button>
    </div>
  {:else}
    <!-- Summary Strip -->
    <div class="summary-strip">
      <div class="summary-card total">
        <div class="summary-icon">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 2L2 18h16L10 2z"/><path d="M10 8v4M10 14h.01"/></svg>
        </div>
        <div class="summary-body">
          <span class="summary-value">{counts.total}</span>
          <span class="summary-label">Total Alerts</span>
        </div>
      </div>
      <div class="summary-card unread">
        <div class="summary-icon">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="7"/><path d="M10 6v4l3 2"/></svg>
        </div>
        <div class="summary-body">
          <span class="summary-value">{counts.unread}</span>
          <span class="summary-label">Unread</span>
        </div>
      </div>
      <div class="summary-card critical">
        <div class="summary-icon">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="7"/><path d="M7.5 7.5l5 5M12.5 7.5l-5 5"/></svg>
        </div>
        <div class="summary-body">
          <span class="summary-value">{counts.critical_unread}</span>
          <span class="summary-label">Critical</span>
        </div>
      </div>
      <div class="summary-card offline">
        <div class="summary-icon">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="7"/><path d="M10 6v8M6 10h8"/></svg>
        </div>
        <div class="summary-body">
          <span class="summary-value">{offlineDevices.length}</span>
          <span class="summary-label">Offline Now</span>
        </div>
      </div>
    </div>

    <!-- Offline Devices Banner -->
    {#if offlineDevices.length > 0}
      <div class="offline-banner">
        <div class="banner-header">
          <svg class="banner-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 5v3M8 10h.01"/></svg>
          <span class="banner-title">{offlineDevices.length} device{offlineDevices.length !== 1 ? 's' : ''} currently offline</span>
        </div>
        <div class="offline-chips">
          {#each offlineDevices as dev}
            <span class="offline-chip" title={dev.entity_id}>
              <span class="offline-dot" />
              {dev.friendly_name || dev.entity_id}
              {#if dev.integration}
                <span class="chip-integration">{dev.integration}</span>
              {/if}
            </span>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Filter Tabs + Actions -->
    <div class="toolbar">
      <div class="filter-tabs">
        <button class="ftab" class:active={filter === 'all'} on:click={() => handleFilterChange('all')}>
          All
          <span class="ftab-count">{counts.total}</span>
        </button>
        <button class="ftab" class:active={filter === 'unread'} on:click={() => handleFilterChange('unread')}>
          Unread
          {#if counts.unread > 0}<span class="ftab-count accent">{counts.unread}</span>{/if}
        </button>
        <button class="ftab" class:active={filter === 'critical'} on:click={() => handleFilterChange('critical')}>
          Critical
          {#if counts.critical_unread > 0}<span class="ftab-count critical">{counts.critical_unread}</span>{/if}
        </button>
        <button class="ftab" class:active={filter === 'warning'} on:click={() => handleFilterChange('warning')}>Warning</button>
        <button class="ftab" class:active={filter === 'info'} on:click={() => handleFilterChange('info')}>Info</button>
      </div>
      <div class="toolbar-actions">
        {#if counts.unread > 0}
          <button class="ack-all-btn" on:click={handleAcknowledgeAll}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 8l4 4 8-8"/></svg>
            Acknowledge All
          </button>
        {/if}
        <button class="refresh-btn" on:click={loadAll} aria-label="Refresh">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 8a6 6 0 0111.5-2.5M14 8a6 6 0 01-11.5 2.5"/><path d="M14 2v4h-4M2 14v-4h4"/></svg>
        </button>
      </div>
    </div>

    <!-- Alert List -->
    {#if alerts.length > 0}
      <div class="alert-list">
        {#each alerts as alert (alert.id)}
          <div
            class="alert-card"
            class:acknowledged={alert.acknowledged}
            class:severity-critical={alert.severity === 'critical'}
            class:severity-warning={alert.severity === 'warning'}
            class:severity-info={alert.severity === 'info'}
          >
            <div class="alert-severity-bar" style="background: {severityColor(alert.severity)}" />
            <div class="alert-body">
              <div class="alert-top-row">
                <span class="alert-severity-badge" style="background: {severityBg(alert.severity)}; color: {severityColor(alert.severity)}">
                  {alert.severity?.toUpperCase()}
                </span>
                <span class="alert-type-label">{alert.alert_type?.replace(/_/g, ' ')}</span>
                <span class="alert-time">{formatTime(alert.timestamp)}</span>
                {#if !alert.acknowledged}
                  <span class="unread-dot" />
                {/if}
              </div>
              <h4 class="alert-title">{alert.title}</h4>
              <p class="alert-message">{alert.message}</p>
              {#if alert.entity_id || alert.integration}
                <div class="alert-meta">
                  {#if alert.entity_id}
                    <span class="meta-tag entity-tag">{alert.entity_id}</span>
                  {/if}
                  {#if alert.integration}
                    <span class="meta-tag integration-tag">{alert.integration}</span>
                  {/if}
                </div>
              {/if}
              {#if alert.details && Object.keys(alert.details).length > 0}
                <details class="alert-details-expand">
                  <summary>Details</summary>
                  <pre class="details-json">{JSON.stringify(alert.details, null, 2)}</pre>
                </details>
              {/if}
            </div>
            <div class="alert-actions">
              {#if !alert.acknowledged}
                <button class="ack-btn" on:click={() => handleAcknowledge(alert.id)} title="Acknowledge">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 8l3.5 3.5L13 5"/></svg>
                </button>
              {:else}
                <span class="ack-check" title="Acknowledged">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 8l3.5 3.5L13 5"/></svg>
                </span>
              {/if}
            </div>
          </div>
        {/each}
      </div>

      <!-- Pagination -->
      {#if totalPages > 1}
        <div class="pagination">
          <button class="page-btn" disabled={page <= 1} on:click={() => handlePageChange(-1)}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 3L5 8l5 5"/></svg>
          </button>
          <span class="page-info">Page {page} of {totalPages}</span>
          <button class="page-btn" disabled={page >= totalPages} on:click={() => handlePageChange(1)}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 3l5 5-5 5"/></svg>
          </button>
        </div>
      {/if}
    {:else}
      <div class="empty-state">
        <div class="empty-icon">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="24" cy="24" r="18" opacity="0.3"/>
            <path d="M24 16v8M24 28h.02"/>
          </svg>
        </div>
        <h3>No alerts</h3>
        <p>Everything is looking good! Alerts will appear here when devices go offline or critical events occur.</p>
      </div>
    {/if}
  {/if}
</section>

<style>
  .alerts-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
    background: var(--color-bg);
    padding: var(--sp-5);
    gap: var(--sp-4);
    width: 100%;
  }

  /* Loading / Error */
  .loading-state, .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--sp-3);
    padding: var(--sp-8);
    color: var(--color-text-muted);
    text-align: center;
  }
  .spinner {
    width: 40px; height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .retry-btn {
    padding: var(--sp-2) var(--sp-4);
    border-radius: var(--radius-md);
    background: var(--color-primary);
    color: white;
    font-weight: 600;
    font-size: var(--text-sm);
  }
  .retry-btn:hover { background: var(--color-primary-hover); }

  /* Summary Strip */
  .summary-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--sp-3);
  }
  .summary-card {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    padding: var(--sp-4);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    transition: all var(--duration-fast);
  }
  .summary-card:hover {
    border-color: var(--color-border-hover);
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
  }
  .summary-card.critical .summary-icon { color: var(--color-error); }
  .summary-card.unread .summary-icon { color: var(--color-warning); }
  .summary-card.offline .summary-icon { color: var(--color-info); }
  .summary-card.total .summary-icon { color: var(--color-primary); }
  .summary-icon {
    width: 36px; height: 36px; flex-shrink: 0; opacity: 0.8;
  }
  .summary-icon svg { width: 100%; height: 100%; }
  .summary-body { display: flex; flex-direction: column; }
  .summary-value {
    font-size: var(--text-xl); font-weight: 700; color: var(--color-text);
    line-height: 1.2;
  }
  .summary-label {
    font-size: var(--text-2xs); font-weight: 600; color: var(--color-text-muted);
    text-transform: uppercase; letter-spacing: 0.04em;
  }

  /* Offline Banner */
  .offline-banner {
    padding: var(--sp-4);
    background: var(--color-error-soft);
    border: 1px solid rgba(248,113,113,.2);
    border-radius: var(--radius-lg);
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .banner-header {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .banner-icon {
    width: 18px; height: 18px; color: var(--color-error); flex-shrink: 0;
  }
  .banner-title {
    font-size: var(--text-sm); font-weight: 700; color: var(--color-error);
  }
  .offline-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .offline-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: var(--radius-full);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--color-text-secondary);
  }
  .offline-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--color-error);
    animation: pulse-offline 2s infinite;
  }
  @keyframes pulse-offline {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  .chip-integration {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: var(--radius-full);
    background: var(--color-bg-elevated);
    color: var(--color-text-muted);
    font-weight: 600;
    text-transform: uppercase;
  }

  /* Toolbar */
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-3);
    flex-wrap: wrap;
  }
  .filter-tabs {
    display: flex;
    gap: 2px;
    padding: 3px;
    background: var(--color-bg-elevated);
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
  }
  .ftab {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 14px;
    border-radius: calc(var(--radius-md) - 2px);
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .ftab:hover { color: var(--color-text-secondary); }
  .ftab.active {
    color: var(--color-text);
    background: var(--color-surface);
    box-shadow: var(--shadow-xs);
  }
  .ftab-count {
    font-size: var(--text-2xs);
    padding: 1px 6px;
    border-radius: var(--radius-full);
    background: var(--color-surface-hover);
    color: var(--color-text-muted);
    font-weight: 600;
  }
  .ftab-count.accent { background: var(--color-warning-soft); color: var(--color-warning); }
  .ftab-count.critical { background: var(--color-error-soft); color: var(--color-error); }
  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .ack-all-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 14px;
    border-radius: var(--radius-md);
    background: var(--color-primary-soft);
    color: var(--color-primary);
    font-size: var(--text-sm);
    font-weight: 600;
    border: 1px solid rgba(21,184,166,.2);
    transition: all var(--duration-fast);
  }
  .ack-all-btn svg { width: 14px; height: 14px; }
  .ack-all-btn:hover {
    background: var(--color-primary);
    color: white;
  }
  .refresh-btn {
    width: 34px; height: 34px;
    display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-bg-elevated);
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .refresh-btn svg { width: 16px; height: 16px; }
  .refresh-btn:hover {
    color: var(--color-text);
    border-color: var(--color-border-hover);
  }

  /* Alert List */
  .alert-list {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .alert-card {
    display: flex;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    transition: all var(--duration-fast);
  }
  .alert-card:hover {
    border-color: var(--color-border-hover);
    box-shadow: var(--shadow-sm);
  }
  .alert-card.acknowledged {
    opacity: 0.6;
  }
  .alert-severity-bar {
    width: 4px;
    flex-shrink: 0;
  }
  .alert-body {
    flex: 1;
    padding: var(--sp-3) var(--sp-4);
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .alert-top-row {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    flex-wrap: wrap;
  }
  .alert-severity-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .alert-type-label {
    font-size: var(--text-2xs);
    color: var(--color-text-muted);
    text-transform: capitalize;
  }
  .alert-time {
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    color: var(--color-text-muted);
    margin-left: auto;
  }
  .unread-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--color-primary);
    flex-shrink: 0;
    animation: pulse-offline 2s infinite;
  }
  .alert-title {
    font-size: var(--text-sm);
    font-weight: 700;
    color: var(--color-text);
    margin: 0;
    line-height: var(--lh-tight);
  }
  .alert-message {
    font-size: var(--text-xs);
    color: var(--color-text-secondary);
    line-height: var(--lh-normal);
    margin: 0;
  }
  .alert-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .meta-tag {
    font-size: 10px;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    font-weight: 500;
    font-family: var(--font-mono);
  }
  .entity-tag {
    background: var(--color-primary-soft);
    color: var(--color-primary);
  }
  .integration-tag {
    background: var(--color-info-soft);
    color: var(--color-info);
  }
  .alert-details-expand {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    margin-top: 2px;
  }
  .alert-details-expand summary {
    cursor: pointer;
    font-weight: 600;
    user-select: none;
  }
  .alert-details-expand summary:hover {
    color: var(--color-text);
  }
  .details-json {
    margin-top: var(--sp-2);
    padding: var(--sp-2);
    background: var(--color-bg-elevated);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.4;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    color: var(--color-text-secondary);
    max-height: 200px;
    overflow-y: auto;
  }
  .alert-actions {
    display: flex;
    align-items: flex-start;
    padding: var(--sp-3) var(--sp-3) var(--sp-3) 0;
  }
  .ack-btn {
    width: 32px; height: 32px;
    display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-bg-elevated);
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
    cursor: pointer;
  }
  .ack-btn svg { width: 14px; height: 14px; }
  .ack-btn:hover {
    color: var(--color-success);
    border-color: var(--color-success);
    background: var(--color-success-soft);
  }
  .ack-check {
    width: 32px; height: 32px;
    display: flex; align-items: center; justify-content: center;
    color: var(--color-success);
    opacity: 0.5;
  }
  .ack-check svg { width: 14px; height: 14px; }

  /* Pagination */
  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-3);
    padding: var(--sp-3) 0;
  }
  .page-btn {
    width: 32px; height: 32px;
    display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-bg-elevated);
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .page-btn svg { width: 14px; height: 14px; }
  .page-btn:hover:not(:disabled) {
    color: var(--color-text);
    border-color: var(--color-border-hover);
  }
  .page-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
  .page-info {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    font-weight: 500;
  }

  /* Empty State */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--sp-3);
    padding: var(--sp-10);
    text-align: center;
  }
  .empty-icon svg {
    width: 64px; height: 64px;
    color: var(--color-text-muted);
    opacity: 0.3;
  }
  .empty-state h3 {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--color-text);
    margin: 0;
  }
  .empty-state p {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
    max-width: 400px;
    margin: 0;
    line-height: var(--lh-relaxed);
  }

  /* Responsive */
  @media (max-width: 768px) {
    .alerts-view {
      padding: var(--sp-3);
      gap: var(--sp-3);
    }
    .summary-strip {
      grid-template-columns: repeat(2, 1fr);
      gap: var(--sp-2);
    }
    .summary-card {
      padding: var(--sp-3);
      gap: var(--sp-2);
    }
    .summary-icon { width: 28px; height: 28px; }
    .summary-value { font-size: var(--text-lg); }
    .toolbar {
      flex-direction: column;
      align-items: stretch;
    }
    .filter-tabs {
      overflow-x: auto;
      scrollbar-width: none;
    }
    .filter-tabs::-webkit-scrollbar { display: none; }
    .toolbar-actions {
      justify-content: flex-end;
    }
    .alert-time { display: none; }
  }

  @media (max-width: 480px) {
    .alerts-view {
      padding: var(--sp-2);
      gap: var(--sp-2);
    }
    .summary-strip {
      grid-template-columns: 1fr 1fr;
    }
    .summary-card { padding: var(--sp-2); }
    .summary-value { font-size: var(--text-md); }
    .ftab {
      padding: 5px 10px;
      font-size: var(--text-xs);
    }
    .offline-chips {
      max-height: 80px;
      overflow-y: auto;
    }
    .alert-card {
      border-radius: var(--radius-md);
    }
    .alert-body {
      padding: var(--sp-2) var(--sp-3);
    }
    .ack-all-btn {
      font-size: var(--text-xs);
      padding: 5px 10px;
    }
    .alert-details-expand { display: none; }
  }
</style>
