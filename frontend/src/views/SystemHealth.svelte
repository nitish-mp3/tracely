<script>
  import { onMount } from 'svelte';
  import DomainIcon from '../components/DomainIcon.svelte';
  import { getSystemHealth } from '../lib/api.js';
  import { selectedEntityTag } from '../stores/events.js';

  let data = null;
  let loading = true;
  let error = null;

  onMount(async () => {
    try {
      data = await getSystemHealth();
    } catch (e) {
      error = e.message;
    }
    loading = false;
  });

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

  function formatTime(ts) {
    if (!ts) return '—';
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }

  function handleEntityClick(entityId) {
    $selectedEntityTag = entityId;
  }

  $: sortedDeviceTypes = data?.device_types
    ? Object.entries(data.device_types).sort((a, b) => b[1] - a[1])
    : [];
</script>

<section class="health-view" aria-label="System Health">
  {#if loading}
    <div class="loading-state">
      <div class="spinner" />
      <span>Loading system health…</span>
    </div>
  {:else if error}
    <div class="error-state">
      <h3>Failed to load</h3>
      <p>{error}</p>
    </div>
  {:else if data}
    <!-- KPI Cards -->
    <div class="kpi-grid">
      <div class="kpi-card" class:kpi-ok={data.ws_connected} class:kpi-warn={!data.ws_connected}>
        <div class="kpi-icon">
          {#if data.ws_connected}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12.55a11 11 0 0114.08 0M8.53 16.11a6 6 0 016.95 0M12 20h.01" /></svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 1l22 22M16.72 11.06A10.94 10.94 0 0119 12.55M5 12.55a11 11 0 014.17-2.56M10.71 5.05A16 16 0 0122.56 9M1.42 9a15.91 15.91 0 014.7-2.88M8.53 16.11a6 6 0 016.95 0M12 20h.01" /></svg>
          {/if}
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{data.ws_connected ? 'Connected' : 'Disconnected'}</span>
          <span class="kpi-label">WebSocket</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{data.total_entities}</span>
          <span class="kpi-label">Total Entities</span>
        </div>
      </div>

      <div class="kpi-card" class:kpi-warn={data.unavailable_count > 0}>
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10" /><path d="M15 9l-6 6M9 9l6 6" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{data.unavailable_count}</span>
          <span class="kpi-label">Unavailable</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{sortedDeviceTypes.length}</span>
          <span class="kpi-label">Integrations</span>
        </div>
      </div>
    </div>

    <!-- Device Types / Integrations Breakdown -->
    {#if sortedDeviceTypes.length > 0}
      <div class="section-card">
        <h3 class="section-title">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="1" y="3" width="14" height="10" rx="2" /><path d="M1 7h14" /></svg>
          Integrations Breakdown
        </h3>
        <div class="integration-list">
          {#each sortedDeviceTypes as [name, count]}
            <div class="integration-row">
              <span class="integration-name">{name}</span>
              <div class="integration-bar-wrap">
                <div class="integration-bar" style="width: {Math.max(4, (count / data.total_entities) * 100)}%" />
              </div>
              <span class="integration-count">{count}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Unavailable Entities -->
    {#if data.unavailable.length > 0}
      <div class="section-card warn-card">
        <h3 class="section-title">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 1L1 14h14L8 1zM8 6v4M8 12h.01" /></svg>
          Unavailable Entities ({data.unavailable_count})
        </h3>
        <div class="unavail-list">
          {#each data.unavailable as entity}
            <button class="unavail-row" on:click={() => handleEntityClick(entity.entity_id)}>
              <DomainIcon domain={entity.domain} />
              <div class="unavail-info">
                <span class="unavail-name">{entity.friendly_name}</span>
                <span class="unavail-id">{entity.entity_id}</span>
              </div>
              <div class="unavail-tags">
                <span class="unavail-state" class:state-unavailable={entity.state === 'unavailable'} class:state-unknown={entity.state === 'unknown'}>{entity.state}</span>
                {#if entity.integration}
                  <span class="unavail-integration">{entity.integration}</span>
                {/if}
              </div>
            </button>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Offline Periods -->
    {#if data.offline_periods.length > 0}
      <div class="section-card">
        <h3 class="section-title">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="7" /><path d="M8 4v4l2.5 1.5" /></svg>
          Offline History
        </h3>
        <div class="offline-list">
          {#each data.offline_periods as period}
            <div class="offline-entry">
              <div class="offline-dot" class:is-ongoing={!period.resumed_at} />
              <div class="offline-info">
                <div class="offline-times">
                  <span class="offline-label">Down:</span>
                  <span class="offline-time">{formatTime(period.stopped_at)}</span>
                  {#if period.resumed_at}
                    <svg class="offline-arrow" viewBox="0 0 12 8" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 4h10M8 1l3 3-3 3" /></svg>
                    <span class="offline-label">Up:</span>
                    <span class="offline-time">{formatTime(period.resumed_at)}</span>
                  {/if}
                </div>
                <span class="offline-duration" class:duration-ongoing={!period.resumed_at}>
                  {formatDuration(period.duration_ms)}
                </span>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {:else}
      <div class="section-card">
        <h3 class="section-title">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="7" /><path d="M8 4v4l2.5 1.5" /></svg>
          Offline History
        </h3>
        <p class="empty-note">No offline periods recorded.</p>
      </div>
    {/if}
  {/if}
</section>

<style>
  .health-view {
    flex: 1; display: flex; flex-direction: column; gap: var(--sp-5);
    padding: var(--sp-6); overflow-y: auto; max-width: 1000px;
    margin: 0 auto; width: 100%;
    animation: fadeIn var(--duration-normal) var(--ease-out);
  }

  .loading-state, .error-state {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: var(--sp-12); gap: var(--sp-3); color: var(--color-text-muted);
  }
  .error-state h3 { color: var(--color-error); }
  .spinner {
    width: 24px; height: 24px; border-radius: 50%;
    border: 2px solid var(--color-border); border-top-color: var(--color-primary);
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* KPI Grid */
  .kpi-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--sp-3);
  }
  .kpi-card {
    display: flex; align-items: center; gap: var(--sp-3);
    padding: var(--sp-4); border-radius: var(--radius-lg);
    background: var(--color-surface); border: 1px solid var(--color-border);
    transition: all var(--duration-fast);
  }
  .kpi-card:hover {
    border-color: var(--color-border-hover);
    box-shadow: 0 2px 8px rgba(0,0,0,.06);
  }
  .kpi-card.kpi-ok { border-color: rgba(52,211,153,.3); }
  .kpi-card.kpi-ok .kpi-icon { color: var(--color-success); background: var(--color-success-soft); }
  .kpi-card.kpi-warn { border-color: rgba(239,68,68,.3); }
  .kpi-card.kpi-warn .kpi-icon { color: var(--color-error, #ef4444); background: rgba(239,68,68,.1); }
  .kpi-icon {
    width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); background: var(--color-surface-hover);
    color: var(--color-text-muted); flex-shrink: 0;
  }
  .kpi-icon svg { width: 20px; height: 20px; }
  .kpi-body { display: flex; flex-direction: column; gap: 2px; }
  .kpi-value { font-size: var(--text-lg); font-weight: 700; color: var(--color-text); letter-spacing: -0.02em; }
  .kpi-label { font-size: var(--text-2xs); color: var(--color-text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }

  /* Section Cards */
  .section-card {
    padding: var(--sp-4) var(--sp-5); border-radius: var(--radius-lg);
    background: var(--color-surface); border: 1px solid var(--color-border);
  }
  .warn-card { border-color: rgba(239,68,68,.25); }
  .section-title {
    display: flex; align-items: center; gap: var(--sp-2);
    font-size: var(--text-md); font-weight: 700; margin-bottom: var(--sp-3);
    letter-spacing: -0.01em;
  }
  .section-title svg { width: 16px; height: 16px; color: var(--color-text-muted); }

  /* Integration Breakdown */
  .integration-list { display: flex; flex-direction: column; gap: var(--sp-2); }
  .integration-row {
    display: flex; align-items: center; gap: var(--sp-3);
    font-size: var(--text-sm);
  }
  .integration-name {
    width: 140px; flex-shrink: 0; font-weight: 500;
    color: var(--color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .integration-bar-wrap {
    flex: 1; height: 8px; border-radius: 4px;
    background: var(--color-surface-hover); overflow: hidden;
  }
  .integration-bar {
    height: 100%; border-radius: 4px;
    background: var(--color-primary); opacity: 0.7;
    transition: width var(--duration-normal) var(--ease-out);
  }
  .integration-count {
    width: 40px; text-align: right; font-weight: 600;
    font-size: var(--text-xs); color: var(--color-text-secondary);
    font-family: var(--font-mono);
  }

  /* Unavailable Entities */
  .unavail-list { display: flex; flex-direction: column; gap: 2px; }
  .unavail-row {
    display: flex; align-items: center; gap: var(--sp-3);
    padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-md);
    text-align: left; transition: background var(--duration-fast);
  }
  .unavail-row:hover { background: var(--color-surface-hover); }
  .unavail-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .unavail-name {
    font-size: var(--text-sm); font-weight: 500; color: var(--color-text);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .unavail-id {
    font-size: var(--text-2xs); color: var(--color-text-muted);
    font-family: var(--font-mono);
  }
  .unavail-tags { display: flex; align-items: center; gap: var(--sp-2); flex-shrink: 0; }
  .unavail-state {
    padding: 2px 8px; border-radius: var(--radius-full);
    font-size: var(--text-2xs); font-weight: 600;
  }
  .state-unavailable {
    color: var(--color-error, #ef4444); background: rgba(239,68,68,.12);
  }
  .state-unknown {
    color: var(--color-warning); background: var(--color-warning-soft);
  }
  .unavail-integration {
    padding: 2px 8px; border-radius: var(--radius-full);
    font-size: var(--text-2xs); color: var(--color-text-muted);
    background: var(--color-surface-hover);
  }

  /* Offline Periods */
  .offline-list { display: flex; flex-direction: column; gap: var(--sp-2); }
  .offline-entry {
    display: flex; align-items: flex-start; gap: var(--sp-3);
    padding: var(--sp-2) 0;
  }
  .offline-dot {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 4px;
    background: var(--color-text-muted);
  }
  .offline-dot.is-ongoing {
    background: var(--color-error, #ef4444);
    animation: pulse-dot 2s ease-in-out infinite;
  }
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(239,68,68,.4); }
    50% { opacity: 0.7; box-shadow: 0 0 8px 2px rgba(239,68,68,.3); }
  }
  .offline-info { flex: 1; display: flex; flex-direction: column; gap: 4px; }
  .offline-times {
    display: flex; flex-wrap: wrap; align-items: center; gap: 4px;
    font-size: var(--text-sm);
  }
  .offline-label { color: var(--color-text-muted); font-weight: 500; font-size: var(--text-2xs); text-transform: uppercase; }
  .offline-time { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--color-text); }
  .offline-arrow { width: 12px; height: 8px; color: var(--color-text-muted); }
  .offline-duration {
    font-size: var(--text-xs); font-weight: 600;
    color: var(--color-text-secondary); font-family: var(--font-mono);
  }
  .offline-duration.duration-ongoing { color: var(--color-error, #ef4444); }

  .empty-note { color: var(--color-text-muted); font-size: var(--text-sm); }

  @media (max-width: 640px) {
    .health-view { padding: var(--sp-4) var(--sp-3); gap: var(--sp-3); }
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .integration-name { width: 100px; }
    .offline-times { flex-direction: column; align-items: flex-start; }
  }
  @media (max-width: 400px) {
    .kpi-grid { grid-template-columns: 1fr; }
  }
</style>
