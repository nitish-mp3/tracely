<script>
  import { onMount, onDestroy } from 'svelte';
  import EventNode from '../components/EventNode.svelte';
  import EntityHistory from '../components/EntityHistory.svelte';
  import DomainHistory from '../components/DomainHistory.svelte';
  import { getEvents, subscribeEvents } from '../lib/api.js';
  import {
    events, pagination, filters, loading, error,
    selectedEventId, sseStatus, selectedEntityTag, selectedDomainTag,
  } from '../stores/events.js';
  import { currentView, filtersApplied } from '../stores/config.js';

  let unsubSSE = null;
  let liveCount = 0;
  let liveIndicator = false;
  let blinkTimer = null;
  let mounted = false;
  let loadingMore = false;
  let hasMore = true;
  let sentinel = null;
  let observer = null;

  async function loadEvents(append = false) {
    if (!append) {
      $loading = true;
      $error = null;
    } else {
      loadingMore = true;
    }
    try {
      const page = append ? $pagination.page : 1;
      const params = { page, limit: $pagination.limit };
      if ($filters.entity) params.entity = $filters.entity;
      if ($filters.domain) params.domain = $filters.domain;
      if ($filters.area) params.area = $filters.area;
      if ($filters.user_id) params.user_id = $filters.user_id;
      if ($filters.event_type) params.event_type = $filters.event_type;
      if ($filters.q) params.q = $filters.q;
      if ($filters.from) params.from = $filters.from;
      if ($filters.to) params.to = $filters.to;
      const data = await getEvents(params);
      const items = data.items || [];
      if (append) {
        $events = [...$events, ...items];
      } else {
        $events = items;
        $pagination = { ...$pagination, page: 1 };
      }
      $pagination = { ...$pagination, total: data.total };
      hasMore = $events.length < data.total;
    } catch (e) {
      $error = e.message;
    } finally {
      $loading = false;
      loadingMore = false;
    }
  }

  function loadNextPage() {
    if (loadingMore || !hasMore) return;
    $pagination = { ...$pagination, page: $pagination.page + 1 };
    loadEvents(true);
  }

  function handleEventClick(event) {
    $selectedEventId = event.id;
    $currentView = 'trace';
  }

  function handleEntityTagClick(entityId) {
    $selectedEntityTag = entityId;
  }

  function handleDomainTagClick(domain) {
    $selectedDomainTag = domain;
  }

  function flashLive() {
    liveIndicator = true;
    if (blinkTimer) clearTimeout(blinkTimer);
    blinkTimer = setTimeout(() => { liveIndicator = false; }, 600);
  }

  function setupObserver() {
    if (observer) observer.disconnect();
    if (!sentinel) return;
    observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !loadingMore && !$loading) {
        loadNextPage();
      }
    }, { rootMargin: '200px' });
    observer.observe(sentinel);
  }

  onMount(() => {
    mounted = true;
    loadEvents();
    unsubSSE = subscribeEvents(
      (event) => {
        liveCount++;
        flashLive();
        events.update((list) => [event, ...list]);
        pagination.update((p) => ({ ...p, total: p.total + 1 }));
      },
      (status) => { $sseStatus = status; }
    );
  });

  onDestroy(() => {
    if (unsubSSE) unsubSSE();
    if (blinkTimer) clearTimeout(blinkTimer);
    if (observer) observer.disconnect();
  });

  // Reload when user explicitly presses "Apply filters"
  $: if (mounted && $filtersApplied) {
    hasMore = true;
    loadEvents(false);
  }

  // Wire up IntersectionObserver when sentinel DOM element is bound
  $: if (sentinel) setupObserver();
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
      <button class="btn btn-primary" on:click={() => loadEvents(false)}>Try again</button>
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
          <EventNode
            {event}
            on:click={() => handleEventClick(event)}
            on:tagclick={(e) => handleEntityTagClick(e.detail)}
            on:domainclick={(e) => handleDomainTagClick(e.detail)}
          />
        </li>
      {/each}
    </ul>

    {#if loadingMore}
      <div class="load-more-indicator">
        <div class="spinner" />
        <span>Loading more…</span>
      </div>
    {/if}

    {#if hasMore}
      <div class="scroll-sentinel" bind:this={sentinel} />
    {:else if $events.length > 0}
      <div class="end-indicator">
        <span>All {$pagination.total.toLocaleString()} events loaded</span>
      </div>
    {/if}
  {/if}
</section>

{#if $selectedEntityTag}
  <EntityHistory entityId={$selectedEntityTag} on:close={() => $selectedEntityTag = null} on:eventclick={(e) => handleEventClick(e.detail)} />
{/if}

{#if $selectedDomainTag}
  <DomainHistory domain={$selectedDomainTag} on:close={() => $selectedDomainTag = null} on:eventclick={(e) => handleEventClick(e.detail)} />
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

  /* Infinite scroll */
  .scroll-sentinel { height: 1px; width: 100%; }
  .load-more-indicator {
    display: flex; align-items: center; justify-content: center; gap: var(--sp-2);
    padding: var(--sp-4) 0; color: var(--color-text-muted); font-size: var(--text-sm);
  }
  .spinner {
    width: 18px; height: 18px; border-radius: 50%;
    border: 2px solid var(--color-border); border-top-color: var(--color-primary);
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .end-indicator {
    text-align: center; padding: var(--sp-4) 0; color: var(--color-text-muted);
    font-size: var(--text-xs); opacity: 0.7;
  }

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
  }
  @media (max-width: 480px) {
    .timeline { padding: var(--sp-3) var(--sp-2); }
    .event-list { gap: var(--sp-1); }
  }
</style>
