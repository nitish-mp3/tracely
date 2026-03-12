<script>
  import { createEventDispatcher } from 'svelte';
  import ConfidenceBadge from './ConfidenceBadge.svelte';
  import DomainIcon from './DomainIcon.svelte';

  export let event;
  export let compact = false;

  const dispatch = createEventDispatcher();
  let showRaw = false;

  function toggleRaw(e) {
    e.stopPropagation();
    showRaw = !showRaw;
  }

  function formatPayload(payload) {
    try {
      const obj = typeof payload === 'string' ? JSON.parse(payload) : payload;
      return JSON.stringify(obj, null, 2);
    } catch {
      return String(payload || '');
    }
  }

  function categoryColor(domain) {
    if (!domain) return 'var(--color-system)';
    const auto = ['automation', 'script', 'scene'];
    const user = ['person', 'device_tracker'];
    const sys = ['homeassistant', 'persistent_notification', 'update'];
    if (auto.includes(domain)) return 'var(--color-automation)';
    if (user.includes(domain)) return 'var(--color-user)';
    if (sys.includes(domain)) return 'var(--color-system)';
    return 'var(--color-device)';
  }

  function relativeTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    if (diff < 5) return 'just now';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 172800) return 'yesterday';
    return `${Math.floor(diff / 86400)}d ago`;
  }

  function exactTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }

  function getStateChange() {
    if (event.event_type !== 'state_changed') return null;
    try {
      const p = typeof event.payload === 'string' ? JSON.parse(event.payload) : event.payload;
      const oldState = p?.old_state?.state ?? p?.old_state;
      const newState = p?.new_state?.state ?? p?.new_state;
      if (oldState !== undefined && newState !== undefined) {
        return { from: String(oldState), to: String(newState) };
      }
    } catch { /* ignore */ }
    return null;
  }

  function isOnState(s) {
    const v = String(s).toLowerCase();
    return v === 'on' || v === 'true' || v === 'home' || v === 'playing' || v === 'open' || v === 'unlocked';
  }
  function isOffState(s) {
    const v = String(s).toLowerCase();
    return v === 'off' || v === 'false' || v === 'not_home' || v === 'idle' || v === 'closed' || v === 'locked';
  }
  function isUnavailable(s) {
    const v = String(s).toLowerCase();
    return v === 'unavailable' || v === 'unknown';
  }

  function parseEventName(name, entityId) {
    if (!name) return { label: event.event_type, action: '' };
    const actionVerbs = /\b(changed|turned|switched|toggled|triggered|started|stopped|finished|called|set|updated|fired|loaded)\b/i;
    const match = name.match(actionVerbs);
    if (match) {
      const idx = match.index;
      let label = name.substring(0, idx).trim();
      let action = name.substring(idx).trim();
      if (entityId && label.toLowerCase() === entityId.replace(/\./g, ' ').replace(/_/g, ' ').toLowerCase()) {
        const parts = entityId.split('.');
        if (parts.length > 1) {
          label = parts[1].replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        }
      }
      if (label.length > 40) {
        const words = label.split(' ');
        if (words.length > 4) label = words.slice(-3).join(' ');
      }
      return { label, action };
    }
    if (name.length > 50) {
      const words = name.split(' ');
      const mid = Math.ceil(words.length / 2);
      return { label: words.slice(0, mid).join(' '), action: words.slice(mid).join(' ') };
    }
    return { label: name, action: '' };
  }

  function friendlyEntityName(entityId) {
    if (!entityId) return '';
    const parts = entityId.split('.');
    if (parts.length < 2) return entityId;
    return parts[1].replace(/_/g, ' ');
  }

  function getUserLabel(userId) {
    if (!userId) return null;
    // Shorten long UUID-style user IDs
    if (userId.length > 16) return userId.substring(0, 8) + '…';
    return userId;
  }

  function handleTagClick(e) {
    e.stopPropagation();
    if (event.entity_id) dispatch('tagclick', event.entity_id);
  }

  function handleDomainClick(e) {
    e.stopPropagation();
    if (event.domain) dispatch('domainclick', event.domain);
  }

  function handleViewInMonitor(e, view) {
    e.stopPropagation();
    dispatch('viewin', view);
  }

  $: stateChange = getStateChange();
  $: parsed = parseEventName(event.name, event.entity_id);
  $: newStateUnavailable = stateChange && isUnavailable(stateChange.to);
  $: userLabel = getUserLabel(event.user_id);
  $: isKnx = event.integration === 'knx' || (event.entity_id && event.entity_id.includes('knx'));
  $: isZigbee = event.integration === 'mqtt' || event.integration === 'zha' || event.integration === 'zigbee2mqtt' || (event.entity_id && (event.entity_id.includes('zigbee') || event.entity_id.includes('z2m')));
