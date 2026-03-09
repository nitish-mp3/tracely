<script>
  import { onMount, onDestroy } from 'svelte';
  import EventNode from '../components/EventNode.svelte';
  import EntityHistory from '../components/EntityHistory.svelte';
  import { getEvents, subscribeEvents } from '../lib/api.js';
  import {
    events, pagination, filters, loading, error,
    selectedEventId, sseStatus, selectedEntityTag,
  } from '../stores/events.js';
  import { currentView } from '../stores/config.js';

  let unsubSSE = null;
  let liveCount = 0;
  let liveIndicator = false;
  let blinkTimer = null;
  let mounted = false;
  let jumpPage = '';

  async function loadEvents() {
    $loading = true;
    $error = null;
    try {
      const params = { page: $pagination.page, limit: $pagination.limit };
      if ($filters.entity) params.entity = $filters.entity;
      if ($filters.domain) params.domain = $filters.domain;
      if ($filters.area) params.area = $filters.area;
      if ($filters.user_id) params.user_id = $filters.user_id;
      if ($filters.event_type) params.event_type = $filters.event_type;
      if ($filters.q) params.q = $filters.q;
      if ($filters.from) params.from = $filters.from;
      if ($filters.to) params.to = $filters.to;
      const data = await getEvents(params);
      $events = data.items || [];
      $pagination = { ...$pagination, total: data.total };
    } catch (e) {
      $error = e.message;
    } finally {
      $loading = false;
    }
  }

  function handleEventClick(event) {
    $selectedEventId = event.id;
    $currentView = 'trace';
  }

  function handleEntityTagClick(entityId) {
    $selectedEntityTag = entityId;
  }

  function handlePage(dir) {
    const next = $pagination.page + dir;
    if (next >= 1 && next <= maxPage) {
      $pagination = { ...$pagination, page: next };
      loadEvents();
    }
  }

  function handleJumpPage() {
    const p = parseInt(jumpPage, 10);
    if (p >= 1 && p <= maxPage) {
      $pagination = { ...$pagination, page: p };
      jumpPage = '';
      loadEvents();
    }
  }

  function handleJumpKeydown(e) {
    if (e.key === 'Enter') handleJumpPage();
  }

  function handlePageClick(p) {
    if (p !== $pagination.page) {
      $pagination = { ...$pagination, page: p };
      loadEvents();
    }
  }

  function flashLive() {
    liveIndicator = true;
    if (blinkTimer) clearTimeout(blinkTimer);
    blinkTimer = setTimeout(() => { liveIndicator = false; }, 600);
  }

  onMount(() => {
    mounted = true;
    loadEvents();
    unsubSSE = subscribeEvents(
      (event) => {
        if ($pagination.page === 1) {
          liveCount++;
          flashLive();
          events.update((list) => [event, ...list].slice(0, $pagination.limit));
          pagination.update((p) => ({ ...p, total: p.total + 1 }));
        }
      },
      (status) => { $sseStatus = status; }
    );
  });

  onDestroy(() => {
    if (unsubSSE) unsubSSE();
    if (blinkTimer) clearTimeout(blinkTimer);
  });

  // Only reload on filter changes after mount (skip initial reactive trigger)
  let prevFilterStr = '';
  $: {
    const filterStr = JSON.stringify($filters);
    if (mounted && filterStr !== prevFilterStr) {
      prevFilterStr = filterStr;
      $pagination.page = 1;
      loadEvents();
    }
  }

  $: maxPage = Math.ceil($pagination.total / $pagination.limit) || 1;

  // Compute visible page numbers (smart pagination)
  $: {
    const cur = $pagination.page;
    const pages = [];
    pages.push(1);
    if (cur > 4) pages.push('...');
    for (let i = Math.max(2, cur - 2); i <= Math.min(maxPage - 1, cur + 2); i++) {
      pages.push(i);
    }
    if (cur < maxPage - 3) pages.push('...');
    if (maxPage > 1) pages.push(maxPage);
    visiblePages = pages;
  }
  let visiblePages = [1];
</script>

