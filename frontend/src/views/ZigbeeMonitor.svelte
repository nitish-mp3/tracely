<script>
  import { onMount, onDestroy } from 'svelte';
  import { getProtocolActivity, subscribeEvents } from '../lib/api.js';
  import { currentView } from '../stores/config.js';
  import { selectedEventId } from '../stores/events.js';
  import EventNode from '../components/EventNode.svelte';

  // ── State ──────────────────────────────────────────────
  let events = [];
  let total = 0;
  let page = 1;
  const LIMIT = 100;

  let loading = false;
  let loadingMore = false;
  let hasMore = true;
  let liveCount = 0;
  let sentinel;
  let observer;
  let unsubSSE;

  // Filter
  let filterEntity = '';
  let fromDate = '';
  let toDate = '';

  // Protocol selector
  let protocol = 'mqtt';
  const PROTOCOLS = [
    { value: 'mqtt', label: 'Zigbee2MQTT' },
    { value: 'zha', label: 'ZHA' },
    { value: 'zigbee', label: 'Zigbee' },
  ];

  // Stats
  $: entityCount = new Set(events.map(e => e.entity_id).filter(Boolean)).size;
  $: domainBreakdown = events.reduce((acc, e) => {
    const d = e.domain || 'unknown';
    acc[d] = (acc[d] || 0) + 1;
    return acc;
  }, {});
  $: sortedDomains = Object.entries(domainBreakdown).sort((a, b) => b[1] - a[1]);

  // ── Data loading ───────────────────────────────────────

  async function loadEvents(append = false) {
    if (!append) {
      loading = true;
      page = 1;
    } else {
      loadingMore = true;
    }
    try {
      const params = { page, limit: LIMIT };
      if (filterEntity) params.entity = filterEntity;
      if (fromDate) params.from = new Date(fromDate).toISOString();
      if (toDate) params.to = new Date(toDate).toISOString();
      const res = await getProtocolActivity(protocol, params);
      total = res.total;
      hasMore = (res.page * res.limit) < res.total;
      if (append) {
        events = [...events, ...res.items];
      } else {
        events = res.items;
        liveCount = 0;
      }
    } catch (err) {
      console.error('Zigbee load error', err);
    } finally {
      loading = false;
      loadingMore = false;
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    page++;
    await loadEvents(true);
  }

  function handleEventClick(event) {
    $selectedEventId = event.id;
    $currentView = 'trace';
  }

  function getZigbeeDetails(event) {
    try {
      const payload = JSON.parse(event.payload || '{}');
      const attrs = (payload.new_state || payload)?.attributes || {};
      const details = [];
      if (attrs.linkquality !== undefined) {
        const lqi = Number(attrs.linkquality);
        details.push({ key: 'LQI', val: `${lqi}/255`, type: lqi > 150 ? 'ok' : lqi > 80 ? 'warn' : 'bad' });
      }
      if (attrs.battery !== undefined) {
        const bat = Number(attrs.battery);
        details.push({ key: 'Battery', val: `${bat}%`, type: bat > 30 ? 'ok' : 'bad' });
      }
      if (attrs.temperature !== undefined) details.push({ key: 'Temp', val: `${attrs.temperature}°C`, type: 'info' });
      if (attrs.humidity !== undefined) details.push({ key: 'Humidity', val: `${attrs.humidity}%`, type: 'info' });
      const lux = attrs.illuminance_lux ?? attrs.illuminance;
      if (lux !== undefined) details.push({ key: 'Lux', val: String(lux), type: 'info' });
      if (attrs.action) details.push({ key: 'Action', val: String(attrs.action), type: 'info' });
      if (attrs.occupancy !== undefined) details.push({ key: 'Occupancy', val: attrs.occupancy ? 'yes' : 'no', type: attrs.occupancy ? 'ok' : 'info' });
      if (attrs.contact !== undefined) details.push({ key: 'Contact', val: attrs.contact ? 'closed' : 'open', type: attrs.contact ? 'ok' : 'warn' });
      return details;
    } catch { return []; }
  }

  function applyFilters() {
    loadEvents(false);
  }

  function clearFilters() {
    filterEntity = '';
    fromDate = '';
    toDate = '';
    loadEvents(false);
  }

  function switchProtocol(p) {
    protocol = p;
    loadEvents(false);
  }

  $: hasFilters = !!(filterEntity || fromDate || toDate);

  function setupObserver() {
    if (observer) observer.disconnect();
    if (!sentinel) return;
    observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMore(); },
      { rootMargin: '200px' },
    );
    observer.observe(sentinel);
  }

  $: if (sentinel) setupObserver();

  onMount(async () => {
    await loadEvents();
    unsubSSE = subscribeEvents(
      (event) => {
        const integ = (event.integration || '').toLowerCase();
        const eid = (event.entity_id || '').toLowerCase();
        if (integ === protocol || integ.includes('zigbee') || integ.includes('z2m') || eid.includes('zigbee') || eid.includes('z2m')) {
          events = [event, ...events.slice(0, 499)];
          liveCount++;
          total++;
        }
      },
      () => {},
    );
  });

  onDestroy(() => {
    if (unsubSSE) unsubSSE();
    if (observer) observer.disconnect();
  });
