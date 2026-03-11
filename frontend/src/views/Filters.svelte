<script>
  import { onMount } from 'svelte';
  import { getEntities } from '../lib/api.js';
  import { filters, hasActiveFilters } from '../stores/events.js';
  import { filtersOpen, availableEntities, filtersApplied } from '../stores/config.js';

  let entities = [];
  let domains = [];
  let areas = [];

  // Searchable dropdown state
  let entitySearch = '';
  let domainSearch = '';
  let areaSearch = '';
  let entityDropOpen = false;
  let domainDropOpen = false;
  let areaDropOpen = false;

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
      entity: '', domain: '', area: '', user_id: '',
      event_type: '', from: '', to: '', q: '',
      bookmarksOnly: false, inferredOnly: false,
    };
    entitySearch = ''; domainSearch = ''; areaSearch = '';
  }
  function handleClose() { $filtersOpen = false; }
  function handleApply() {
    $filtersApplied += 1;  // explicit signal for Timeline/Search to reload
    $filtersOpen = false;
  }

  // Searchable dropdown helpers
  function selectEntity(entityId) {
    $filters.entity = entityId;
    entitySearch = '';
    entityDropOpen = false;
  }
  function selectDomain(d) {
    $filters.domain = d;
    domainSearch = '';
    domainDropOpen = false;
  }
  function selectArea(a) {
    $filters.area = a;
    areaSearch = '';
    areaDropOpen = false;
  }
  function clearEntity() { $filters.entity = ''; }
  function clearDomain() { $filters.domain = ''; }
  function clearArea() { $filters.area = ''; }

  function handleDropdownBlur(closeFn) {
    // Delay so click on option registers first
    setTimeout(() => closeFn(), 150);
  }

  $: filteredEntities = entitySearch
    ? entities.filter(e => {
        const q = entitySearch.toLowerCase();
        return (e.entity_id && e.entity_id.toLowerCase().includes(q))
          || (e.friendly_name && e.friendly_name.toLowerCase().includes(q));
      }).slice(0, 50)
    : entities.slice(0, 50);

  $: filteredDomains = domainSearch
    ? domains.filter(d => d.toLowerCase().includes(domainSearch.toLowerCase()))
    : domains;

  $: filteredAreas = areaSearch
    ? areas.filter(a => a.toLowerCase().includes(areaSearch.toLowerCase()))
    : areas;

  $: activeCount = Object.entries($filters).filter(([k, v]) => {
    if (typeof v === 'boolean') return v;
    return v !== '';
  }).length;

  function friendlyName(entityId) {
    const ent = entities.find(e => e.entity_id === entityId);
    return ent?.friendly_name || entityId;
  }

  function toLocalISOString(date) {
    const offset = date.getTimezoneOffset();
    const local = new Date(date.getTime() - offset * 60000);
    return local.toISOString().slice(0, 16);
  }

  function setTimePreset(hours) {
    const now = new Date();
    const from = new Date(now.getTime() - hours * 3600000);
    $filters.from = toLocalISOString(from);
    $filters.to = toLocalISOString(now);
  }

  // Auto-default "to" to now when only "from" is set (on apply)
  $: if ($filters.from && !$filters.to) {
    // Keep "to" empty in UI but backend treats missing "to" as now
  }
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

        <!-- Entity searchable dropdown -->
        <div class="filter-group">
          <span class="label">Entity</span>
          {#if $filters.entity}
            <div class="selected-chip">
              <span class="chip-text">{friendlyName($filters.entity)}</span>
              <button class="chip-clear" on:click={clearEntity} aria-label="Clear entity">
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6" /></svg>
              </button>
            </div>
          {:else}
            <div class="searchable-select">
              <div class="ss-input-wrap">
                <svg class="ss-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="6" r="4"/><path d="M9 9l3 3"/></svg>
                <input
                  class="ss-input"
                  type="text"
                  bind:value={entitySearch}
                  on:focus={() => entityDropOpen = true}
                  on:blur={() => handleDropdownBlur(() => entityDropOpen = false)}
                  placeholder="Search entities…"
                  aria-label="Search entities"
                />
                {#if entities.length > 0}
                  <span class="ss-count">{entities.length}</span>
                {/if}
              </div>
              {#if entityDropOpen}
                <ul class="ss-dropdown">
                  {#if filteredEntities.length === 0}
                    <li class="ss-empty">No matches</li>
                  {:else}
                    {#each filteredEntities as ent}
                      <li>
                        <button class="ss-option" on:mousedown|preventDefault={() => selectEntity(ent.entity_id)}>
                          <span class="ss-opt-name">{ent.friendly_name || ent.entity_id}</span>
                          <span class="ss-opt-id">{ent.entity_id}</span>
                        </button>
                      </li>
                    {/each}
                    {#if entitySearch && filteredEntities.length >= 50}
                      <li class="ss-more">Keep typing to narrow results…</li>
                    {/if}
                  {/if}
                </ul>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Domain searchable dropdown -->
        <div class="filter-group">
          <span class="label">Domain</span>
          {#if $filters.domain}
            <div class="selected-chip domain-chip">
              <span class="chip-text">{$filters.domain}</span>
              <button class="chip-clear" on:click={clearDomain} aria-label="Clear domain">
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6" /></svg>
              </button>
            </div>
          {:else}
            <div class="searchable-select">
              <div class="ss-input-wrap">
                <svg class="ss-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="6" r="4"/><path d="M9 9l3 3"/></svg>
                <input
                  class="ss-input"
                  type="text"
                  bind:value={domainSearch}
                  on:focus={() => domainDropOpen = true}
                  on:blur={() => handleDropdownBlur(() => domainDropOpen = false)}
                  placeholder="Search domains…"
                  aria-label="Search domains"
                />
                {#if domains.length > 0}
                  <span class="ss-count">{domains.length}</span>
                {/if}
              </div>
              {#if domainDropOpen}
                <ul class="ss-dropdown">
                  {#if filteredDomains.length === 0}
                    <li class="ss-empty">No matches</li>
                  {:else}
                    {#each filteredDomains as d}
                      <li>
                        <button class="ss-option" on:mousedown|preventDefault={() => selectDomain(d)}>
                          <span class="ss-opt-name">{d}</span>
                        </button>
                      </li>
                    {/each}
                  {/if}
                </ul>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Area searchable dropdown -->
        <div class="filter-group">
          <span class="label">Area</span>
          {#if $filters.area}
            <div class="selected-chip area-chip">
              <span class="chip-text">{$filters.area}</span>
              <button class="chip-clear" on:click={clearArea} aria-label="Clear area">
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6" /></svg>
              </button>
            </div>
          {:else}
            <div class="searchable-select">
              <div class="ss-input-wrap">
                <svg class="ss-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="6" r="4"/><path d="M9 9l3 3"/></svg>
                <input
                  class="ss-input"
                  type="text"
                  bind:value={areaSearch}
                  on:focus={() => areaDropOpen = true}
                  on:blur={() => handleDropdownBlur(() => areaDropOpen = false)}
                  placeholder="Search areas…"
                  aria-label="Search areas"
                />
                {#if areas.length > 0}
                  <span class="ss-count">{areas.length}</span>
                {/if}
              </div>
              {#if areaDropOpen}
                <ul class="ss-dropdown">
                  {#if filteredAreas.length === 0}
                    <li class="ss-empty">No matches</li>
                  {:else}
                    {#each filteredAreas as a}
                      <li>
                        <button class="ss-option" on:mousedown|preventDefault={() => selectArea(a)}>
                          <span class="ss-opt-name">{a}</span>
                        </button>
                      </li>
                    {/each}
                  {/if}
                </ul>
              {/if}
            </div>
          {/if}
        </div>
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
          <input class="input-field" type="text" bind:value={$filters.user_id} placeholder="Filter by user..." />
        </label>
      </div>

      <div class="section-divider" />

      <div class="section">
        <span class="section-title">Time</span>
        <div class="filter-group">
          <div class="time-presets">
            <button class="preset-btn" on:click={() => setTimePreset(1)}>Last 1h</button>
            <button class="preset-btn" on:click={() => setTimePreset(6)}>Last 6h</button>
            <button class="preset-btn" on:click={() => setTimePreset(24)}>Last 24h</button>
            <button class="preset-btn" on:click={() => setTimePreset(168)}>Last 7d</button>
            <button class="preset-btn" on:click={() => setTimePreset(720)}>Last 30d</button>
          </div>
          <div class="date-row">
            <div class="date-input-wrap">
              <span class="date-label">From</span>
              <input class="input-field" type="datetime-local" bind:value={$filters.from} aria-label="From date" />
            </div>
            <svg class="date-arrow" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 8h10M10 5l3 3-3 3" /></svg>
            <div class="date-input-wrap">
              <span class="date-label">To</span>
              <input class="input-field" type="datetime-local" bind:value={$filters.to} placeholder="Now" aria-label="To date" />
            </div>
          </div>
          {#if $filters.from && !$filters.to}
            <span class="time-hint">"To" defaults to now</span>
          {/if}
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
      <button class="btn btn-primary" on:click={handleApply}>Apply filters</button>
    </footer>
  </aside>
{/if}

<style>
  .overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.5);
    backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
    z-index: 100; animation: fadeIn var(--duration-fast) ease-out;
  }
  .filter-drawer {
    position: fixed; top: 0; right: 0; bottom: 0; width: 380px; max-width: 92vw;
    background: var(--color-bg); border-left: 1px solid var(--color-border);
    z-index: 101; display: flex; flex-direction: column;
    animation: slideInRight var(--duration-normal) var(--ease-out);
    box-shadow: var(--shadow-lg);
  }
  .drawer-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--sp-4) var(--sp-5); border-bottom: 1px solid var(--color-border);
    background: var(--color-surface); flex-shrink: 0;
  }
  .header-left { display: flex; align-items: center; gap: var(--sp-2); }
  .header-icon { width: 18px; height: 18px; color: var(--color-primary); }
  .drawer-header h3 { font-size: var(--text-lg); font-weight: 700; letter-spacing: -0.02em; }
  .active-badge {
    padding: 1px 7px; border-radius: var(--radius-full);
    background: var(--color-primary); color: white;
    font-size: var(--text-2xs); font-weight: 600; min-width: 18px; text-align: center;
  }
  .close-btn {
    width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); color: var(--color-text-muted); transition: all var(--duration-fast);
  }
  .close-btn svg { width: 14px; height: 14px; }
  .close-btn:hover { background: var(--color-surface-hover); color: var(--color-text); }

  .filter-body {
    flex: 1; overflow-y: auto; padding: var(--sp-4) var(--sp-5);
    display: flex; flex-direction: column; gap: 0;
  }
  .section { display: flex; flex-direction: column; gap: var(--sp-3); padding: var(--sp-3) 0; }
  .section-title {
    font-size: var(--text-2xs); font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--color-text-muted);
  }
  .section-divider { height: 1px; background: var(--color-border); }

  .filter-group { display: flex; flex-direction: column; gap: 6px; }
  .label { font-size: var(--text-xs); font-weight: 500; color: var(--color-text-secondary); }

  /* Searchable select */
  .searchable-select { position: relative; }
  .ss-input-wrap {
    display: flex; align-items: center; gap: 6px;
    padding: 0 10px; height: 38px;
    border-radius: var(--radius-md); border: 1px solid var(--color-border);
    background: var(--color-bg-elevated); transition: all var(--duration-fast);
  }
  .ss-input-wrap:focus-within {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px var(--color-primary-soft);
    background: var(--color-surface);
  }
  .ss-icon { width: 13px; height: 13px; color: var(--color-text-muted); flex-shrink: 0; }
  .ss-input {
    flex: 1; border: none; background: none; color: var(--color-text);
    font-size: var(--text-sm); outline: none; padding: 0; min-width: 0;
  }
  .ss-input::placeholder { color: var(--color-text-muted); }
  .ss-count {
    font-size: 10px; color: var(--color-text-muted); font-weight: 500;
    padding: 1px 6px; border-radius: var(--radius-full);
    background: var(--color-surface-hover); white-space: nowrap;
  }
  .ss-dropdown {
    position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
    max-height: 240px; overflow-y: auto; margin-top: 4px;
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: var(--radius-md); box-shadow: var(--shadow-lg);
    list-style: none; padding: 4px;
    animation: fadeIn var(--duration-fast) var(--ease-out);
  }
  .ss-option {
    display: flex; flex-direction: column; gap: 1px;
    width: 100%; text-align: left; padding: 8px 10px;
    border-radius: var(--radius-sm); transition: all var(--duration-fast);
    cursor: pointer;
  }
  .ss-option:hover { background: var(--color-surface-hover); }
  .ss-opt-name { font-size: var(--text-sm); font-weight: 500; color: var(--color-text); }
  .ss-opt-id { font-size: 10px; font-family: var(--font-mono); color: var(--color-text-muted); }
  .ss-empty, .ss-more {
    padding: 10px; text-align: center; font-size: var(--text-xs);
    color: var(--color-text-muted); font-style: italic;
  }

  /* Selected chip */
  .selected-chip {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 10px; border-radius: var(--radius-md);
    background: var(--color-primary-soft); border: 1px solid rgba(124,92,252,.2);
    font-size: var(--text-sm); color: var(--color-primary); font-weight: 500;
  }
  .selected-chip.domain-chip { background: var(--color-info-soft); border-color: rgba(56,189,248,.2); color: var(--color-info); }
  .selected-chip.area-chip { background: var(--color-warning-soft); border-color: rgba(251,191,36,.2); color: var(--color-warning); }
  .chip-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip-clear {
    flex-shrink: 0; width: 18px; height: 18px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 50%; transition: all var(--duration-fast);
    opacity: 0.6;
  }
  .chip-clear svg { width: 10px; height: 10px; }
  .chip-clear:hover { opacity: 1; background: rgba(255,255,255,.1); }

  /* Standard fields */
  .select-wrap { position: relative; }
  .select-field {
    width: 100%; padding: 8px 12px; border-radius: var(--radius-md);
    border: 1px solid var(--color-border); background: var(--color-bg-elevated);
    color: var(--color-text); font-size: var(--text-sm); outline: none;
    appearance: none; -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 12 12' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M3 4.5l3 3 3-3' stroke='%236b7280' stroke-width='1.5'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 10px center; background-size: 12px;
    padding-right: 30px;
  }
  .select-field:focus { border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--color-primary-soft); }
  .input-field {
    width: 100%; padding: 8px 12px; border-radius: var(--radius-md);
    border: 1px solid var(--color-border); background: var(--color-bg-elevated);
    color: var(--color-text); font-size: var(--text-sm); outline: none;
  }
  .input-field:focus { border-color: var(--color-primary); box-shadow: 0 0 0 3px var(--color-primary-soft); }
  .input-field::placeholder { color: var(--color-text-muted); }

  .date-row { display: flex; align-items: center; gap: var(--sp-2); }
  .date-input-wrap { flex: 1; display: flex; flex-direction: column; gap: 3px; }
  .date-label { font-size: var(--text-2xs); color: var(--color-text-muted); font-weight: 500; }
  .date-arrow { width: 16px; height: 16px; color: var(--color-text-muted); flex-shrink: 0; margin-top: 14px; }

  .toggle-row {
    display: flex; align-items: center; gap: var(--sp-3);
    padding: var(--sp-1) 0; cursor: pointer;
  }
  .toggle-track {
    position: relative; width: 38px; height: 20px;
    background: var(--color-surface-active); border-radius: var(--radius-full);
    transition: background var(--duration-fast);
  }
  .toggle-track.active { background: var(--color-primary); }
  .toggle-track input { position: absolute; opacity: 0; width: 0; height: 0; }
  .toggle-thumb {
    position: absolute; top: 2px; left: 2px; width: 16px; height: 16px;
    border-radius: 50%; background: white; transition: transform var(--duration-fast);
    box-shadow: 0 1px 2px rgba(0,0,0,.2);
  }
  .toggle-track.active .toggle-thumb { transform: translateX(18px); }
  .toggle-label { font-size: var(--text-sm); color: var(--color-text-secondary); }

  .drawer-footer {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--sp-4) var(--sp-5); border-top: 1px solid var(--color-border);
    background: var(--color-surface); flex-shrink: 0; gap: var(--sp-3);
  }

  @media (max-width: 480px) {
    .filter-drawer { width: 100%; max-width: 100%; }
    .date-row { flex-direction: column; }
    .date-arrow { display: none; }
  }

  .time-presets {
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: var(--sp-2);
  }
  .preset-btn {
    padding: 4px 12px; border-radius: var(--radius-full);
    font-size: var(--text-2xs); font-weight: 600;
    background: var(--color-surface-hover); color: var(--color-text-secondary);
    border: 1px solid var(--color-border); transition: all var(--duration-fast);
  }
  .preset-btn:hover {
    background: var(--color-primary-soft); color: var(--color-primary);
    border-color: var(--color-primary);
  }
  .time-hint {
    font-size: var(--text-2xs); color: var(--color-text-muted);
    font-style: italic; margin-top: 2px;
  }
</style>
