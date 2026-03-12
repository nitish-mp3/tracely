<script>
  import { onMount, onDestroy } from 'svelte';
  import { getKnxTelegrams, getKnxGroupAddresses, getKnxFlow, subscribeKnxEvents } from '../lib/api.js';
  import { currentView } from '../stores/config.js';

  // ── State ──────────────────────────────────────────────
  let telegrams = [];
  let groupAddresses = [];
  let total = 0;
  let page = 1;
  const LIMIT = 100;

  // Filters
  let filterDirection = '';    // '' | 'Incoming' | 'Outgoing'
  let filterGA = '';
  let filterEntity = '';
  let fromDate = '';
  let toDate = '';

  // GA detail panel
  let selectedGA = null;
  let flowData = null;
  let flowLoading = false;

  // Table state
  let loading = false;
  let loadingMore = false;
  let hasMore = true;
  let liveCount = 0;   // telegrams received via SSE since last reload

  // Summary stats (derived)
  $: totalGAs = groupAddresses.length;
  $: incoming = telegrams.filter(t => t.direction === 'Incoming').length;
  $: outgoing = telegrams.filter(t => t.direction === 'Outgoing').length;
  $: activeGAs = new Set(telegrams.map(t => t.group_address)).size;

  let unsubscribeKnx;
  let scrollEl;

  // ── Data loading ───────────────────────────────────────

  async function loadTelegrams(append = false) {
    if (!append) {
      loading = true;
      page = 1;
    } else {
      loadingMore = true;
    }
    try {
      const params = { page, limit: LIMIT };
      if (filterDirection) params.direction = filterDirection;
      if (filterGA)        params.group_address = filterGA;
      if (filterEntity)    params.entity = filterEntity;
      if (fromDate)        params.from = new Date(fromDate).toISOString();
      if (toDate)          params.to = new Date(toDate).toISOString();

      const res = await getKnxTelegrams(params);
      total = res.total;
      hasMore = (res.page * res.limit) < res.total;
      if (append) {
        telegrams = [...telegrams, ...res.items];
      } else {
        telegrams = res.items;
        liveCount = 0;
      }
    } catch (err) {
      console.error('KNX telegram load error', err);
    } finally {
      loading = false;
      loadingMore = false;
    }
  }

  async function loadGAs() {
    try {
      const res = await getKnxGroupAddresses();
      groupAddresses = res.items || [];
    } catch (err) {
      console.error('KNX GA load error', err);
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    page++;
    await loadTelegrams(true);
  }

  // ── GA flow panel ──────────────────────────────────────

  async function openGA(ga, aroundTs) {
    selectedGA = ga;
    flowLoading = true;
    flowData = null;
    try {
      flowData = await getKnxFlow(ga, aroundTs, 8000);
    } catch (err) {
      console.error('KNX flow load error', err);
    } finally {
      flowLoading = false;
    }
  }

  function closePanel() {
    selectedGA = null;
    flowData = null;
  }

  // ── Live SSE ───────────────────────────────────────────

  function handleLiveTelegram(tg) {
    // Prepend to list (most recent first) and count
    telegrams = [tg, ...telegrams.slice(0, 499)];
    liveCount++;
    total++;

    // Keep GA list up to date
    const existing = groupAddresses.find(g => g.group_address === tg.group_address);
    if (existing) {
      existing.last_seen = tg.timestamp;
      existing.last_value = tg.decoded_value;
      if (tg.telegram_type === 'GroupValueWrite')    existing.total_writes++;
      if (tg.telegram_type === 'GroupValueRead')     existing.total_reads++;
      if (tg.telegram_type === 'GroupValueResponse') existing.total_responses++;
      groupAddresses = groupAddresses; // trigger reactivity
    } else {
      groupAddresses = [{
        group_address: tg.group_address,
        friendly_name: null,
        last_seen: tg.timestamp,
        last_value: tg.decoded_value,
        total_writes: tg.telegram_type === 'GroupValueWrite' ? 1 : 0,
        total_reads: tg.telegram_type === 'GroupValueRead' ? 1 : 0,
        total_responses: tg.telegram_type === 'GroupValueResponse' ? 1 : 0,
      }, ...groupAddresses];
    }
  }

  // ── Helpers ────────────────────────────────────────────

  function fmtTime(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return iso; }
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return iso; }
  }

  function tgTypeShort(t) {
    if (!t) return '?';
    if (t.includes('Write'))    return 'Write';
    if (t.includes('Read'))     return 'Read';
    if (t.includes('Response')) return 'Resp';
    return t.slice(0, 5);
  }

  function decodeValue(v) {
    if (v === null || v === undefined) return '—';
    try {
      const p = JSON.parse(v);
      if (typeof p === 'boolean') return p ? 'ON' : 'OFF';
      if (typeof p === 'number')  return String(p);
      if (typeof p === 'string')  return p;
      return JSON.stringify(p);
    } catch {
      return String(v);
    }
  }

  function applyFilters() {
    loadTelegrams(false);
  }

  function clearFilters() {
    filterDirection = '';
    filterGA = '';
    filterEntity = '';
    fromDate = '';
    toDate = '';
    loadTelegrams(false);
  }

  $: hasFilters = !!(filterDirection || filterGA || filterEntity || fromDate || toDate);

  // Infinite scroll sentinel
  let sentinel;

  function setupInfiniteScroll() {
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMore(); },
      { rootMargin: '200px' },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }

  onMount(async () => {
    await Promise.all([loadTelegrams(), loadGAs()]);
    unsubscribeKnx = subscribeKnxEvents(handleLiveTelegram);
    return setupInfiniteScroll();
  });

  onDestroy(() => {
    if (unsubscribeKnx) unsubscribeKnx();
  });
