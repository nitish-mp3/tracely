<script>
  import Timeline from './views/Timeline.svelte';
  import TraceView from './views/TraceView.svelte';
  import Filters from './views/Filters.svelte';
  import Search from './views/Search.svelte';
  import Stats from './views/Stats.svelte';
  import SystemHealth from './views/SystemHealth.svelte';
  import KnxMonitor from './views/KnxMonitor.svelte';
  import ZigbeeMonitor from './views/ZigbeeMonitor.svelte';
  import Toast from './components/Toast.svelte';
  import { currentView, filtersOpen, healthStatus, addToast } from './stores/config.js';
  import { filters, hasActiveFilters, viewHistory } from './stores/events.js';
  import { getHealth } from './lib/api.js';
  import { onMount } from 'svelte';

  let searchQuery = '';
  let healthInterval;

  function handleNav(view) {
    // Push current view to history for back-navigation
    if ($currentView !== view) {
      $viewHistory = [...$viewHistory, $currentView];
    }
    $currentView = view;
  }

  function handleSearchSubmit() {
    if (searchQuery.trim()) {
      $filters = { ...$filters, q: searchQuery.trim() };
      handleNav('search');
    }
  }

  function handleSearchKeydown(e) {
    if (e.key === 'Enter') handleSearchSubmit();
    if (e.key === 'Escape') {
      searchQuery = '';
      e.target.blur();
    }
  }

  function handleSearchClear() {
    searchQuery = '';
    $filters = { ...$filters, q: '' };
  }

  function toggleFilters() {
    $filtersOpen = !$filtersOpen;
  }

  async function checkHealth() {
    try {
      $healthStatus = await getHealth();
    } catch { /* silent */ }
  }

  onMount(() => {
    checkHealth();
    healthInterval = setInterval(checkHealth, 30000);
    return () => clearInterval(healthInterval);
  });

  // Keep header search in sync with filters.q (bidirectional)
  $: if ($filters.q !== searchQuery && $filters.q === '') {
    // Filters were cleared externally — clear header input too
    searchQuery = '';
  }
  $: if ($currentView === 'search' && $filters.q && !searchQuery) {
    searchQuery = $filters.q;
  }

  $: statusLabel = $healthStatus?.ws_connected ? 'Connected' : 'Disconnected';
  $: eventsCount = $healthStatus?.events_count ?? null;
</script>

