<script>
  import { onMount } from 'svelte';
  import { getEntities } from '../lib/api.js';
  import { filters, hasActiveFilters } from '../stores/events.js';
  import { filtersOpen, availableEntities } from '../stores/config.js';

  let entities = [];
  let domains = [];
  let areas = [];

  onMount(async () => {
    try {
      const data = await getEntities();
      entities = data.items || [];
      $availableEntities = entities;
      domains = [...new Set(entities.map((e) => e.domain).filter(Boolean))].sort();
      areas = [...new Set(entities.map((e) => e.area).filter(Boolean))].sort();
    } catch { /* fail silently */ }
  });

  function handleClear() {
    $filters = {
      entity: '',
      domain: '',
      area: '',
      user_id: '',
      event_type: '',
      from: '',
      to: '',
      q: '',
      bookmarksOnly: false,
      inferredOnly: false,
    };
  }

  function handleClose() {
    $filtersOpen = false;
  }

  $: activeCount = Object.entries($filters).filter(([k, v]) => {
    if (typeof v === 'boolean') return v;
    return v !== '';
  }).length;
</script>

{#if $filtersOpen}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="overlay" on:click={handleClose} role="presentation" />

  <aside class="filter-drawer" role="dialog" aria-label="Filters">
    <header class="drawer-header">
      <div class="header-left">
        <svg class="header-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 3h12M4 8h8M6 13h4" /></svg>
        <h3>Filters</h3>
        {#if activeCount > 0}
          <span class="active-badge">{activeCount}</span>
        {/if}
      </div>
      <button class="close-btn" on:click={handleClose} aria-label="Close filters">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
      </button>
    </header>

    <div class="filter-body">
      <div class="section">
        <span class="section-title">Source</span>

        <label class="filter-group">
          <span class="label">Entity</span>
          <div class="select-wrap">
            <select class="select-field" bind:value={$filters.entity}>
              <option value="">All entities</option>
              {#each entities as ent}
                <option value={ent.entity_id}>{ent.friendly_name || ent.entity_id}</option>
              {/each}
            </select>
          </div>
        </label>

        <label class="filter-group">
          <span class="label">Domain</span>
          <div class="select-wrap">
            <select class="select-field" bind:value={$filters.domain}>
              <option value="">All domains</option>
              {#each domains as d}
                <option value={d}>{d}</option>
              {/each}
            </select>
          </div>
        </label>

        <label class="filter-group">
          <span class="label">Area</span>
          <div class="select-wrap">
            <select class="select-field" bind:value={$filters.area}>
              <option value="">All areas</option>
              {#each areas as a}
                <option value={a}>{a}</option>
              {/each}
            </select>
          </div>
        </label>
      </div>

      <div class="section-divider" />

      <div class="section">
        <span class="section-title">Event</span>

        <label class="filter-group">
          <span class="label">Event Type</span>
          <div class="select-wrap">
            <select class="select-field" bind:value={$filters.event_type}>
              <option value="">All types</option>
              <option value="state_changed">state_changed</option>
              <option value="call_service">call_service</option>
              <option value="automation_triggered">automation_triggered</option>
              <option value="script_started">script_started</option>
              <option value="script_finished">script_finished</option>
              <option value="logbook_entry">logbook_entry</option>
            </select>
          </div>
        </label>

        <label class="filter-group">
          <span class="label">User ID</span>
          <input
            class="input-field"
            type="text"
            bind:value={$filters.user_id}
            placeholder="Filter by user..."
          />
        </label>
      </div>

      <div class="section-divider" />

      <div class="section">
        <span class="section-title">Time</span>
        <div class="filter-group">
          <div class="date-row">
            <div class="date-input-wrap">
              <span class="date-label">From</span>
              <input class="input-field" type="datetime-local" bind:value={$filters.from} aria-label="From date" />
            </div>
            <svg class="date-arrow" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 8h10M10 5l3 3-3 3" /></svg>
            <div class="date-input-wrap">
              <span class="date-label">To</span>
              <input class="input-field" type="datetime-local" bind:value={$filters.to} aria-label="To date" />
            </div>
          </div>
        </div>
      </div>

      <div class="section-divider" />

      <div class="section">
        <span class="section-title">Display</span>

        <label class="toggle-row">
          <div class="toggle-track" class:active={$filters.inferredOnly}>
            <input type="checkbox" bind:checked={$filters.inferredOnly} />
            <span class="toggle-thumb" />
          </div>
          <span class="toggle-label">Inferred links only</span>
        </label>

        <label class="toggle-row">
          <div class="toggle-track" class:active={$filters.bookmarksOnly}>
            <input type="checkbox" bind:checked={$filters.bookmarksOnly} />
            <span class="toggle-thumb" />
          </div>
          <span class="toggle-label">Bookmarked events only</span>
        </label>
      </div>
    </div>

    <footer class="drawer-footer">
      <button class="btn btn-surface" on:click={handleClear}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 4h12M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M6 7v5M10 7v5" /></svg>
        Clear all
      </button>
      <button class="btn btn-primary" on:click={handleClose}>Apply filters</button>
    </footer>
  </aside>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    z-index: 100;
    animation: fadeIn var(--duration-fast) ease-out;
  }

  .filter-drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 360px;
    max-width: 92vw;
    background: var(--color-bg);
    border-left: 1px solid var(--color-border);
    z-index: 101;
    display: flex;
    flex-direction: column;
    animation: slideInRight var(--duration-normal) var(--ease-out);
    box-shadow: var(--shadow-lg);
  }

  .drawer-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--sp-4) var(--sp-5);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface);
    flex-shrink: 0;
  }
  .header-left {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .header-icon {
    width: 18px;
    height: 18px;
    color: var(--color-primary);
  }
  .drawer-header h3 {
    font-size: var(--text-lg);
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .active-badge {
    padding: 1px 7px;
    border-radius: var(--radius-full);
    background: var(--color-primary);
    color: white;
    font-size: var(--text-2xs);
    font-weight: 600;
    min-width: 18px;
    text-align: center;
  }
  .close-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md);
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .close-btn svg { width: 14px; height: 14px; }
  .close-btn:hover {
    background: var(--color-surface-hover);
    color: var(--color-text);
  }

  .filter-body {
    flex: 1;
    overflow-y: auto;
    padding: var(--sp-4) var(--sp-5);
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-3) 0;
  }
  .section-title {
    font-size: var(--text-2xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-text-muted);
  }
  .section-divider {
    height: 1px;
    background: var(--color-border);
    margin: 0;
  }

  .filter-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .label {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .date-row {
    display: flex;
    align-items: flex-end;
    gap: var(--sp-2);
  }
  .date-input-wrap {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .date-label {
    font-size: var(--text-2xs);
    font-weight: 500;
    color: var(--color-text-muted);
  }
  .date-arrow {
    width: 16px;
    height: 16px;
    color: var(--color-text-muted);
    flex-shrink: 0;
    margin-bottom: 10px;
  }

  /* Toggle switch */
  .toggle-row {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    cursor: pointer;
    padding: 4px 0;
  }
  .toggle-track {
    position: relative;
    width: 36px;
    height: 20px;
    border-radius: var(--radius-full);
    background: var(--color-surface-active);
    transition: background var(--duration-fast);
    flex-shrink: 0;
  }
  .toggle-track.active {
    background: var(--color-primary);
  }
  .toggle-track input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }
  .toggle-thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: white;
    transition: transform var(--duration-fast) var(--ease-out);
    pointer-events: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  }
  .toggle-track.active .toggle-thumb {
    transform: translateX(16px);
  }
  .toggle-label {
    font-size: var(--text-sm);
    color: var(--color-text-secondary);
  }

  .drawer-footer {
    padding: var(--sp-4) var(--sp-5);
    border-top: 1px solid var(--color-border);
    display: flex;
    gap: var(--sp-3);
    flex-shrink: 0;
    background: var(--color-surface);
  }
  .drawer-footer .btn {
    flex: 1;
    justify-content: center;
  }
  .drawer-footer .btn svg {
    width: 14px;
    height: 14px;
  }
</style>
