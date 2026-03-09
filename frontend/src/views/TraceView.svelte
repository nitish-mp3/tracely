<script>
  import { onMount, tick } from 'svelte';
  import ConfidenceBadge from '../components/ConfidenceBadge.svelte';
  import DomainIcon from '../components/DomainIcon.svelte';
  import EntityHistory from '../components/EntityHistory.svelte';
  import { getEvent, bookmarkEvent } from '../lib/api.js';
  import {
    buildTree, flattenTree, getMaxDepth,
    getSubtreeSize, getDomainBreakdown, getTimeDelta,
    getBreadcrumbs, getCriticalPath, getTreeStats,
    formatDuration, formatDelta,
  } from '../lib/treeLayout.js';
  import { selectedEventId, treeData, selectedEntityTag } from '../stores/events.js';
  import { currentView, addToast } from '../stores/config.js';

  // ── State ──
  let treeNodes = [];
  let rootId = '';
  let treeDepth = 0;
  let currentEvent = null;
  let expandedNodes = new Set();
  let selectedNode = null;
  let loading = true;
  let errorMsg = null;

  // Analytics
  let treeRoots = [];
  let nodeMap = new Map();
  let stats = null;
  let criticalPath = new Set();
  let breadcrumbs = [];

  // In-tree search
  let searchQuery = '';
  let searchMatches = new Set();
  let showSearch = false;

  // View modes
  let showCriticalOnly = false;
  let showTimings = true;
  let showStats = true;
  let viewMode = 'list'; // 'list' | 'graph'

  // Graph pan/zoom state
  let graphContainer;
  let panX = 0, panY = 0, zoom = 1;
  let isPanning = false;
  let panStart = { x: 0, y: 0, panX: 0, panY: 0 };
  let lastPinchDist = 0;

  // Keyboard focus
  let focusedIdx = -1;
  let treeContainer;

  const DOMAIN_COLORS = {
    automation: 'var(--color-automation)', script: 'var(--color-automation)',
    scene: 'var(--color-automation)', light: 'var(--color-device)',
    switch: 'var(--color-device)', cover: 'var(--color-device)',
    fan: 'var(--color-device)', climate: 'var(--color-device)',
    media_player: 'var(--color-device)', person: 'var(--color-user)',
    device_tracker: 'var(--color-user)', homeassistant: 'var(--color-system)',
    persistent_notification: 'var(--color-system)', update: 'var(--color-system)',
  };

  function domainColor(domain) {
    return DOMAIN_COLORS[domain] || 'var(--color-device)';
  }

  async function loadTree() {
    if (!$selectedEventId) return;
    loading = true;
    errorMsg = null;
    try {
      const data = await getEvent($selectedEventId);
      if (data.error) throw new Error(data.error);
      currentEvent = data.event;
      rootId = data.root_id;
      treeDepth = data.tree_depth;
      const built = buildTree(data.tree || []);
      treeRoots = built.roots;
      nodeMap = built.nodeMap;
      treeNodes = flattenTree(treeRoots);
      expandedNodes = new Set(treeNodes.map(n => n.id));
      stats = getTreeStats(treeNodes, nodeMap);
      criticalPath = getCriticalPath(treeRoots);
      breadcrumbs = [];
      searchQuery = '';
      searchMatches = new Set();
      focusedIdx = -1;
      selectedNode = null;
      panX = 0; panY = 0; zoom = 1;
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }

  function handleBack() {
    $currentView = 'timeline';
    $selectedEventId = null;
  }

  function handleToggle(nodeId) {
    expandedNodes.has(nodeId) ? expandedNodes.delete(nodeId) : expandedNodes.add(nodeId);
    expandedNodes = expandedNodes;
  }

  function handleExpandAll() { expandedNodes = new Set(treeNodes.map(n => n.id)); }
  function handleCollapseAll() { expandedNodes = new Set(); }

  function handleNodeSelect(node) {
    if (selectedNode?.id === node.id) { selectedNode = null; breadcrumbs = []; }
    else { selectedNode = node; breadcrumbs = getBreadcrumbs(node.id, nodeMap); }
  }

  function handleEntityTagClick(entityId) {
    $selectedEntityTag = entityId;
  }

  async function handleBookmark() {
    if (!$selectedEventId) return;
    try { await bookmarkEvent($selectedEventId); addToast('Event bookmarked', 'success'); }
    catch { addToast('Failed to bookmark', 'error'); }
  }

  function handleExport() {
    const exportData = {
      root_id: rootId, tree_depth: treeDepth, stats,
      nodes: treeNodes.map(n => ({
        id: n.id, parent_id: n.parent_id, event_type: n.event_type,
        domain: n.domain, entity_id: n.entity_id, name: n.name,
        timestamp: n.timestamp, confidence: n.confidence, payload: n.payload,
      })),
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `tracely-tree-${rootId || 'export'}.json`; a.click();
    URL.revokeObjectURL(url);
    addToast('Tree exported', 'success');
  }

  function handleCopy(text, label) {
    navigator.clipboard.writeText(text).then(
      () => addToast(`${label} copied`, 'success'),
      () => addToast('Copy failed', 'error'),
    );
  }

  function formatTime(iso) { return iso ? new Date(iso).toLocaleString() : ''; }
  function formatTimeShort(iso) {
    return iso ? new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
  }

  function isVisible(node) {
    if (node.depth === 0) return true;
    let cur = node;
    while (cur.parent_id) {
      if (!expandedNodes.has(cur.parent_id)) return false;
      cur = nodeMap.get(cur.parent_id) || { parent_id: null };
    }
    return true;
  }

  // Search
  function handleSearch() {
    if (!searchQuery.trim()) { searchMatches = new Set(); return; }
    const q = searchQuery.toLowerCase();
    const matches = new Set();
    for (const n of treeNodes) {
      const text = `${n.name || ''} ${n.event_type || ''} ${n.entity_id || ''} ${n.domain || ''} ${n.area || ''}`.toLowerCase();
      if (text.includes(q)) matches.add(n.id);
    }
    searchMatches = matches;
    for (const id of matches) {
      let cur = nodeMap.get(id);
      while (cur?.parent_id) { expandedNodes.add(cur.parent_id); cur = nodeMap.get(cur.parent_id); }
    }
    expandedNodes = expandedNodes;
  }

  function toggleSearch() {
    showSearch = !showSearch;
    if (!showSearch) { searchQuery = ''; searchMatches = new Set(); }
  }

  // Keyboard
  function handleTreeKeydown(e) {
    const visible = treeNodes.filter(n => isVisible(n));
    if (!visible.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); focusedIdx = Math.min(focusedIdx + 1, visible.length - 1); handleNodeSelect(visible[focusedIdx]); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusedIdx = Math.max(focusedIdx - 1, 0); handleNodeSelect(visible[focusedIdx]); }
    else if (e.key === 'ArrowRight' && focusedIdx >= 0) { e.preventDefault(); expandedNodes.add(visible[focusedIdx].id); expandedNodes = expandedNodes; }
    else if (e.key === 'ArrowLeft' && focusedIdx >= 0) { e.preventDefault(); expandedNodes.delete(visible[focusedIdx].id); expandedNodes = expandedNodes; }
    else if (e.key === 'Enter' && focusedIdx >= 0) { e.preventDefault(); handleNodeSelect(visible[focusedIdx]); }
    else if (e.key === '/' && !showSearch) { e.preventDefault(); toggleSearch(); }
    else if (e.key === 'Escape') { if (showSearch) toggleSearch(); else if (selectedNode) { selectedNode = null; breadcrumbs = []; } }
  }

  // Helpers
  function getNodeDelta(node) { return getTimeDelta(node, nodeMap); }
  function getCollapsedCount(node) { return expandedNodes.has(node.id) ? 0 : getSubtreeSize(node) - 1; }

  function getStateChange(node) {
    if (node.event_type !== 'state_changed') return null;
    try {
      const p = typeof node.payload === 'string' ? JSON.parse(node.payload) : node.payload;
      const os = p?.old_state?.state ?? p?.old_state;
      const ns = p?.new_state?.state ?? p?.new_state;
      if (os !== undefined && ns !== undefined) return { from: String(os), to: String(ns) };
    } catch { /* ignore */ }
    return null;
  }

  function isOnState(s) { const v = String(s).toLowerCase(); return v === 'on' || v === 'true' || v === 'home' || v === 'playing' || v === 'open'; }
  function isOffState(s) { const v = String(s).toLowerCase(); return v === 'off' || v === 'false' || v === 'not_home' || v === 'idle' || v === 'closed' || v === 'unavailable'; }

  // ── Graph mode pan/zoom ──
  function handleGraphWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    zoom = Math.max(0.2, Math.min(3, zoom * delta));
  }

  function handleGraphMouseDown(e) {
    if (e.button !== 0) return;
    isPanning = true;
    panStart = { x: e.clientX, y: e.clientY, panX, panY };
  }

  function handleGraphMouseMove(e) {
    if (!isPanning) return;
    panX = panStart.panX + (e.clientX - panStart.x);
    panY = panStart.panY + (e.clientY - panStart.y);
  }

  function handleGraphMouseUp() { isPanning = false; }

  function handleGraphTouchStart(e) {
    if (e.touches.length === 1) {
      isPanning = true;
      panStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, panX, panY };
    } else if (e.touches.length === 2) {
      isPanning = false;
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      lastPinchDist = Math.hypot(dx, dy);
      panStart = {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
        panX, panY
      };
    }
  }
  function handleGraphTouchMove(e) {
    e.preventDefault();
    if (e.touches.length === 1 && isPanning) {
      panX = panStart.panX + (e.touches[0].clientX - panStart.x);
      panY = panStart.panY + (e.touches[0].clientY - panStart.y);
    } else if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const dist = Math.hypot(dx, dy);
      if (lastPinchDist > 0) {
        const scale = dist / lastPinchDist;
        zoom = Math.max(0.2, Math.min(3, zoom * scale));
      }
      lastPinchDist = dist;
      // Two-finger pan: track midpoint movement
      const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
      const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      panX = panStart.panX + (midX - panStart.x);
      panY = panStart.panY + (midY - panStart.y);
    }
  }
  function handleGraphTouchEnd() { isPanning = false; lastPinchDist = 0; }

  function resetView() { panX = 0; panY = 0; zoom = 1; }

  // Graph node positions (simple layered layout)
  function computeGraphLayout(roots) {
    const positions = new Map();
    let maxX = 0;
    const NODE_W = 220, NODE_H = 70, GAP_X = 40, GAP_Y = 90;
    let leafIdx = 0;

    function layoutNode(node, depth) {
      if (!node.children || node.children.length === 0) {
        const x = leafIdx * (NODE_W + GAP_X);
        const y = depth * (NODE_H + GAP_Y);
        positions.set(node.id, { x, y, w: NODE_W, h: NODE_H });
        leafIdx++;
        return x;
      }
      const childXs = node.children.map(c => layoutNode(c, depth + 1));
      const x = (Math.min(...childXs) + Math.max(...childXs)) / 2;
      const y = depth * (NODE_H + GAP_Y);
      positions.set(node.id, { x, y, w: NODE_W, h: NODE_H });
      if (x + NODE_W > maxX) maxX = x + NODE_W;
      return x;
    }

    for (const root of roots) layoutNode(root, 0);
    return { positions, maxX };
  }

  function getGraphEdges(roots, positions) {
    const edges = [];
    function walk(node) {
      const from = positions.get(node.id);
      if (!from) return;
      for (const child of node.children || []) {
        const to = positions.get(child.id);
        if (to) {
          edges.push({
            x1: from.x + from.w / 2, y1: from.y + from.h,
            x2: to.x + to.w / 2, y2: to.y,
            parentId: node.id, childId: child.id,
            isCritical: criticalPath.has(node.id) && criticalPath.has(child.id),
          });
        }
        walk(child);
      }
    }
    for (const root of roots) walk(root);
    return edges;
  }

  $: visibleNodes = treeNodes.filter(n => isVisible(n));
  $: domainEntries = stats ? Object.entries(stats.domainBreakdown).sort((a, b) => b[1] - a[1]) : [];
  $: domainTotal = stats?.totalNodes || 1;
  $: matchCount = searchMatches.size;
  $: graphLayout = viewMode === 'graph' ? computeGraphLayout(treeRoots) : null;
  $: graphEdges = viewMode === 'graph' && graphLayout ? getGraphEdges(treeRoots, graphLayout.positions) : [];

  $: if (searchQuery !== undefined) handleSearch();
  onMount(loadTree);
  $: if ($selectedEventId) loadTree();