<div class="app-layout">
  <!-- Header -->
  <header class="app-header">
    <div class="header-left">
      <button class="logo-btn" on:click={() => handleNav('timeline')} aria-label="Go to timeline">
        <img src="./logo.png" alt="Tracely" class="logo-img" />
        <span class="logo-text">Tracely</span>
      </button>

      <div class="header-divider" />

      <nav class="nav-pills" aria-label="Main navigation">
        <button
          class="nav-pill"
          class:active={$currentView === 'timeline'}
          on:click={() => handleNav('timeline')}
        >
          <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M2 4h12M2 8h8M2 12h10" />
          </svg>
          Timeline
        </button>
        <button
          class="nav-pill"
          class:active={$currentView === 'search'}
          on:click={() => handleNav('search')}
        >
          <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" />
          </svg>
          Search
        </button>
        <button
          class="nav-pill"
          class:active={$currentView === 'stats'}
          on:click={() => handleNav('stats')}
        >
          <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <rect x="2" y="9" width="2.5" height="5" rx="0.5" /><rect x="6.75" y="5" width="2.5" height="9" rx="0.5" /><rect x="11.5" y="2" width="2.5" height="12" rx="0.5" />
          </svg>
          Stats
        </button>
        <button
          class="nav-pill"
          class:active={$currentView === 'health'}
          on:click={() => handleNav('health')}
        >
          <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M8 1v14M1 8h14" /><circle cx="8" cy="8" r="6" />
          </svg>
          Health
        </button>
        <button
          class="nav-pill knx-pill"
          class:active={$currentView === 'knx'}
          on:click={() => handleNav('knx')}
        >
          <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="3" cy="8" r="1.5" /><circle cx="8" cy="3" r="1.5" /><circle cx="13" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
            <path d="M4.5 8h7M8 4.5v7" />
          </svg>
          KNX
        </button>
        <button
          class="nav-pill zigbee-pill"
          class:active={$currentView === 'zigbee'}
          on:click={() => handleNav('zigbee')}
        >
          <svg class="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M2 4l6-2 6 2M2 8l6 2 6-2M2 12l6 2 6-2"/>
          </svg>
          Zigbee
        </button>
      </nav>
    </div>

    <div class="header-right">
      <div class="search-wrapper">
        <svg class="search-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" />
        </svg>
        <input
          type="search"
          class="search-input"
          bind:value={searchQuery}
          on:keydown={handleSearchKeydown}
          placeholder="Search events... (Enter)"
          aria-label="Quick search"
        />
        {#if searchQuery}
          <button class="search-clear" on:click={handleSearchClear} aria-label="Clear search">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6" /></svg>
          </button>
        {/if}
      </div>

      <button
        class="icon-btn"
        on:click={toggleFilters}
        aria-label="Toggle filters"
        class:active={$filtersOpen}
        class:has-filters={$hasActiveFilters}
      >
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M1.5 3h13M3.5 8h9M5.5 13h5" />
        </svg>
        {#if $hasActiveFilters}
          <span class="filter-badge" />
        {/if}
      </button>

      <div class="status-chip" class:connected={$healthStatus?.ws_connected}>
        <span class="status-dot-inner" />
        <span class="status-label">{statusLabel}</span>
        {#if eventsCount !== null}
          <span class="status-count">{eventsCount.toLocaleString()}</span>
        {/if}
      </div>
    </div>
  </header>

  <!-- Main content -->
  <main class="app-main">
    {#if $currentView === 'timeline'}
      <Timeline />
    {:else if $currentView === 'trace'}
      <TraceView />
    {:else if $currentView === 'search'}
      <Search />
    {:else if $currentView === 'stats'}
      <Stats />
    {:else if $currentView === 'health'}
      <SystemHealth />
    {:else if $currentView === 'knx'}
      <KnxMonitor />
    {:else if $currentView === 'zigbee'}
      <ZigbeeMonitor />
    {/if}
  </main>

  <!-- Drawers & overlays -->
  <Filters />
  <Toast />
</div>

<style>
  .app-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background: var(--color-bg);
  }

  /* ─── Header ─────────────────────────────────────── */

  .app-header {
    height: var(--header-h);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--sp-5);
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    flex-shrink: 0;
    gap: var(--sp-4);
    z-index: 50;
    backdrop-filter: blur(12px);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: var(--sp-4);
  }

  .logo-btn {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-1) var(--sp-2);
    border-radius: var(--radius-md);
    transition: all var(--duration-fast);
  }
  .logo-btn:hover {
    background: var(--color-surface-hover);
  }
  .logo-img {
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    object-fit: contain;
  }
  .logo-text {
    font-weight: 700;
    font-size: var(--text-md);
    color: var(--color-text);
    letter-spacing: -0.02em;
  }

  .header-divider {
    width: 1px;
    height: 24px;
    background: var(--color-border);
  }

  .nav-pills {
    display: flex;
    gap: 2px;
    padding: 3px;
    background: var(--color-bg-elevated);
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
  }
  .nav-pill {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 14px;
    border-radius: calc(var(--radius-md) - 2px);
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .nav-pill:hover {
    color: var(--color-text-secondary);
  }
  .nav-pill.active {
    color: var(--color-text);
    background: var(--color-surface);
    box-shadow: var(--shadow-xs);
  }
  .nav-pill.knx-pill.active {
    color: #818cf8;
  }
  .nav-pill.zigbee-pill.active {
    color: #22c55e;
  }
  .nav-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
  }

  /* Search */
  .search-wrapper {
    position: relative;
    display: flex;
    align-items: center;
  }
  .search-icon {
    position: absolute;
    left: 10px;
    width: 14px;
    height: 14px;
    color: var(--color-text-muted);
    pointer-events: none;
  }
  .search-input {
    width: 200px;
    padding: 7px 12px 7px 32px;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-bg-elevated);
    color: var(--color-text);
    font-size: var(--text-sm);
    outline: none;
    transition: all var(--duration-normal) var(--ease-out);
  }
  .search-input:focus {
    width: 280px;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px var(--color-primary-soft);
    background: var(--color-surface);
  }
  .search-input::placeholder {
    color: var(--color-text-muted);
  }
  .search-clear {
    position: absolute;
    right: 8px;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .search-clear svg { width: 10px; height: 10px; }
  .search-clear:hover {
    color: var(--color-text);
    background: var(--color-surface-hover);
  }

  /* Filter button */
  .icon-btn {
    position: relative;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-bg-elevated);
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .icon-btn svg {
    width: 16px;
    height: 16px;
  }
  .icon-btn:hover {
    color: var(--color-text);
    border-color: var(--color-border-hover);
    background: var(--color-surface-hover);
  }
  .icon-btn.active {
    color: var(--color-primary);
    border-color: var(--color-primary);
    background: var(--color-primary-soft);
  }
  .filter-badge {
    position: absolute;
    top: -2px;
    right: -2px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color-primary);
    border: 2px solid var(--color-surface);
  }

  /* Status chip */
  .status-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: var(--radius-full);
    background: var(--color-error-soft);
    border: 1px solid transparent;
    font-size: var(--text-xs);
    color: var(--color-error);
    font-weight: 500;
    transition: all var(--duration-normal);
  }
  .status-chip.connected {
    background: var(--color-success-soft);
    color: var(--color-success);
  }
  .status-dot-inner {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    animation: breathe 2s infinite;
  }
  .status-label {
    line-height: 1;
  }
  .status-count {
    opacity: 0.7;
    font-size: var(--text-2xs);
  }

  /* ─── Main ───────────────────────────────────────── */

  .app-main {
    flex: 1;
    overflow: hidden;
    display: flex;
  }

  /* ─── Responsive ─────────────────────────────────── */

  @media (max-width: 768px) {
    .search-wrapper {
      display: none;
    }
    .header-divider {
      display: none;
    }
    .status-label, .status-count {
      display: none;
    }
    .status-chip {
      padding: 6px;
      min-width: 0;
    }
    .nav-pill {
      padding: 6px 10px;
      font-size: var(--text-xs);
    }
  }

  @media (max-width: 480px) {
    .logo-text {
      display: none;
    }
    .nav-pills {
      padding: 2px;
    }
    .app-header {
      padding: 0 var(--sp-3);
      gap: var(--sp-2);
    }
  }
</style>
