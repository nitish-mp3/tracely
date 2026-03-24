<script>
  import { onMount } from 'svelte';
  import { getLifecycleEvents, getSupervisorInfo, getLogs } from '../lib/api.js';

  let lifecycle = null;
  let supervisor = null;
  let coreLogs = [];
  let loading = true;
  let error = null;
  let activeTab = 'overview'; // overview | events | supervisor | logs

  onMount(async () => {
    try {
      const [lcData, supData, logData] = await Promise.all([
        getLifecycleEvents(200).catch(() => null),
        getSupervisorInfo().catch(() => null),
        getLogs(150).catch(() => null),
      ]);
      lifecycle = lcData;
      supervisor = supData;
      if (logData?.available && logData.lines) {
        coreLogs = logData.lines;
      }
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

  function relativeTime(ts) {
    if (!ts) return '';
    const diff = Date.now() - new Date(ts).getTime();
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }

  function formatDuration(ms) {
    if (!ms) return '—';
    const secs = Math.floor(ms / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ${secs % 60}s`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ${mins % 60}m`;
  }

  function isStart(item) {
    return item.source === 'homeassistant_start' || item.incident_type?.includes('start');
  }
  function isStop(item) {
    return item.source === 'homeassistant_stop' || item.incident_type?.includes('stop');
  }

  $: items = lifecycle?.items ?? [];
  $: startCount = items.filter(isStart).length;
  $: stopCount = items.filter(isStop).length;
  $: restartCount = Math.max(0, Math.min(startCount, stopCount));
  $: lastEvent = items.length > 0 ? items[0] : null;
  $: uptimeStatus = supervisor?.core_state || 'unknown';
  $: errorLogLines = coreLogs.filter(l => l.level === 'ERROR' || l.level === 'CRITICAL');
  $: warningLogLines = coreLogs.filter(l => l.level === 'WARNING');

  // Disk usage percentage
  $: diskPercent = supervisor?.disk_total
    ? Math.round((supervisor.disk_used / supervisor.disk_total) * 100)
    : null;
</script>

<section class="lifecycle-view" aria-label="HA Lifecycle & System Monitor">
  {#if loading}
    <div class="center-state">
      <div class="spinner" />
      <span>Loading system info…</span>
    </div>
  {:else if error}
    <div class="center-state error">
      <h3>Failed to load</h3>
      <p>{error}</p>
    </div>
  {:else}
    <!-- System Status Hero -->
    <div class="hero-section">
      <div class="hero-status" class:healthy={uptimeStatus === 'running'} class:degraded={uptimeStatus !== 'running' && uptimeStatus !== 'unknown'}>
        <div class="status-orb">
          <div class="orb-inner" />
        </div>
        <div class="hero-info">
          <h2>Home Assistant</h2>
          <span class="status-text">
            {#if uptimeStatus === 'running'}
              Running
            {:else if uptimeStatus === 'unknown'}
              Status Unknown
            {:else}
              {uptimeStatus}
            {/if}
          </span>
        </div>
      </div>

      <div class="hero-stats">
        <div class="hero-stat">
          <span class="hs-value">{startCount}</span>
          <span class="hs-label">Starts</span>
        </div>
        <div class="hero-divider" />
        <div class="hero-stat">
          <span class="hs-value">{stopCount}</span>
          <span class="hs-label">Stops</span>
        </div>
        <div class="hero-divider" />
        <div class="hero-stat">
          <span class="hs-value">{restartCount}</span>
          <span class="hs-label">Restarts</span>
        </div>
        {#if lastEvent}
          <div class="hero-divider" />
          <div class="hero-stat">
            <span class="hs-value">{relativeTime(lastEvent.timestamp)}</span>
            <span class="hs-label">Last Event</span>
          </div>
        {/if}
      </div>
    </div>

    <!-- Tabs -->
    <div class="section-tabs">
      <button class="stab" class:active={activeTab === 'overview'} on:click={() => activeTab = 'overview'}>
        <svg class="stab-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>
        Overview
      </button>
      <button class="stab" class:active={activeTab === 'events'} on:click={() => activeTab = 'events'}>
        <svg class="stab-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4h12M2 8h8M2 12h10"/></svg>
        Events
        <span class="stab-count">{items.length}</span>
      </button>
      <button class="stab" class:active={activeTab === 'supervisor'} on:click={() => activeTab = 'supervisor'}>
        <svg class="stab-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l3 2"/></svg>
        System Info
      </button>
      <button class="stab" class:active={activeTab === 'logs'} on:click={() => activeTab = 'logs'}>
        <svg class="stab-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3h10v10H3z"/><path d="M5 6h6M5 8h4M5 10h5"/></svg>
        Logs
        {#if errorLogLines.length > 0}
          <span class="stab-count error">{errorLogLines.length}</span>
        {/if}
      </button>
    </div>

    <!-- Tab Content -->
    <div class="tab-content">
      {#if activeTab === 'overview'}
        <div class="overview-grid">
          <!-- Supervisor Info Card -->
          {#if supervisor?.available}
            <div class="info-card wide">
              <h3 class="card-title">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 1"/></svg>
                System Details
              </h3>
              <div class="kv-grid">
                {#if supervisor.core_version}
                  <span class="kv-key">Core Version</span>
                  <span class="kv-val">{supervisor.core_version}</span>
                {/if}
                {#if supervisor.supervisor_version}
                  <span class="kv-key">Supervisor</span>
                  <span class="kv-val">{supervisor.supervisor_version}</span>
                {/if}
                {#if supervisor.operating_system}
                  <span class="kv-key">OS</span>
                  <span class="kv-val">{supervisor.operating_system}</span>
                {/if}
                {#if supervisor.hostname}
                  <span class="kv-key">Hostname</span>
                  <span class="kv-val">{supervisor.hostname}</span>
                {/if}
                {#if supervisor.arch}
                  <span class="kv-key">Architecture</span>
                  <span class="kv-val">{supervisor.arch}</span>
                {/if}
                {#if supervisor.kernel}
                  <span class="kv-key">Kernel</span>
                  <span class="kv-val mono">{supervisor.kernel}</span>
                {/if}
              </div>
            </div>

            <!-- Disk Usage -->
            {#if diskPercent !== null}
              <div class="info-card">
                <h3 class="card-title">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="10" rx="2"/><path d="M5 8h6"/></svg>
                  Disk Usage
                </h3>
                <div class="disk-visual">
                  <div class="disk-bar">
                    <div class="disk-fill" class:warning={diskPercent > 75} class:danger={diskPercent > 90} style="width: {diskPercent}%" />
                  </div>
                  <div class="disk-labels">
                    <span>{(supervisor.disk_used / 1024).toFixed(1)} GB used</span>
                    <span>{(supervisor.disk_free / 1024).toFixed(1)} GB free</span>
                  </div>
                  <span class="disk-percent" class:warning={diskPercent > 75} class:danger={diskPercent > 90}>{diskPercent}%</span>
                </div>
              </div>
            {/if}

            <!-- Health Flags -->
            <div class="info-card">
              <h3 class="card-title">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2l1.5 3 3.5.5-2.5 2.5.5 3.5L8 10l-3 1.5.5-3.5L3 5.5 6.5 5z"/></svg>
                Health
              </h3>
              <div class="health-flags">
                <div class="hflag" class:ok={supervisor.supervisor_healthy !== false} class:bad={supervisor.supervisor_healthy === false}>
                  <span class="hflag-dot" />
                  <span>Supervisor {supervisor.supervisor_healthy !== false ? 'Healthy' : 'Unhealthy'}</span>
                </div>
                <div class="hflag" class:ok={supervisor.supervisor_supported !== false} class:bad={supervisor.supervisor_supported === false}>
                  <span class="hflag-dot" />
                  <span>System {supervisor.supervisor_supported !== false ? 'Supported' : 'Unsupported'}</span>
                </div>
                <div class="hflag" class:ok={uptimeStatus === 'running'} class:bad={uptimeStatus !== 'running'}>
                  <span class="hflag-dot" />
                  <span>Core {uptimeStatus === 'running' ? 'Running' : uptimeStatus}</span>
                </div>
              </div>
            </div>
          {:else}
            <div class="info-card wide">
              <div class="card-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 14h.01"/></svg>
                <p>Supervisor API not available. System details require Home Assistant OS with Supervisor.</p>
              </div>
            </div>
          {/if}

          <!-- Log Summary Card -->
          <div class="info-card">
            <h3 class="card-title">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3h10v10H3z"/><path d="M5 6h6M5 8h4"/></svg>
              Log Summary
            </h3>
            <div class="log-summary">
              <div class="ls-row">
                <span class="ls-dot error" />
                <span class="ls-label">Errors</span>
                <span class="ls-value">{errorLogLines.length}</span>
              </div>
              <div class="ls-row">
                <span class="ls-dot warning" />
                <span class="ls-label">Warnings</span>
                <span class="ls-value">{warningLogLines.length}</span>
              </div>
              <div class="ls-row">
                <span class="ls-dot info" />
                <span class="ls-label">Total Lines</span>
                <span class="ls-value">{coreLogs.length}</span>
              </div>
            </div>
          </div>
        </div>

      {:else if activeTab === 'events'}
        {#if items.length > 0}
          <div class="events-list">
            {#each items as item (item.id)}
              <div class="event-row" class:is-start={isStart(item)} class:is-stop={isStop(item)}>
                <div class="ev-indicator">
                  {#if isStart(item)}
                    <div class="ev-dot start" />
                  {:else}
                    <div class="ev-dot stop" />
                  {/if}
                </div>
                <div class="ev-body">
                  <div class="ev-top">
                    <span class="ev-badge" class:badge-start={isStart(item)} class:badge-stop={isStop(item)}>
                      {isStart(item) ? 'START' : 'STOP'}
                    </span>
                    <span class="ev-time">{formatTime(item.timestamp)}</span>
                    <span class="ev-relative">{relativeTime(item.timestamp)}</span>
                  </div>
                  <p class="ev-message">{item.message}</p>
                  {#if item.details}
                    <div class="ev-details">
                      {#if item.details.reason}
                        <span class="ev-detail"><strong>Reason:</strong> {item.details.reason}</span>
                      {/if}
                      {#if item.details.duration_ms}
                        <span class="ev-detail"><strong>Offline:</strong> {formatDuration(item.details.duration_ms)}</span>
                      {/if}
                    </div>
                  {/if}
                  <div class="ev-metrics">
                    <span class="ev-metric">CPU {Number(item.cpu_percent || 0).toFixed(1)}%</span>
                    <span class="ev-metric">MEM {Number(item.memory_percent || 0).toFixed(1)}%</span>
                    <span class="ev-metric">{Number(item.memory_rss_mb || 0).toFixed(0)} MB</span>
                  </div>
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="center-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3" width="48" height="48"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 14h.01"/></svg>
            <p>No lifecycle events recorded yet. Events appear when HA starts or stops.</p>
          </div>
        {/if}

      {:else if activeTab === 'supervisor'}
        {#if supervisor?.available}
          <div class="log-block">
            {#if supervisor.supervisor_logs}
              <h3 class="log-title">Supervisor Logs</h3>
              <pre class="log-pre">{supervisor.supervisor_logs}</pre>
            {/if}
            {#if supervisor.core_logs}
              <h3 class="log-title">Core Logs</h3>
              <pre class="log-pre">{supervisor.core_logs}</pre>
            {/if}
            {#if !supervisor.supervisor_logs && !supervisor.core_logs}
              <div class="center-state">
                <p>No supervisor logs available.</p>
              </div>
            {/if}
          </div>
        {:else}
          <div class="center-state">
            <p>Supervisor API not available on this installation.</p>
          </div>
        {/if}

      {:else if activeTab === 'logs'}
        {#if coreLogs.length > 0}
          <div class="log-lines">
            {#each coreLogs as line, i}
              <div class="log-line" class:log-error={line.level === 'ERROR' || line.level === 'CRITICAL'} class:log-warning={line.level === 'WARNING'}>
                <span class="ll-num">{i + 1}</span>
                <span class="ll-level" class:level-error={line.level === 'ERROR' || line.level === 'CRITICAL'} class:level-warning={line.level === 'WARNING'} class:level-info={line.level === 'INFO'}>{line.level || ''}</span>
                <span class="ll-ts">{line.timestamp || ''}</span>
                <span class="ll-msg">{line.message || ''}</span>
              </div>
            {/each}
          </div>
        {:else}
          <div class="center-state">
            <p>No log entries available. HA Core logs may not be accessible on this setup.</p>
          </div>
        {/if}
      {/if}
    </div>
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
    width: 100%;
  }

  .center-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--sp-3);
    padding: var(--sp-8);
    color: var(--color-text-muted);
    text-align: center;
  }
  .center-state.error h3 { color: var(--color-error); }
  .center-state p { margin: 0; font-size: var(--text-sm); max-width: 400px; line-height: var(--lh-relaxed); }
  .spinner {
    width: 40px; height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Hero */
  .hero-section {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--sp-5);
    background: linear-gradient(135deg, var(--color-surface), var(--color-surface-hover));
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    gap: var(--sp-5);
    flex-wrap: wrap;
  }
  .hero-status {
    display: flex;
    align-items: center;
    gap: var(--sp-4);
  }
  .status-orb {
    width: 48px; height: 48px;
    border-radius: 50%;
    background: var(--color-surface-active);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }
  .hero-status.healthy .status-orb { background: var(--color-success-soft); }
  .hero-status.degraded .status-orb { background: var(--color-warning-soft); }
  .orb-inner {
    width: 16px; height: 16px;
    border-radius: 50%;
    background: var(--color-text-muted);
  }
  .hero-status.healthy .orb-inner {
    background: var(--color-success);
    box-shadow: 0 0 12px var(--color-success);
    animation: pulse-orb 2s infinite;
  }
  .hero-status.degraded .orb-inner {
    background: var(--color-warning);
    box-shadow: 0 0 12px var(--color-warning);
  }
  @keyframes pulse-orb {
    0%, 100% { opacity: 1; box-shadow: 0 0 12px var(--color-success); }
    50% { opacity: 0.7; box-shadow: 0 0 6px var(--color-success); }
  }
  .hero-info h2 {
    font-size: var(--text-lg); font-weight: 700; color: var(--color-text); margin: 0;
  }
  .status-text {
    font-size: var(--text-sm); color: var(--color-text-muted); font-weight: 500;
  }
  .hero-status.healthy .status-text { color: var(--color-success); }
  .hero-status.degraded .status-text { color: var(--color-warning); }

  .hero-stats {
    display: flex;
    align-items: center;
    gap: var(--sp-4);
  }
  .hero-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 60px;
  }
  .hs-value {
    font-size: var(--text-xl); font-weight: 700; color: var(--color-text);
    line-height: 1.2;
  }
  .hs-label {
    font-size: var(--text-2xs); font-weight: 600; color: var(--color-text-muted);
    text-transform: uppercase; letter-spacing: 0.04em;
  }
  .hero-divider {
    width: 1px; height: 32px; background: var(--color-border);
  }

  /* Tabs */
  .section-tabs {
    display: flex;
    gap: 2px;
    padding: 3px;
    background: var(--color-bg-elevated);
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    align-self: flex-start;
  }
  .stab {
    display: flex; align-items: center; gap: 5px;
    padding: 7px 16px;
    border-radius: calc(var(--radius-md) - 2px);
    font-size: var(--text-sm); font-weight: 500;
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .stab:hover { color: var(--color-text-secondary); }
  .stab.active {
    color: var(--color-text);
    background: var(--color-surface);
    box-shadow: var(--shadow-xs);
  }
  .stab-icon { width: 14px; height: 14px; }
  .stab-count {
    font-size: var(--text-2xs); padding: 1px 6px;
    border-radius: var(--radius-full);
    background: var(--color-surface-hover);
    color: var(--color-text-muted); font-weight: 600;
  }
  .stab-count.error { background: var(--color-error-soft); color: var(--color-error); }

  .tab-content { flex: 1; min-height: 0; }

  /* Overview Grid */
  .overview-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: var(--sp-3);
  }
  .info-card {
    padding: var(--sp-4);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .info-card.wide { grid-column: 1 / -1; }
  .card-title {
    display: flex; align-items: center; gap: var(--sp-2);
    font-size: var(--text-sm); font-weight: 700; color: var(--color-text);
    margin: 0;
  }
  .card-title svg { width: 16px; height: 16px; color: var(--color-primary); }
  .card-empty {
    display: flex; flex-direction: column; align-items: center;
    gap: var(--sp-3); padding: var(--sp-4); text-align: center;
    color: var(--color-text-muted);
  }
  .card-empty svg { width: 36px; height: 36px; }
  .card-empty p { margin: 0; font-size: var(--text-sm); }

  .kv-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px var(--sp-4);
    font-size: var(--text-sm);
  }
  .kv-key { color: var(--color-text-muted); font-weight: 500; }
  .kv-val { color: var(--color-text); font-weight: 600; }
  .kv-val.mono { font-family: var(--font-mono); font-size: var(--text-xs); }

  /* Disk */
  .disk-visual { display: flex; flex-direction: column; gap: 8px; }
  .disk-bar {
    height: 10px; background: var(--color-bg-elevated);
    border-radius: var(--radius-full); overflow: hidden;
  }
  .disk-fill {
    height: 100%; background: var(--color-primary);
    border-radius: var(--radius-full);
    transition: width 0.5s ease;
  }
  .disk-fill.warning { background: var(--color-warning); }
  .disk-fill.danger { background: var(--color-error); }
  .disk-labels {
    display: flex; justify-content: space-between;
    font-size: var(--text-2xs); color: var(--color-text-muted);
  }
  .disk-percent {
    font-size: var(--text-xl); font-weight: 700; color: var(--color-text);
    text-align: center;
  }
  .disk-percent.warning { color: var(--color-warning); }
  .disk-percent.danger { color: var(--color-error); }

  /* Health Flags */
  .health-flags { display: flex; flex-direction: column; gap: 8px; }
  .hflag {
    display: flex; align-items: center; gap: var(--sp-2);
    font-size: var(--text-sm); font-weight: 500;
    color: var(--color-text-secondary);
  }
  .hflag-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--color-text-muted);
  }
  .hflag.ok .hflag-dot { background: var(--color-success); }
  .hflag.bad .hflag-dot { background: var(--color-error); }
  .hflag.ok { color: var(--color-success); }
  .hflag.bad { color: var(--color-error); }

  /* Log Summary */
  .log-summary { display: flex; flex-direction: column; gap: 10px; }
  .ls-row {
    display: flex; align-items: center; gap: var(--sp-2);
    font-size: var(--text-sm);
  }
  .ls-dot {
    width: 8px; height: 8px; border-radius: 50%;
  }
  .ls-dot.error { background: var(--color-error); }
  .ls-dot.warning { background: var(--color-warning); }
  .ls-dot.info { background: var(--color-info); }
  .ls-label { color: var(--color-text-secondary); flex: 1; }
  .ls-value { font-weight: 700; color: var(--color-text); font-family: var(--font-mono); }

  /* Events list */
  .events-list {
    display: flex; flex-direction: column; gap: var(--sp-2);
  }
  .event-row {
    display: flex; gap: var(--sp-3);
    padding: var(--sp-3) var(--sp-4);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    transition: all var(--duration-fast);
  }
  .event-row:hover {
    border-color: var(--color-border-hover);
    box-shadow: var(--shadow-xs);
  }
  .ev-indicator {
    display: flex; align-items: flex-start; padding-top: 4px;
  }
  .ev-dot {
    width: 12px; height: 12px; border-radius: 50%;
    border: 3px solid var(--color-text-muted);
  }
  .ev-dot.start { border-color: var(--color-success); background: var(--color-success-soft); }
  .ev-dot.stop { border-color: var(--color-error); background: var(--color-error-soft); }
  .ev-body {
    flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0;
  }
  .ev-top {
    display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap;
  }
  .ev-badge {
    font-size: 10px; font-weight: 700; padding: 2px 8px;
    border-radius: var(--radius-full); text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .ev-badge.badge-start { color: var(--color-success); background: var(--color-success-soft); }
  .ev-badge.badge-stop { color: var(--color-error); background: var(--color-error-soft); }
  .ev-time {
    font-size: var(--text-xs); font-family: var(--font-mono);
    color: var(--color-text-muted);
  }
  .ev-relative {
    font-size: var(--text-2xs); color: var(--color-text-muted);
    margin-left: auto;
  }
  .ev-message {
    font-size: var(--text-sm); color: var(--color-text-secondary);
    line-height: var(--lh-normal); margin: 0;
  }
  .ev-details {
    display: flex; flex-wrap: wrap; gap: var(--sp-2);
    font-size: var(--text-xs); color: var(--color-text-muted);
  }
  .ev-detail strong { color: var(--color-text-secondary); }
  .ev-metrics {
    display: flex; gap: var(--sp-3);
    font-size: var(--text-2xs); color: var(--color-text-muted); font-weight: 500;
  }

  /* Supervisor Logs */
  .log-block { display: flex; flex-direction: column; gap: var(--sp-3); }
  .log-title {
    font-size: var(--text-sm); font-weight: 700; color: var(--color-text); margin: 0;
  }
  .log-pre {
    padding: var(--sp-4);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.5;
    color: var(--color-text-secondary);
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 500px;
    overflow-y: auto;
  }

  /* Parsed Log Lines */
  .log-lines {
    display: flex; flex-direction: column;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    max-height: 600px;
    overflow-y: auto;
  }
  .log-line {
    display: flex; align-items: baseline; gap: var(--sp-2);
    padding: 3px var(--sp-3);
    font-family: var(--font-mono); font-size: 11px;
    border-bottom: 1px solid var(--color-border);
    line-height: 1.5;
  }
  .log-line:last-child { border-bottom: none; }
  .log-line.log-error { background: rgba(248,113,113,.05); }
  .log-line.log-warning { background: rgba(251,191,36,.04); }
  .ll-num {
    color: var(--color-text-muted); min-width: 30px;
    text-align: right; font-size: 10px; opacity: 0.5; user-select: none;
  }
  .ll-level {
    min-width: 50px; font-weight: 700; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.03em;
    color: var(--color-text-muted);
  }
  .ll-level.level-error { color: var(--color-error); }
  .ll-level.level-warning { color: var(--color-warning); }
  .ll-level.level-info { color: var(--color-info); }
  .ll-ts {
    color: var(--color-text-muted); font-size: 10px; white-space: nowrap;
  }
  .ll-msg {
    color: var(--color-text-secondary); flex: 1; min-width: 0;
    word-break: break-word;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .lifecycle-view { padding: var(--sp-3); gap: var(--sp-3); }
    .hero-section {
      flex-direction: column;
      align-items: flex-start;
      padding: var(--sp-4);
      gap: var(--sp-3);
    }
    .hero-stats {
      flex-wrap: wrap;
      gap: var(--sp-3);
    }
    .hero-divider { display: none; }
    .section-tabs {
      overflow-x: auto;
      scrollbar-width: none;
      align-self: stretch;
    }
    .section-tabs::-webkit-scrollbar { display: none; }
    .stab { padding: 6px 12px; font-size: var(--text-xs); }
    .overview-grid {
      grid-template-columns: 1fr;
    }
    .kv-grid { font-size: var(--text-xs); }
    .ev-time { display: none; }
    .log-line { font-size: 10px; padding: 2px var(--sp-2); }
    .ll-ts { display: none; }
  }

  @media (max-width: 480px) {
    .lifecycle-view { padding: var(--sp-2); gap: var(--sp-2); }
    .hero-section { padding: var(--sp-3); border-radius: var(--radius-lg); }
    .status-orb { width: 36px; height: 36px; }
    .orb-inner { width: 12px; height: 12px; }
    .hero-info h2 { font-size: var(--text-md); }
    .hs-value { font-size: var(--text-lg); }
    .stab { padding: 5px 10px; font-size: var(--text-2xs); gap: 3px; }
    .stab-icon { width: 12px; height: 12px; }
    .info-card { padding: var(--sp-3); }
    .ev-metrics { flex-wrap: wrap; }
    .log-lines { max-height: 400px; }
    .ll-num { display: none; }
  }
</style>
