<script>
  import { onMount } from 'svelte';
  import EventNode from '../components/EventNode.svelte';
  import EntityHistory from '../components/EntityHistory.svelte';
  import { searchEvents } from '../lib/api.js';
  import { selectedEventId, filters, selectedEntityTag, selectedDomainTag } from '../stores/events.js';
  import { currentView } from '../stores/config.js';

  let query = '';
  let results = [];
  let total = 0;
  let searching = false;
  let searched = false;
  let loadingMore = false;
  let offset = 0;
  const LIMIT = 50;

  async function handleSearch(append = false) {
    if (!query.trim()) return;
    if (!append) {
      searching = true;
      searched = true;
      offset = 0;
      results = [];
    } else {
      loadingMore = true;
    }
    try {
      const data = await searchEvents(query.trim(), LIMIT, offset);
      const items = data.items || [];
      if (append) {
        results = [...results, ...items];
      } else {
        results = items;
      }
      total = data.total || results.length;
      offset = results.length;
    } catch {
      if (!append) { results = []; total = 0; }
    } finally {
      searching = false;
      loadingMore = false;
    }
  }

  function handleLoadMore() {
    if (loadingMore || results.length >= total) return;
    handleSearch(true);
  }

  function handleKeydown(e) {
    if (e.key === 'Enter') handleSearch();
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

  function handleClear() {
    query = '';
    results = [];
    total = 0;
    searched = false;
    $filters = { ...$filters, q: '' };
  }

  // Sync with header search bar on mount
  onMount(() => {
    if ($filters.q && !query) {
      query = $filters.q;
      handleSearch();
    }
  });

  $: hasMore = results.length < total;
</script>

<section class="search-view" aria-label="Search">
  <div class="search-header">
    <div class="search-input-wrap">
      <svg class="search-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" /></svg>
      <input
        type="search"
        class="search-input"
        bind:value={query}
        on:keydown={handleKeydown}
        placeholder="Search events by name, entity, or payload..."
        aria-label="Search events"
      />
      {#if query}
        <button class="clear-btn" on:click={handleClear} aria-label="Clear search">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
        </button>
      {/if}
    </div>
    <button class="btn btn-primary search-btn" on:click={handleSearch} disabled={searching || !query.trim()}>
      {#if searching}
        <span class="spinner" />
        Searching...
      {:else}
        Search
      {/if}
    </button>
  </div>

  {#if searching}
    <div class="skeleton-list">
      {#each Array(5) as _, i}
        <div class="skeleton" style="height: 56px; animation-delay: {i * 60}ms;" />
      {/each}
    </div>
  {:else if searched && results.length === 0}
    <div class="state-card">
      <div class="state-icon empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="11" cy="11" r="7" /><path d="M16 16l4 4" /><path d="M8 11h6" />
        </svg>
      </div>
      <h3>No results found</h3>
      <p class="state-detail">No events matching "<strong>{query}</strong>"</p>
      <p class="state-hint">Try a different term, entity_id, or keyword from a payload.</p>
    </div>
  {:else if results.length > 0}
    <div class="results-header">
      <span class="result-count">{total} result{total !== 1 ? 's' : ''} for "<strong>{query}</strong>"</span>
    </div>
    <ul class="result-list">
      {#each results as event, i (event.id)}
        <li style="animation-delay: {Math.min(i * 30, 300)}ms;">
          <EventNode
            {event}
            on:click={() => handleEventClick(event)}
            on:tagclick={(e) => handleEntityTagClick(e.detail)}
            on:domainclick={(e) => handleDomainTagClick(e.detail)}
          />
        </li>
      {/each}
    </ul>

    {#if hasMore}
      <div class="load-more-wrap">
        <button class="btn btn-secondary load-more-btn" on:click={handleLoadMore} disabled={loadingMore}>
          {#if loadingMore}
            <span class="spinner" /> Loading…
          {:else}
            Load more ({total - results.length} remaining)
          {/if}
        </button>
      </div>
    {:else if results.length > 0}
      <div class="end-indicator">All {total} results shown</div>
    {/if}
  {:else}
    <div class="state-card">
      <div class="state-icon initial-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="11" cy="11" r="7" /><path d="M16 16l4 4" />
        </svg>
      </div>
      <h3>Search events</h3>
      <p class="state-detail">Full-text search across all captured events.</p>
      <p class="state-hint">Search by entity name, friendly name, or any text in the payload.</p>
    </div>
  {/if}
</section>

{#if $selectedEntityTag}
  <EntityHistory entityId={$selectedEntityTag} on:close={() => $selectedEntityTag = null} on:eventclick={(e) => handleEventClick(e.detail)} />
{/if}

<style>
  .search-view {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
    padding: var(--sp-5) var(--sp-6);
    overflow-y: auto;
    animation: fadeIn var(--duration-normal) var(--ease-out);
  }

  .search-header {
    display: flex;
    gap: var(--sp-3);
  }
  .search-input-wrap {
    flex: 1;
    position: relative;
    display: flex;
    align-items: center;
  }
  .search-icon {
    position: absolute;
    left: 14px;
    width: 16px;
    height: 16px;
    color: var(--color-text-muted);
    pointer-events: none;
  }
  .search-input {
    width: 100%;
    padding: 10px 38px 10px 40px;
    border-radius: var(--radius-lg);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    transition: all var(--duration-fast);
    outline: none;
  }
  .search-input:focus {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px var(--color-primary-soft);
  }
  .search-input::placeholder {
    color: var(--color-text-muted);
  }
  .clear-btn {
    position: absolute;
    right: 10px;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .clear-btn svg { width: 12px; height: 12px; }
  .clear-btn:hover {
    color: var(--color-text);
    background: var(--color-surface-hover);
  }
  .search-btn {
    white-space: nowrap;
    min-width: 100px;
  }
  .search-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .results-header {
    display: flex;
    align-items: center;
    padding: 0 var(--sp-1);
  }
  .result-count {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
  }
  .result-count strong {
    color: var(--color-text);
  }

  .result-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
  }
  .result-list li {
    animation: fadeInScale var(--duration-normal) var(--ease-out) both;
  }

  /* State cards */
  .state-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--sp-12) var(--sp-6);
    text-align: center;
    gap: var(--sp-3);
    animation: fadeInScale var(--duration-slow) var(--ease-out);
  }
  .state-icon {
    width: 64px;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-lg);
    margin-bottom: var(--sp-2);
  }
  .state-icon svg {
    width: 30px;
    height: 30px;
  }
  .initial-icon {
    color: var(--color-primary);
    background: var(--color-primary-soft);
  }
  .empty-icon {
    color: var(--color-text-muted);
    background: var(--color-surface-hover);
  }
  .state-card h3 {
    font-size: var(--text-md);
    font-weight: 600;
  }
  .state-detail {
    color: var(--color-text-secondary);
    font-size: var(--text-sm);
  }
  .state-detail strong {
    color: var(--color-text);
  }
  .state-hint {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    max-width: 340px;
  }

  .skeleton-list {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .skeleton-list .skeleton {
    border-radius: var(--radius-md);
    animation-fill-mode: both;
  }

  .load-more-wrap {
    display: flex; justify-content: center; padding: var(--sp-3) 0;
  }
  .load-more-btn {
    display: inline-flex; align-items: center; gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-5); font-size: var(--text-sm);
  }
  .end-indicator {
    text-align: center; padding: var(--sp-3) 0; color: var(--color-text-muted);
    font-size: var(--text-xs); opacity: 0.7;
  }
</style>
