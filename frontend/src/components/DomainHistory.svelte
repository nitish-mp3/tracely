<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import DomainIcon from './DomainIcon.svelte';
  import ConfidenceBadge from './ConfidenceBadge.svelte';
  import { getEvents } from '../lib/api.js';

  export let domain;

  const dispatch = createEventDispatcher();
  let history = [];
  let total = 0;
  let loading = true;
  let loadingMore = false;
  let page = 1;
  const LIMIT = 50;

  onMount(async () => {
    await loadPage();
  });

  async function loadPage(append = false) {
    if (!append) { loading = true; } else { loadingMore = true; }
    try {
      const data = await getEvents({ domain, page, limit: LIMIT });
      const items = data.items || [];
      if (append) {
        history = [...history, ...items];
      } else {
        history = items;
      }
      total = data.total || history.length;
    } catch { /* silent */ }
    loading = false;
    loadingMore = false;
  }

  function handleLoadMore() {
    if (loadingMore || history.length >= total) return;
    page++;
    loadPage(true);
  }

  function handleClose() { dispatch('close'); }

  function handleEventClick(event) {
    dispatch('eventclick', event);
    dispatch('close');
  }

  function formatTime(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  }

  function getStateChange(event) {
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

  function isOnState(state) {
    const s = String(state).toLowerCase();
    return s === 'on' || s === 'true' || s === 'home' || s === 'playing' || s === 'open' || s === 'unlocked';
  }

  function isOffState(state) {
    const s = String(state).toLowerCase();
    return s === 'off' || s === 'false' || s === 'not_home' || s === 'idle' || s === 'closed' || s === 'locked';
  }

  $: hasMore = history.length < total;
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<div class="overlay" on:click={handleClose} role="presentation" />

<aside class="history-panel" role="dialog" aria-label="Domain history for {domain}">
  <header class="panel-header">
    <div class="header-left">
      <DomainIcon {domain} />
      <div class="header-info">
        <h3>Domain History</h3>
        <span class="domain-name">{domain}</span>
      </div>
    </div>
    <div class="header-right">
      <span class="history-count">{total} events</span>
      <button class="close-btn" on:click={handleClose} aria-label="Close">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
      </button>
    </div>
  </header>

  <div class="panel-body">
    {#if loading}
      <div class="loading-state">
        <div class="spinner" />
        <span>Loading history…</span>
      </div>
    {:else if history.length === 0}
      <div class="empty-state">
        <p>No events recorded for this domain.</p>
      </div>
    {:else}
      <div class="history-timeline">
        {#each history as event, i (event.id)}
          {@const sc = getStateChange(event)}
          <button class="history-entry" on:click={() => handleEventClick(event)}>
            <div class="entry-timeline-dot" class:is-on={sc && isOnState(sc.to)} class:is-off={sc && isOffState(sc.to)} />
            {#if i < history.length - 1}
              <div class="entry-timeline-line" />
            {/if}
            <div class="entry-content">
              <div class="entry-main">
                <span class="entry-name">{event.name || event.event_type}</span>
                {#if event.entity_id}
                  <span class="entry-entity">{event.entity_id}</span>
                {/if}
                {#if sc}
                  <div class="entry-state-change">
                    <span class="state-val" class:val-off={isOffState(sc.from)} class:val-on={isOnState(sc.from)}>{sc.from}</span>
                    <svg class="state-arrow" viewBox="0 0 12 8" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 4h10M8 1l3 3-3 3" /></svg>
                    <span class="state-val" class:val-on={isOnState(sc.to)} class:val-off={isOffState(sc.to)}>{sc.to}</span>
                  </div>
                {/if}
              </div>
              <div class="entry-meta">
                <time class="entry-time">{formatTime(event.timestamp)}</time>
                <ConfidenceBadge confidence={event.confidence} />
              </div>
            </div>
          </button>
        {/each}
      </div>

      {#if hasMore}
        <div class="load-more-wrap">
          <button class="load-more-btn" on:click={handleLoadMore} disabled={loadingMore}>
            {#if loadingMore}
              <span class="spinner-sm" /> Loading…
            {:else}
              Load more ({total - history.length} remaining)
            {/if}
          </button>
        </div>
      {/if}
    {/if}
  </div>
</aside>

<style>
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.5); backdrop-filter: blur(4px);
    z-index: 200; animation: fadeIn var(--duration-fast) ease-out;
  }
  .history-panel {
    position: fixed; top: 0; right: 0; bottom: 0;
    width: 440px; max-width: 94vw;
    background: var(--color-bg); border-left: 1px solid var(--color-border);
    z-index: 201; display: flex; flex-direction: column;
    animation: slideInRight var(--duration-normal) var(--ease-out);
    box-shadow: var(--shadow-lg);
  }
  .panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--sp-4) var(--sp-5);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface); flex-shrink: 0;
  }
  .header-left { display: flex; align-items: center; gap: var(--sp-3); }
  .header-info { display: flex; flex-direction: column; gap: 2px; }
  .panel-header h3 { font-size: var(--text-md); font-weight: 700; letter-spacing: -0.02em; }
  .domain-name {
    font-family: var(--font-mono); font-size: var(--text-2xs);
    color: var(--color-info); letter-spacing: 0.01em; font-weight: 600;
  }
  .header-right { display: flex; align-items: center; gap: var(--sp-3); }
  .history-count {
    font-size: var(--text-2xs); color: var(--color-text-muted); font-weight: 500;
    padding: 2px 8px; border-radius: var(--radius-full);
    background: var(--color-surface-hover);
  }
  .close-btn {
    width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); color: var(--color-text-muted); transition: all var(--duration-fast);
  }
  .close-btn svg { width: 14px; height: 14px; }
  .close-btn:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .panel-body { flex: 1; overflow-y: auto; padding: var(--sp-4) var(--sp-5); }
  .loading-state, .empty-state {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: var(--sp-12) var(--sp-4); gap: var(--sp-3);
    color: var(--color-text-muted); font-size: var(--text-sm);
  }
  .spinner {
    width: 20px; height: 20px;
    border: 2px solid var(--color-border); border-top-color: var(--color-primary);
    border-radius: 50%; animation: spin 0.6s linear infinite;
  }
  .spinner-sm {
    display: inline-block; width: 14px; height: 14px;
    border: 2px solid var(--color-border); border-top-color: var(--color-primary);
    border-radius: 50%; animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .history-timeline { display: flex; flex-direction: column; }
  .history-entry {
    display: flex; gap: var(--sp-3); padding: var(--sp-2) 0;
    position: relative; text-align: left;
    transition: background var(--duration-fast);
    border-radius: var(--radius-md);
    padding-left: var(--sp-2); padding-right: var(--sp-2);
  }
  .history-entry:hover { background: var(--color-surface-hover); }
  .entry-timeline-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--color-border-hover); flex-shrink: 0; margin-top: 5px;
    border: 2px solid var(--color-bg); z-index: 1;
  }
  .entry-timeline-dot.is-on { background: var(--color-success); box-shadow: 0 0 6px rgba(52,211,153,.4); }
  .entry-timeline-dot.is-off { background: var(--color-text-muted); }
  .entry-timeline-line {
    position: absolute; left: calc(var(--sp-2) + 4px); top: 18px; bottom: -2px;
    width: 2px; background: var(--color-border);
  }
  .entry-content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .entry-main { display: flex; flex-direction: column; gap: 2px; }
  .entry-name {
    font-size: var(--text-sm); font-weight: 500; color: var(--color-text);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .entry-entity {
    font-size: var(--text-2xs); color: var(--color-primary); font-family: var(--font-mono);
    opacity: 0.8;
  }
  .entry-state-change {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: var(--text-2xs); font-family: var(--font-mono);
  }
  .state-val {
    padding: 1px 6px; border-radius: 3px;
    background: var(--color-surface); color: var(--color-text-muted);
  }
  .state-val.val-on { color: var(--color-success); background: var(--color-success-soft); font-weight: 600; }
  .state-val.val-off { color: var(--color-text-muted); background: var(--color-surface-hover); }
  .state-arrow { width: 12px; height: 8px; color: var(--color-text-muted); flex-shrink: 0; }
  .entry-meta { display: flex; align-items: center; gap: var(--sp-2); }
  .entry-time {
    font-size: var(--text-2xs); color: var(--color-text-muted);
    font-family: var(--font-mono);
  }

  .load-more-wrap {
    display: flex; justify-content: center; padding: var(--sp-3) 0;
  }
  .load-more-btn {
    display: inline-flex; align-items: center; gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-4); font-size: var(--text-xs);
    border-radius: var(--radius-md); background: var(--color-surface);
    border: 1px solid var(--color-border); color: var(--color-text-secondary);
    transition: all var(--duration-fast);
  }
  .load-more-btn:hover:not(:disabled) {
    background: var(--color-surface-hover); border-color: var(--color-primary);
    color: var(--color-primary);
  }
  .load-more-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  @media (max-width: 480px) {
    .history-panel { width: 100%; max-width: 100%; }
    .panel-header { padding: var(--sp-3); }
    .panel-body { padding: var(--sp-3); }
  }
</style>
