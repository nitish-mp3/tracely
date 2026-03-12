<script>
  import { onMount } from 'svelte';
  import DomainIcon from '../components/DomainIcon.svelte';
  import { getSystemHealth } from '../lib/api.js';
  import { selectedEntityTag } from '../stores/events.js';

  let data = null;
  let loading = true;
  let error = null;
  let showAllNetwork = false;
  const NETWORK_PREVIEW = 5;

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

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatUptime(secs) {
    if (!secs) return '—';
    const days = Math.floor(secs / 86400);
    const hrs = Math.floor((secs % 86400) / 3600);
    const mins = Math.floor((secs % 3600) / 60);
    if (days > 0) return `${days}d ${hrs}h ${mins}m`;
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
  }

  function handleEntityClick(entityId) {
    $selectedEntityTag = entityId;
  }

  $: sortedDeviceTypes = data?.device_types
    ? Object.entries(data.device_types).sort((a, b) => b[1] - a[1])
    : [];

  $: sortedDomains = data?.domain_counts
    ? Object.entries(data.domain_counts).sort((a, b) => b[1] - a[1])
    : [];

  $: sortedAreas = data?.area_counts
    ? Object.entries(data.area_counts).sort((a, b) => b[1] - a[1])
    : [];

  $: networkDevices = data?.network_info || [];
  $: visibleNetwork = showAllNetwork ? networkDevices : networkDevices.slice(0, NETWORK_PREVIEW);
  $: hiddenNetworkCount = networkDevices.length - NETWORK_PREVIEW;
  $: availabilityPct = data ? Math.round(((data.total_entities - data.unavailable_count) / Math.max(data.total_entities, 1)) * 100) : 100;
  $: topIntegrations = sortedDeviceTypes.slice(0, 4);
  $: networkConnected = networkDevices.filter(n => {
    const s = n.state || '';
    return s === 'home' || s === 'on' || s === 'connected' || s === 'online';
  }).length;
  $: networkDisconnected = networkDevices.filter(n => {
    const s = n.state || '';
    return s === 'not_home' || s === 'off' || s === 'disconnected' || s === 'unavailable';
  }).length;

  // Collapsible section state
  let sectionOpen = {
    network: true,
    areas: true,
    integrations: true,
    domains: true,
    unavailable: false,  // closed by default — can be 1000+ items
    offline: true,
  };
  function toggleSection(key) { sectionOpen[key] = !sectionOpen[key]; sectionOpen = sectionOpen; }
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
    <!-- KPI Cards Row 1: Core status -->
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

      <div class="kpi-card" class:kpi-warn={data.unavailable_count > 0} class:kpi-ok={data.unavailable_count === 0}>
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><path d="M22 4L12 14.01l-3-3" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{availabilityPct}%</span>
          <span class="kpi-label">Availability</span>
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

      <div class="kpi-card">
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.66 0 3-4.03 3-9s-1.34-9-3-9m0 18c-1.66 0-3-4.03-3-9s1.34-9 3-9" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{formatBytes(data.db_size_bytes)}</span>
          <span class="kpi-label">Database Size</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{formatUptime(data.uptime_seconds)}</span>
          <span class="kpi-label">Tracely Uptime</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{(data.events_count || 0).toLocaleString()}</span>
          <span class="kpi-label">Total Events</span>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></svg>
        </div>
        <div class="kpi-body">
          <span class="kpi-value">{sortedAreas.length}</span>
          <span class="kpi-label">Areas</span>
        </div>
      </div>
    </div>

    <!-- Top Integrations Quick Glance -->
    {#if topIntegrations.length > 0}
      <div class="top-integrations">
        {#each topIntegrations as [name, count]}
          <div class="top-integ-card">
            <span class="top-integ-name">{name}</span>
            <span class="top-integ-count">{count}</span>
            <div class="top-integ-bar">
              <div class="top-integ-fill" style="width: {Math.max(8, (count / data.total_entities) * 100)}%" />
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <!-- Network Devices (collapsible, compact) -->
    {#if networkDevices.length > 0}
      <div class="section-card">
        <button class="section-header" on:click={() => toggleSection('network')} aria-expanded={sectionOpen.network}>
          <h3 class="section-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 10.55a7 7 0 019.08 0M5.53 12.61a3 3 0 013.95 0M8 15h.01M1 8.25a10 10 0 0114 0" /></svg>
            Network Devices
            <span class="section-count">{networkDevices.length}</span>
            <span class="section-summary net-summary">
              <span class="net-sum-item net-sum-ok">{networkConnected} online</span>
              {#if networkDisconnected > 0}
                <span class="net-sum-item net-sum-bad">{networkDisconnected} offline</span>
              {/if}
            </span>
          </h3>
          <svg class="section-chevron" class:open={sectionOpen.network} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6l4 4 4-4"/></svg>
        </button>
        {#if sectionOpen.network}
          <div class="network-table">
            <div class="net-table-head">
              <span class="nth-name">Device</span>
              <span class="nth-ip">IP Address</span>
              <span class="nth-integ">Integration</span>
              <span class="nth-state">Status</span>
            </div>
            {#each visibleNetwork as net}
              <div class="net-table-row">
                <span class="nth-name" title={net.entity_id}>{net.friendly_name}</span>
                <span class="nth-ip">{net.ip_address || '—'}</span>
                <span class="nth-integ">{net.integration || '—'}</span>
                <span class="nth-state">
                  <span class="net-state-dot"
                    class:dot-ok={net.state === 'home' || net.state === 'on' || net.state === 'connected'}
                    class:dot-bad={net.state === 'not_home' || net.state === 'off' || net.state === 'disconnected' || net.state === 'unavailable'}
                  ></span>
                  {net.state || '—'}
                </span>
              </div>
            {/each}
            {#if !showAllNetwork && hiddenNetworkCount > 0}
              <button class="show-more-btn" on:click|stopPropagation={() => showAllNetwork = true}>
                Show {hiddenNetworkCount} more devices
              </button>
            {/if}
            {#if showAllNetwork && hiddenNetworkCount > 0}
              <button class="show-more-btn" on:click|stopPropagation={() => showAllNetwork = false}>
                Show less
              </button>
            {/if}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Area Breakdown -->
    {#if sortedAreas.length > 0}
      <div class="section-card">
        <button class="section-header" on:click={() => toggleSection('areas')} aria-expanded={sectionOpen.areas}>
          <h3 class="section-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 6l6-4 6 4v7a1 1 0 01-1 1H3a1 1 0 01-1-1V6z" /><path d="M6 14V8h4v6" /></svg>
            Areas
            <span class="section-count">{sortedAreas.length}</span>
          </h3>
          <svg class="section-chevron" class:open={sectionOpen.areas} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6l4 4 4-4"/></svg>
        </button>
        {#if sectionOpen.areas}
          <div class="area-grid">
            {#each sortedAreas as [name, count]}
              <div class="area-chip">
                <span class="area-name">{name}</span>
                <span class="area-count">{count}</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Integrations Breakdown -->
    {#if sortedDeviceTypes.length > 0}
      <div class="section-card">
        <button class="section-header" on:click={() => toggleSection('integrations')} aria-expanded={sectionOpen.integrations}>
          <h3 class="section-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="1" y="3" width="14" height="10" rx="2" /><path d="M1 7h14" /></svg>
            Integrations Breakdown
            <span class="section-count">{sortedDeviceTypes.length}</span>
          </h3>
          <svg class="section-chevron" class:open={sectionOpen.integrations} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6l4 4 4-4"/></svg>
        </button>
        {#if sectionOpen.integrations}
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
        {/if}
      </div>
    {/if}

    <!-- Domain Breakdown -->
    {#if sortedDomains.length > 0}
      <div class="section-card">
        <button class="section-header" on:click={() => toggleSection('domains')} aria-expanded={sectionOpen.domains}>
          <h3 class="section-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4h8M4 8h8M4 12h5" /></svg>
            Domains
            <span class="section-count">{sortedDomains.length}</span>
          </h3>
          <svg class="section-chevron" class:open={sectionOpen.domains} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6l4 4 4-4"/></svg>
        </button>
        {#if sectionOpen.domains}
          <div class="domain-grid">
            {#each sortedDomains.slice(0, 30) as [name, count]}
              <div class="domain-chip">
                <DomainIcon domain={name} />
                <span class="domain-name">{name}</span>
                <span class="domain-count">{count}</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Unavailable Entities -->
    {#if data.unavailable.length > 0}
      <div class="section-card warn-card">
        <button class="section-header" on:click={() => toggleSection('unavailable')} aria-expanded={sectionOpen.unavailable}>
          <h3 class="section-title">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 1L1 14h14L8 1zM8 6v4M8 12h.01" /></svg>
            Unavailable Entities
            <span class="section-count warn">{data.unavailable_count}</span>
            {#if !sectionOpen.unavailable}
              <span class="section-hint">click to expand</span>
            {/if}
          </h3>
          <svg class="section-chevron" class:open={sectionOpen.unavailable} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6l4 4 4-4"/></svg>
        </button>
        {#if sectionOpen.unavailable}
          <div class="unavail-list">
            {#each data.unavailable as entity}
              <button class="unavail-row" on:click|stopPropagation={() => handleEntityClick(entity.entity_id)}>
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
                  {#if entity.area}
                    <span class="unavail-area">{entity.area}</span>
                  {/if}
                </div>
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Offline History -->
    <div class="section-card">
      <button class="section-header" on:click={() => toggleSection('offline')} aria-expanded={sectionOpen.offline}>
        <h3 class="section-title">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="7" /><path d="M8 4v4l2.5 1.5" /></svg>
          Offline History
          {#if data.offline_periods.length > 0}
            <span class="section-count">{data.offline_periods.length}</span>
          {/if}
        </h3>
        <svg class="section-chevron" class:open={sectionOpen.offline} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6l4 4 4-4"/></svg>
      </button>
      {#if sectionOpen.offline}
        {#if data.offline_periods.length > 0}
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
        {:else}
          <p class="empty-note">No offline periods recorded.</p>
        {/if}
      {/if}
    </div>
  {/if}
</section>

<style>
  .health-view {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
    padding: var(--sp-6);
    overflow-y: auto;
    max-width: 1000px;
    margin: 0 auto;
    width: 100%;
    animation: fadeIn var(--duration-normal) var(--ease-out);
  }
  /* Prevent flex children from collapsing (section-card has overflow:hidden which disables min-height:auto) */
  .health-view > * {
    flex-shrink: 0;
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
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: var(--sp-3);
  }
  .kpi-card {
    display: flex; align-items: center; gap: var(--sp-3);
    padding: var(--sp-3) var(--sp-4); border-radius: var(--radius-lg);
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
    width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); background: var(--color-surface-hover);
    color: var(--color-text-muted); flex-shrink: 0;
  }
  .kpi-icon svg { width: 18px; height: 18px; }
  .kpi-body { display: flex; flex-direction: column; gap: 1px; }
  .kpi-value { font-size: var(--text-md); font-weight: 700; color: var(--color-text); letter-spacing: -0.02em; }
  .kpi-label { font-size: var(--text-2xs); color: var(--color-text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }

  /* Top Integrations Quick Glance */
  .top-integrations {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: var(--sp-2);
  }
  .top-integ-card {
    padding: var(--sp-3); border-radius: var(--radius-md);
    background: var(--color-surface); border: 1px solid var(--color-border);
    display: flex; flex-direction: column; gap: var(--sp-1);
  }
  .top-integ-name {
    font-size: var(--text-xs); font-weight: 600; color: var(--color-text);
    text-transform: capitalize; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .top-integ-count {
    font-size: var(--text-lg); font-weight: 800; color: var(--color-primary);
    font-family: var(--font-mono); letter-spacing: -0.02em;
  }
  .top-integ-bar {
    height: 4px; border-radius: 2px; background: var(--color-surface-hover);
    overflow: hidden; margin-top: 2px;
  }
  .top-integ-fill {
    height: 100%; border-radius: 2px; background: var(--color-primary); opacity: 0.6;
  }

  /* Section Cards */
  .section-card {
    border-radius: var(--radius-lg);
    background: var(--color-surface); border: 1px solid var(--color-border);
    overflow: hidden;
  }
  .warn-card { border-color: rgba(239,68,68,.25); }

  /* Section Header */
  .section-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--sp-3) var(--sp-4);
    border-bottom: 1px solid var(--color-border);
    width: 100%; cursor: pointer;
    background: none; border-radius: 0; font: inherit; text-align: left;
    transition: background 0.15s;
  }
  .section-header:hover { background: var(--color-surface-hover, rgba(255,255,255,0.03)); }
  .section-header[aria-expanded="false"] { border-bottom-color: transparent; }
  .section-chevron {
    width: 16px; height: 16px; color: var(--color-text-muted); flex-shrink: 0;
    transition: transform 0.2s ease; transform: rotate(0deg);
  }
  .section-chevron.open { transform: rotate(180deg); }
  .section-hint {
    font-size: var(--text-2xs); color: var(--color-text-muted); font-weight: 400;
    margin-left: var(--sp-1); opacity: 0.7;
  }
  .section-title {
    display: flex; align-items: center; gap: var(--sp-2);
    font-size: var(--text-sm); font-weight: 700;
    letter-spacing: -0.01em; margin: 0; color: var(--color-text);
  }
  .section-title svg { width: 14px; height: 14px; color: var(--color-text-muted); flex-shrink: 0; }
  .section-count {
    font-size: var(--text-2xs); font-weight: 700; font-family: var(--font-mono);
    padding: 1px 7px; border-radius: var(--radius-full);
    background: var(--color-primary-soft, rgba(99,102,241,.1)); color: var(--color-primary);
  }
  .section-count.warn {
    background: rgba(239,68,68,.1); color: var(--color-error, #ef4444);
  }
  .section-summary {
    display: flex; gap: var(--sp-2); margin-left: var(--sp-2);
  }
  .net-sum-item {
    font-size: var(--text-2xs); font-weight: 600; padding: 1px 6px;
    border-radius: var(--radius-full);
  }
  .net-sum-ok { color: var(--color-success); background: var(--color-success-soft); }
  .net-sum-bad { color: var(--color-error, #ef4444); background: rgba(239,68,68,.1); }


  /* Network Table (compact) */
  .network-table { padding: var(--sp-2) var(--sp-4) var(--sp-3); }
  .net-table-head {
    display: grid; grid-template-columns: 1fr 120px 100px 90px;
    gap: var(--sp-2); padding: var(--sp-1) var(--sp-2);
    font-size: var(--text-2xs); font-weight: 600; color: var(--color-text-muted);
    text-transform: uppercase; letter-spacing: 0.04em;
    border-bottom: 1px solid var(--color-border);
  }
  .net-table-row {
    display: grid; grid-template-columns: 1fr 120px 100px 90px;
    gap: var(--sp-2); padding: var(--sp-2);
    font-size: var(--text-xs); color: var(--color-text);
    border-bottom: 1px solid var(--color-border);
    transition: background var(--duration-fast);
    align-items: center;
  }
  .net-table-row:last-of-type { border-bottom: none; }
  .net-table-row:hover { background: var(--color-surface-hover); }
  .nth-name {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-weight: 500;
  }
  .nth-ip {
    font-family: var(--font-mono); font-size: var(--text-2xs);
    color: var(--color-text-secondary);
  }
  .nth-integ {
    font-size: var(--text-2xs); color: var(--color-text-muted);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .nth-state {
    display: flex; align-items: center; gap: 4px;
    font-size: var(--text-2xs); font-weight: 600;
  }
  .net-state-dot {
    width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
    background: var(--color-text-muted);
  }
  .net-state-dot.dot-ok { background: var(--color-success); }
  .net-state-dot.dot-bad { background: var(--color-error, #ef4444); }
  .show-more-btn {
    display: block; width: 100%; padding: var(--sp-2);
    text-align: center; font-size: var(--text-xs); font-weight: 600;
    color: var(--color-primary); background: none; border: none;
    border-top: 1px solid var(--color-border); cursor: pointer;
    transition: background var(--duration-fast);
  }
  .show-more-btn:hover { background: var(--color-surface-hover); }

  /* Integration Breakdown */
  .integration-list { display: flex; flex-direction: column; gap: var(--sp-1); padding: var(--sp-2) var(--sp-4) var(--sp-3); }
  .integration-row {
    display: flex; align-items: center; gap: var(--sp-3);
    font-size: var(--text-sm);
  }
  .integration-name {
    width: 140px; flex-shrink: 0; font-weight: 500;
    color: var(--color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .integration-bar-wrap {
    flex: 1; height: 6px; border-radius: 3px;
    background: var(--color-surface-hover); overflow: hidden;
  }
  .integration-bar {
    height: 100%; border-radius: 3px;
    background: var(--color-primary); opacity: 0.7;
    transition: width var(--duration-normal) var(--ease-out);
  }
  .integration-count {
    width: 40px; text-align: right; font-weight: 600;
    font-size: var(--text-xs); color: var(--color-text-secondary);
    font-family: var(--font-mono);
  }

  /* Unavailable Entities */
  .unavail-list { display: flex; flex-direction: column; gap: 2px; padding: 0 var(--sp-2) var(--sp-3); }
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
  .unavail-area {
    padding: 2px 8px; border-radius: var(--radius-full);
    font-size: var(--text-2xs); color: var(--color-text-muted);
    background: var(--color-surface-hover);
  }

  /* Offline Periods */
  .offline-list { display: flex; flex-direction: column; gap: var(--sp-2); padding: 0 var(--sp-4) var(--sp-3); }
  .offline-entry {
    display: flex; align-items: flex-start; gap: var(--sp-3);
    padding: var(--sp-2) 0;
  }
  .offline-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px;
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

  .empty-note { color: var(--color-text-muted); font-size: var(--text-sm); padding: 0 var(--sp-4) var(--sp-3); }

  /* Area Breakdown */
  .area-grid { display: flex; flex-wrap: wrap; gap: var(--sp-2); padding: var(--sp-2) var(--sp-4) var(--sp-3); }
  .area-chip {
    display: flex; align-items: center; gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-full);
    background: var(--color-surface-hover); border: 1px solid var(--color-border);
    font-size: var(--text-sm); transition: all var(--duration-fast);
  }
  .area-chip:hover { border-color: var(--color-border-hover); }
  .area-name { font-weight: 500; color: var(--color-text); }
  .area-count {
    font-family: var(--font-mono); font-size: var(--text-2xs);
    font-weight: 700; color: var(--color-primary);
    background: var(--color-primary-soft, rgba(99,102,241,.1));
    padding: 1px 6px; border-radius: var(--radius-full);
  }

  /* Domain Breakdown */
  .domain-grid { display: flex; flex-wrap: wrap; gap: var(--sp-2); padding: var(--sp-2) var(--sp-4) var(--sp-3); }
  .domain-chip {
    display: flex; align-items: center; gap: var(--sp-1);
    padding: 3px var(--sp-2); border-radius: var(--radius-full);
    background: var(--color-surface-hover); border: 1px solid var(--color-border);
    font-size: var(--text-xs); transition: all var(--duration-fast);
  }
  .domain-chip:hover { border-color: var(--color-border-hover); }
  .domain-name { font-weight: 500; color: var(--color-text); }
  .domain-count {
    font-family: var(--font-mono); font-size: var(--text-2xs);
    font-weight: 600; color: var(--color-text-muted);
  }

  @media (max-width: 640px) {
    .health-view { padding: var(--sp-4) var(--sp-3); gap: var(--sp-3); }
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .top-integrations { grid-template-columns: repeat(2, 1fr); }
    .integration-name { width: 100px; }
    .offline-times { flex-direction: column; align-items: flex-start; }
    .net-table-head, .net-table-row { grid-template-columns: 1fr 90px 80px 70px; }
    .section-summary { display: none; }
  }
  @media (max-width: 400px) {
    .kpi-grid { grid-template-columns: 1fr; }
    .net-table-head, .net-table-row { grid-template-columns: 1fr 70px; }
    .nth-ip, .nth-integ { display: none; }
  }
</style>
