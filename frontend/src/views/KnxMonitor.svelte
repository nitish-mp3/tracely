<script>
  import { onMount, onDestroy } from 'svelte';
  import { getKnxTelegrams, getKnxGroupAddresses, getKnxFlow, subscribeKnxEvents, getKnxActivity, subscribeEvents } from '../lib/api.js';
  import { currentView, addToast } from '../stores/config.js';
  import { selectedEventId, monitorTarget } from '../stores/events.js';
  import EventNode from '../components/EventNode.svelte';

  // Navigation target (from timeline click)
  let highlightId = null;

  // Telegram detail panel
  let selectedTelegram = null;
  $: selectedTgIndex = selectedTelegram ? telegrams.findIndex(t => t.id === selectedTelegram.id) : -1;

  function openTelegram(tg) { selectedTelegram = tg; }
  function closeTelegramPanel() { selectedTelegram = null; }
  function prevTelegram() {
    if (selectedTgIndex > 0) selectedTelegram = telegrams[selectedTgIndex - 1];
  }
  function nextTelegram() {
    if (selectedTgIndex < telegrams.length - 1) selectedTelegram = telegrams[selectedTgIndex + 1];
  }

  function timeAgo(iso) {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 60000) return `${Math.round(diff / 1000)}s ago`;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }

  function hexGroup(raw) {
    if (!raw) return [];
    // split hex string into groups of 2 chars
    return raw.match(/.{1,2}/g) || [];
  }

  // ── Tab state ──────────────────────────────────────────
  let activeTab = 'telegrams'; // 'telegrams' | 'activity'

  // ── KNX Entity Activity state ──────────────────────────
  let activityEvents = [];
  let activityTotal = 0;
  let activityPage = 1;
  let activityLoading = false;
  let activityLoadingMore = false;
  let activityHasMore = true;
  let activitySentinel;
  let activityObserver;
  let unsubActivitySSE;

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

  // ── KNX Activity (entity state changes) ────────────────

  async function loadActivity(append = false) {
    if (!append) {
      activityLoading = true;
      activityPage = 1;
    } else {
      activityLoadingMore = true;
    }
    try {
      const params = { page: activityPage, limit: LIMIT };
      if (fromDate) params.from = new Date(fromDate).toISOString();
      if (toDate) params.to = new Date(toDate).toISOString();
      const res = await getKnxActivity(params);
      activityTotal = res.total;
      activityHasMore = (res.page * res.limit) < res.total;
      if (append) {
        activityEvents = [...activityEvents, ...res.items];
      } else {
        activityEvents = res.items;
      }
    } catch (err) {
      console.error('KNX activity load error', err);
    } finally {
      activityLoading = false;
      activityLoadingMore = false;
    }
  }

  async function loadMoreActivity() {
    if (activityLoadingMore || !activityHasMore) return;
    activityPage++;
    await loadActivity(true);
  }

  function handleActivityEventClick(event) {
    $selectedEventId = event.id;
    $currentView = 'trace';
  }

  function getKnxDetails(event) {
    try {
      const payload = JSON.parse(event.payload || '{}');
      const ns = payload.new_state || payload;
      const attrs = ns?.attributes || {};
      const stateVal = ns?.state;
      const details = [];

      // Combine value + unit into one readable chip
      const unit = attrs.unit_of_measurement;
      const dc = attrs.device_class;
      if (unit && stateVal !== undefined && stateVal !== 'unavailable' && stateVal !== 'unknown') {
        details.push({ key: dc || 'Value', val: `${stateVal} ${unit}`, type: 'info' });
      } else if (stateVal !== undefined && stateVal !== null && stateVal !== 'unavailable' && stateVal !== 'unknown') {
        if (dc) details.push({ key: dc, val: String(stateVal), type: 'info' });
        else details.push({ key: 'Value', val: String(stateVal), type: 'info' });
      }

      // KNX-specific: group address
      const ga = attrs.knx_group_address_send || attrs.group_address || attrs.knx_group_address;
      if (ga) details.push({ key: 'GA', val: String(ga), type: 'info' });

      return details;
    } catch { return []; }
  }

  function setupActivityObserver() {
    if (activityObserver) activityObserver.disconnect();
    if (!activitySentinel) return;
    activityObserver = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMoreActivity(); },
      { rootMargin: '200px' },
    );
    activityObserver.observe(activitySentinel);
  }

  $: if (activitySentinel) setupActivityObserver();

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
    // Check if navigated here from timeline with a target event
    const target = $monitorTarget;
    if (target && target.view === 'knx') {
      if (target.entityId) filterEntity = target.entityId;
      highlightId = target.eventId || null;
      activeTab = 'activity';
      monitorTarget.set(null);
    }
    await Promise.all([loadTelegrams(), loadGAs(), loadActivity()]);
    // After load, scroll to highlighted activity event
    if (highlightId) {
      setTimeout(() => {
        const el = document.querySelector(`[data-event-id="${highlightId}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 300);
    }
    unsubscribeKnx = subscribeKnxEvents(handleLiveTelegram);
    // Also listen to main SSE for KNX entity state changes
    unsubActivitySSE = subscribeEvents(
      (event) => {
        const integ = (event.integration || '').toLowerCase();
        const eid = (event.entity_id || '').toLowerCase();
        if (integ === 'knx' || eid.includes('knx')) {
          activityEvents = [event, ...activityEvents.slice(0, 499)];
          activityTotal++;
        }
      },
      () => {},
    );
    return setupInfiniteScroll();
  });

  onDestroy(() => {
    if (unsubscribeKnx) unsubscribeKnx();
    if (unsubActivitySSE) unsubActivitySSE();
    if (activityObserver) activityObserver.disconnect();
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

      <!-- Tab switcher -->
      <div class="tab-switcher">
        <button class="tab-btn" class:active={activeTab === 'telegrams'} on:click={() => activeTab = 'telegrams'}>
          Bus Telegrams
          <span class="tab-count">{total}</span>
        </button>
        <button class="tab-btn" class:active={activeTab === 'activity'} on:click={() => activeTab = 'activity'}>
          Entity Activity
          <span class="tab-count">{activityTotal}</span>
        </button>
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
        <a class="chip chip-diag" href="/api/knx/diagnostics" target="_blank" rel="noopener" title="View KNX ingestion diagnostics in a new tab">
          <span class="chip-label">Diagnostics</span>
          <span class="chip-value">↗</span>
        </a>
      </div>
    </div>

    <!-- Filter bar -->
    {#if activeTab === 'telegrams'}
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
          <span>Telegrams appear after the addon backend is restarted with the latest code. Check the <a class="diag-link" href="/api/knx/diagnostics" target="_blank" rel="noopener">Diagnostics</a> chip above to verify events are being received.</span>
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
                class:tg-selected={selectedTelegram?.id === tg.id}
                on:click={() => openTelegram(tg)}
                aria-label="View telegram details for {tg.group_address}"
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
                    <button class="entity-link" title="Filter by {tg.linked_entity_id}"
                      on:click|stopPropagation={() => { filterEntity = tg.linked_entity_id; applyFilters(); addToast(`Filtered by entity`, 'info', 2000); }}>
                      {tg.linked_entity_id.split('.').pop()}
                    </button>
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
    {/if}

    <!-- ── Activity tab: entity state changes ─────────── -->
    {#if activeTab === 'activity'}
    <div class="activity-panel">
      {#if activityLoading}
        <div class="loading-state">
          <div class="spinner" />
          <span>Loading KNX entity activity…</span>
        </div>
      {:else if activityEvents.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="10" cy="24" r="4"/><circle cx="24" cy="10" r="4"/><circle cx="38" cy="24" r="4"/><circle cx="24" cy="38" r="4"/>
            <path d="M14 24h20M24 14v20"/>
          </svg>
          <p>No KNX entity activity yet.</p>
          <span>State changes from KNX entities (sensors, switches, lights, etc.) will appear here.</span>
        </div>
      {:else}
        <ul class="activity-list">
          {#each activityEvents as event (event.id)}
            <li class="activity-item" class:highlighted={event.id === highlightId} data-event-id={event.id}>
              <EventNode
                {event}
                on:click={() => handleActivityEventClick(event)}
                on:viewin={(e) => { $currentView = e.detail; }}
                on:tagclick={(e) => { filterEntity = e.detail; applyFilters(); addToast(`Filtered by entity: ${e.detail}`, 'info', 2500); }}
                on:integrationclick={(e) => addToast(`Integration filter: ${e.detail}`, 'info', 2000)}
              />
              {#if getKnxDetails(event).length > 0}
                <div class="proto-details">
                  {#each getKnxDetails(event) as d}
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
        {#if activityHasMore}
          <div bind:this={activitySentinel} class="scroll-sentinel">
            {#if activityLoadingMore}
              <div class="spinner small" />
            {/if}
          </div>
        {/if}
      {/if}
    </div>
    {/if}
  </div>

  <!-- ── Right: GA explorer (only shown when there's data) ──── -->
  {#if groupAddresses.length > 0}
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
    </div>
  </div>
  {/if}

</div>

<!-- ── Telegram detail modal ─────────────────────── -->
{#if selectedTelegram}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="tg-overlay" on:click={closeTelegramPanel} role="button" tabindex="0" aria-label="Close" />
  <div class="tg-modal" role="dialog" aria-label="KNX Telegram detail">

    <!-- Modal header -->
    <div class="tg-modal-header">
      <div class="tg-modal-title-group">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="3" cy="8" r="1.5"/><circle cx="13" cy="8" r="1.5"/><path d="M4.5 8h7"/>
        </svg>
        <span class="tg-modal-title">KNX Telegram</span>
      </div>
      <div class="tg-modal-header-right">
        <span class="tg-modal-time">{fmtDateTime(selectedTelegram.timestamp)} ({timeAgo(selectedTelegram.timestamp)})</span>
        {#if selectedTelegram.direction === 'Outgoing'}
          <span class="tg-dir-pill outgoing">OUTGOING</span>
        {:else}
          <span class="tg-dir-pill incoming">INCOMING</span>
        {/if}
        <button class="close-btn" on:click={closeTelegramPanel} aria-label="Close">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l8 8M10 2l-8 8"/></svg>
        </button>
      </div>
    </div>

    <!-- Source → Destination row -->
    <div class="tg-addr-row">
      <div class="tg-addr-block">
        <div class="tg-addr-label">Source</div>
        <div class="tg-addr-value">{selectedTelegram.source_address ?? '—'}</div>
        {#if selectedTelegram.direction === 'Outgoing'}
          <div class="tg-addr-sub">Home Assistant</div>
        {/if}
      </div>
      <div class="tg-addr-arrow">
        <svg viewBox="0 0 24 8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M0 4h20M16 1l4 3-4 3"/>
        </svg>
      </div>
      <div class="tg-addr-block">
        <div class="tg-addr-label">Destination</div>
        <div class="tg-addr-value">{selectedTelegram.group_address ?? '—'}</div>
        {#if selectedTelegram.linked_entity_id}
          <div class="tg-addr-sub">{selectedTelegram.linked_entity_id.split('.').pop()}</div>
        {/if}
      </div>
    </div>

    <!-- Value highlight -->
    <div class="tg-value-block">
      <div class="tg-value-label">Value</div>
      <div class="tg-value-display">{decodeValue(selectedTelegram.decoded_value)}</div>
    </div>

    <!-- Details grid -->
    <div class="tg-details-grid">
      <div class="tg-detail-cell">
        <div class="tg-detail-label">Type</div>
        <div class="tg-detail-value bold">{selectedTelegram.telegram_type ?? '—'}</div>
      </div>
      <div class="tg-detail-cell">
        <div class="tg-detail-label">DPT</div>
        <div class="tg-detail-value bold">{selectedTelegram.dpt_type ?? '—'}</div>
      </div>
      {#if selectedTelegram.linked_entity_id}
        <div class="tg-detail-cell" style="grid-column: 1/-1">
          <div class="tg-detail-label">HA Entity</div>
          <div class="tg-detail-value mono">{selectedTelegram.linked_entity_id}</div>
        </div>
      {/if}
    </div>

    <!-- Payload bytes -->
    <div class="tg-payload-block">
      <div class="tg-detail-label">Payload</div>
      {#if selectedTelegram.raw_data}
        <div class="tg-hex-row">
          {#each hexGroup(selectedTelegram.raw_data) as byte}
            <span class="tg-hex-byte">{byte}</span>
          {/each}
        </div>
      {:else}
        <div class="tg-payload-empty">no payload</div>
      {/if}
    </div>

    <!-- Actions: GA flow + navigation -->
    <div class="tg-modal-footer">
      <button class="tg-flow-btn" on:click={() => { closeTelegramPanel(); openGA(selectedTelegram.group_address, selectedTelegram.timestamp); }}
        title="View all telegrams for {selectedTelegram.group_address} in ±8s window">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M3 8h10M9 4l4 4-4 4"/>
        </svg>
        View GA Flow ({selectedTelegram.group_address})
      </button>
      <div class="tg-nav">
        <button class="tg-nav-btn" disabled={selectedTgIndex <= 0} on:click={prevTelegram} aria-label="Previous telegram">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M10 4l-5 4 5 4"/></svg>
          Previous
        </button>
        <span class="tg-nav-pos">{selectedTgIndex + 1} / {telegrams.length}</span>
        <button class="tg-nav-btn" disabled={selectedTgIndex >= telegrams.length - 1} on:click={nextTelegram} aria-label="Next telegram">
          Next
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M6 4l5 4-5 4"/></svg>
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ── GA flow panel (slide-in, from GA sidebar) ────── -->
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
        {#if flowData.knx_telegrams?.length > 0}
          <div class="flow-section">
            <div class="flow-section-title">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <circle cx="3" cy="8" r="1.5"/><circle cx="13" cy="8" r="1.5"/><path d="M4.5 8h7"/>
              </svg>
              KNX Telegrams ({flowData.knx_telegrams.length})
            </div>
            {#each flowData.knx_telegrams as tg}
              <div class="flow-row knx" class:incoming={tg.direction === 'Incoming'} class:outgoing={tg.direction === 'Outgoing'}>
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
                      <span class="flow-key">Raw</span>
                      <span class="flow-val mono small">{tg.raw_data}</span>
                    </div>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
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
                  {#if ev.name}<div class="ha-name">{ev.name}</div>{/if}
                  {#if ev.entity_id}
                    <div class="flow-detail-row">
                      <span class="flow-key">Entity</span>
                      <span class="flow-val entity-link">{ev.entity_id}</span>
                    </div>
                  {/if}
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
    flex: 1;
    min-width: 0;
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
  .chip-diag { text-decoration: none; cursor: pointer; }
  .chip-diag:hover { background: var(--color-surface-hover); }
  .chip-diag .chip-value { color: var(--color-text-muted); }
  a.diag-link { color: var(--color-accent, #6366f1); text-underline-offset: 2px; }

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
    background: none;
    border: none;
    padding: 2px 4px;
    border-radius: 4px;
    cursor: pointer;
    text-decoration: underline dotted;
    transition: background 0.15s;
  }
  .entity-link:hover { background: var(--color-accent-dim, rgba(99,102,241,0.12)); }

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

  /* ── Tab switcher ───────────────────────────── */
  .tab-switcher {
    display: flex;
    gap: 2px;
    padding: 3px;
    background: var(--color-bg);
    border-radius: 8px;
    border: 1px solid var(--color-border);
  }
  .tab-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 14px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-muted);
    transition: all 0.15s;
    white-space: nowrap;
  }
  .tab-btn:hover { color: var(--color-text-secondary); }
  .tab-btn.active {
    color: var(--color-text);
    background: var(--color-surface);
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
  }
  .tab-count {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 999px;
    background: var(--color-surface-hover);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
  }
  .tab-btn.active .tab-count {
    background: rgba(99,102,241,.15);
    color: #818cf8;
  }

  /* ── Activity panel ─────────────────────────── */
  .activity-panel {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
  }
  .activity-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .activity-item {
    animation: fadeIn 0.2s ease both;
  }
  .activity-item.highlighted {
    border-left: 3px solid var(--color-primary, #6366f1);
    background: color-mix(in srgb, var(--color-primary, #6366f1) 8%, transparent);
    border-radius: 4px;
    outline: 1px solid color-mix(in srgb, var(--color-primary, #6366f1) 30%, transparent);
  }

  /* ── Protocol Detail Chips ────────────────── */
  .proto-details {
    display: flex; flex-wrap: wrap; gap: 4px;
    padding: 3px 12px 8px 40px;
  }
  .proto-chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 500;
    background: var(--color-surface-hover);
    border: 1px solid var(--color-border);
  }
  .proto-info { border-color: rgba(99,102,241,.3); background: rgba(99,102,241,.06); }
  .pc-k { color: var(--color-text-muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
  .pc-v { color: var(--color-text); font-weight: 600; }
  .proto-ok .pc-v { color: var(--color-success); }
  .proto-bad .pc-v { color: var(--color-error, #ef4444); }
  .proto-warn .pc-v { color: #f59e0b; }

  /* ── Selected row highlight ─────────────────── */
  .tg-row.tg-selected {
    background: color-mix(in srgb, var(--color-primary, #6366f1) 8%, transparent);
    outline: 1px solid rgba(99,102,241,.25);
  }

  /* ── Telegram detail modal ───────────────────── */
  .tg-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(2px);
    z-index: 200;
  }

  .tg-modal {
    position: fixed;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: min(540px, 95vw);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 14px;
    box-shadow: 0 24px 80px rgba(0,0,0,0.35);
    z-index: 201;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: modal-in 0.18s ease;
  }

  @keyframes modal-in {
    from { opacity: 0; transform: translate(-50%, calc(-50% + 12px)); }
    to   { opacity: 1; transform: translate(-50%, -50%); }
  }

  .tg-modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 18px 20px 14px;
    border-bottom: 1px solid var(--color-border);
    gap: 12px;
  }

  .tg-modal-title-group {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .tg-modal-title-group svg { width: 18px; height: 18px; color: var(--color-primary, #6366f1); flex-shrink: 0; }
  .tg-modal-title { font-size: 16px; font-weight: 700; color: var(--color-text); }

  .tg-modal-header-right {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
  }

  .tg-modal-time {
    font-size: 12px;
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
  }

  .tg-dir-pill {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 3px 10px;
    border-radius: 999px;
  }
  .tg-dir-pill.outgoing { background: rgba(99,102,241,.15); color: #818cf8; }
  .tg-dir-pill.incoming { background: rgba(34,197,94,.15);  color: #4ade80; }

  /* Source → Destination */
  .tg-addr-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 20px 12px;
    border-bottom: 1px solid var(--color-border);
  }

  .tg-addr-block {
    flex: 1;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 10px;
    padding: 12px 16px;
    min-width: 0;
  }

  .tg-addr-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--color-text-muted);
    margin-bottom: 5px;
  }

  .tg-addr-value {
    font-family: ui-monospace, monospace;
    font-size: 20px;
    font-weight: 700;
    color: var(--color-text);
    letter-spacing: -0.01em;
  }

  .tg-addr-sub {
    font-size: 11px;
    color: var(--color-text-muted);
    margin-top: 3px;
  }

  .tg-addr-arrow {
    flex-shrink: 0;
    color: var(--color-text-muted);
    padding: 4px;
  }
  .tg-addr-arrow svg { width: 28px; height: 10px; display: block; }

  /* Value highlight */
  .tg-value-block {
    padding: 16px 20px 14px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-bg);
  }
  .tg-value-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--color-text-muted);
    margin-bottom: 6px;
  }
  .tg-value-display {
    font-size: 26px;
    font-weight: 800;
    color: var(--color-primary, #6366f1);
    letter-spacing: -0.02em;
    font-family: ui-monospace, monospace;
  }

  /* Details grid */
  .tg-details-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: var(--color-border);
    border-top: 1px solid var(--color-border);
    border-bottom: 1px solid var(--color-border);
  }
  .tg-detail-cell {
    background: var(--color-surface);
    padding: 12px 16px;
  }
  .tg-detail-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-text-muted);
    margin-bottom: 4px;
  }
  .tg-detail-value {
    font-size: 13px;
    color: var(--color-text);
  }
  .tg-detail-value.bold { font-weight: 700; }
  .tg-detail-value.mono { font-family: ui-monospace, monospace; font-size: 12px; }

  /* Payload bytes */
  .tg-payload-block {
    padding: 14px 20px;
    border-bottom: 1px solid var(--color-border);
  }
  .tg-hex-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 6px;
  }
  .tg-hex-byte {
    font-family: ui-monospace, monospace;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 5px;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    color: var(--color-text);
    letter-spacing: 0.04em;
  }
  .tg-payload-empty {
    font-size: 12px;
    color: var(--color-text-muted);
    font-style: italic;
    margin-top: 4px;
  }

  /* Footer: GA flow button + nav */
  .tg-modal-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    gap: 12px;
  }

  .tg-flow-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 7px;
    border: 1px solid var(--color-border);
    background: var(--color-surface-hover);
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-secondary);
    cursor: pointer;
    transition: all 0.12s;
  }
  .tg-flow-btn svg { width: 14px; height: 14px; flex-shrink: 0; }
  .tg-flow-btn:hover {
    border-color: var(--color-primary, #6366f1);
    color: var(--color-primary, #6366f1);
    background: rgba(99,102,241,.08);
  }

  .tg-nav {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .tg-nav-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 5px 12px;
    border-radius: 7px;
    border: 1px solid var(--color-border);
    background: transparent;
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-muted);
    cursor: pointer;
    transition: all 0.12s;
  }
  .tg-nav-btn svg { width: 14px; height: 14px; }
  .tg-nav-btn:not(:disabled):hover { color: var(--color-text); border-color: var(--color-border-hover); }
  .tg-nav-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .tg-nav-pos {
    font-size: 11px;
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
    min-width: 50px;
    text-align: center;
  }

  /* ── Mobile responsive ──────────────────────── */
  @media (max-width: 768px) {
    /* Stack layout: hide sidebar by default on mobile */
    .knx-layout {
      flex-direction: column;
    }
    .ga-sidebar {
      width: 100%;
      max-height: 200px;
      border-right: none;
      border-top: 1px solid var(--color-border);
      flex-shrink: 0;
    }
    .ga-list {
      display: flex;
      flex-direction: row;
      flex-wrap: nowrap;
      overflow-x: auto;
      padding: 6px;
      gap: 6px;
    }
    .ga-row {
      min-width: 120px;
      flex-shrink: 0;
      margin-bottom: 0;
    }
    /* Filter bar wraps */
    .filter-row {
      flex-wrap: wrap;
      gap: 8px;
    }
    .filter-group {
      flex: 1 1 140px;
    }
    /* Summary chips scroll */
    .summary-chips {
      overflow-x: auto;
      flex-wrap: nowrap;
      padding-bottom: 2px;
    }
    .chip {
      flex-shrink: 0;
    }
    /* Panel header wraps */
    .panel-header {
      flex-wrap: wrap;
    }
    /* Cols hidden on mobile: entity + raw */
    .tg-table .col-entity,
    .tg-table thead th:nth-child(7),
    .tg-table .col-raw,
    .tg-table thead th:nth-child(8) {
      display: none;
    }
    /* Telegram modal: full-screen on mobile */
    .tg-modal {
      width: 100%;
      max-width: 100%;
      height: 100%;
      top: 0;
      left: 0;
      transform: none;
      border-radius: 0;
    }
    @keyframes modal-in {
      from { opacity: 0; transform: translateY(20px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .tg-modal-header-right {
      flex-wrap: wrap;
      gap: 6px;
    }
    .tg-modal-time { display: none; }
    .tg-addr-value { font-size: 16px; }
    .tg-value-display { font-size: 22px; }
    .tg-modal-footer {
      flex-direction: column;
      align-items: stretch;
    }
    .tg-flow-btn { justify-content: center; }
    .tg-nav { justify-content: center; }
  }

  @media (max-width: 480px) {
    .panel-header {
      padding: 10px 12px 8px;
    }
    .tab-switcher { order: -1; width: 100%; }
    .tab-btn { flex: 1; justify-content: center; }
    .filter-bar { padding: 8px 12px; }
    .table-wrapper { font-size: 11.5px; }
    .tg-row td { padding: 6px 8px; }
    .tg-table thead th { padding: 6px 8px; }
    /* Also hide source col on very small phones */
    .tg-table .col-source,
    .tg-table thead th:nth-child(6) {
      display: none;
    }
  }
</style>
