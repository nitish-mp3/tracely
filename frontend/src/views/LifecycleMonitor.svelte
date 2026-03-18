<script>
  import { onMount } from 'svelte';
  import { getLifecycleEvents } from '../lib/api.js';

  let data = null;
  let loading = true;
  let error = null;
  let filter = 'all'; // all, starts, stops, restarts

  onMount(async () => {
    try {
      data = await getLifecycleEvents(200);
    } catch (e) {
      error = e.message;
    }
    loading = false;
  });

  function formatTime(ts) {
    if (!ts) return '—';
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }

  function formatDuration(ms) {
    if (!ms) return 'ongoing';
    const secs = Math.floor(ms / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ${secs % 60}s`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ${mins % 60}m`;
    const days = Math.floor(hrs / 24);
    return `${days}d ${hrs % 24}h`;
  }

  function getEventType(item) {
    if (item.source === 'homeassistant_start') return 'start';
    if (item.source === 'homeassistant_stop') return 'stop';
    return 'unknown';
  }

  function isStart(item) {
    return item.source === 'homeassistant_start' || item.incident_type?.includes('start');
  }

  function isStop(item) {
    return item.source === 'homeassistant_stop' || item.incident_type?.includes('stop');
  }

  $: filtered = data?.items?.filter((item) => {
    if (filter === 'starts') return isStart(item);
    if (filter === 'stops') return isStop(item);
    return true;
  }) ?? [];

  $: startCount = data?.items?.filter(isStart).length ?? 0;
  $: stopCount = data?.items?.filter(isStop).length ?? 0;
  $: restartCount = Math.max(0, stopCount - 1); // N stops = N restarts (minus initial startup)

  $: avgDowntime = filtered.length > 0 ? (
    filtered
      .filter(i => i.details?.duration_ms)
      .reduce((sum, i) => sum + (i.details.duration_ms || 0), 0) / filtered.length
  ) : 0;
</script>

<section class="lifecycle-view" aria-label="HA Lifecycle Monitor">
  {#if loading}
    <div class="loading-state">
      <div class="spinner" />
      <span>Loading lifecycle events…</span>
    </div>
  {:else if error}
    <div class="error-state">
      <h3>Failed to load</h3>
      <p>{error}</p>
    </div>
  {:else if data}
    <!-- Stats Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 18h6M2 12a10 10 0 0120 0 10 10 0 01-20 0z" /><path d="M12 6v6l4 2" /></svg>
        </div>
        <div class="stat-body">
          <span class="stat-value">{startCount}</span>
          <span class="stat-label">Starts</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 18h6M2 12a10 10 0 0120 0 10 10 0 01-20 0z" /><path d="M12 6v6l4 2" /></svg>
        </div>
        <div class="stat-body">
          <span class="stat-value">{stopCount}</span>
          <span class="stat-label">Stops</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l-4 2" /></svg>
        </div>
        <div class="stat-body">
          <span class="stat-value">{restartCount}</span>
          <span class="stat-label">Restarts</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>
        </div>
        <div class="stat-body">
          <span class="stat-value">{formatDuration(avgDowntime)}</span>
          <span class="stat-label">Avg Downtime</span>
        </div>
      </div>
    </div>

    <!-- Filter Tabs -->
    <div class="filter-tabs">
      <button
        class="filter-tab"
        class:active={filter === 'all'}
        on:click={() => (filter = 'all')}
      >
        All Events
        <span class="tab-count">{filtered.length}</span>
      </button>
      <button
        class="filter-tab"
        class:active={filter === 'starts'}
        on:click={() => (filter = 'starts')}
        class:tab-success={filter === 'starts'}
      >
        Starts
        <span class="tab-count">{startCount}</span>
      </button>
      <button
        class="filter-tab"
        class:active={filter === 'stops'}
        on:click={() => (filter = 'stops')}
        class:tab-error={filter === 'stops'}
      >
        Stops
        <span class="tab-count">{stopCount}</span>
      </button>
    </div>

    <!-- Timeline -->
    {#if filtered.length > 0}
      <div class="lifecycle-timeline">
        {#each filtered as item (item.id)}
          <div
            class="timeline-event"
            class:is-start={isStart(item)}
            class:is-stop={isStop(item)}
          >
            <div class="timeline-dot" />
            <div class="timeline-content">
              <div class="event-header">
                <span class="event-type-badge">
                  {#if isStart(item)}
                    <span class="badge-start">▲ START</span>
                  {:else if isStop(item)}
                    <span class="badge-stop">▼ STOP</span>
                  {/if}
                </span>
                <span class="event-timestamp">{formatTime(item.timestamp)}</span>
              </div>

              <div class="event-message">{item.message}</div>

              {#if item.details}
                <div class="event-details">
                  {#if item.details.reason}
                    <div class="detail-row">
                      <span class="detail-label">Reason:</span>
                      <span class="detail-value">{item.details.reason}</span>
                    </div>
                  {/if}
                  {#if item.details.duration_ms}
                    <div class="detail-row">
                      <span class="detail-label">Offline Duration:</span>
                      <span class="detail-value">{formatDuration(item.details.duration_ms)}</span>
                    </div>
                  {/if}
                </div>
              {/if}

              <div class="event-metrics">
                <span class="metric" title="CPU usage at event time">
                  <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 4h2v2H4zM7 4h2v2H7zM10 4h2v2h-2zM4 7h2v2H4zM7 7h2v2H7zM10 7h2v2h-2z" /></svg>
                  {Number(item.cpu_percent || 0).toFixed(1)}%
                </span>
                <span class="metric" title="Memory usage at event time">
                  <svg viewBox="0 0 16 16" fill="currentColor"><rect x="2" y="4" width="12" height="8" rx="1" /><path d="M6 12h4" /></svg>
                  {Number(item.memory_percent || 0).toFixed(1)}%
                </span>
                <span class="metric" title="Memory RSS (MB)">
                  <svg viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="5" /></svg>
                  {Number(item.memory_rss_mb || 0).toFixed(1)} MB
                </span>
                <span class="metric" title="Event queue depth">
                  <svg viewBox="0 0 16 16" fill="currentColor"><path d="M2 3h12v10H2z" /></svg>
                  Queue: {item.event_queue_depth || 0}
                </span>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <div class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M12 1C6.5 1 2 5.5 2 11s4.5 10 10 10 10-4.5 10-10S17.5 1 12 1z" />
          <path d="M12 7v4M12 15h.01" />
        </svg>
        <p>No lifecycle events match this filter.</p>
      </div>
    {/if}
  {/if}
</section>

<style>
  .lifecycle-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
    background: var(--color-bg);
    padding: var(--sp-5);
    gap: var(--sp-4);
  }

  /* Loading / Error States */
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
    width: 40px;
    height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .error-state h3 {
    color: var(--color-text);
    margin: 0;
  }

  /* Stats Grid */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--sp-3);
  }

  .stat-card {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    padding: var(--sp-4);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    transition: all var(--duration-fast);
  }

  .stat-card:hover {
    border-color: var(--color-border-hover);
    background: var(--color-surface-hover);
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
  }

  .stat-icon {
    width: 40px;
    height: 40px;
    flex-shrink: 0;
    color: var(--color-primary);
    opacity: 0.7;
  }

  .stat-body {
    display: flex;
    flex-direction: column;
  }

  .stat-value {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--color-text);
  }

  .stat-label {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  /* Filter Tabs */
  .filter-tabs {
    display: flex;
    gap: var(--sp-2);
    border-bottom: 1px solid var(--color-border);
    padding-bottom: var(--sp-3);
  }

  .filter-tab {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: var(--sp-2) var(--sp-3);
    border-radius: var(--radius-md) var(--radius-md) 0 0;
    border-bottom: 3px solid transparent;
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: all var(--duration-fast);
  }

  .filter-tab:hover {
    color: var(--color-text);
  }

  .filter-tab.active {
    color: var(--color-primary);
    border-bottom-color: var(--color-primary);
  }

  .filter-tab.tab-success.active {
    color: var(--color-success, #22c55e);
    border-bottom-color: var(--color-success, #22c55e);
  }

  .filter-tab.tab-error.active {
    color: var(--color-error, #ef4444);
    border-bottom-color: var(--color-error, #ef4444);
  }

  .tab-count {
    font-size: var(--text-xs);
    opacity: 0.7;
    background: var(--color-bg-elevated);
    padding: 2px 6px;
    border-radius: var(--radius-full);
  }

  /* Timeline */
  .lifecycle-timeline {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    position: relative;
  }

  .lifecycle-timeline::before {
    content: '';
    position: absolute;
    left: 12px;
    top: 24px;
    bottom: 0;
    width: 2px;
    background: linear-gradient(180deg, var(--color-primary) 0%, transparent 100%);
    opacity: 0.2;
  }

  .timeline-event {
    display: flex;
    gap: var(--sp-3);
    position: relative;
    padding-left: var(--sp-3);
  }

  .timeline-dot {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 3px solid var(--color-primary);
    background: var(--color-surface);
    flex-shrink: 0;
    margin-top: 2px;
    box-shadow: 0 0 0 3px rgba(79, 172, 254, 0.1);
    z-index: 1;
  }

  .timeline-event.is-start .timeline-dot {
    border-color: var(--color-success, #22c55e);
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.1);
  }

  .timeline-event.is-stop .timeline-dot {
    border-color: var(--color-error, #ef4444);
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
  }

  .timeline-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 2px;
  }

  .event-header {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    flex-wrap: wrap;
  }

  .event-type-badge {
    display: inline-flex;
    align-items: center;
  }

  .badge-start, .badge-stop {
    font-size: var(--text-xs);
    font-weight: 700;
    padding: 3px 10px;
    border-radius: var(--radius-full);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .badge-start {
    color: var(--color-success, #22c55e);
    background: rgba(34, 197, 94, 0.1);
  }

  .badge-stop {
    color: var(--color-error, #ef4444);
    background: rgba(239, 68, 68, 0.1);
  }

  .event-timestamp {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--color-text-muted);
    margin-left: auto;
  }

  .event-message {
    font-size: var(--text-sm);
    color: var(--color-text-secondary);
    line-height: 1.4;
  }

  .event-details {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: var(--sp-2);
    background: var(--color-bg-elevated);
    border-radius: var(--radius-md);
    border-left: 3px solid var(--color-border);
  }

  .detail-row {
    display: flex;
    gap: var(--sp-2);
    font-size: var(--text-xs);
  }

  .detail-label {
    color: var(--color-text-muted);
    font-weight: 600;
    min-width: 120px;
  }

  .detail-value {
    color: var(--color-text);
    font-family: var(--font-mono);
    font-weight: 500;
  }

  .event-metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: var(--text-xs);
    padding: var(--sp-2);
    background: var(--color-bg-elevated);
    border-radius: var(--radius-md);
  }

  .metric {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--color-text-muted);
    font-weight: 500;
  }

  .metric svg {
    width: 12px;
    height: 12px;
    opacity: 0.6;
  }

  .metric:hover {
    color: var(--color-text);
  }

  /* Empty State */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--sp-4);
    padding: var(--sp-8);
    color: var(--color-text-muted);
    text-align: center;
  }

  .empty-state svg {
    width: 48px;
    height: 48px;
    opacity: 0.4;
  }

  .empty-state p {
    margin: 0;
    font-size: var(--text-sm);
  }

  /* Responsive */
  @media (max-width: 768px) {
    .lifecycle-view {
      padding: var(--sp-3);
      gap: var(--sp-3);
    }

    .stats-grid {
      grid-template-columns: repeat(2, 1fr);
      gap: var(--sp-2);
    }

    .stat-card {
      padding: var(--sp-3);
      gap: var(--sp-2);
    }

    .stat-icon {
      width: 32px;
      height: 32px;
    }

    .stat-value {
      font-size: var(--text-md);
    }

    .filter-tabs {
      gap: var(--sp-1);
      padding-bottom: var(--sp-2);
    }

    .filter-tab {
      padding: var(--sp-1) var(--sp-2);
      font-size: var(--text-xs);
    }

    .event-timestamp {
      display: none;
    }

    .event-header {
      gap: 4px;
    }
  }

  @media (max-width: 480px) {
    .lifecycle-view {
      padding: var(--sp-2);
      gap: var(--sp-2);
    }

    .stats-grid {
      grid-template-columns: 1fr 1fr;
    }

    .stat-card {
      padding: var(--sp-2);
    }

    .stat-value {
      font-size: var(--text-base);
    }

    .filter-tabs {
      flex-wrap: wrap;
    }

    .timeline-event {
      gap: var(--sp-2);
    }

    .event-metrics {
      flex-direction: column;
      gap: 8px;
    }

    .detail-label {
      min-width: 100px;
    }
  }
</style>