<section class="timeline" aria-label="Event Timeline">
  <header class="timeline-header">
    <div class="header-title-group">
      <h2>Timeline</h2>
      <div class="live-status" class:is-live={$sseStatus === 'connected'} class:is-reconnecting={$sseStatus === 'reconnecting'}>
        <span class="live-dot" class:blink={liveIndicator} />
        {#if $sseStatus === 'connected'}
          <span class="live-text">Live</span>
        {:else if $sseStatus === 'reconnecting'}
          <span class="live-text reconnecting">Reconnecting…</span>
        {:else}
          <span class="live-text offline">Offline</span>
        {/if}
        {#if liveCount > 0}
          <span class="live-counter">+{liveCount}</span>
        {/if}
      </div>
    </div>
    <div class="header-meta">
      <span class="event-count">{$pagination.total.toLocaleString()} events</span>
    </div>
  </header>

  {#if $loading && $events.length === 0}
    <div class="skeleton-list">
      {#each Array(8) as _, i}
        <div class="skeleton skeleton-row" style="animation-delay: {i * 80}ms;" />
      {/each}
    </div>
  {:else if $error}
    <div class="state-card error-card">
      <div class="state-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="12" cy="12" r="10" /><path d="M15 9l-6 6M9 9l6 6" />
        </svg>
      </div>
      <h3>Failed to load events</h3>
      <p class="state-detail">{$error}</p>
      <button class="btn btn-primary" on:click={loadEvents}>Try again</button>
    </div>
  {:else if $events.length === 0}
    <div class="state-card">
      <div class="state-icon empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
        </svg>
      </div>
      <h3>No events yet</h3>
      <p class="state-detail">Events will appear here as Home Assistant generates them.</p>
    </div>
  {:else}
    <ul class="event-list">
      {#each $events as event, i (event.id)}
        <li class="event-item" class:is-new={i === 0 && liveIndicator} style="animation-delay: {Math.min(i * 30, 300)}ms;">
          <EventNode {event} on:click={() => handleEventClick(event)} on:tagclick={(e) => handleEntityTagClick(e.detail)} />
        </li>
      {/each}
    </ul>

    <!-- Enhanced pagination -->
    <nav class="pagination" aria-label="Pagination">
      <button class="page-btn" on:click={() => handlePage(-1)} disabled={$pagination.page <= 1} aria-label="Previous page">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M10 3L5 8l5 5" /></svg>
      </button>

      <div class="page-numbers">
        {#each visiblePages as p}
          {#if p === '...'}
            <span class="page-ellipsis">…</span>
          {:else}
            <button class="page-num" class:active={p === $pagination.page} on:click={() => handlePageClick(p)}>{p}</button>
          {/if}
        {/each}
      </div>

      <button class="page-btn" on:click={() => handlePage(1)} disabled={$pagination.page >= maxPage} aria-label="Next page">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M6 3l5 5-5 5" /></svg>
      </button>

      <div class="page-jump">
        <input
          type="number"
          class="jump-input"
          bind:value={jumpPage}
          on:keydown={handleJumpKeydown}
          placeholder="Go to"
          min="1"
          max={maxPage}
          aria-label="Jump to page"
        />
        <button class="jump-btn" on:click={handleJumpPage} disabled={!jumpPage} aria-label="Go">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 8h10M10 5l3 3-3 3" /></svg>
        </button>
      </div>
    </nav>
  {/if}
</section>

{#if $selectedEntityTag}
  <EntityHistory entityId={$selectedEntityTag} on:close={() => $selectedEntityTag = null} on:eventclick={(e) => handleEventClick(e.detail)} />
{/if}

<style>
  .timeline {
    flex: 1; display: flex; flex-direction: column; gap: var(--sp-4);
    padding: var(--sp-6); overflow-y: auto; max-width: 960px; margin: 0 auto; width: 100%;
  }
  .timeline-header {
    display: flex; align-items: center; justify-content: space-between;
    padding-bottom: var(--sp-3); border-bottom: 1px solid var(--color-border);
    flex-wrap: wrap; gap: var(--sp-2);
  }
  .header-title-group { display: flex; align-items: center; gap: var(--sp-3); }
  .timeline-header h2 { font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.02em; }
  .live-status {
    display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px;
    border-radius: var(--radius-full); background: var(--color-surface-hover);
    font-size: var(--text-2xs); font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--color-text-muted); transition: all var(--duration-normal);
  }
  .live-status.is-live { background: var(--color-success-soft); color: var(--color-success); }
  .live-status.is-reconnecting { background: var(--color-warning-soft); color: var(--color-warning); }
  .live-dot {
    width: 6px; height: 6px; border-radius: 50%; background: var(--color-text-muted); transition: all 0.15s;
  }
  .live-status.is-live .live-dot { background: var(--color-success); animation: breathe 2s infinite; }
  .live-dot.blink { background: var(--color-primary) !important; box-shadow: 0 0 8px var(--color-primary); transform: scale(1.5); }
  .live-status.is-reconnecting .live-dot { background: var(--color-warning); }
  .live-text { line-height: 1; }
  .live-text.reconnecting { color: var(--color-warning); }
  .live-text.offline { color: var(--color-text-muted); }
  .live-counter {
    padding: 0 4px; border-radius: var(--radius-full);
    background: rgba(255,255,255,.1); font-size: 9px; font-variant-numeric: tabular-nums;
  }
  .event-count { font-size: var(--text-xs); color: var(--color-text-muted); font-weight: 500; }
  .event-list { list-style: none; display: flex; flex-direction: column; gap: var(--sp-2); }
  .event-item { animation: fadeIn var(--duration-normal) var(--ease-out) both; }
  .event-item.is-new { animation: liveFlash 0.6s var(--ease-out); }
  @keyframes liveFlash {
    0% { transform: translateX(-4px); opacity: 0.6; }
    100% { transform: translateX(0); opacity: 1; }
  }

  /* Enhanced pagination */
  .pagination {
    display: flex; align-items: center; justify-content: center;
    gap: var(--sp-2); padding: var(--sp-5) 0 var(--sp-3); flex-wrap: wrap;
  }
  .page-btn {
    width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); background: var(--color-surface);
    border: 1px solid var(--color-border); color: var(--color-text-secondary);
    transition: all var(--duration-fast);
  }
  .page-btn svg { width: 14px; height: 14px; }
  .page-btn:hover:not(:disabled) {
    background: var(--color-surface-hover); border-color: var(--color-primary);
    color: var(--color-primary); transform: translateY(-1px);
  }
  .page-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  .page-numbers { display: flex; align-items: center; gap: 2px; }
  .page-num {
    min-width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500;
    color: var(--color-text-secondary); border: 1px solid transparent;
    transition: all var(--duration-fast); padding: 0 4px;
  }
  .page-num:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .page-num.active {
    background: var(--color-primary); color: white; font-weight: 700;
    border-color: var(--color-primary); box-shadow: 0 2px 8px rgba(124,92,252,.3);
  }
  .page-ellipsis {
    width: 28px; text-align: center; color: var(--color-text-muted);
    font-size: var(--text-sm); user-select: none;
  }

  .page-jump {
    display: flex; align-items: center; gap: 4px;
    margin-left: var(--sp-3); padding-left: var(--sp-3);
    border-left: 1px solid var(--color-border);
  }
  .jump-input {
    width: 64px; height: 36px; padding: 0 8px;
    border-radius: var(--radius-md); border: 1px solid var(--color-border);
    background: var(--color-bg-elevated); color: var(--color-text);
    font-size: var(--text-sm); text-align: center; outline: none;
    -moz-appearance: textfield;
  }
  .jump-input::-webkit-outer-spin-button,
  .jump-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
  .jump-input:focus { border-color: var(--color-primary); box-shadow: 0 0 0 2px var(--color-primary-soft); }
  .jump-input::placeholder { color: var(--color-text-muted); font-size: var(--text-xs); }
  .jump-btn {
    width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); background: var(--color-primary);
    color: white; transition: all var(--duration-fast);
  }
  .jump-btn svg { width: 14px; height: 14px; }
  .jump-btn:hover:not(:disabled) { background: var(--color-primary-hover); transform: translateY(-1px); }
  .jump-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  /* States */
  .state-card {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: var(--sp-12) var(--sp-6); text-align: center; gap: var(--sp-3);
    animation: fadeInScale var(--duration-slow) var(--ease-out);
  }
  .state-icon {
    width: 56px; height: 56px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-lg); background: var(--color-surface);
    border: 1px solid var(--color-border); color: var(--color-text-muted); margin-bottom: var(--sp-2);
  }
  .state-icon svg { width: 28px; height: 28px; }
  .state-card h3 { font-size: var(--text-md); font-weight: 600; }
  .state-detail { color: var(--color-text-muted); font-size: var(--text-sm); max-width: 340px; line-height: var(--lh-relaxed); }
  .error-card { color: var(--color-error); }
  .error-card .state-icon { color: var(--color-error); background: var(--color-error-soft); border-color: transparent; }
  .skeleton-list { display: flex; flex-direction: column; gap: var(--sp-2); }
  .skeleton-row { height: 72px; border-radius: var(--radius-md); animation-fill-mode: both; }
  @media (max-width: 768px) {
    .timeline { padding: var(--sp-4) var(--sp-3); gap: var(--sp-3); }
    .timeline-header h2 { font-size: var(--text-lg); }
    .page-jump { margin-left: var(--sp-2); padding-left: var(--sp-2); }
    .jump-input { width: 52px; height: 32px; font-size: var(--text-xs); }
    .page-btn, .page-num, .jump-btn { width: 32px; height: 32px; min-width: 32px; }
    .page-num { font-size: var(--text-xs); }
  }
  @media (max-width: 480px) {
    .timeline { padding: var(--sp-3) var(--sp-2); }
    .event-list { gap: var(--sp-1); }
    .page-jump { display: none; }
  }
</style>