</script>

<div class="knx-layout">

  <!-- ── Left: telegram stream ───────────────────────── -->
  <div class="main-panel">

    <!-- Header bar -->
    <div class="panel-header">
      <div class="header-left">
        <h2 class="panel-title">
          <svg class="title-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="3" cy="8" r="1.5"/><circle cx="8" cy="3" r="1.5"/><circle cx="13" cy="8" r="1.5"/><circle cx="8" cy="13" r="1.5"/>
            <path d="M4.5 8h7M8 4.5v7"/>
          </svg>
          KNX Monitor
        </h2>
        {#if liveCount > 0}
          <span class="live-badge">{liveCount} new</span>
        {/if}
      </div>

      <!-- Summary chips -->
      <div class="summary-chips">
        <div class="chip chip-total">
          <span class="chip-label">Total</span>
          <span class="chip-value">{total.toLocaleString()}</span>
        </div>
        <div class="chip chip-ga">
          <span class="chip-label">Group Addresses</span>
          <span class="chip-value">{totalGAs}</span>
        </div>
        <div class="chip chip-in">
          <span class="chip-label">↓ In</span>
          <span class="chip-value">{incoming}</span>
        </div>
        <div class="chip chip-out">
          <span class="chip-label">↑ Out</span>
          <span class="chip-value">{outgoing}</span>
        </div>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="filter-row">
        <div class="filter-group">
          <label for="dir-filter" class="filter-label">Direction</label>
          <select id="dir-filter" class="filter-select" bind:value={filterDirection}>
            <option value="">All</option>
            <option value="Incoming">↓ Incoming</option>
            <option value="Outgoing">↑ Outgoing</option>
          </select>
        </div>
        <div class="filter-group">
          <label for="ga-filter" class="filter-label">Group Address</label>
          <input id="ga-filter" class="filter-input" type="text" bind:value={filterGA}
            placeholder="e.g. 1/2/3" list="ga-datalist" />
          <datalist id="ga-datalist">
            {#each groupAddresses as ga}
              <option value={ga.group_address}>{ga.group_address}{ga.friendly_name ? ' — ' + ga.friendly_name : ''}</option>
            {/each}
          </datalist>
        </div>
        <div class="filter-group">
          <label for="entity-filter" class="filter-label">Entity</label>
          <input id="entity-filter" class="filter-input" type="text" bind:value={filterEntity}
            placeholder="e.g. light.office" />
        </div>
        <div class="filter-group">
          <label for="from-filter" class="filter-label">From</label>
          <input id="from-filter" class="filter-input" type="datetime-local" bind:value={fromDate} />
        </div>
        <div class="filter-group">
          <label for="to-filter" class="filter-label">To</label>
          <input id="to-filter" class="filter-input" type="datetime-local" bind:value={toDate} />
        </div>
        <div class="filter-actions">
          <button class="btn-apply" on:click={applyFilters}>Apply</button>
          {#if hasFilters}
            <button class="btn-clear" on:click={clearFilters}>Clear</button>
          {/if}
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="table-wrapper" bind:this={scrollEl}>
      {#if loading}
        <div class="loading-state">
          <div class="spinner" />
          <span>Loading KNX telegrams…</span>
        </div>
      {:else if telegrams.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="10" cy="24" r="4"/><circle cx="24" cy="10" r="4"/><circle cx="38" cy="24" r="4"/><circle cx="24" cy="38" r="4"/>
            <path d="M14 24h20M24 14v20"/>
          </svg>
          <p>No KNX telegrams yet.</p>
          <span>Telegrams will appear here as KNX activity occurs on the bus.</span>
        </div>
      {:else}
        <table class="tg-table" aria-label="KNX Telegrams">
          <thead>
            <tr>
              <th>Time</th>
              <th>Dir</th>
              <th>Group Address</th>
              <th>Type</th>
              <th>Value</th>
              <th>Source</th>
              <th>Entity</th>
              <th>Raw</th>
            </tr>
          </thead>
          <tbody>
            {#each telegrams as tg (tg.id)}
              <tr
                class="tg-row"
                class:incoming={tg.direction === 'Incoming'}
                class:outgoing={tg.direction === 'Outgoing'}
                on:click={() => openGA(tg.group_address, tg.timestamp)}
                aria-label="View flow for {tg.group_address}"
              >
                <td class="col-time" title={tg.timestamp}>{fmtTime(tg.timestamp)}</td>
                <td class="col-dir">
                  {#if tg.direction === 'Incoming'}
                    <span class="dir-badge incoming" title="Incoming from bus">↓ IN</span>
                  {:else}
                    <span class="dir-badge outgoing" title="Outgoing to bus">↑ OUT</span>
                  {/if}
                </td>
                <td class="col-ga">
                  <button class="ga-chip" on:click|stopPropagation={() => { filterGA = tg.group_address; applyFilters(); }}
                    title="Filter by {tg.group_address}">
                    {tg.group_address}
                  </button>
                </td>
                <td class="col-type">
                  <span class="type-badge type-{tg.telegram_type?.toLowerCase().replace('groupvalue', '')}">
                    {tgTypeShort(tg.telegram_type)}
                  </span>
                </td>
                <td class="col-value">{decodeValue(tg.decoded_value)}</td>
                <td class="col-source">{tg.source_address ?? '—'}</td>
                <td class="col-entity">
                  {#if tg.linked_entity_id}
                    <span class="entity-link" title={tg.linked_entity_id}>
                      {tg.linked_entity_id.split('.').pop()}
                    </span>
                  {:else}
                    <span class="dim">—</span>
                  {/if}
                </td>
                <td class="col-raw">
                  {#if tg.raw_data}
                    <span class="raw-bytes" title="Raw hex: {tg.raw_data}">{tg.raw_data.slice(0,8)}{tg.raw_data.length > 8 ? '…' : ''}</span>
                  {:else}
                    <span class="dim">—</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>

        <!-- Infinite scroll sentinel -->
        {#if hasMore}
          <div bind:this={sentinel} class="scroll-sentinel">
            {#if loadingMore}
              <div class="spinner small" />
            {/if}
          </div>
        {/if}
      {/if}
    </div>
  </div>

  <!-- ── Right: GA explorer ──────────────────────────── -->
  <div class="ga-sidebar">
    <div class="sidebar-header">
      <h3 class="sidebar-title">Group Addresses</h3>
      <span class="sidebar-count">{groupAddresses.length}</span>
    </div>
    <div class="ga-list">
      {#each groupAddresses as ga}
        <button
          class="ga-row"
          class:selected={selectedGA === ga.group_address}
          on:click={() => openGA(ga.group_address, null)}
          aria-label="Open {ga.group_address}"
        >
          <div class="ga-address">{ga.group_address}</div>
          {#if ga.friendly_name}
            <div class="ga-name">{ga.friendly_name}</div>
          {/if}
          <div class="ga-meta">
            <span class="ga-stat" title="Writes">W:{ga.total_writes ?? 0}</span>
            <span class="ga-stat" title="Reads">R:{ga.total_reads ?? 0}</span>
            <span class="ga-stat" title="Responses">P:{ga.total_responses ?? 0}</span>
            {#if ga.last_value !== null && ga.last_value !== undefined}
              <span class="ga-last-val">{decodeValue(ga.last_value)}</span>
            {/if}
          </div>
        </button>
      {/each}
      {#if groupAddresses.length === 0}
        <div class="sidebar-empty">No group addresses seen yet</div>
      {/if}
    </div>
  </div>

</div>

<!-- ── Flow detail panel (slide-in) ─────────────────── -->
{#if selectedGA}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="panel-overlay" on:click={closePanel} aria-label="Close panel" role="button" tabindex="0" />
  <div class="flow-panel" role="dialog" aria-label="KNX flow for {selectedGA}">
    <div class="flow-header">
      <div class="flow-title">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M3 8h10M9 4l4 4-4 4"/>
        </svg>
        <span>Flow — <strong>{selectedGA}</strong></span>
      </div>
      <button class="close-btn" on:click={closePanel} aria-label="Close">
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l8 8M10 2l-8 8"/></svg>
      </button>
    </div>

    {#if flowLoading}
      <div class="flow-loading"><div class="spinner" /></div>
    {:else if flowData}
      <div class="flow-body">

        <!-- KNX telegrams section -->
        {#if flowData.knx_telegrams?.length > 0}
          <div class="flow-section">
            <div class="flow-section-title">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <circle cx="3" cy="8" r="1.5"/><circle cx="13" cy="8" r="1.5"/><path d="M4.5 8h7"/>
              </svg>
              KNX Telegrams ({flowData.knx_telegrams.length})
            </div>
            {#each flowData.knx_telegrams as tg}
              <div class="flow-row knx"
                   class:incoming={tg.direction === 'Incoming'}
                   class:outgoing={tg.direction === 'Outgoing'}>
                <div class="flow-row-head">
                  {#if tg.direction === 'Incoming'}
                    <span class="dir-badge incoming">↓ IN</span>
                  {:else}
                    <span class="dir-badge outgoing">↑ OUT</span>
                  {/if}
                  <span class="type-badge type-{tg.telegram_type?.toLowerCase().replace('groupvalue', '')}">
                    {tgTypeShort(tg.telegram_type)}
                  </span>
                  <span class="flow-time">{fmtDateTime(tg.timestamp)}</span>
                </div>
                <div class="flow-row-body">
                  <div class="flow-detail-row">
                    <span class="flow-key">Address</span>
                    <span class="flow-val ga-chip-sm">{tg.group_address}</span>
                  </div>
                  <div class="flow-detail-row">
                    <span class="flow-key">Value</span>
                    <span class="flow-val value-highlight">{decodeValue(tg.decoded_value)}</span>
                  </div>
                  {#if tg.source_address}
                    <div class="flow-detail-row">
                      <span class="flow-key">Source</span>
                      <span class="flow-val mono">{tg.source_address}</span>
                    </div>
                  {/if}
                  {#if tg.raw_data}
                    <div class="flow-detail-row">
                      <span class="flow-key">Raw (hex)</span>
                      <span class="flow-val mono small">{tg.raw_data}</span>
                    </div>
                  {/if}
                  {#if tg.linked_entity_id}
                    <div class="flow-detail-row">
                      <span class="flow-key">HA Entity</span>
                      <span class="flow-val entity-link">{tg.linked_entity_id}</span>
                    </div>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- HA Events section -->
        {#if flowData.ha_events?.length > 0}
          <div class="flow-section">
            <div class="flow-section-title">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <rect x="1" y="4" width="14" height="9" rx="1.5"/><path d="M5 4V2.5M11 4V2.5"/>
              </svg>
              HA Events ({flowData.ha_events.length})
            </div>
            {#each flowData.ha_events as ev}
              <div class="flow-row ha">
                <div class="flow-row-head">
                  <span class="domain-badge">{ev.domain ?? ev.event_type.split('_')[0]}</span>
                  <span class="flow-time">{fmtDateTime(ev.timestamp)}</span>
                </div>
                <div class="flow-row-body">
                  {#if ev.name}
                    <div class="ha-name">{ev.name}</div>
                  {/if}
                  {#if ev.entity_id}
                    <div class="flow-detail-row">
                      <span class="flow-key">Entity</span>
                      <span class="flow-val entity-link">{ev.entity_id}</span>
                    </div>
                  {/if}
                  <div class="flow-detail-row">
                    <span class="flow-key">Type</span>
                    <span class="flow-val mono small">{ev.event_type}</span>
                  </div>
                  <div class="flow-detail-row">
                    <span class="flow-key">Confidence</span>
                    <span class="flow-val conf-{ev.confidence}">{ev.confidence}</span>
                  </div>
                </div>
              </div>
            {/each}
          </div>
        {/if}

        {#if !flowData.knx_telegrams?.length && !flowData.ha_events?.length}
          <div class="flow-empty">No activity found in the 8-second window.</div>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  /* ── Layout ─────────────────────────────────── */
  .knx-layout {
    display: flex;
    height: 100%;
    overflow: hidden;
    gap: 0;
    background: var(--color-bg);
  }

  .main-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-right: 1px solid var(--color-border);
  }

  .ga-sidebar {
    width: 240px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--color-surface);
  }

  /* ── Panel header ───────────────────────────── */
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
    color: var(--color-accent, #6366f1);
  }

  .live-badge {
    background: #22c55e22;
    color: #22c55e;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 9px;
    border-radius: 999px;
    animation: pulse-in 0.4s ease;
  }

  @keyframes pulse-in {
    from { opacity: 0; transform: scale(0.85); }
    to   { opacity: 1; transform: scale(1); }
  }

  .summary-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
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
  .chip-in .chip-value  { color: #22c55e; }
  .chip-out .chip-value { color: #6366f1; }
  .chip-ga .chip-value  { color: var(--color-accent, #6366f1); }

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

  .filter-select,
  .filter-input {
    height: 30px;
    padding: 0 10px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 12px;
    outline: none;
    transition: border-color 0.15s;
  }

  .filter-select:focus,
  .filter-input:focus {
    border-color: var(--color-accent, #6366f1);
  }

  .filter-select { min-width: 110px; }
  .filter-input  { min-width: 130px; }

  .filter-actions {
    display: flex;
    gap: 6px;
    align-items: flex-end;
    padding-bottom: 1px;
  }

  .btn-apply {
    height: 30px;
    padding: 0 14px;
    border-radius: 6px;
    background: var(--color-accent, #6366f1);
    color: #fff;
    font-size: 12px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .btn-apply:hover { opacity: 0.85; }

  .btn-clear {
    height: 30px;
    padding: 0 12px;
    border-radius: 6px;
    background: transparent;
    color: var(--color-text-muted);
    font-size: 12px;
    border: 1px solid var(--color-border);
    cursor: pointer;
    transition: color 0.15s;
  }

  .btn-clear:hover { color: var(--color-text); }

  /* ── Table ──────────────────────────────────── */
  .table-wrapper {
    flex: 1;
    overflow-y: auto;
    overflow-x: auto;
  }

  .tg-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
  }

  .tg-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--color-surface);
    padding: 8px 12px;
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-muted);
    border-bottom: 1px solid var(--color-border);
    white-space: nowrap;
  }

  .tg-row {
    cursor: pointer;
    transition: background 0.08s;
    border-bottom: 1px solid var(--color-border);
  }

  .tg-row:hover { background: var(--color-surface); }

  .tg-row td {
    padding: 7px 12px;
    vertical-align: middle;
    white-space: nowrap;
  }

  .tg-row.incoming { border-left: 3px solid #22c55e55; }
  .tg-row.outgoing { border-left: 3px solid #6366f155; }

  /* Direction badge */
  .dir-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
  }

  .dir-badge.incoming { background: #22c55e22; color: #22c55e; }
  .dir-badge.outgoing { background: #6366f122; color: #818cf8; }

  /* Type badge */
  .type-badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 5px;
    font-size: 10.5px;
    font-weight: 600;
  }

  .type-write    { background: #f59e0b22; color: #f59e0b; }
  .type-read     { background: #3b82f622; color: #60a5fa; }
  .type-resp     { background: #8b5cf622; color: #a78bfa; }

  /* GA chip */
  .ga-chip {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 600;
    font-family: ui-monospace, monospace;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    color: var(--color-text);
    cursor: pointer;
    transition: border-color 0.15s, background 0.1s;
  }

  .ga-chip:hover {
    border-color: var(--color-accent, #6366f1);
    background: var(--color-accent-muted, #6366f110);
  }

  .entity-link {
    font-size: 11.5px;
    color: var(--color-accent, #6366f1);
    font-family: ui-monospace, monospace;
  }

  .raw-bytes {
    font-family: ui-monospace, monospace;
    font-size: 11px;
    color: var(--color-text-muted);
  }

  .dim   { color: var(--color-text-muted); }
  .col-value { font-weight: 600; }

  /* ── Scroll sentinel ────────────────────────── */
  .scroll-sentinel {
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* ── Loading / empty ────────────────────────── */
  .loading-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 60px 24px;
    color: var(--color-text-muted);
    text-align: center;
  }

  .empty-state svg { width: 48px; height: 48px; opacity: 0.3; }
  .empty-state p { font-weight: 600; margin: 0; font-size: 14px; }
  .empty-state span { font-size: 13px; }

  .spinner {
    width: 22px;
    height: 22px;
    border: 2px solid var(--color-border);
    border-top-color: var(--color-accent, #6366f1);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  .spinner.small { width: 16px; height: 16px; }

  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── GA sidebar ─────────────────────────────── */
  .sidebar-header {
    padding: 14px 14px 10px;
    border-bottom: 1px solid var(--color-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .sidebar-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-text-muted);
    margin: 0;
  }

  .sidebar-count {
    font-size: 11px;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 999px;
    padding: 1px 8px;
    color: var(--color-text-muted);
  }

  .ga-list {
    flex: 1;
    overflow-y: auto;
    padding: 6px 8px;
  }

  .ga-row {
    display: block;
    width: 100%;
    text-align: left;
    padding: 8px 10px;
    border-radius: 7px;
    border: 1px solid transparent;
    background: transparent;
    cursor: pointer;
    margin-bottom: 3px;
    transition: background 0.12s, border-color 0.12s;
  }

  .ga-row:hover {
    background: var(--color-bg);
    border-color: var(--color-border);
  }

  .ga-row.selected {
    background: var(--color-accent-muted, #6366f110);
    border-color: var(--color-accent, #6366f1);
  }

  .ga-address {
    font-family: ui-monospace, monospace;
    font-size: 13px;
    font-weight: 700;
    color: var(--color-text);
  }

  .ga-name {
    font-size: 11px;
    color: var(--color-text-muted);
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .ga-meta {
    display: flex;
    gap: 6px;
    margin-top: 5px;
    flex-wrap: wrap;
    align-items: center;
  }

  .ga-stat {
    font-size: 10px;
    color: var(--color-text-muted);
    background: var(--color-bg);
    padding: 1px 6px;
    border-radius: 4px;
    border: 1px solid var(--color-border);
  }

  .ga-last-val {
    font-size: 11px;
    font-weight: 600;
    color: var(--color-text);
    margin-left: auto;
  }

  .sidebar-empty {
    padding: 20px 12px;
    font-size: 12px;
    color: var(--color-text-muted);
    text-align: center;
  }

  /* ── Flow panel overlay ─────────────────────── */
  .panel-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.35);
    z-index: 100;
  }

  .flow-panel {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    width: 440px;
    max-width: 95vw;
    background: var(--color-surface);
    border-left: 1px solid var(--color-border);
    box-shadow: -8px 0 32px rgba(0,0,0,0.15);
    z-index: 101;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: slide-in 0.22s ease;
  }

  @keyframes slide-in {
    from { transform: translateX(30px); opacity: 0; }
    to   { transform: translateX(0);    opacity: 1; }
  }

  .flow-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 18px;
    border-bottom: 1px solid var(--color-border);
    flex-shrink: 0;
  }

  .flow-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text);
  }

  .flow-title svg { width: 16px; height: 16px; color: var(--color-accent, #6366f1); }

  .close-btn {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    background: transparent;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-text-muted);
    transition: color 0.15s, background 0.12s;
  }

  .close-btn svg { width: 12px; height: 12px; }
  .close-btn:hover { color: var(--color-text); background: var(--color-bg); }

  .flow-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
  }

  .flow-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .flow-section-title {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--color-text-muted);
    margin-bottom: 10px;
  }

  .flow-section-title svg { width: 14px; height: 14px; }

  .flow-row {
    border-radius: 9px;
    border: 1px solid var(--color-border);
    overflow: hidden;
    margin-bottom: 8px;
  }

  .flow-row.knx.incoming { border-left: 4px solid #22c55e; }
  .flow-row.knx.outgoing { border-left: 4px solid #6366f1; }
  .flow-row.ha { border-left: 4px solid #f59e0b; }

  .flow-row-head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--color-bg);
    border-bottom: 1px solid var(--color-border);
  }

  .flow-time {
    font-size: 11px;
    color: var(--color-text-muted);
    margin-left: auto;
  }

  .flow-row-body {
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .flow-detail-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12.5px;
  }

  .flow-key {
    min-width: 70px;
    color: var(--color-text-muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .flow-val { color: var(--color-text); }
  .flow-val.mono  { font-family: ui-monospace, monospace; }
  .flow-val.small { font-size: 11px; }
  .flow-val.value-highlight { font-weight: 700; font-size: 14px; }
  .flow-val.ga-chip-sm {
    font-family: ui-monospace, monospace;
    font-weight: 700;
    font-size: 13px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    padding: 1px 7px;
    border-radius: 5px;
  }

  .ha-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: 2px;
  }

  .domain-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 600;
    background: #f59e0b22;
    color: #f59e0b;
  }

  .conf-propagated { color: #22c55e; }
  .conf-inferred   { color: #f59e0b; }

  .flow-empty {
    text-align: center;
    color: var(--color-text-muted);
    font-size: 13px;
    padding: 32px 0;
  }
</style>