</script>

<div class="zigbee-layout">
  <div class="main-panel">

    <!-- Header -->
    <div class="panel-header">
      <div class="header-left">
        <h2 class="panel-title">
          <svg class="title-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M2 4l6-2 6 2M2 8l6 2 6-2M2 12l6 2 6-2"/>
          </svg>
          Zigbee Monitor
        </h2>
        {#if liveCount > 0}
          <span class="live-badge">{liveCount} new</span>
        {/if}
      </div>

      <!-- Protocol selector -->
      <div class="protocol-selector">
        {#each PROTOCOLS as p}
          <button
            class="protocol-btn"
            class:active={protocol === p.value}
            on:click={() => switchProtocol(p.value)}
          >{p.label}</button>
        {/each}
      </div>

      <!-- Summary chips -->
      <div class="summary-chips">
        <div class="chip">
          <span class="chip-label">Events</span>
          <span class="chip-value">{total.toLocaleString()}</span>
        </div>
        <div class="chip">
          <span class="chip-label">Entities</span>
          <span class="chip-value">{entityCount}</span>
        </div>
        {#each sortedDomains.slice(0, 5) as [domain, count]}
          <div class="chip chip-domain">
            <span class="chip-label">{domain}</span>
            <span class="chip-value">{count}</span>
          </div>
        {/each}
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="filter-row">
        <div class="filter-group">
          <label for="z-entity-filter" class="filter-label">Entity</label>
          <input id="z-entity-filter" class="filter-input" type="text" bind:value={filterEntity}
            placeholder="e.g. light.living_room" />
        </div>
        <div class="filter-group">
          <label for="z-from-filter" class="filter-label">From</label>
          <input id="z-from-filter" class="filter-input" type="datetime-local" bind:value={fromDate} />
        </div>
        <div class="filter-group">
          <label for="z-to-filter" class="filter-label">To</label>
          <input id="z-to-filter" class="filter-input" type="datetime-local" bind:value={toDate} />
        </div>
        <div class="filter-actions">
          <button class="btn-apply" on:click={applyFilters}>Apply</button>
          {#if hasFilters}
            <button class="btn-clear" on:click={clearFilters}>Clear</button>
          {/if}
        </div>
      </div>
    </div>

    <!-- Event list -->
    <div class="content-area">
      {#if loading}
        <div class="loading-state">
          <div class="spinner" />
          <span>Loading Zigbee activity…</span>
        </div>
      {:else if events.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M8 16l16-8 16 8M8 24l16 8 16-8M8 32l16 8 16-8"/>
          </svg>
          <p>No Zigbee activity yet.</p>
          <span>Events from {PROTOCOLS.find(p => p.value === protocol)?.label || protocol} integration will appear here.</span>
        </div>
      {:else}
        <ul class="event-list">
          {#each events as event (event.id)}
            <li class="event-item">
              <EventNode
                {event}
                on:click={() => handleEventClick(event)}
                on:viewin={(e) => { $currentView = e.detail; }}
              />
              {#if getZigbeeDetails(event).length > 0}
                <div class="proto-details">
                  {#each getZigbeeDetails(event) as d}
                    <span class="proto-chip proto-{d.type}">
                      <span class="pc-k">{d.key}</span>
                      <span class="pc-v">{d.val}</span>
                    </span>
                  {/each}
                </div>
              {/if}
            </li>
          {/each}
        </ul>
        {#if hasMore}
          <div bind:this={sentinel} class="scroll-sentinel">
            {#if loadingMore}
              <div class="load-more"><div class="spinner small" /><span>Loading more…</span></div>
            {/if}
          </div>
        {/if}
      {/if}
    </div>
  </div>

</div>

<style>
  .zigbee-layout {
    display: flex;
    height: 100%;
    overflow: hidden;
    background: var(--color-bg);
  }
  .main-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Header ─────────────────────────────────── */
  .panel-header {
    padding: 14px 16px 10px;
    border-bottom: 1px solid var(--color-border);
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    flex-shrink: 0;
    background: var(--color-surface);
  }
  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .panel-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text);
    display: flex;
    align-items: center;
    gap: 7px;
    margin: 0;
  }
  .title-icon {
    width: 18px;
    height: 18px;
    color: #22c55e;
  }
  .live-badge {
    background: #22c55e22;
    color: #22c55e;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 9px;
    border-radius: 999px;
  }

  /* ── Protocol selector ──────────────────────── */
  .protocol-selector {
    display: flex;
    gap: 2px;
    padding: 3px;
    background: var(--color-bg);
    border-radius: 8px;
    border: 1px solid var(--color-border);
  }
  .protocol-btn {
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-muted);
    transition: all 0.15s;
  }
  .protocol-btn:hover { color: var(--color-text-secondary); }
  .protocol-btn.active {
    color: var(--color-text);
    background: var(--color-surface);
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
  }

  .summary-chips {
    display: flex;
    gap: 8px;
    margin-left: auto;
  }
  .chip {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 12px;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
  }
  .chip-label { color: var(--color-text-muted); }
  .chip-value { font-weight: 600; color: var(--color-text); }

  /* ── Filter bar ─────────────────────────────── */
  .filter-bar {
    padding: 10px 16px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-bg);
    flex-shrink: 0;
  }
  .filter-row {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    flex-wrap: wrap;
  }
  .filter-group {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .filter-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-text-muted);
  }
  .filter-input {
    height: 30px;
    padding: 0 10px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 12px;
    outline: none;
  }
  .filter-input:focus {
    border-color: #22c55e;
  }
  .filter-actions {
    display: flex;
    gap: 6px;
    align-items: flex-end;
  }
  .btn-apply {
    height: 30px;
    padding: 0 16px;
    border-radius: 6px;
    background: #22c55e;
    color: #fff;
    font-size: 12px;
    font-weight: 600;
  }
  .btn-apply:hover { background: #16a34a; }
  .btn-clear {
    height: 30px;
    padding: 0 12px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    color: var(--color-text-muted);
    font-size: 12px;
  }

  /* ── Content ────────────────────────────────── */
  .content-area {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
  }
  .event-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .event-item {
    animation: fadeIn 0.2s ease both;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .loading-state, .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 16px;
    gap: 12px;
    color: var(--color-text-muted);
    text-align: center;
  }
  .empty-state svg { width: 48px; height: 48px; opacity: 0.4; }
  .empty-state p { font-weight: 600; font-size: 14px; color: var(--color-text-secondary); }
  .empty-state span { font-size: 12px; }
  .spinner {
    width: 24px; height: 24px; border-radius: 50%;
    border: 2px solid var(--color-border); border-top-color: #22c55e;
    animation: spin 0.6s linear infinite;
  }
  .spinner.small { width: 16px; height: 16px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .scroll-sentinel { height: 1px; }
  .load-more {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    padding: 12px; color: var(--color-text-muted); font-size: 12px;
  }

  /* ── Protocol Detail Chips ──────────────────── */
  .proto-details {
    display: flex; flex-wrap: wrap; gap: 4px;
    padding: 4px 12px 8px 40px;
  }
  .proto-chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 500;
    background: var(--color-surface-hover);
    border: 1px solid var(--color-border);
  }
  .proto-ok { border-color: rgba(52,211,153,.4); background: rgba(52,211,153,.08); }
  .proto-warn { border-color: rgba(251,191,36,.4); background: rgba(251,191,36,.08); }
  .proto-bad { border-color: rgba(239,68,68,.4); background: rgba(239,68,68,.08); }
  .pc-k { color: var(--color-text-muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
  .pc-v { color: var(--color-text); font-weight: 600; }
  .proto-ok .pc-v { color: var(--color-success); }
  .proto-bad .pc-v { color: var(--color-error, #ef4444); }
  .proto-warn .pc-v { color: #f59e0b; }

  /* ── Domain chips in header ──────────────────── */
  .chip-domain {
    background: var(--color-surface-hover);
    border-color: var(--color-border);
  }
</style>