</script>

<svelte:window on:keydown={handleTreeKeydown} />

<section class="trace-view" aria-label="Trace View">
  <!-- Top bar -->
  <header class="trace-bar">
    <div class="bar-left">
      <button class="back-btn" on:click={handleBack} aria-label="Back to timeline">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M10 3L5 8l5 5" /></svg>
        <span class="back-text">Back</span>
      </button>

      <div class="bar-title">
        <h2>Causal Trace</h2>
        {#if !loading && !errorMsg && stats}
          <div class="bar-chips">
            <span class="stat-chip">{stats.totalNodes} nodes</span>
            <span class="stat-chip">depth {treeDepth}</span>
            {#if stats.durationMs !== null}
              <span class="stat-chip">{formatDuration(stats.durationMs)}</span>
            {/if}
          </div>
        {/if}
      </div>
    </div>

    <div class="bar-actions">
      <!-- View mode toggle -->
      <div class="view-toggle">
        <button class="vt-btn" class:active={viewMode === 'list'} on:click={() => viewMode = 'list'} aria-label="List view" title="List view">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 4h12M2 8h8M2 12h10" /></svg>
        </button>
        <button class="vt-btn" class:active={viewMode === 'graph'} on:click={() => viewMode = 'graph'} aria-label="Graph view" title="Interactive graph">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="3" r="2"/><circle cx="4" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><path d="M8 5v3M6.5 9.5L5 10.5M9.5 9.5L11 10.5"/></svg>
        </button>
      </div>

      <button class="action-btn ghost" on:click={toggleSearch} aria-label="Search (/)">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4" /><path d="M10 10l4 4" /></svg>
      </button>
      <button class="action-btn ghost" class:active={showTimings} on:click={() => showTimings = !showTimings} aria-label="Toggle timings">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="6" /><path d="M8 4v4l3 2" /></svg>
      </button>
      <button class="action-btn ghost" class:active={showCriticalOnly} on:click={() => showCriticalOnly = !showCriticalOnly} aria-label="Critical path">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 14L8 2l6 12H2z" /></svg>
      </button>

      <div class="bar-divider hide-mobile" />
      <button class="action-btn ghost" on:click={handleExpandAll} aria-label="Expand all"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 6l5 5 5-5" /></svg></button>
      <button class="action-btn ghost" on:click={handleCollapseAll} aria-label="Collapse all"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 10l5-5 5 5" /></svg></button>

      <div class="bar-divider hide-mobile" />
      <button class="action-btn hide-mobile" on:click={handleBookmark} aria-label="Bookmark">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 2h8v12l-4-3-4 3V2z" /></svg>
        <span class="btn-label">Bookmark</span>
      </button>
      <button class="action-btn primary" on:click={handleExport} aria-label="Export">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 2v9M4 8l4 4 4-4M2 13h12" /></svg>
        <span class="btn-label">Export</span>
      </button>
    </div>
  </header>

  <!-- Search bar -->
  {#if showSearch}
    <div class="search-bar" role="search">
      <svg class="s-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6.5" cy="6.5" r="4" /><path d="M10 10l4 4" /></svg>
      <input class="s-input" type="text" bind:value={searchQuery} placeholder="Search nodes…" aria-label="Search" />
      {#if searchQuery}<span class="s-count">{matchCount} match{matchCount !== 1 ? 'es' : ''}</span>{/if}
      <button class="s-close" on:click={toggleSearch} aria-label="Close"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4l8 8M12 4l-8 8" /></svg></button>
    </div>
  {/if}

  {#if loading}
    <div class="loading-area">
      {#each Array(6) as _, i}
        <div class="skeleton skeleton-node" style="margin-left: {(i % 3) * 28}px; animation-delay: {i * 100}ms;" />
      {/each}
    </div>
  {:else if errorMsg}
    <div class="state-card error-card">
      <div class="state-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="10" /><path d="M15 9l-6 6M9 9l6 6" /></svg></div>
      <h3>Failed to load trace</h3>
      <p class="state-detail">{errorMsg}</p>
      <button class="btn btn-primary" on:click={loadTree}>Try again</button>
    </div>
  {:else}
    <!-- Stats dashboard -->
    {#if stats && showStats}
      <div class="stats-dashboard">
        <div class="stat-card"><span class="stat-value">{stats.totalNodes}</span><span class="stat-label">Events</span></div>
        <div class="stat-card"><span class="stat-value">{treeDepth}</span><span class="stat-label">Depth</span></div>
        <div class="stat-card"><span class="stat-value">{stats.domainCount}</span><span class="stat-label">Domains</span></div>
        <div class="stat-card"><span class="stat-value">{stats.entityCount}</span><span class="stat-label">Entities</span></div>
        <div class="stat-card"><span class="stat-value">{formatDuration(stats.durationMs)}</span><span class="stat-label">Duration</span></div>
        <div class="stat-card"><span class="stat-value verified-text">{stats.verifiedCount}</span><span class="stat-label">Verified</span></div>
        <div class="stat-card"><span class="stat-value inferred-text">{stats.inferredCount}</span><span class="stat-label">Inferred</span></div>
        {#if stats.topEntity}
          <div class="stat-card wide"><span class="stat-value mono-sm">{stats.topEntity.id}</span><span class="stat-label">Top Entity ({stats.topEntity.count}×)</span></div>
        {/if}
        {#if domainEntries.length > 0}
          <div class="domain-bar-card">
            <span class="stat-label">Domain Breakdown</span>
            <div class="domain-bar">
              {#each domainEntries as [domain, count]}
                <div class="domain-segment" style="flex: {count}; background: {domainColor(domain)};" title="{domain}: {count} ({Math.round(count / domainTotal * 100)}%)" />
              {/each}
            </div>
            <div class="domain-legend">
              {#each domainEntries as [domain, count]}
                <span class="legend-item"><span class="legend-dot" style="background: {domainColor(domain)};" />{domain} <span class="legend-count">{count}</span></span>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}

    <!-- Breadcrumb trail -->
    {#if breadcrumbs.length > 1}
      <nav class="breadcrumbs" aria-label="Node path">
        {#each breadcrumbs as crumb, i}
          {#if i > 0}<span class="crumb-sep">›</span>{/if}
          <button class="crumb" class:crumb-current={i === breadcrumbs.length - 1} on:click={() => handleNodeSelect(nodeMap.get(crumb.id))}>
            <DomainIcon domain={crumb.domain} /><span>{crumb.name}</span>
          </button>
        {/each}
      </nav>
    {/if}

    <div class="trace-body" class:has-inspector={selectedNode}>
      {#if viewMode === 'list'}
        <!-- LIST VIEW -->
        <div class="tree-panel" bind:this={treeContainer} tabindex="0" role="toolbar">
          <div class="tree-container" role="tree" aria-label="Causal tree">
            {#each visibleNodes as node, i (node.id)}
              {@const delta = showTimings ? getNodeDelta(node) : null}
              {@const collapsed = getCollapsedCount(node)}
              {@const stateChange = getStateChange(node)}
              {@const isOnCritical = criticalPath.has(node.id)}
              {@const isSearchHit = searchMatches.size > 0 && searchMatches.has(node.id)}
              {@const isDimmed = (showCriticalOnly && !isOnCritical) || (searchMatches.size > 0 && !isSearchHit)}

              {#if showTimings && delta !== null && node.depth > 0}
                <div class="delta-badge" style="margin-left: {node.depth * 24 + 14}px;">+{formatDelta(delta)}</div>
              {/if}

              <div
                class="tree-node"
                class:is-root={node.id === rootId}
                class:is-selected={selectedNode?.id === node.id}
                class:is-focused={focusedIdx === i}
                class:is-critical={isOnCritical}
                class:is-search-hit={isSearchHit}
                class:is-dimmed={isDimmed}
                style="--indent: {node.depth}; animation-delay: {Math.min(i * 15, 150)}ms;"
                role="treeitem"
                aria-selected={selectedNode?.id === node.id}
                aria-expanded={expandedNodes.has(node.id)}
              >
                {#if node.depth > 0}
                  <div class="tree-connector" style="width: {node.depth * 24}px;">
                    <div class="connector-line" class:critical-line={isOnCritical} />
                  </div>
                {/if}

                {#if node.children && node.children.length > 0}
                  <button class="toggle-btn" on:click|stopPropagation={() => handleToggle(node.id)} aria-label={expandedNodes.has(node.id) ? 'Collapse' : 'Expand'}>
                    <svg class="toggle-icon" class:expanded={expandedNodes.has(node.id)} viewBox="0 0 12 12" fill="currentColor"><path d="M4 3l5 3.5L4 10V3z" /></svg>
                    {#if collapsed > 0}<span class="collapse-badge">{collapsed}</span>{/if}
                  </button>
                {:else}
                  <span class="toggle-spacer"><span class="leaf-dot" /></span>
                {/if}

                <button class="node-body" on:click={() => handleNodeSelect(node)}>
                  <span class="node-icon" style="border-color: {domainColor(node.domain)};"><DomainIcon domain={node.domain} /></span>
                  <span class="node-content">
                    <span class="node-name">{node.name || node.event_type}</span>
                    {#if stateChange}
                      <span class="state-change">
                        <span class="sc-from" class:sc-on={isOnState(stateChange.from)} class:sc-off={isOffState(stateChange.from)}>{stateChange.from}</span>
                        <svg class="sc-arrow" viewBox="0 0 12 8" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 4h10M8 1l3 3-3 3" /></svg>
                        <span class="sc-to" class:sc-on={isOnState(stateChange.to)} class:sc-off={isOffState(stateChange.to)}>{stateChange.to}</span>
                      </span>
                    {/if}
                    {#if node.entity_id}
                      <button class="node-entity-tag" on:click|stopPropagation={() => handleEntityTagClick(node.entity_id)} title="View history">{node.entity_id}</button>
                    {/if}
                  </span>
                  <ConfidenceBadge confidence={node.confidence} />
                  <time class="node-time">{formatTimeShort(node.timestamp)}</time>
                </button>
              </div>
            {/each}
          </div>
        </div>

      {:else}
        <!-- GRAPH VIEW (interactive pan/zoom) -->
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <div
          class="graph-panel"
          bind:this={graphContainer}
          on:wheel={handleGraphWheel}
          on:mousedown={handleGraphMouseDown}
          on:mousemove={handleGraphMouseMove}
          on:mouseup={handleGraphMouseUp}
          on:mouseleave={handleGraphMouseUp}
          on:touchstart={handleGraphTouchStart}
          on:touchmove={handleGraphTouchMove}
          on:touchend={handleGraphTouchEnd}
          role="application"
          aria-label="Interactive causal graph"
        >
          <div class="graph-controls">
            <button class="gc-btn" on:click={() => zoom = Math.min(3, zoom * 1.2)} aria-label="Zoom in">+</button>
            <button class="gc-btn" on:click={() => zoom = Math.max(0.2, zoom * 0.8)} aria-label="Zoom out">−</button>
            <button class="gc-btn" on:click={resetView} aria-label="Reset view">⟲</button>
            <span class="gc-label">{Math.round(zoom * 100)}%</span>
          </div>

          <div class="graph-canvas" style="transform: translate({panX}px, {panY}px) scale({zoom}); cursor: {isPanning ? 'grabbing' : 'grab'};">
            <!-- Edges (SVG) -->
            {#if graphLayout}
              <svg class="graph-edges" width="{graphLayout.maxX + 300}" height="{(treeDepth + 1) * 160 + 100}">
                {#each graphEdges as edge}
                  <path
                    d="M {edge.x1} {edge.y1} C {edge.x1} {edge.y1 + 40}, {edge.x2} {edge.y2 - 40}, {edge.x2} {edge.y2}"
                    fill="none"
                    stroke={edge.isCritical ? 'var(--color-primary)' : 'var(--color-border-hover)'}
                    stroke-width={edge.isCritical ? '2.5' : '1.5'}
                    opacity={edge.isCritical ? '0.8' : '0.4'}
                  />
                {/each}
              </svg>

              <!-- Graph nodes -->
              {#each treeNodes as node (node.id)}
                {@const pos = graphLayout.positions.get(node.id)}
                {@const sc = getStateChange(node)}
                {#if pos}
                  <button
                    class="graph-node"
                    class:gn-root={node.id === rootId}
                    class:gn-selected={selectedNode?.id === node.id}
                    class:gn-critical={criticalPath.has(node.id)}
                    class:gn-dimmed={(showCriticalOnly && !criticalPath.has(node.id)) || (searchMatches.size > 0 && !searchMatches.has(node.id))}
                    style="left: {pos.x}px; top: {pos.y}px; width: {pos.w}px; height: {pos.h}px;"
                    on:click|stopPropagation={() => handleNodeSelect(node)}
                  >
                    <span class="gn-accent" style="background: {domainColor(node.domain)};" />
                    <span class="gn-icon"><DomainIcon domain={node.domain} /></span>
                    <span class="gn-info">
                      <span class="gn-name">{node.name || node.event_type}</span>
                      {#if sc}
                        <span class="gn-state">
                          <span class="gn-sv" class:gn-on={isOnState(sc.to)} class:gn-off={isOffState(sc.to)}>{sc.from} → {sc.to}</span>
                        </span>
                      {/if}
                      {#if node.entity_id}<span class="gn-entity">{node.entity_id}</span>{/if}
                    </span>
                  </button>
                {/if}
              {/each}
            {/if}
          </div>
        </div>
      {/if}

      <!-- Inspector panel -->
      {#if selectedNode}
        <aside class="inspector" aria-label="Event inspector">
          <header class="insp-header">
            <h3>Inspector</h3>
            <button class="close-icon" on:click={() => { selectedNode = null; breadcrumbs = []; }} aria-label="Close">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4l8 8M12 4l-8 8" /></svg>
            </button>
          </header>

          <div class="insp-body">
            {#if selectedNode}
            {@const inspDelta = getNodeDelta(selectedNode)}
            {@const inspState = getStateChange(selectedNode)}

            {#if inspDelta !== null}
              <div class="insp-timing">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6" /><path d="M8 4v4l3 2" /></svg>
                <span>{formatDelta(inspDelta)} after parent</span>
              </div>
            {/if}

            <div class="meta-grid">
              <div class="meta-item">
                <span class="meta-label">Event ID</span>
                <button class="meta-value mono copy-btn" on:click={() => handleCopy(selectedNode.id, 'Event ID')} title="Copy">
                  {selectedNode.id}
                  <svg class="copy-icon" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.3"><rect x="4" y="4" width="8" height="8" rx="1.5"/><path d="M4 10H3a1.5 1.5 0 01-1.5-1.5v-6A1.5 1.5 0 013 1h6a1.5 1.5 0 011.5 1.5V4"/></svg>
                </button>
              </div>
              <div class="meta-item">
                <span class="meta-label">Type</span>
                <span class="meta-value type-chip">{selectedNode.event_type}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">Entity</span>
                {#if selectedNode.entity_id}
                  <button class="meta-value entity-link" on:click={() => handleEntityTagClick(selectedNode.entity_id)} title="View entity history">
                    {selectedNode.entity_id}
                    <svg class="link-icon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M4 8l4-4M5 3h4v4" /></svg>
                  </button>
                {:else}
                  <span class="meta-value dim">—</span>
                {/if}
              </div>
              <div class="meta-item">
                <span class="meta-label">Timestamp</span>
                <span class="meta-value">{formatTime(selectedNode.timestamp)}</span>
              </div>
              {#if selectedNode.area}
                <div class="meta-item"><span class="meta-label">Area</span><span class="meta-value">{selectedNode.area}</span></div>
              {/if}
              {#if selectedNode.integration}
                <div class="meta-item"><span class="meta-label">Integration</span><span class="meta-value">{selectedNode.integration}</span></div>
              {/if}
              <div class="meta-item"><span class="meta-label">Confidence</span><span class="meta-value"><ConfidenceBadge confidence={selectedNode.confidence} /></span></div>
              <div class="meta-item"><span class="meta-label">Children</span><span class="meta-value">{selectedNode.children?.length || 0} direct</span></div>
            </div>

            {#if inspState}
              <div class="insp-state-change">
                <span class="meta-label">State Change</span>
                <div class="state-visual">
                  <span class="sv-box sv-from" class:sv-on={isOnState(inspState.from)} class:sv-off={isOffState(inspState.from)}>{inspState.from}</span>
                  <svg viewBox="0 0 20 8" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 4h16M14 1l3 3-3 3" /></svg>
                  <span class="sv-box sv-to" class:sv-on={isOnState(inspState.to)} class:sv-off={isOffState(inspState.to)}>{inspState.to}</span>
                </div>
              </div>
            {/if}

            {#if selectedNode.entity_id}
              <a class="ha-link" href="/developer-tools/state?entity_id={encodeURIComponent(selectedNode.entity_id)}" target="_blank" rel="noopener">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 3H3v10h10v-3M9 2h5v5M7 9l7-7" /></svg>
                Open in Home Assistant
              </a>
            {/if}

            {#if selectedNode.children?.length > 0}
              <div class="insp-children">
                <span class="meta-label">Direct Children ({selectedNode.children.length})</span>
                <div class="children-list">
                  {#each selectedNode.children as child}
                    <button class="child-item" on:click={() => handleNodeSelect(child)}>
                      <DomainIcon domain={child.domain} />
                      <span class="child-name">{child.name || child.event_type}</span>
                      <span class="child-time">{formatTimeShort(child.timestamp)}</span>
                    </button>
                  {/each}
                </div>
              </div>
            {/if}

            <div class="payload-section">
              <div class="payload-header">
                <span class="payload-label">Raw Payload</span>
                <button class="copy-payload" on:click={() => handleCopy(JSON.stringify(typeof selectedNode.payload === 'string' ? JSON.parse(selectedNode.payload) : selectedNode.payload, null, 2), 'Payload')}>
                  <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.3"><rect x="4" y="4" width="8" height="8" rx="1.5"/><path d="M4 10H3a1.5 1.5 0 01-1.5-1.5v-6A1.5 1.5 0 013 1h6a1.5 1.5 0 011.5 1.5V4"/></svg>
                  Copy
                </button>
              </div>
              <pre class="payload-json">{JSON.stringify(typeof selectedNode.payload === 'string' ? JSON.parse(selectedNode.payload) : selectedNode.payload, null, 2)}</pre>
            </div>
            {/if}
          </div>
        </aside>
      {/if}
    </div>
  {/if}
</section>

{#if $selectedEntityTag}
  <EntityHistory entityId={$selectedEntityTag} on:close={() => $selectedEntityTag = null} on:eventclick={(e) => { $selectedEventId = e.detail.id; loadTree(); }} />
{/if}

<style>
  .trace-view { flex: 1; display: flex; flex-direction: column; overflow: hidden; animation: fadeIn var(--duration-normal) var(--ease-out); }

  /* Top bar */
  .trace-bar {
    display: flex; align-items: center; justify-content: space-between;
    gap: var(--sp-3); padding: var(--sp-3) var(--sp-5);
    border-bottom: 1px solid var(--color-border); flex-shrink: 0;
    background: var(--color-surface); flex-wrap: wrap;
  }
  .bar-left { display: flex; align-items: center; gap: var(--sp-3); min-width: 0; flex: 1; }
  .back-btn {
    display: flex; align-items: center; gap: 4px;
    padding: 6px 12px; border-radius: var(--radius-md);
    font-size: var(--text-sm); font-weight: 500; color: var(--color-text-secondary);
    transition: all var(--duration-fast); flex-shrink: 0;
  }
  .back-btn svg { width: 14px; height: 14px; }
  .back-btn:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .bar-title { display: flex; align-items: center; gap: var(--sp-3); min-width: 0; flex: 1; }
  .bar-title h2 { font-size: var(--text-lg); font-weight: 700; letter-spacing: -0.02em; white-space: nowrap; }
  .bar-chips { display: flex; gap: var(--sp-1); }
  .stat-chip { padding: 2px 8px; border-radius: var(--radius-full); background: var(--color-surface-hover); font-size: var(--text-2xs); font-weight: 500; color: var(--color-text-muted); }
  .bar-actions { display: flex; align-items: center; gap: var(--sp-1); flex-wrap: wrap; }
  .bar-divider { width: 1px; height: 20px; background: var(--color-border); margin: 0 var(--sp-1); }

  /* View toggle */
  .view-toggle {
    display: flex; gap: 1px; padding: 2px; border-radius: var(--radius-md);
    background: var(--color-bg-elevated); border: 1px solid var(--color-border);
  }
  .vt-btn {
    width: 30px; height: 28px; display: flex; align-items: center; justify-content: center;
    border-radius: calc(var(--radius-md) - 2px); color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .vt-btn svg { width: 14px; height: 14px; }
  .vt-btn:hover { color: var(--color-text-secondary); }
  .vt-btn.active { background: var(--color-surface); color: var(--color-text); box-shadow: var(--shadow-xs); }

  .action-btn {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 6px 12px; border-radius: var(--radius-md);
    font-size: var(--text-sm); font-weight: 500; color: var(--color-text-secondary);
    border: 1px solid var(--color-border); background: var(--color-surface);
    transition: all var(--duration-fast);
  }
  .action-btn svg { width: 14px; height: 14px; }
  .action-btn:hover { background: var(--color-surface-hover); border-color: var(--color-border-hover); color: var(--color-text); }
  .action-btn.ghost { border-color: transparent; background: none; padding: 6px; }
  .action-btn.ghost:hover { background: var(--color-surface-hover); }
  .action-btn.ghost.active { color: var(--color-primary); background: var(--color-primary-soft); }
  .action-btn.primary { background: var(--color-primary); color: white; border-color: transparent; }
  .action-btn.primary:hover { background: var(--color-primary-hover); transform: translateY(-1px); box-shadow: var(--shadow-glow); }

  /* Search */
  .search-bar {
    display: flex; align-items: center; gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-5); border-bottom: 1px solid var(--color-border);
    background: var(--color-bg-elevated); animation: fadeIn var(--duration-fast) var(--ease-out);
  }
  .s-icon { width: 14px; height: 14px; color: var(--color-text-muted); flex-shrink: 0; }
  .s-input { flex: 1; background: none; border: none; color: var(--color-text); font-size: var(--text-sm); outline: none; padding: 4px 0; }
  .s-input::placeholder { color: var(--color-text-muted); }
  .s-count { font-size: var(--text-2xs); color: var(--color-primary); font-weight: 500; white-space: nowrap; padding: 2px 8px; border-radius: var(--radius-full); background: var(--color-primary-soft); }
  .s-close { width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); color: var(--color-text-muted); }
  .s-close svg { width: 12px; height: 12px; }
  .s-close:hover { background: var(--color-surface-hover); color: var(--color-text); }

  /* Stats */
  .stats-dashboard {
    display: flex; gap: var(--sp-2); padding: var(--sp-3) var(--sp-5);
    border-bottom: 1px solid var(--color-border); overflow-x: auto; flex-shrink: 0; flex-wrap: wrap;
  }
  .stat-card {
    display: flex; flex-direction: column; align-items: center; gap: 2px;
    padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-md);
    background: var(--color-surface); border: 1px solid var(--color-border); min-width: 60px;
  }
  .stat-card.wide { min-width: 120px; padding: var(--sp-2) var(--sp-4); }
  .stat-value { font-size: var(--text-md); font-weight: 700; letter-spacing: -0.02em; }
  .stat-value.mono-sm { font-family: var(--font-mono); font-size: var(--text-2xs); font-weight: 500; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .stat-value.verified-text { color: var(--color-success); }
  .stat-value.inferred-text { color: var(--color-warning); }
  .stat-label { font-size: var(--text-2xs); color: var(--color-text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; }

  .domain-bar-card {
    display: flex; flex-direction: column; gap: 6px; padding: var(--sp-2) var(--sp-4);
    border-radius: var(--radius-md); background: var(--color-surface);
    border: 1px solid var(--color-border); min-width: 200px; flex: 1;
  }
  .domain-bar { display: flex; height: 6px; border-radius: var(--radius-full); overflow: hidden; gap: 1px; }
  .domain-segment { border-radius: 2px; min-width: 4px; transition: opacity var(--duration-fast); }
  .domain-segment:hover { opacity: 0.8; }
  .domain-legend { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .legend-item { display: flex; align-items: center; gap: 4px; font-size: var(--text-2xs); color: var(--color-text-secondary); }
  .legend-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
  .legend-count { color: var(--color-text-muted); font-weight: 500; }

  /* Breadcrumbs */
  .breadcrumbs {
    display: flex; align-items: center; gap: var(--sp-1);
    padding: var(--sp-2) var(--sp-5); border-bottom: 1px solid var(--color-border);
    background: var(--color-bg-elevated); overflow-x: auto; flex-shrink: 0;
  }
  .crumb { display: flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: var(--radius-sm); font-size: var(--text-2xs); color: var(--color-text-secondary); white-space: nowrap; transition: all var(--duration-fast); }
  .crumb:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .crumb-current { color: var(--color-primary); font-weight: 600; background: var(--color-primary-soft); }
  .crumb-sep { color: var(--color-text-muted); font-size: var(--text-xs); }

  /* Body */
  .trace-body { flex: 1; display: flex; overflow: hidden; }
  .tree-panel { flex: 1; overflow-y: auto; padding: var(--sp-3) var(--sp-4); outline: none; }
  .trace-body.has-inspector .tree-panel { flex: 3; }

  /* Delta */
  .delta-badge { font-size: 9px; font-family: var(--font-mono); color: var(--color-text-muted); padding: 0 4px; height: 14px; display: flex; align-items: center; opacity: 0.7; }

  /* Tree list */
  .tree-container { display: flex; flex-direction: column; }
  .tree-node {
    display: flex; align-items: center; min-height: 40px; border-radius: var(--radius-md);
    transition: all var(--duration-fast); animation: fadeIn var(--duration-normal) var(--ease-out) both;
    position: relative; border: 1px solid transparent;
  }
  .tree-node:hover { background: var(--color-surface-hover); }
  .tree-node.is-root { background: var(--color-warning-soft); border-color: rgba(251,191,36,.15); }
  .tree-node.is-root:hover { background: rgba(251,191,36,.12); }
  .tree-node.is-selected { background: var(--color-primary-soft); border-color: rgba(124,92,252,.2); }
  .tree-node.is-focused { outline: 2px solid var(--color-primary); outline-offset: -2px; }
  .tree-node.is-critical { background: rgba(124,92,252,.04); }
  .tree-node.is-search-hit { background: rgba(56,189,248,.08); border-color: rgba(56,189,248,.2); }
  .tree-node.is-dimmed { opacity: 0.25; }

  .tree-connector { display: flex; align-items: center; justify-content: flex-end; flex-shrink: 0; height: 100%; position: relative; }
  .connector-line { position: absolute; left: 12px; width: calc(100% - 12px); height: 1px; background: var(--color-border); }
  .connector-line.critical-line { background: var(--color-primary); height: 2px; opacity: 0.5; }

  .toggle-btn {
    width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-sm); flex-shrink: 0; color: var(--color-text-muted);
    transition: all var(--duration-fast); margin: 0 2px; position: relative;
  }
  .toggle-btn:hover { background: var(--color-surface-active); color: var(--color-text); }
  .toggle-icon { width: 10px; height: 10px; transition: transform var(--duration-fast) var(--ease-out); }
  .toggle-icon.expanded { transform: rotate(90deg); }
  .collapse-badge {
    position: absolute; top: -4px; right: -6px; min-width: 14px; height: 14px;
    border-radius: var(--radius-full); background: var(--color-primary); color: white;
    font-size: 9px; font-weight: 600; display: flex; align-items: center; justify-content: center; padding: 0 3px;
  }
  .toggle-spacer { width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin: 0 2px; }
  .leaf-dot { width: 4px; height: 4px; border-radius: 50%; background: var(--color-border-hover); }

  .node-body {
    display: flex; align-items: center; gap: var(--sp-2); flex: 1; min-width: 0;
    padding: 5px var(--sp-3); border-radius: var(--radius-sm); text-align: left;
    transition: background var(--duration-fast);
  }
  .node-body:hover { background: var(--color-surface-active); }
  .node-icon {
    flex-shrink: 0; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-sm); background: var(--color-surface); font-size: var(--text-sm);
    border-left: 2px solid var(--color-border);
  }
  .node-content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .node-name { font-size: var(--text-sm); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .node-entity-tag {
    font-size: 10px; color: var(--color-primary); font-family: var(--font-mono);
    padding: 0 6px; border-radius: var(--radius-full); background: var(--color-primary-soft);
    border: 1px solid rgba(124,92,252,.15); cursor: pointer; width: fit-content;
    transition: all var(--duration-fast);
  }
  .node-entity-tag:hover { border-color: var(--color-primary); background: var(--color-primary-bg); }

  /* State change */
  .state-change { display: inline-flex; align-items: center; gap: 4px; font-size: var(--text-2xs); font-family: var(--font-mono); }
  .sc-from, .sc-to { padding: 1px 5px; border-radius: 3px; font-weight: 500; }
  .sc-from { background: var(--color-surface-hover); color: var(--color-text-muted); }
  .sc-from.sc-on { color: var(--color-success); background: var(--color-success-soft); }
  .sc-from.sc-off { color: var(--color-text-muted); }
  .sc-to { background: var(--color-success-soft); color: var(--color-success); font-weight: 700; }
  .sc-to.sc-on { color: var(--color-success); background: var(--color-success-soft); box-shadow: 0 0 6px rgba(52,211,153,.2); }
  .sc-to.sc-off { color: var(--color-text-muted); background: var(--color-surface-hover); box-shadow: none; font-weight: 500; }
  .sc-arrow { width: 12px; height: 8px; color: var(--color-text-muted); flex-shrink: 0; }
  .node-time { font-size: var(--text-2xs); color: var(--color-text-muted); white-space: nowrap; flex-shrink: 0; font-family: var(--font-mono); }

  /* ─── GRAPH VIEW ─── */
  .graph-panel {
    flex: 1; overflow: hidden; position: relative;
    background: var(--color-bg);
    background-image: radial-gradient(circle, var(--color-border) 1px, transparent 1px);
    background-size: 24px 24px;
    touch-action: none; user-select: none;
  }
  .graph-controls {
    position: absolute; top: var(--sp-3); right: var(--sp-3); z-index: 5;
    display: flex; gap: 2px; padding: 3px; border-radius: var(--radius-md);
    background: var(--color-surface); border: 1px solid var(--color-border);
    box-shadow: var(--shadow-md);
  }
  .gc-btn {
    width: 30px; height: 28px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-sm); font-size: var(--text-md); font-weight: 600;
    color: var(--color-text-secondary); transition: all var(--duration-fast);
  }
  .gc-btn:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .gc-label { font-size: var(--text-2xs); color: var(--color-text-muted); display: flex; align-items: center; padding: 0 6px; font-variant-numeric: tabular-nums; }
  .graph-canvas {
    position: absolute; top: 0; left: 0; transform-origin: 0 0;
    transition: none; will-change: transform;
  }
  .graph-edges { position: absolute; top: 0; left: 0; pointer-events: none; overflow: visible; }

  .graph-node {
    position: absolute; display: flex; align-items: center; gap: var(--sp-2);
    border-radius: var(--radius-md); background: var(--color-surface);
    border: 1px solid var(--color-border); padding: var(--sp-2) var(--sp-3);
    cursor: pointer; transition: all var(--duration-fast); text-align: left; overflow: hidden;
  }
  .graph-node:hover { border-color: var(--color-border-hover); box-shadow: var(--shadow-md); transform: translateY(-1px); z-index: 2; }
  .graph-node.gn-root { border-color: rgba(251,191,36,.4); background: var(--color-warning-soft); }
  .graph-node.gn-selected { border-color: var(--color-primary); background: var(--color-primary-soft); box-shadow: var(--shadow-glow); z-index: 3; }
  .graph-node.gn-critical { border-color: rgba(124,92,252,.3); }
  .graph-node.gn-dimmed { opacity: 0.2; }
  .gn-accent { position: absolute; left: 0; top: 0; bottom: 0; width: 3px; border-radius: 2px 0 0 2px; }
  .gn-icon { flex-shrink: 0; font-size: var(--text-sm); }
  .gn-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
  .gn-name { font-size: var(--text-xs); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gn-state { font-size: 10px; font-family: var(--font-mono); }
  .gn-sv { padding: 0 4px; border-radius: 3px; background: var(--color-surface-hover); color: var(--color-text-muted); }
  .gn-sv.gn-on { color: var(--color-success); background: var(--color-success-soft); }
  .gn-sv.gn-off { color: var(--color-text-muted); }
  .gn-entity { font-size: 9px; font-family: var(--font-mono); color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* Inspector */
  .inspector {
    flex: 2; max-width: 420px; border-left: 1px solid var(--color-border);
    background: var(--color-bg-elevated); display: flex; flex-direction: column;
    animation: slideInRight var(--duration-slow) var(--ease-out); overflow: hidden;
  }
  .insp-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--sp-3) var(--sp-4); border-bottom: 1px solid var(--color-border); flex-shrink: 0;
  }
  .insp-header h3 { font-size: var(--text-base); font-weight: 600; }
  .close-icon {
    width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-sm); color: var(--color-text-muted); transition: all var(--duration-fast);
  }
  .close-icon svg { width: 14px; height: 14px; }
  .close-icon:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .insp-body { flex: 1; overflow-y: auto; padding: var(--sp-4); display: flex; flex-direction: column; gap: var(--sp-4); }
  .insp-timing {
    display: flex; align-items: center; gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3); border-radius: var(--radius-md);
    background: var(--color-primary-soft); color: var(--color-primary);
    font-size: var(--text-sm); font-weight: 500;
  }
  .insp-timing svg { width: 14px; height: 14px; flex-shrink: 0; }

  .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3); }
  .meta-item { display: flex; flex-direction: column; gap: 3px; }
  .meta-label { font-size: var(--text-2xs); font-weight: 500; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .meta-value { font-size: var(--text-sm); word-break: break-all; }
  .meta-value.mono { font-family: var(--font-mono); font-size: var(--text-xs); }
  .meta-value.dim { color: var(--color-text-muted); }
  .copy-btn {
    display: flex; align-items: center; gap: 4px; cursor: pointer; text-align: left;
    border-radius: var(--radius-sm); padding: 2px 4px; margin: -2px -4px;
    font-family: var(--font-mono); font-size: var(--text-xs);
    transition: background var(--duration-fast);
  }
  .copy-btn:hover { background: var(--color-surface-hover); }
  .copy-icon { width: 11px; height: 11px; color: var(--color-text-muted); flex-shrink: 0; opacity: 0; transition: opacity var(--duration-fast); }
  .copy-btn:hover .copy-icon { opacity: 1; }
  .type-chip {
    display: inline-block; padding: 1px 8px; border-radius: var(--radius-full);
    background: var(--color-primary-soft); color: var(--color-primary);
    font-size: var(--text-xs); font-weight: 500; width: fit-content;
  }
  .entity-link {
    display: flex; align-items: center; gap: 3px; cursor: pointer;
    font-family: var(--font-mono); font-size: var(--text-xs);
    color: var(--color-primary); text-align: left;
    transition: all var(--duration-fast); border-radius: var(--radius-sm);
    padding: 2px 4px; margin: -2px -4px;
  }
  .entity-link:hover { background: var(--color-primary-soft); }
  .link-icon { width: 10px; height: 10px; flex-shrink: 0; opacity: 0; transition: opacity var(--duration-fast); }
  .entity-link:hover .link-icon { opacity: 1; }

  .insp-state-change { display: flex; flex-direction: column; gap: var(--sp-2); }
  .state-visual { display: flex; align-items: center; gap: var(--sp-2); }
  .state-visual svg { width: 20px; height: 8px; color: var(--color-text-muted); flex-shrink: 0; }
  .sv-box { padding: 4px 10px; border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: var(--text-sm); font-weight: 600; }
  .sv-from { background: var(--color-surface); border: 1px solid var(--color-border); color: var(--color-text-secondary); }
  .sv-from.sv-on { color: var(--color-success); background: var(--color-success-soft); border-color: rgba(52,211,153,.2); }
  .sv-from.sv-off { color: var(--color-text-muted); }
  .sv-to { background: var(--color-success-soft); border: 1px solid rgba(52,211,153,.2); color: var(--color-success); }
  .sv-to.sv-on { color: var(--color-success); box-shadow: 0 0 8px rgba(52,211,153,.15); }
  .sv-to.sv-off { color: var(--color-text-muted); background: var(--color-surface-hover); border-color: var(--color-border); box-shadow: none; }

  .ha-link {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 14px; border-radius: var(--radius-md);
    background: var(--color-surface); border: 1px solid var(--color-border);
    color: var(--color-primary); font-size: var(--text-sm); font-weight: 500;
    transition: all var(--duration-fast); text-decoration: none;
  }
  .ha-link svg { width: 14px; height: 14px; }
  .ha-link:hover { border-color: var(--color-primary); background: var(--color-primary-soft); }

  .insp-children { display: flex; flex-direction: column; gap: var(--sp-2); }
  .children-list { display: flex; flex-direction: column; gap: 2px; max-height: 160px; overflow-y: auto; }
  .child-item {
    display: flex; align-items: center; gap: var(--sp-2); padding: 4px 8px;
    border-radius: var(--radius-sm); font-size: var(--text-xs); color: var(--color-text-secondary);
    transition: all var(--duration-fast); text-align: left;
  }
  .child-item:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .child-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .child-time { font-family: var(--font-mono); font-size: var(--text-2xs); color: var(--color-text-muted); flex-shrink: 0; }

  .payload-section { display: flex; flex-direction: column; gap: var(--sp-2); }
  .payload-header { display: flex; align-items: center; justify-content: space-between; }
  .payload-label { font-size: var(--text-2xs); font-weight: 500; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .copy-payload {
    display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
    border-radius: var(--radius-sm); font-size: var(--text-2xs); color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .copy-payload svg { width: 11px; height: 11px; }
  .copy-payload:hover { background: var(--color-surface-hover); color: var(--color-text); }
  .payload-json {
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: var(--radius-md); padding: var(--sp-3); font-family: var(--font-mono);
    font-size: var(--text-xs); line-height: var(--lh-relaxed); overflow-x: auto;
    white-space: pre-wrap; word-break: break-all; max-height: 280px; overflow-y: auto;
    color: var(--color-text-secondary);
  }

  /* State/loading cards */
  .state-card {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: var(--sp-12) var(--sp-6); text-align: center; gap: var(--sp-3);
  }
  .state-icon { width: 56px; height: 56px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-lg); color: var(--color-text-muted); margin-bottom: var(--sp-2); }
  .state-icon svg { width: 28px; height: 28px; }
  .error-card .state-icon { color: var(--color-error); background: var(--color-error-soft); }
  .state-card h3 { font-size: var(--text-md); font-weight: 600; }
  .state-detail { color: var(--color-text-muted); font-size: var(--text-sm); }
  .loading-area { padding: var(--sp-5); display: flex; flex-direction: column; gap: var(--sp-2); }
  .skeleton-node { height: 40px; border-radius: var(--radius-md); animation-fill-mode: both; }

  /* ─── Responsive ─── */
  @media (max-width: 900px) {
    .inspector {
      position: fixed; top: var(--header-h); right: 0; bottom: 0;
      max-width: 90vw; width: 380px; z-index: 90; box-shadow: var(--shadow-lg);
    }
  }
  @media (max-width: 768px) {
    .trace-bar { padding: var(--sp-2) var(--sp-3); gap: var(--sp-2); }
    .bar-chips { display: none; }
    .bar-divider { display: none; }
    .hide-mobile { display: none; }
    .btn-label { display: none; }
    .action-btn { padding: 6px; }
    .stats-dashboard { padding: var(--sp-2) var(--sp-3); }
    .stat-card { min-width: 50px; padding: var(--sp-1) var(--sp-2); }
    .stat-value { font-size: var(--text-sm); }
    .breadcrumbs { padding: var(--sp-2) var(--sp-3); }
    .search-bar { padding: var(--sp-2) var(--sp-3); }
    .tree-panel { padding: var(--sp-2) var(--sp-2); }
    .back-text { display: none; }
    .meta-grid { grid-template-columns: 1fr; }
    .inspector { width: 320px; }
    .insp-body { padding: var(--sp-3); }
  }
  @media (max-width: 480px) {
    .inspector { width: 100%; max-width: 100%; }
    .view-toggle { display: none; }
    .bar-title h2 { font-size: var(--text-md); }
  }
</style>
