<script>
  import { onMount, onDestroy } from 'svelte';
  import { getProtocolActivity, subscribeEvents } from '../lib/api.js';
  import { currentView, addToast } from '../stores/config.js';
  import { selectedEventId, monitorTarget } from '../stores/events.js';
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

  // Navigation target (from timeline click)
  let highlightId = null;

  // ── Event detail modal ──────────────────────────────
  let selectedZigbeeEvent = null;
  $: selectedEventIndex = selectedZigbeeEvent
    ? events.findIndex(e => e.id === selectedZigbeeEvent.id)
    : -1;

  function openEventDetail(ev) { selectedZigbeeEvent = ev; showRawPayload = false; }
  function closeEventDetail() { selectedZigbeeEvent = null; }
  function prevEvent() {
    if (selectedEventIndex > 0) selectedZigbeeEvent = events[selectedEventIndex - 1];
  }
  function nextEvent() {
    if (selectedEventIndex < events.length - 1) selectedZigbeeEvent = events[selectedEventIndex + 1];
  }

  function timeAgo(iso) {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 60000) return `${Math.round(diff / 1000)}s ago`;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString([], {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    } catch { return iso; }
  }

  function formatAttrVal(key, val) {
    if (typeof val === 'boolean') return val ? 'Yes' : 'No';
    if (key === 'battery' || key === 'battery_level') return `${val}%`;
    if (key === 'lqi' || key === 'linkquality') return `${Number(val)}/255`;
    if (key === 'temperature') return `${val} °C`;
    if (key === 'humidity') return `${val} %`;
    if (key === 'pressure') return `${val} hPa`;
    if (key === 'illuminance' || key === 'illuminance_lux') return `${val} lx`;
    if (typeof val === 'object' && val !== null) return JSON.stringify(val);
    return String(val);
  }

  function getEventFullDetails(ev) {
    try {
      const payload = JSON.parse(ev.payload || '{}');

      // ── call_service events ──────────────────────────────────────
      if (ev.event_type === 'call_service' || payload.domain) {
        const domain = payload.domain || ev.domain || '';
        const service = payload.service || ev.service || '';
        const serviceData = payload.service_data || {};
        const details = [];
        // Flatten service_data into key-value pairs
        for (const [k, v] of Object.entries(serviceData)) {
          if (v === null || v === undefined) continue;
          const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
          details.push({ key: k, val });
        }
        // Target entity
        const targets = payload.target || serviceData.entity_id;
        const targetStr = Array.isArray(targets) ? targets.join(', ') : String(targets || '');
        return {
          type: 'call_service',
          serviceCall: `${domain}.${service}`,
          targetEntities: targetStr,
          newVal: null, oldVal: null, unit: '', deviceClass: '',
          friendlyName: ev.name || `${domain}.${service}`,
          details,
        };
      }

      // ── automation_triggered ────────────────────────────────────
      if (ev.event_type === 'automation_triggered') {
        const name = payload.name || ev.name || ev.entity_id || 'automation';
        const reason = payload.context?.parent_id ? `Triggered by context` : (payload.source || '');
        return {
          type: 'automation',
          serviceCall: null,
          newVal: null, oldVal: null, unit: '', deviceClass: '',
          friendlyName: name,
          details: reason ? [{ key: 'Trigger', val: reason }] : [],
        };
      }

      // ── state_changed events ─────────────────────────────────────
      const ns = payload.new_state || payload;
      const os = payload.old_state || null;
      const attrs = ns?.attributes || {};
      const SKIP = new Set([
        'friendly_name', 'icon', 'supported_features', 'supported_color_modes',
        'entity_picture', 'attribution', 'restored', 'assumed_state',
        'color_mode', 'hs_color', 'rgb_color', 'xy_color', 'min_mireds',
        'max_mireds', 'effect_list',
      ]);
      const PRIORITY = [
        'battery', 'battery_level', 'lqi', 'linkquality',
        'temperature', 'humidity', 'pressure', 'co2', 'voc', 'pm25', 'pm10',
        'illuminance', 'illuminance_lux', 'occupancy', 'contact', 'action',
        'brightness', 'color_temp', 'device_class', 'unit_of_measurement',
        'current', 'voltage', 'power', 'energy', 'rssi',
      ];
      const shown = new Set();
      const details = [];
      for (const key of PRIORITY) {
        if (attrs[key] !== undefined && !shown.has(key)) {
          shown.add(key);
          details.push({ key, val: formatAttrVal(key, attrs[key]) });
        }
      }
      for (const [key, val] of Object.entries(attrs)) {
        if (!shown.has(key) && !SKIP.has(key) && val !== null && val !== undefined) {
          shown.add(key);
          details.push({ key, val: formatAttrVal(key, val) });
        }
      }
      return {
        type: 'state_changed',
        serviceCall: null,
        newVal: ns?.state ?? null,
        oldVal: os?.state ?? null,
        unit: attrs.unit_of_measurement || '',
        deviceClass: attrs.device_class || '',
        friendlyName: attrs.friendly_name || ev.name || ev.entity_id || '',
        details,
      };
    } catch {
      return {
        type: 'unknown', serviceCall: null,
        newVal: null, oldVal: null, unit: '', deviceClass: '',
        friendlyName: ev.name || ev.entity_id || '',
        details: [],
      };
    }
  }

  // Raw payload state for the detail modal
  let showRawPayload = false;
  function fmtPayloadJson(ev) {
    try { return JSON.stringify(JSON.parse(ev.payload || '{}'), null, 2); }
    catch { return ev.payload || '{}'; }
  }

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
    if (!event) return;
    $selectedEventId = event.id;
    $currentView = 'trace';
    addToast('Opening trace view…', 'info', 2000);
  }

  function getZigbeeDetails(event) {
    try {
      const payload = JSON.parse(event.payload || '{}');
      const ns = payload.new_state || payload;
      const attrs = ns?.attributes || {};
      const stateVal = ns?.state;
      const details = [];

      // Protocol quality (ZHA uses lqi, Z2M uses linkquality)
      const lqi = attrs.lqi ?? attrs.linkquality;
      if (lqi !== undefined) {
        const n = Number(lqi);
        details.push({ key: 'LQI', val: `${n}/255`, type: n > 150 ? 'ok' : n > 80 ? 'warn' : 'bad' });
      }
      const bat = attrs.battery ?? attrs.battery_level;
      if (bat !== undefined) {
        const n = Number(bat);
        details.push({ key: 'Battery', val: `${n}%`, type: n > 30 ? 'ok' : 'bad' });
      }

      // For HA sensors: value is in state, unit + device_class are in attributes
      const unit = attrs.unit_of_measurement;
      const dc = attrs.device_class;
      if (unit && stateVal !== undefined && stateVal !== 'unavailable' && stateVal !== 'unknown') {
        details.push({ key: dc || 'Value', val: `${stateVal} ${unit}`, type: 'info' });
      } else if (dc && !unit && stateVal !== undefined && stateVal !== 'unavailable' && stateVal !== 'unknown') {
        details.push({ key: dc, val: String(stateVal), type: 'info' });
      }

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
    // Check if navigated here from timeline with a target event
    const target = $monitorTarget;
    if (target && target.view === 'zigbee') {
      if (target.entityId) filterEntity = target.entityId;
      highlightId = target.eventId || null;
      monitorTarget.set(null);
    }
    await loadEvents();
    // After load, scroll to highlighted event
    if (highlightId) {
      setTimeout(() => {
        const el = document.querySelector(`[data-event-id="${highlightId}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 300);
    }
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
            <li
              class="event-item"
              class:highlighted={event.id === highlightId}
              data-event-id={event.id}
              on:click={() => openEventDetail(event)}
              on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && openEventDetail(event)}
              role="button"
              tabindex="0"
              aria-label="View details for {event.entity_id}"
            >
              <EventNode
                {event}
                on:viewin={(e) => { $currentView = e.detail; }}
                on:tagclick={(e) => { filterEntity = e.detail; applyFilters(); addToast(`Filtered by entity: ${e.detail}`, 'info', 2500); }}
                on:integrationclick={(e) => { const p = PROTOCOLS.find(x => x.value === e.detail); if (p) { protocol = e.detail; applyFilters(); addToast(`Switched to ${p.label}`, 'info', 2000); } else { addToast(`Integration: ${e.detail}`, 'info', 2000); } }}
                on:domainclick={(e) => { addToast(`Domain: ${e.detail}`, 'info', 2000); }}
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

<!-- ── Zigbee Event Detail Modal ─────────────── -->
{#if selectedZigbeeEvent}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="zb-overlay" on:click={closeEventDetail} role="button" tabindex="0" aria-label="Close" />
  <div class="zb-modal" role="dialog" aria-label="Zigbee event detail">

    <!-- Header -->
    <div class="zb-modal-header">
      <div class="zb-modal-title-group">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M2 4l6-2 6 2M2 8l6 2 6-2M2 12l6 2 6-2"/>
        </svg>
        <div>
          <div class="zb-modal-title">{getEventFullDetails(selectedZigbeeEvent).friendlyName}</div>
          <div class="zb-modal-entity">{selectedZigbeeEvent.entity_id}</div>
        </div>
      </div>
      <div class="zb-modal-header-right">
        <div class="zb-modal-meta">
          <span class="zb-modal-time">{fmtDateTime(selectedZigbeeEvent.timestamp)}</span>
          <span class="zb-modal-ago">{timeAgo(selectedZigbeeEvent.timestamp)}</span>
        </div>
        {#if selectedZigbeeEvent.integration}
          <span class="zb-integ-pill">{selectedZigbeeEvent.integration}</span>
        {/if}
        <button class="zb-close-btn" on:click={closeEventDetail} aria-label="Close">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l8 8M10 2l-8 8"/></svg>
        </button>
      </div>
    </div>

    <!-- Event type badge -->
    {#if selectedZigbeeEvent.event_type}
      <div class="zb-event-type-row">
        <span class="zb-event-type-badge">{selectedZigbeeEvent.event_type.replace(/_/g, ' ')}</span>
        {#if getEventFullDetails(selectedZigbeeEvent).serviceCall}
          <span class="zb-service-call">{getEventFullDetails(selectedZigbeeEvent).serviceCall}</span>
        {/if}
      </div>
    {/if}

    <!-- call_service: target entities -->
    {#if getEventFullDetails(selectedZigbeeEvent).type === 'call_service' && getEventFullDetails(selectedZigbeeEvent).targetEntities}
      <div class="zb-state-row">
        <div class="zb-state-block main">
          <div class="zb-state-label">Target Entity</div>
          <div class="zb-state-val current">{getEventFullDetails(selectedZigbeeEvent).targetEntities}</div>
        </div>
      </div>
    {/if}

    <!-- State change row -->
    {#if getEventFullDetails(selectedZigbeeEvent).newVal !== null}
      {@const dets = getEventFullDetails(selectedZigbeeEvent)}
      <div class="zb-state-row">
        {#if dets.oldVal !== null && dets.oldVal !== dets.newVal}
          <div class="zb-state-block">
            <div class="zb-state-label">Previous</div>
            <div class="zb-state-val old">{dets.oldVal}{dets.unit ? ' ' + dets.unit : ''}</div>
          </div>
          <div class="zb-state-arrow">
            <svg viewBox="0 0 24 8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M0 4h20M16 1l4 3-4 3"/>
            </svg>
          </div>
        {/if}
        <div class="zb-state-block main">
          <div class="zb-state-label">Current{dets.deviceClass ? ' · ' + dets.deviceClass : ''}</div>
          <div class="zb-state-val current">{dets.newVal}{dets.unit ? ' ' + dets.unit : ''}</div>
        </div>
      </div>
    {/if}

    <!-- Attributes grid -->
    {#if getEventFullDetails(selectedZigbeeEvent).details.length > 0}
      <div class="zb-attrs-block">
        <div class="zb-section-label">Attributes</div>
        <div class="zb-attrs-grid">
          {#each getEventFullDetails(selectedZigbeeEvent).details as d}
            <div class="zb-attr-cell">
              <div class="zb-attr-key">{d.key.replace(/_/g, ' ')}</div>
              <div class="zb-attr-val">{d.val}</div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Footer: trace + navigation -->
    <div class="zb-modal-footer">
      <!-- Raw payload toggle -->
      <button class="zb-raw-toggle" on:click={() => showRawPayload = !showRawPayload}>
        {showRawPayload ? 'Hide' : 'Show'} Raw Payload
      </button>
    </div>

    {#if showRawPayload}
      <div class="zb-raw-block">
        <pre class="zb-raw-pre">{fmtPayloadJson(selectedZigbeeEvent)}</pre>
      </div>
    {/if}

    <div class="zb-modal-footer zb-modal-footer-nav">
      <button class="zb-trace-btn" on:click={() => { const ev = selectedZigbeeEvent; closeEventDetail(); handleEventClick(ev); }}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M3 8h10M9 4l4 4-4 4"/>
        </svg>
        View Trace
      </button>
      <div class="zb-nav">
        <button class="zb-nav-btn" disabled={selectedEventIndex <= 0} on:click={prevEvent} aria-label="Previous">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M10 4l-5 4 5 4"/></svg>
          Prev
        </button>
        <span class="zb-nav-pos">{selectedEventIndex + 1} / {events.length}</span>
        <button class="zb-nav-btn" disabled={selectedEventIndex >= events.length - 1} on:click={nextEvent} aria-label="Next">
          Next
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M6 4l5 4-5 4"/></svg>
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .zigbee-layout {
    flex: 1;
    min-width: 0;
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
    cursor: pointer;
    border-radius: 6px;
    transition: background 0.08s;
  }
  .event-item:hover {
    background: var(--color-surface-hover);
  }
  .event-item.highlighted {
    border-left: 3px solid var(--color-primary, #6366f1);
    background: color-mix(in srgb, var(--color-primary, #6366f1) 8%, transparent);
    border-radius: 4px;
    outline: 1px solid color-mix(in srgb, var(--color-primary, #6366f1) 30%, transparent);
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

  /* ── Zigbee detail modal ─────────────────────── */
  .zb-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(2px);
    z-index: 200;
  }

  .zb-modal {
    position: fixed;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: min(520px, 95vw);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 14px;
    box-shadow: 0 24px 80px rgba(0,0,0,0.35);
    z-index: 201;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: zb-modal-in 0.18s ease;
  }

  @keyframes zb-modal-in {
    from { opacity: 0; transform: translate(-50%, calc(-50% + 12px)); }
    to   { opacity: 1; transform: translate(-50%, -50%); }
  }

  .zb-modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 16px 18px 14px;
    border-bottom: 1px solid var(--color-border);
    gap: 12px;
  }

  .zb-modal-title-group {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    min-width: 0;
  }
  .zb-modal-title-group svg {
    width: 18px; height: 18px;
    color: #22c55e;
    flex-shrink: 0;
    margin-top: 3px;
  }

  .zb-modal-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--color-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .zb-modal-entity {
    font-size: 11px;
    color: var(--color-text-muted);
    font-family: ui-monospace, monospace;
    margin-top: 2px;
    word-break: break-all;
  }

  .zb-modal-header-right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .zb-modal-meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 1px;
  }
  .zb-modal-time {
    font-size: 11px;
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .zb-modal-ago {
    font-size: 10px;
    color: var(--color-text-muted);
    opacity: 0.7;
  }

  .zb-integ-pill {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 3px 9px;
    border-radius: 999px;
    background: rgba(34,197,94,.13);
    color: #4ade80;
    white-space: nowrap;
  }

  .zb-close-btn {
    width: 28px; height: 28px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    background: transparent;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    color: var(--color-text-muted);
    transition: color 0.15s, background 0.12s;
    flex-shrink: 0;
  }
  .zb-close-btn svg { width: 12px; height: 12px; }
  .zb-close-btn:hover { color: var(--color-text); background: var(--color-bg); }

  /* State change row */
  .zb-state-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 20px 14px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-bg);
  }

  .zb-state-block {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .zb-state-block.main { flex: 1; }

  .zb-state-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--color-text-muted);
  }

  .zb-state-val {
    font-size: 22px;
    font-weight: 800;
    font-family: ui-monospace, monospace;
    letter-spacing: -0.02em;
    color: var(--color-text-muted);
  }
  .zb-state-val.old {
    color: var(--color-text-muted);
    font-size: 18px;
    font-weight: 600;
    text-decoration: line-through;
    opacity: 0.6;
  }
  .zb-state-val.current {
    color: #22c55e;
  }

  .zb-state-arrow {
    flex-shrink: 0;
    color: var(--color-text-muted);
    padding: 4px;
  }
  .zb-state-arrow svg { width: 28px; height: 10px; display: block; }

  /* Attributes grid */
  .zb-attrs-block {
    padding: 14px 18px;
    border-bottom: 1px solid var(--color-border);
  }
  .zb-section-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--color-text-muted);
    margin-bottom: 10px;
  }
  .zb-attrs-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 8px;
  }
  .zb-attr-cell {
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 8px 12px;
  }
  .zb-attr-key {
    font-size: 10px;
    font-weight: 600;
    text-transform: capitalize;
    color: var(--color-text-muted);
    letter-spacing: 0.02em;
    margin-bottom: 3px;
  }
  .zb-attr-val {
    font-size: 13px;
    font-weight: 700;
    color: var(--color-text);
    font-family: ui-monospace, monospace;
    word-break: break-word;
  }

  /* Event type badge */
  .zb-event-type-row {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 16px 4px;
    flex-shrink: 0;
  }
  .zb-event-type-badge {
    font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
    color: var(--color-text-muted);
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 2px 7px;
  }
  .zb-service-call {
    font-size: 12px; font-weight: 600; font-family: monospace;
    color: var(--color-accent, #6366f1);
  }

  /* Raw payload */
  .zb-raw-toggle {
    margin: 0 16px 4px;
    padding: 5px 12px;
    border-radius: 5px;
    font-size: 12px; font-weight: 500;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .zb-raw-toggle:hover { background: var(--color-surface-hover); }
  .zb-raw-block {
    margin: 0 16px 8px;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    background: var(--color-bg);
    max-height: 200px;
    overflow: auto;
  }
  .zb-raw-pre {
    margin: 0;
    padding: 10px 12px;
    font-size: 11px;
    font-family: monospace;
    white-space: pre;
    color: var(--color-text-muted);
  }

  /* Footer */
  .zb-modal-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    gap: 12px;
  }
  .zb-modal-footer-nav {
    border-top: 1px solid var(--color-border);
  }

  .zb-trace-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 8px;
    background: rgba(34,197,94,.12);
    border: 1px solid rgba(34,197,94,.3);
    color: #4ade80;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
  }
  .zb-trace-btn svg { width: 14px; height: 14px; }
  .zb-trace-btn:hover { background: rgba(34,197,94,.2); }

  .zb-nav {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .zb-nav-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 10px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    background: transparent;
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-muted);
    cursor: pointer;
    transition: all 0.12s;
  }
  .zb-nav-btn svg { width: 14px; height: 14px; }
  .zb-nav-btn:not(:disabled):hover { color: var(--color-text); border-color: var(--color-border-hover); }
  .zb-nav-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .zb-nav-pos {
    font-size: 11px;
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
    min-width: 50px;
    text-align: center;
  }

  /* ── Mobile responsive ──────────────────────── */
  @media (max-width: 768px) {
    .panel-header { flex-wrap: wrap; gap: 10px; }
    .filter-row { flex-wrap: wrap; gap: 8px; }
    .filter-group { flex: 1 1 140px; }
    .summary-chips { overflow-x: auto; flex-wrap: nowrap; padding-bottom: 2px; }
    .chip { flex-shrink: 0; }
  }
  @media (max-width: 640px) {
    .protocol-selector { width: 100%; justify-content: stretch; }
    .protocol-btn { flex: 1; text-align: center; }
    .zb-modal {
      width: 100%;
      max-width: 100%;
      height: 100%;
      top: 0; left: 0;
      transform: none;
      border-radius: 0;
    }
    @keyframes zb-modal-in {
      from { opacity: 0; transform: translateY(20px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .zb-modal-time, .zb-modal-ago { display: none; }
    .zb-attrs-grid { grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); }
    .zb-modal-footer { flex-direction: column; align-items: stretch; }
    .zb-trace-btn { justify-content: center; }
    .zb-nav { justify-content: center; }
  }
  @media (max-width: 480px) {
    .filter-group { flex: 1 1 100%; }
    .chip { font-size: 10px; padding: 2px 8px; }
    .zb-attrs-grid { grid-template-columns: 1fr; }
  }
</style>
