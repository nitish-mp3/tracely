<script>
  import { onMount } from 'svelte';
  import { getStats } from '../lib/api.js';
  import { currentView } from '../stores/config.js';
  import { selectedEventId } from '../stores/events.js';

  let stats = null;
  let loading = true;
  let err = null;
  let activeTab = 'overview';

  onMount(async () => {
    try {
      stats = await getStats();
    } catch (e) {
      err = e.message || 'Failed to load stats';
    } finally {
      loading = false;
    }
  });

  async function refresh() {
    loading = true;
    err = null;
    try {
      stats = await getStats();
    } catch (e) {
      err = e.message || 'Failed to load stats';
    } finally {
      loading = false;
    }
  }

  // Chart helpers
  function maxOf(arr, key) {
    if (!arr || arr.length === 0) return 1;
    return Math.max(...arr.map(a => a[key]), 1);
  }

  function formatHour(h) {
    if (h === 0) return '12am';
    if (h < 12) return h + 'am';
    if (h === 12) return '12pm';
    return (h - 12) + 'pm';
  }

  function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function dayLabel(dayEpoch) {
    const d = new Date(dayEpoch * 86400000);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function pctChange(current, previous) {
    if (previous === 0) return current > 0 ? +100 : 0;
    return Math.round(((current - previous) / previous) * 100);
  }

  function entityShortName(eid) {
    if (!eid) return '—';
    const parts = eid.split('.');
    if (parts.length > 1) {
      return parts.slice(1).join('.').replace(/_/g, ' ');
    }
    return eid.replace(/_/g, ' ');
  }

  function entityDomain(eid) {
    if (!eid) return '';
    return eid.split('.')[0] || '';
  }

  $: totalConfidence = stats?.confidence
    ? Object.values(stats.confidence).reduce((s, v) => s + v, 0)
    : 0;

  $: hourlyMax = stats ? maxOf(stats.hourly_24h, 'count') : 1;
  $: dailyMax = stats ? maxOf(stats.daily_30d, 'count') : 1;
  $: entityMax = stats && stats.entity_counts.length > 0 ? stats.entity_counts[0].count : 1;
  $: domainMax = stats && stats.domain_counts.length > 0 ? stats.domain_counts[0].count : 1;

  $: propagated = stats?.confidence?.['propagated'] || 0;
  $: inferred = stats?.confidence?.['inferred'] || 0;
  $: propPct = totalConfidence > 0 ? (propagated / totalConfidence) * 100 : 0;
  $: infPct = totalConfidence > 0 ? (inferred / totalConfidence) * 100 : 0;

  $: change = stats ? pctChange(stats.today_count, stats.yesterday_count) : 0;
</script>

<div class="stats-view">
  {#if loading}
    <div class="loading-state">
      <div class="spinner" />
      <span>Loading statistics…</span>
    </div>
  {:else if err}
    <div class="error-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
      <p>{err}</p>
      <button class="btn btn-primary" on:click={refresh}>Retry</button>
    </div>
  {:else if stats}
    <!-- Header -->
    <header class="stats-header">
      <div class="stats-title-row">
        <div class="stats-title-left">
          <svg class="title-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="10" width="3" height="8" rx="1"/><rect x="8" y="6" width="3" height="12" rx="1"/><rect x="14" y="2" width="3" height="16" rx="1"/></svg>
          <h2>Activity Dashboard</h2>
        </div>
        <button class="refresh-btn" on:click={refresh} aria-label="Refresh stats">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M1 8a7 7 0 0113.4-2.8M15 8a7 7 0 01-13.4 2.8"/><path d="M14.4 1v4.2h-4.2M1.6 15v-4.2h4.2"/></svg>
        </button>
      </div>

      <nav class="tab-nav">
        <button class="tab" class:active={activeTab === 'overview'} on:click={() => activeTab = 'overview'}>Overview</button>
        <button class="tab" class:active={activeTab === 'entities'} on:click={() => activeTab = 'entities'}>Entities</button>
        <button class="tab" class:active={activeTab === 'activity'} on:click={() => activeTab = 'activity'}>Activity</button>
      </nav>
    </header>

    <div class="stats-content">
      {#if activeTab === 'overview'}
        <!-- KPI Cards -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <span class="kpi-label">Total Events</span>
            <span class="kpi-value">{formatNumber(stats.total_events)}</span>
            <span class="kpi-sub">all time</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Today</span>
            <span class="kpi-value">{formatNumber(stats.today_count)}</span>
            <span class="kpi-sub kpi-change" class:positive={change > 0} class:negative={change < 0}>
              {change > 0 ? '+' : ''}{change}% vs yesterday
            </span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Yesterday</span>
            <span class="kpi-value">{formatNumber(stats.yesterday_count)}</span>
            <span class="kpi-sub">events</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Peak Hour</span>
            <span class="kpi-value">{stats.peak_hour !== null ? formatHour(stats.peak_hour) : '—'}</span>
            <span class="kpi-sub">last 7 days</span>
          </div>
        </div>

        <!-- Hourly chart -->
        <div class="chart-card">
          <h3 class="chart-title">Hourly Activity <span class="chart-sub">(last 24h)</span></h3>
          <div class="bar-chart hourly-chart">
            {#each Array(24) as _, h}
              {@const entry = stats.hourly_24h.find(e => e.hour === h)}
              {@const count = entry ? entry.count : 0}
              <div class="bar-col" title="{formatHour(h)}: {count} events">
                <div class="bar-fill" style="height: {Math.max((count / hourlyMax) * 100, 2)}%"
                  class:peak={stats.peak_hour === h}>
                  {#if count > 0 && count / hourlyMax > 0.3}
                    <span class="bar-val">{formatNumber(count)}</span>
                  {/if}
                </div>
                <span class="bar-label">{h % 6 === 0 ? formatHour(h) : ''}</span>
              </div>
            {/each}
          </div>
        </div>

        <!-- Domain & Confidence side by side -->
        <div class="dual-grid">
          <div class="chart-card">
            <h3 class="chart-title">By Domain</h3>
            <div class="rank-list">
              {#each stats.domain_counts.slice(0, 10) as d, i}
                <div class="rank-row">
                  <span class="rank-idx">{i + 1}</span>
                  <span class="rank-name domain-tag">{d.domain}</span>
                  <div class="rank-bar-wrap">
                    <div class="rank-bar domain-bar" style="width: {(d.count / domainMax) * 100}%" />
                  </div>
                  <span class="rank-count">{formatNumber(d.count)}</span>
                </div>
              {/each}
            </div>
          </div>

          <div class="chart-card">
            <h3 class="chart-title">Confidence</h3>
            {#if totalConfidence > 0}
              <div class="confidence-visual">
                <div class="conf-ring">
                  <svg viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-border)" stroke-width="10" />
                    <circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-success)" stroke-width="10"
                      stroke-dasharray="{propPct * 2.64} {264 - propPct * 2.64}"
                      stroke-dashoffset="66" stroke-linecap="round" />
                    <circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-warning)" stroke-width="10"
                      stroke-dasharray="{infPct * 2.64} 264"
                      stroke-dashoffset="{66 - propPct * 2.64}" stroke-linecap="round" />
                  </svg>
                  <div class="conf-center">
                    <span class="conf-pct">{Math.round((stats.confidence['propagated'] || 0) / totalConfidence * 100)}%</span>
                    <span class="conf-small">verified</span>
                  </div>
                </div>
                <div class="conf-legend">
                  {#each Object.entries(stats.confidence) as [label, count]}
                    <div class="conf-item">
                      <span class="conf-dot" class:propagated={label === 'propagated'} class:inferred={label === 'inferred'} />
                      <span class="conf-label">{label}</span>
                      <span class="conf-count">{formatNumber(count)}</span>
                    </div>
                  {/each}
                </div>
              </div>
            {:else}
              <p class="empty-text">No confidence data</p>
            {/if}

            <h3 class="chart-title" style="margin-top: var(--sp-5)">By Event Type</h3>
            <div class="rank-list compact">
              {#each stats.type_counts.slice(0, 8) as t}
                <div class="rank-row">
                  <span class="rank-name type-tag">{t.event_type}</span>
                  <span class="rank-count">{formatNumber(t.count)}</span>
                </div>
              {/each}
            </div>
          </div>
        </div>

      {:else if activeTab === 'entities'}
        <!-- Entity ranking -->
        <div class="chart-card full">
          <h3 class="chart-title">Top Entities by Event Count</h3>
          <div class="entity-table">
            <div class="entity-header">
              <span class="eth rank-col">#</span>
              <span class="eth name-col">Entity</span>
              <span class="eth domain-col">Domain</span>
              <span class="eth bar-col-h">Activity</span>
              <span class="eth count-col">Events</span>
            </div>
            {#each stats.entity_counts as e, i}
              <div class="entity-row" class:top3={i < 3}>
                <span class="rank-col entity-rank" class:gold={i === 0} class:silver={i === 1} class:bronze={i === 2}>{i + 1}</span>
                <span class="name-col entity-name" title={e.entity_id}>{entityShortName(e.entity_id)}</span>
                <span class="domain-col"><span class="domain-pill">{entityDomain(e.entity_id)}</span></span>
                <div class="bar-col-h">
                  <div class="entity-bar" style="width: {(e.count / entityMax) * 100}%" />
                </div>
                <span class="count-col entity-count">{formatNumber(e.count)}</span>
              </div>
            {/each}
          </div>
        </div>

      {:else if activeTab === 'activity'}
        <!-- Daily chart (30d) -->
        <div class="chart-card full">
          <h3 class="chart-title">Daily Activity <span class="chart-sub">(last 30 days)</span></h3>
          {#if stats.daily_30d.length > 0}
            <div class="daily-chart">
              <div class="daily-bars">
                {#each stats.daily_30d as d}
                  <div class="daily-col" title="{dayLabel(d.day)}: {d.count} events">
                    <div class="daily-fill" style="height: {Math.max((d.count / dailyMax) * 100, 3)}%" />
                  </div>
                {/each}
              </div>
              <div class="daily-labels">
                {#each stats.daily_30d as d, i}
                  {#if i === 0 || i === stats.daily_30d.length - 1 || i % 7 === 0}
                    <span class="daily-label" style="left: {(i / Math.max(stats.daily_30d.length - 1, 1)) * 100}%">{dayLabel(d.day)}</span>
                  {/if}
                {/each}
              </div>
            </div>
          {:else}
            <p class="empty-text">No daily data available</p>
          {/if}
        </div>

        <!-- Hourly heatmap -->
        <div class="chart-card full">
          <h3 class="chart-title">Hourly Breakdown <span class="chart-sub">(last 24h)</span></h3>
          <div class="heatmap-grid">
            {#each Array(24) as _, h}
              {@const entry = stats.hourly_24h.find(e => e.hour === h)}
              {@const count = entry ? entry.count : 0}
              {@const intensity = hourlyMax > 0 ? count / hourlyMax : 0}
              <div class="heat-cell" title="{formatHour(h)}: {count} events"
                style="background: color-mix(in srgb, var(--color-primary) {Math.max(intensity * 100, 5)}%, var(--color-surface-hover))">
                <span class="heat-hour">{formatHour(h)}</span>
                <span class="heat-count">{formatNumber(count)}</span>
              </div>
            {/each}
          </div>
        </div>

        <!-- Compare cards -->
        <div class="compare-grid">
          <div class="compare-card">
            <span class="compare-label">Today</span>
            <span class="compare-value">{formatNumber(stats.today_count)}</span>
          </div>
          <div class="compare-vs">vs</div>
          <div class="compare-card">
            <span class="compare-label">Yesterday</span>
            <span class="compare-value">{formatNumber(stats.yesterday_count)}</span>
          </div>
          <div class="compare-result" class:up={change > 0} class:down={change < 0}>
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              {#if change >= 0}
                <path d="M6 9V3M3 5l3-3 3 3"/>
              {:else}
                <path d="M6 3v6M3 7l3 3 3-3"/>
              {/if}
            </svg>
            <span>{change > 0 ? '+' : ''}{change}%</span>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .stats-view {
    flex: 1; overflow-y: auto; padding: var(--sp-5);
    display: flex; flex-direction: column; gap: var(--sp-5);
    max-width: 1200px; margin: 0 auto; width: 100%;
  }

  /* Loading / Error */
  .loading-state, .error-state {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: var(--sp-3);
    color: var(--color-text-muted);
  }
  .spinner {
    width: 28px; height: 28px; border: 3px solid var(--color-border);
    border-top-color: var(--color-primary); border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error-state svg { width: 32px; height: 32px; color: var(--color-error); }

  /* Header */
  .stats-header {
    display: flex; flex-direction: column; gap: var(--sp-3);
  }
  .stats-title-row {
    display: flex; align-items: center; justify-content: space-between;
  }
  .stats-title-left {
    display: flex; align-items: center; gap: var(--sp-2);
  }
  .title-icon { width: 22px; height: 22px; color: var(--color-primary); }
  .stats-header h2 {
    font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.02em;
  }
  .refresh-btn {
    width: 34px; height: 34px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); border: 1px solid var(--color-border);
    color: var(--color-text-muted); transition: all var(--duration-fast);
  }
  .refresh-btn svg { width: 15px; height: 15px; }
  .refresh-btn:hover { color: var(--color-primary); border-color: var(--color-primary); background: var(--color-primary-soft); }

  .tab-nav {
    display: flex; gap: 2px; padding: 3px;
    background: var(--color-bg-elevated); border-radius: var(--radius-md);
    border: 1px solid var(--color-border); width: fit-content;
  }
  .tab {
    padding: 6px 16px; border-radius: calc(var(--radius-md) - 2px);
    font-size: var(--text-sm); font-weight: 500; color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .tab:hover { color: var(--color-text-secondary); }
  .tab.active { color: var(--color-text); background: var(--color-surface); box-shadow: var(--shadow-xs); }

  /* KPI cards */
  .kpi-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--sp-4);
  }
  .kpi-card {
    display: flex; flex-direction: column; gap: 4px;
    padding: var(--sp-5); border-radius: var(--radius-lg);
    background: var(--color-surface); border: 1px solid var(--color-border);
    transition: all var(--duration-fast);
  }
  .kpi-card:hover { border-color: var(--color-border-hover); box-shadow: var(--shadow-sm); }
  .kpi-label { font-size: var(--text-xs); font-weight: 500; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .kpi-value { font-size: 28px; font-weight: 700; color: var(--color-text); letter-spacing: -0.03em; }
  .kpi-sub { font-size: var(--text-xs); color: var(--color-text-muted); }
  .kpi-change.positive { color: var(--color-success); }
  .kpi-change.negative { color: var(--color-error); }

  /* Chart card */
  .chart-card {
    padding: var(--sp-5); border-radius: var(--radius-lg);
    background: var(--color-surface); border: 1px solid var(--color-border);
  }
  .chart-card.full { grid-column: 1 / -1; }
  .chart-title {
    font-size: var(--text-md); font-weight: 600; margin-bottom: var(--sp-4);
    display: flex; align-items: baseline; gap: var(--sp-2);
  }
  .chart-sub { font-size: var(--text-xs); color: var(--color-text-muted); font-weight: 400; }

  /* Bar chart (hourly) */
  .bar-chart {
    display: flex; align-items: flex-end; gap: 2px; height: 180px;
  }
  .bar-col {
    flex: 1; display: flex; flex-direction: column; align-items: center;
    height: 100%; justify-content: flex-end; gap: 4px;
  }
  .bar-fill {
    width: 100%; border-radius: 3px 3px 0 0;
    background: var(--color-primary); opacity: 0.7;
    transition: height 0.5s var(--ease-out); position: relative;
    display: flex; align-items: flex-start; justify-content: center;
    min-height: 2px;
  }
  .bar-fill.peak { opacity: 1; background: var(--color-warning); }
  .bar-val { font-size: 9px; color: white; font-weight: 600; padding-top: 3px; }
  .bar-label { font-size: 9px; color: var(--color-text-muted); height: 14px; }

  /* Dual grid */
  .dual-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4);
  }

  /* Rank list */
  .rank-list { display: flex; flex-direction: column; gap: 6px; }
  .rank-list.compact { gap: 4px; }
  .rank-row {
    display: flex; align-items: center; gap: var(--sp-2);
    padding: 4px 0;
  }
  .rank-idx {
    width: 20px; font-size: var(--text-xs); color: var(--color-text-muted);
    font-weight: 600; text-align: center;
  }
  .rank-name {
    min-width: 80px; font-size: var(--text-sm); font-weight: 500;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .domain-tag { color: var(--color-info); }
  .type-tag {
    font-family: var(--font-mono); font-size: var(--text-xs);
    color: var(--color-text-secondary); flex: 1;
  }
  .rank-bar-wrap { flex: 1; height: 6px; background: var(--color-bg-elevated); border-radius: var(--radius-full); overflow: hidden; }
  .rank-bar { height: 100%; border-radius: var(--radius-full); transition: width 0.5s var(--ease-out); }
  .domain-bar { background: var(--color-info); opacity: 0.6; }
  .rank-count { font-size: var(--text-xs); font-weight: 600; color: var(--color-text-secondary); min-width: 40px; text-align: right; }

  /* Confidence ring */
  .confidence-visual { display: flex; align-items: center; gap: var(--sp-5); }
  .conf-ring { position: relative; width: 120px; height: 120px; flex-shrink: 0; }
  .conf-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  .conf-center {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
  }
  .conf-pct { font-size: 22px; font-weight: 700; color: var(--color-text); }
  .conf-small { font-size: 10px; color: var(--color-text-muted); }
  .conf-legend { display: flex; flex-direction: column; gap: var(--sp-2); }
  .conf-item { display: flex; align-items: center; gap: var(--sp-2); }
  .conf-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-text-muted); }
  .conf-dot.propagated { background: var(--color-success); }
  .conf-dot.inferred { background: var(--color-warning); }
  .conf-label { font-size: var(--text-sm); color: var(--color-text-secondary); flex: 1; text-transform: capitalize; }
  .conf-count { font-size: var(--text-xs); font-weight: 600; color: var(--color-text-muted); }

  /* Entity table */
  .entity-table { display: flex; flex-direction: column; }
  .entity-header {
    display: flex; align-items: center; gap: var(--sp-3);
    padding: var(--sp-2) var(--sp-3);
    border-bottom: 1px solid var(--color-border);
  }
  .eth { font-size: var(--text-2xs); font-weight: 600; text-transform: uppercase; color: var(--color-text-muted); letter-spacing: 0.06em; }
  .entity-row {
    display: flex; align-items: center; gap: var(--sp-3);
    padding: var(--sp-2) var(--sp-3);
    border-bottom: 1px solid var(--color-border-subtle, var(--color-border));
    transition: background var(--duration-fast);
  }
  .entity-row:hover { background: var(--color-surface-hover); }
  .entity-row.top3 { background: var(--color-bg-elevated); }
  .rank-col { width: 32px; text-align: center; flex-shrink: 0; }
  .name-col { flex: 2; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .domain-col { width: 100px; flex-shrink: 0; }
  .bar-col-h { flex: 3; min-width: 0; }
  .count-col { width: 70px; text-align: right; flex-shrink: 0; }
  .entity-rank { font-weight: 700; font-size: var(--text-sm); color: var(--color-text-muted); }
  .entity-rank.gold { color: #f59e0b; }
  .entity-rank.silver { color: #94a3b8; }
  .entity-rank.bronze { color: #d97706; }
  .entity-name { font-size: var(--text-sm); font-weight: 500; text-transform: capitalize; }
  .domain-pill {
    display: inline-block; padding: 1px 8px; border-radius: var(--radius-full);
    font-size: 10px; font-weight: 600; background: var(--color-info-soft);
    color: var(--color-info); text-transform: uppercase;
  }
  .entity-bar {
    height: 8px; border-radius: var(--radius-full);
    background: linear-gradient(90deg, var(--color-primary), var(--color-primary-hover, var(--color-primary)));
    opacity: 0.6; transition: width 0.5s var(--ease-out);
  }
  .entity-count { font-size: var(--text-sm); font-weight: 600; color: var(--color-text-secondary); }

  /* Daily chart */
  .daily-chart { position: relative; }
  .daily-bars {
    display: flex; align-items: flex-end; gap: 3px; height: 200px;
  }
  .daily-col {
    flex: 1; height: 100%; display: flex; align-items: flex-end;
  }
  .daily-fill {
    width: 100%; border-radius: 3px 3px 0 0;
    background: var(--color-primary); opacity: 0.6;
    transition: height 0.5s var(--ease-out);
  }
  .daily-fill:hover { opacity: 1; }
  .daily-labels {
    position: relative; height: 20px; margin-top: 6px;
  }
  .daily-label {
    position: absolute; transform: translateX(-50%);
    font-size: 9px; color: var(--color-text-muted); white-space: nowrap;
  }

  /* Heatmap */
  .heatmap-grid {
    display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px;
  }
  .heat-cell {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: var(--sp-3); border-radius: var(--radius-md);
    transition: all var(--duration-fast); gap: 2px;
  }
  .heat-cell:hover { transform: scale(1.05); }
  .heat-hour { font-size: 10px; font-weight: 600; color: var(--color-text-secondary); }
  .heat-count { font-size: var(--text-sm); font-weight: 700; color: var(--color-text); }

  /* Compare */
  .compare-grid {
    display: flex; align-items: center; justify-content: center; gap: var(--sp-5);
    padding: var(--sp-5);
  }
  .compare-card {
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    padding: var(--sp-5) var(--sp-8); border-radius: var(--radius-lg);
    background: var(--color-surface); border: 1px solid var(--color-border);
  }
  .compare-label { font-size: var(--text-xs); color: var(--color-text-muted); font-weight: 500; text-transform: uppercase; }
  .compare-value { font-size: 32px; font-weight: 700; color: var(--color-text); letter-spacing: -0.03em; }
  .compare-vs { font-size: var(--text-lg); color: var(--color-text-muted); font-weight: 500; }
  .compare-result {
    display: flex; align-items: center; gap: 4px;
    padding: 8px 16px; border-radius: var(--radius-full);
    font-size: var(--text-md); font-weight: 700;
    background: var(--color-surface-hover); color: var(--color-text-muted);
  }
  .compare-result svg { width: 14px; height: 14px; }
  .compare-result.up { color: var(--color-success); background: var(--color-success-soft); }
  .compare-result.down { color: var(--color-error); background: var(--color-error-soft); }

  .empty-text { font-size: var(--text-sm); color: var(--color-text-muted); text-align: center; padding: var(--sp-5); }

  /* Responsive */
  @media (max-width: 768px) {
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .dual-grid { grid-template-columns: 1fr; }
    .heatmap-grid { grid-template-columns: repeat(6, 1fr); }
    .entity-header .bar-col-h, .entity-row .bar-col-h { display: none; }
    .entity-header .domain-col, .entity-row .domain-col { display: none; }
    .compare-grid { flex-direction: column; }
    .confidence-visual { flex-direction: column; align-items: center; }
    .stats-view { padding: var(--sp-3); }
    .kpi-value { font-size: 22px; }
  }
  @media (max-width: 480px) {
    .kpi-grid { grid-template-columns: 1fr 1fr; gap: var(--sp-2); }
    .kpi-card { padding: var(--sp-3); }
    .kpi-value { font-size: 20px; }
    .heatmap-grid { grid-template-columns: repeat(4, 1fr); }
    .bar-chart { height: 120px; }
  }
</style>
