<script>
  import { createEventDispatcher } from 'svelte';
  import ConfidenceBadge from './ConfidenceBadge.svelte';
  import DomainIcon from './DomainIcon.svelte';

  export let event;
  export let compact = false;

  const dispatch = createEventDispatcher();

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
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
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
    return v === 'off' || v === 'false' || v === 'not_home' || v === 'idle' || v === 'closed' || v === 'locked' || v === 'unavailable';
  }

  function handleTagClick(e) {
    e.stopPropagation();
    if (event.entity_id) {
      dispatch('tagclick', event.entity_id);
    }
  }

  $: stateChange = getStateChange();
</script>

<button
  class="event-node"
  class:compact
  class:bookmarked={event.important}
  style="--accent: {categoryColor(event.domain)}"
  on:click
  aria-label="View trace for {event.name || event.event_type}"
>
  <div class="indicator" />

  <div class="icon-col">
    <DomainIcon domain={event.domain} />
  </div>

  <div class="content">
    <span class="name">{event.name || event.event_type}</span>

    {#if stateChange}
      <div class="state-change-row">
        <span class="sc-val" class:sc-on={isOnState(stateChange.from)} class:sc-off={isOffState(stateChange.from)}>{stateChange.from}</span>
        <svg class="sc-arrow" viewBox="0 0 12 8" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 4h10M8 1l3 3-3 3" /></svg>
        <span class="sc-val" class:sc-on={isOnState(stateChange.to)} class:sc-off={isOffState(stateChange.to)}>{stateChange.to}</span>
      </div>
    {/if}

    <div class="tags-row">
      {#if event.entity_id}
        <button class="tag entity-tag" on:click={handleTagClick} title="View history for {event.entity_id}">
          <svg class="tag-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="6" r="4" /></svg>
          {event.entity_id}
        </button>
      {/if}
      {#if event.domain}
        <span class="tag domain-tag">{event.domain}</span>
      {/if}
      {#if event.area}
        <span class="tag area-tag">
          <svg class="tag-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M6 1L1 5v6h4V8h2v3h4V5L6 1z" /></svg>
          {event.area}
        </span>
      {/if}
    </div>
  </div>

  <div class="meta">
    <ConfidenceBadge confidence={event.confidence} />
    <time class="time" datetime={event.timestamp}>
      {relativeTime(event.timestamp)}
    </time>
  </div>

  {#if event.important}
    <span class="bookmark-icon" aria-label="Bookmarked">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 2h8v12l-4-3-4 3V2z" /></svg>
    </span>
  {/if}
</button>

<style>
  .event-node {
    display: flex;
    align-items: flex-start;
    gap: var(--sp-3);
    width: 100%;
    padding: var(--sp-3) var(--sp-4);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    text-align: left;
    transition: all var(--duration-fast);
    position: relative;
  }
  .event-node:hover {
    background: var(--color-surface-hover);
    border-color: var(--color-border-hover);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
  }
  .event-node:active { transform: translateY(0); }
  .event-node:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
  .event-node.compact { padding: var(--sp-2) var(--sp-3); gap: var(--sp-2); }

  .indicator {
    width: 3px; height: 100%; min-height: 36px;
    border-radius: 2px; background: var(--accent);
    flex-shrink: 0; opacity: 0.7;
    transition: opacity var(--duration-fast);
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

  .content {
    flex: 1; min-width: 0;
    display: flex; flex-direction: column; gap: 4px;
  }
  .name {
    font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-size: var(--text-sm); color: var(--color-text); letter-spacing: -0.01em;
  }

  /* State change inline */
  .state-change-row {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: var(--text-2xs); font-family: var(--font-mono);
  }
  .sc-val {
    padding: 1px 6px; border-radius: 4px;
    background: var(--color-surface-hover); color: var(--color-text-secondary);
    font-weight: 500; transition: all var(--duration-fast);
  }
  .sc-val.sc-on {
    color: var(--color-success); background: var(--color-success-soft);
    font-weight: 700; box-shadow: 0 0 4px rgba(52,211,153,.15);
  }
  .sc-val.sc-off {
    color: var(--color-text-muted); background: var(--color-surface-active);
  }
  .sc-arrow { width: 12px; height: 8px; color: var(--color-text-muted); flex-shrink: 0; }

  /* Tags */
  .tags-row {
    display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
  }
  .tag {
    display: inline-flex; align-items: center; gap: 3px;
    padding: 1px 7px; border-radius: var(--radius-full);
    font-size: 10px; font-weight: 500; letter-spacing: 0.01em;
    white-space: nowrap; transition: all var(--duration-fast);
    border: 1px solid transparent;
  }
  .tag-icon { width: 9px; height: 9px; flex-shrink: 0; }

  .entity-tag {
    color: var(--color-primary); background: var(--color-primary-soft);
    font-family: var(--font-mono); cursor: pointer;
    border-color: rgba(124,92,252,.15);
  }
  .entity-tag:hover {
    background: var(--color-primary-bg);
    border-color: var(--color-primary);
    box-shadow: 0 0 6px rgba(124,92,252,.2);
    transform: translateY(-1px);
  }
  .domain-tag {
    color: var(--color-info); background: var(--color-info-soft);
    border-color: rgba(56,189,248,.12);
  }
  .area-tag {
    color: var(--color-warning); background: var(--color-warning-soft);
    border-color: rgba(251,191,36,.12);
  }

  .meta {
    display: flex; flex-direction: column; align-items: flex-end;
    gap: 4px; flex-shrink: 0; margin-top: 2px;
  }
  .time {
    font-size: var(--text-2xs); color: var(--color-text-muted);
    white-space: nowrap; font-family: var(--font-mono);
  }

  .bookmark-icon {
    position: absolute; top: 6px; right: 6px;
    color: var(--color-warning); width: 12px; height: 12px;
  }
  .bookmark-icon svg { width: 12px; height: 12px; }
  .bookmarked { border-color: rgba(251,191,36,.3); background: rgba(251,191,36,.03); }
  .bookmarked:hover { border-color: rgba(251,191,36,.5); }

  /* Responsive */
  @media (max-width: 640px) {
    .event-node { padding: var(--sp-2) var(--sp-3); gap: var(--sp-2); }
    .icon-col { width: 30px; height: 30px; }
    .meta { flex-direction: row; gap: var(--sp-2); }
    .tags-row { gap: 3px; }
    .tag { font-size: 9px; padding: 0 5px; }
  }
  @media (max-width: 400px) {
    .icon-col { display: none; }
  }
</style>
