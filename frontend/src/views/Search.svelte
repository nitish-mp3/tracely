<script>
  import { onMount } from 'svelte';
  import EventNode from '../components/EventNode.svelte';
  import EntityHistory from '../components/EntityHistory.svelte';
  import { searchEvents } from '../lib/api.js';
  import { selectedEventId, filters, selectedEntityTag, selectedDomainTag } from '../stores/events.js';
  import { currentView, filtersApplied } from '../stores/config.js';

  let query = '';
  let results = [];
  let total = 0;
  let searching = false;
  let searched = false;
  let loadingMore = false;
  let offset = 0;
  const LIMIT = 50;

  function _buildExtraParams() {
    const p = {};
    if ($filters.entity) p.entity = $filters.entity;
    if ($filters.domain) p.domain = $filters.domain;
    if ($filters.from)   p['from'] = $filters.from;
    if ($filters.to)     p['to'] = $filters.to;
    return p;
  }

  async function handleSearch(append = false) {
    const q = query.trim();
    if (!q) return;
    if (!append) {
      searching = true;
      searched = true;
      offset = 0;
      results = [];
    } else {
      loadingMore = true;
    }
    try {
      const data = await searchEvents(q, LIMIT, offset, _buildExtraParams());
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

  function handleEntityTagClick(entityId) { $selectedEntityTag = entityId; }
  function handleDomainTagClick(domain)   { $selectedDomainTag = domain;   }

  function handleClear() {
    query = '';
    results = [];
    total = 0;
    searched = false;
    $filters = { ...$filters, q: '' };
  }

  // Sync with header search bar on mount
  onMount(() => {
    if ($filters.q) {
      query = $filters.q;
      handleSearch();
    }
  });

  // Re-run search when user explicitly clicks "Apply filters"
  $: if (searched && $filtersApplied) {
    handleSearch(false);
  }

  // Re-run search when filter context changes (entity / domain / time window)
  let prevFilterCtx = '';
  $: {
    const ctx = JSON.stringify({
      entity: $filters.entity,
      domain: $filters.domain,
      from: $filters.from,
      to: $filters.to,
    });
    if (searched && ctx !== prevFilterCtx) {
      prevFilterCtx = ctx;
      handleSearch(false);
    } else {
      prevFilterCtx = ctx;
    }
  }

  $: hasMore = results.length < total;

  // Active filter chips for display
  $: activeFilterChips = [
    $filters.entity  && { key: 'entity',  label: $filters.entity },
    $filters.domain  && { key: 'domain',  label: $filters.domain },
    ($filters.from || $filters.to) && {
      key: 'time',
      label: $filters.from && $filters.to
        ? `${fmtDate($filters.from)} → ${fmtDate($filters.to)}`
        : $filters.from ? `From ${fmtDate($filters.from)}`
        : `Until ${fmtDate($filters.to)}`,
    },
  ].filter(Boolean);

  function fmtDate(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return iso; }
  }

  function clearFilterChip(key) {
    if (key === 'entity') $filters = { ...$filters, entity: '' };
    if (key === 'domain') $filters = { ...$filters, domain: '' };
    if (key === 'time')   $filters = { ...$filters, from: '', to: '' };
  }
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
        placeholder="Search by name, entity, or payload… (Enter)"
        aria-label="Search events"
      />
      {#if query}
        <button class="clear-btn" on:click={handleClear} aria-label="Clear search">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
        </button>
      {/if}
    </div>
    <button class="btn btn-primary search-btn" on:click={() => handleSearch()} disabled={searching || !query.trim()}>
      {#if searching}
        <span class="spinner" /> Searching…
      {:else}
        Search
      {/if}
    </button>
  </div>

  {#if activeFilterChips.length > 0}
    <div class="active-filters" aria-label="Active filters">
      <span class="af-label">Filters:</span>
      {#each activeFilterChips as chip (chip.key)}
        <span class="af-chip">
          {chip.label}
          <button class="af-remove" on:click={() => clearFilterChip(chip.key)} aria-label="Remove {chip.key} filter">
            <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l6 6M8 2l-6 6" /></svg>
          </button>
        </span>
      {/each}
    </div>
  {/if}

  {#if searching}
    <div class="skeleton-list">
      {#each Array(5) as _, i}
        <div class="skeleton" style="height: 56px; animation-delay: {i * 60}ms;" />
      {/each}
    </div>
  {:else if searched && results.length === 0}
    <div class="state-card">
      <div class="state-icon empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="11" cy="11" r="7" /><path d="M16 16l4 4" /><path d="M8 11h6" /></svg>
      </div>
      <h3>No results found</h3>
      <p class="state-detail">No events match "<strong>{query}</strong>"</p>
      <p class="state-hint">Try a broader term or remove active filters.</p>
    </div>
  {:else if results.length > 0}
    <div class="results-header">
      <span class="result-count">{total.toLocaleString()} result{total !== 1 ? 's' : ''} for "<strong>{query}</strong>"</span>
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
            Load {Math.min(LIMIT, total - results.length)} more of {total - results.length} remaining
          {/if}
        </button>
      </div>
    {:else if results.length > 0}
      <div class="end-indicator">All {total} results shown</div>
    {/if}
  {:else}
    <div class="state-card">
      <div class="state-icon initial-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="11" cy="11" r="7" /><path d="M16 16l4 4" /></svg>
      </div>
      <h3>Search events</h3>
      <p class="state-detail">Full-text search across all captured events.</p>
      <p class="state-hint">Use the Filters panel to narrow by entity, domain, or time window before searching.</p>
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
  .search-input::placeholder { color: var(--color-text-muted); }
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
  .clear-btn:hover { color: var(--color-text); background: var(--color-surface-hover); }
  .search-btn {
    white-space: nowrap;
    min-width: 100px;
  }
  .search-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Active filter chips */
  .active-filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-1);
    animation: fadeIn var(--duration-fast) var(--ease-out);
  }
  .af-label {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .af-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px 3px 10px;
    background: var(--color-primary-soft);
    color: var(--color-primary);
    border-radius: 999px;
    font-size: var(--text-xs);
    font-weight: 500;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .af-remove {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    opacity: 0.7;
    transition: opacity var(--duration-fast);
    color: inherit;
  }
  .af-remove:hover { opacity: 1; }
  .af-remove svg { width: 8px; height: 8px; }

  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .results-header {
    display: flex;
    align-items: center;
    padding: 0 var(--sp-1);
  }
  .result-count { font-size: var(--text-sm); color: var(--color-text-muted); }
  .result-count strong { color: var(--color-text); }

  .result-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
  }
  .result-list li { animation: fadeInScale var(--duration-normal) var(--ease-out) both; }

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
  .state-icon svg { width: 30px; height: 30px; }
  .initial-icon { color: var(--color-primary); background: var(--color-primary-soft); }
  .empty-icon { color: var(--color-text-muted); background: var(--color-surface-hover); }
  .state-card h3 { font-size: var(--text-md); font-weight: 600; }
  .state-detail { color: var(--color-text-secondary); font-size: var(--text-sm); }
  .state-detail strong { color: var(--color-text); }
  .state-hint { color: var(--color-text-muted); font-size: var(--text-xs); max-width: 340px; }

  .skeleton-list { display: flex; flex-direction: column; gap: var(--sp-2); }
  .skeleton-list .skeleton { border-radius: var(--radius-md); animation-fill-mode: both; }

  .load-more-wrap { display: flex; justify-content: center; padding: var(--sp-3) 0; }
  .load-more-btn { display: inline-flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-5); font-size: var(--text-sm); }
  .end-indicator { text-align: center; padding: var(--sp-3) 0; color: var(--color-text-muted); font-size: var(--text-xs); opacity: 0.7; }

  @media (max-width: 768px) {
    .search-view { padding: var(--sp-4) var(--sp-3); gap: var(--sp-3); }
    .search-header { gap: var(--sp-2); }
    .search-btn { min-width: 80px; font-size: var(--text-sm); padding: 8px 12px; }
    .search-input { font-size: var(--text-sm); padding: 8px 34px 8px 36px; }
    .af-chip { max-width: 160px; }
    .state-card { padding: var(--sp-8) var(--sp-4); }
    .state-icon { width: 52px; height: 52px; }
    .state-icon svg { width: 24px; height: 24px; }
  }

  @media (max-width: 480px) {
    .search-view { padding: var(--sp-3) var(--sp-2); gap: var(--sp-2); }
    .search-header { flex-direction: column; }
    .search-btn { width: 100%; min-width: unset; }
    .af-chip { max-width: 140px; font-size: var(--text-2xs); }
    .state-hint { max-width: 260px; }
    .state-card { padding: var(--sp-6) var(--sp-3); }
    .load-more-btn { width: 100%; justify-content: center; }
  }
</style>