</script>

<button
  class="event-node"
  class:compact
  class:bookmarked={event.important}
  class:unavailable-event={newStateUnavailable}
  style="--accent: {categoryColor(event.domain)}"
  on:click
  aria-label="View trace for {event.name || event.event_type}"
>
  <div class="indicator" />

  <div class="icon-col">
    <DomainIcon domain={event.domain} />
  </div>

  <div class="content">
    <div class="name-row">
      <span class="name-label">{parsed.label}</span>
      {#if parsed.action}
        <span class="name-action">{parsed.action}</span>
      {/if}
    </div>

    {#if stateChange}
      <div class="state-change-row">
        <span class="sc-val" class:sc-on={isOnState(stateChange.from)} class:sc-off={isOffState(stateChange.from)} class:sc-unavail={isUnavailable(stateChange.from)}>{stateChange.from}</span>
        <svg class="sc-arrow" viewBox="0 0 16 8" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 4h14M12 1l3 3-3 3" /></svg>
        <span class="sc-val sc-target" class:sc-on={isOnState(stateChange.to)} class:sc-off={isOffState(stateChange.to)} class:sc-unavail={isUnavailable(stateChange.to)}>{stateChange.to}</span>
      </div>
    {/if}

    <div class="tags-row">
      {#if event.entity_id}
        <button class="tag entity-tag" on:click={handleTagClick} title="View history for {event.entity_id}">
          <svg class="tag-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="6" r="4" /></svg>
          <span class="tag-entity-name">{friendlyEntityName(event.entity_id)}</span>
        </button>
      {/if}
      {#if event.domain}
        <button class="tag domain-tag" on:click={handleDomainClick} title="View all {event.domain} events">
          {event.domain}
        </button>
      {/if}
      {#if event.area}
        <span class="tag area-tag">
          <svg class="tag-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M6 1L1 5v6h4V8h2v3h4V5L6 1z" /></svg>
          {event.area}
        </span>
      {/if}
      {#if userLabel}
        <span class="tag user-tag" title="Triggered by user: {event.user_id}">
          <svg class="tag-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="6" cy="4" r="2.5" /><path d="M2 11c0-2.2 1.8-4 4-4s4 1.8 4 4" /></svg>
          {userLabel}
        </span>
      {/if}
      {#if event.integration}
        <span class="tag integration-tag" title="Integration: {event.integration}">
          {event.integration}
        </span>
      {/if}
      {#if isKnx}
        <button class="tag crosslink-tag knx-link" on:click={(e) => handleViewInMonitor(e, 'knx')} title="View in KNX Monitor">
          <svg class="tag-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M2 6h3l1-3 2 6 1-3h3" /></svg>
          KNX
        </button>
      {/if}
      {#if isZigbee}
        <button class="tag crosslink-tag zigbee-link" on:click={(e) => handleViewInMonitor(e, 'zigbee')} title="View in Zigbee Monitor">
          <svg class="tag-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M2 3h8L2 9h8" /></svg>
          Zigbee
        </button>
      {/if}
    </div>
  </div>

  <div class="meta">
    <ConfidenceBadge confidence={event.confidence} />
    <time class="time" datetime={event.timestamp} title={exactTime(event.timestamp)}>
      {relativeTime(event.timestamp)}
    </time>
    <span class="time-exact">{exactTime(event.timestamp)}</span>
  </div>

  {#if event.important}
    <span class="bookmark-icon" aria-label="Bookmarked">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 2h8v12l-4-3-4 3V2z" /></svg>
    </span>
  {/if}

  {#if !compact}
    <button class="raw-toggle" on:click={toggleRaw} title={showRaw ? 'Hide raw data' : 'Show raw data'} aria-label="Toggle raw payload">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M5 4L1 8l4 4M11 4l4 4-4 4M9 2l-2 12" /></svg>
    </button>
  {/if}
</button>

{#if showRaw && event.payload}
  <div class="raw-panel">
    <div class="raw-header">
      <span class="raw-title">Raw Payload</span>
      <span class="raw-type">{event.event_type}</span>
      {#if event.id}
        <span class="raw-id">{event.id}</span>
      {/if}
    </div>
    <pre class="raw-json">{formatPayload(event.payload)}</pre>
  </div>
{/if}

<style>
  .event-node {
    display: flex; align-items: flex-start; gap: var(--sp-3);
    width: 100%; padding: var(--sp-3) var(--sp-4);
    border-radius: var(--radius-md); background: var(--color-surface);
    border: 1px solid var(--color-border); text-align: left;
    transition: all var(--duration-fast); position: relative;
  }
  .event-node:hover {
    background: var(--color-surface-hover); border-color: var(--color-border-hover);
    transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,0,0,.08);
  }
  .event-node:active { transform: translateY(0); }
  .event-node:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
  .event-node.compact { padding: var(--sp-2) var(--sp-3); gap: var(--sp-2); }

  .indicator {
    width: 3px; height: 100%; min-height: 36px;
    border-radius: 2px; background: var(--accent);
    flex-shrink: 0; opacity: 0.7; transition: opacity var(--duration-fast);
  }
  .event-node:hover .indicator { opacity: 1; }
  .compact .indicator { min-height: 20px; }

  .icon-col {
    flex-shrink: 0; width: 36px; height: 36px;
    display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); background: var(--color-bg-elevated);
    font-size: var(--text-base); margin-top: 2px;
  }
  .compact .icon-col { width: 28px; height: 28px; }

  .content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }

  /* Improved name display */
  .name-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px; line-height: 1.3; }
  .name-label {
    font-weight: 600; font-size: var(--text-sm); color: var(--color-text);
    letter-spacing: -0.01em;
  }
  .name-action {
    font-weight: 400; font-size: var(--text-xs); color: var(--color-text-secondary);
  }

  /* State change */
  .state-change-row {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: var(--text-xs); font-family: var(--font-mono);
    padding: 2px 0;
  }
  .sc-val {
    padding: 2px 8px; border-radius: var(--radius-sm);
    background: var(--color-surface-hover); color: var(--color-text-secondary);
    font-weight: 500; transition: all var(--duration-fast);
    font-size: var(--text-xs);
  }
  .sc-val.sc-on {
    color: var(--color-success); background: var(--color-success-soft);
    font-weight: 700;
  }
  .sc-val.sc-off { color: var(--color-text-muted); background: var(--color-surface-active); }
  .sc-val.sc-target.sc-on { box-shadow: 0 0 6px rgba(52,211,153,.2); }
  .sc-arrow { width: 16px; height: 8px; color: var(--color-text-muted); flex-shrink: 0; }

  /* Tags */
  .tags-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .tag {
    display: inline-flex; align-items: center; gap: 3px;
    padding: 2px 8px; border-radius: var(--radius-full);
    font-size: var(--text-2xs); font-weight: 500; letter-spacing: 0.01em;
    white-space: nowrap; transition: all var(--duration-fast);
    border: 1px solid transparent;
  }
  .tag-icon { width: 9px; height: 9px; flex-shrink: 0; }
  .entity-tag {
    color: var(--color-primary); background: var(--color-primary-soft);
    font-family: var(--font-mono); cursor: pointer; border-color: rgba(124,92,252,.15);
  }
  .entity-tag:hover {
    background: var(--color-primary-bg); border-color: var(--color-primary);
    box-shadow: 0 0 6px rgba(124,92,252,.2); transform: translateY(-1px);
  }
  .tag-entity-name { text-transform: capitalize; }
  .domain-tag {
    color: var(--color-info); background: var(--color-info-soft);
    border-color: rgba(56,189,248,.12); cursor: pointer;
  }
  .domain-tag:hover {
    background: rgba(56,189,248,.18); border-color: var(--color-info);
    box-shadow: 0 0 6px rgba(56,189,248,.2); transform: translateY(-1px);
  }
  .area-tag { color: var(--color-warning); background: var(--color-warning-soft); border-color: rgba(251,191,36,.12); }
  .user-tag {
    color: var(--color-success); background: var(--color-success-soft);
    border-color: rgba(52,211,153,.15);
  }
  .integration-tag {
    color: var(--color-text-secondary); background: var(--color-surface-hover);
    border-color: var(--color-border);
  }

  /* Cross-link monitor buttons */
  .crosslink-tag {
    cursor: pointer; font-weight: 600;
  }
  .crosslink-tag:hover { transform: translateY(-1px); }
  .knx-link {
    color: #f59e0b; background: rgba(245,158,11,.1);
    border-color: rgba(245,158,11,.2);
  }
  .knx-link:hover {
    background: rgba(245,158,11,.2); border-color: #f59e0b;
    box-shadow: 0 0 6px rgba(245,158,11,.2);
  }
  .zigbee-link {
    color: #22c55e; background: rgba(34,197,94,.1);
    border-color: rgba(34,197,94,.2);
  }
  .zigbee-link:hover {
    background: rgba(34,197,94,.2); border-color: #22c55e;
    box-shadow: 0 0 6px rgba(34,197,94,.2);
  }

  /* Unavailable state styling */
  .sc-val.sc-unavail {
    color: var(--color-error, #ef4444); background: rgba(239,68,68,.12);
    font-weight: 700; animation: pulse-unavail 2s ease-in-out infinite;
  }
  .unavailable-event {
    border-color: rgba(239,68,68,.25); background: rgba(239,68,68,.03);
  }
  .unavailable-event .indicator { background: var(--color-error, #ef4444); }
  @keyframes pulse-unavail {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  .meta { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; flex-shrink: 0; margin-top: 2px; }
  .time { font-size: var(--text-2xs); color: var(--color-text-muted); white-space: nowrap; font-family: var(--font-mono); }
  .time-exact {
    font-size: 9px; color: var(--color-text-muted); opacity: 0.6;
    white-space: nowrap; font-family: var(--font-mono);
  }

  .bookmark-icon { position: absolute; top: 6px; right: 6px; color: var(--color-warning); width: 12px; height: 12px; }
  .bookmark-icon svg { width: 12px; height: 12px; }
  .bookmarked { border-color: rgba(251,191,36,.3); background: rgba(251,191,36,.03); }
  .bookmarked:hover { border-color: rgba(251,191,36,.5); }

  /* Raw data toggle button */
  .raw-toggle {
    position: absolute; bottom: 6px; right: 6px;
    width: 22px; height: 22px; padding: 3px;
    border-radius: var(--radius-sm); background: var(--color-surface-hover);
    color: var(--color-text-muted); opacity: 0;
    transition: all var(--duration-fast); cursor: pointer;
    display: flex; align-items: center; justify-content: center;
  }
  .raw-toggle svg { width: 14px; height: 14px; }
  .event-node:hover .raw-toggle { opacity: 0.6; }
  .raw-toggle:hover { opacity: 1 !important; color: var(--color-primary); background: var(--color-primary-soft); }

  /* Raw payload panel */
  .raw-panel {
    margin-top: -1px; padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--color-border); border-top: none;
    border-radius: 0 0 var(--radius-md) var(--radius-md);
    background: var(--color-bg-elevated);
    animation: slideDown 0.15s ease-out;
  }
  @keyframes slideDown {
    from { opacity: 0; max-height: 0; }
    to { opacity: 1; max-height: 600px; }
  }
  .raw-header {
    display: flex; align-items: center; gap: var(--sp-2);
    margin-bottom: var(--sp-2); padding-bottom: var(--sp-2);
    border-bottom: 1px solid var(--color-border);
  }
  .raw-title { font-size: var(--text-xs); font-weight: 600; color: var(--color-text); }
  .raw-type {
    font-size: var(--text-2xs); font-family: var(--font-mono);
    padding: 1px 6px; border-radius: var(--radius-full);
    background: var(--color-info-soft); color: var(--color-info);
  }
  .raw-id {
    font-size: var(--text-2xs); font-family: var(--font-mono);
    color: var(--color-text-muted); margin-left: auto;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px;
  }
  .raw-json {
    font-size: 11px; font-family: var(--font-mono);
    color: var(--color-text-secondary); line-height: 1.5;
    max-height: 400px; overflow-y: auto; overflow-x: auto;
    white-space: pre; tab-size: 2; margin: 0;
    padding: var(--sp-2); border-radius: var(--radius-sm);
    background: var(--color-surface);
  }

  @media (max-width: 640px) {
    .event-node { padding: var(--sp-2) var(--sp-3); gap: var(--sp-2); }
    .icon-col { width: 30px; height: 30px; }
    .meta { flex-direction: row; gap: var(--sp-2); }
    .tags-row { gap: 3px; }
    .tag { font-size: 9px; padding: 1px 5px; }
  }
  @media (max-width: 400px) {
    .icon-col { display: none; }
  }
</style>
