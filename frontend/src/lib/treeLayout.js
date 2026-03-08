/**
 * Tree layout helpers — position nodes for the TraceView.
 * Uses a simple indented-list approach (no d3 dependency needed).
 */

/**
 * Take a flat array of event nodes and build a tree structure.
 * @param {Array} nodes — flat array of events with id + parent_id
 * @returns {{ roots: Array, nodeMap: Map }}
 */
export function buildTree(nodes) {
  const nodeMap = new Map();
  const roots = [];

  for (const node of nodes) {
    nodeMap.set(node.id, { ...node, children: [] });
  }

  for (const node of nodes) {
    const mapped = nodeMap.get(node.id);
    if (node.parent_id && nodeMap.has(node.parent_id)) {
      nodeMap.get(node.parent_id).children.push(mapped);
    } else {
      roots.push(mapped);
    }
  }

  return { roots, nodeMap };
}

/**
 * Flatten a tree back into a depth-first ordered list with depth info.
 * @param {Array} roots — root nodes from buildTree
 * @returns {Array} — [{...node, depth: number}]
 */
export function flattenTree(roots) {
  const result = [];

  function walk(node, depth) {
    result.push({ ...node, depth });
    for (const child of node.children || []) {
      walk(child, depth + 1);
    }
  }

  for (const root of roots) {
    walk(root, 0);
  }

  return result;
}

/**
 * Get the maximum depth of a tree.
 */
export function getMaxDepth(roots) {
  let max = 0;
  function walk(node, depth) {
    if (depth > max) max = depth;
    for (const child of node.children || []) {
      walk(child, depth + 1);
    }
  }
  for (const root of roots) {
    walk(root, 0);
  }
  return max;
}

// ─── Analytics helpers for enriched trace display ───────

/**
 * Count subtree size (including the node itself).
 */
export function getSubtreeSize(node) {
  let count = 1;
  for (const child of node.children || []) {
    count += getSubtreeSize(child);
  }
  return count;
}

/**
 * Build a domain breakdown: { domain: count }
 */
export function getDomainBreakdown(flatNodes) {
  const map = {};
  for (const n of flatNodes) {
    const d = n.domain || 'unknown';
    map[d] = (map[d] || 0) + 1;
  }
  return map;
}

/**
 * Compute the time delta between a node and its parent in ms.
 * Returns null if no parent timestamp or this node's timestamp is missing.
 */
export function getTimeDelta(node, nodeMap) {
  if (!node.parent_id || !nodeMap) return null;
  const parent = nodeMap.get(node.parent_id);
  if (!parent) return null;
  const parentTs = toEpoch(parent.timestamp);
  const nodeTs = toEpoch(node.timestamp);
  if (parentTs === null || nodeTs === null) return null;
  return nodeTs - parentTs;
}

/**
 * Parse an ISO string or epoch-ms number into epoch-ms.
 */
function toEpoch(ts) {
  if (!ts) return null;
  if (typeof ts === 'number') return ts;
  const d = new Date(ts);
  return isNaN(d.getTime()) ? null : d.getTime();
}

/**
 * Build the breadcrumb (ancestor chain) from a node up to the root.
 * Returns [{id, name, domain}] starting from root.
 */
export function getBreadcrumbs(nodeId, nodeMap) {
  const trail = [];
  let current = nodeMap?.get(nodeId);
  while (current) {
    trail.unshift({ id: current.id, name: current.name || current.event_type, domain: current.domain });
    current = current.parent_id ? nodeMap.get(current.parent_id) : null;
  }
  return trail;
}

/**
 * Compute the critical (longest) path — deepest chain from root to leaf.
 * Returns a Set of node IDs on that path.
 */
export function getCriticalPath(roots) {
  let bestPath = [];

  function walk(node, path) {
    const current = [...path, node.id];
    if (!node.children || node.children.length === 0) {
      if (current.length > bestPath.length) bestPath = current;
      return;
    }
    for (const child of node.children) {
      walk(child, current);
    }
  }

  for (const root of roots) {
    walk(root, []);
  }
  return new Set(bestPath);
}

/**
 * Compute aggregate tree stats.
 */
export function getTreeStats(flatNodes, nodeMap) {
  const domainBreakdown = getDomainBreakdown(flatNodes);
  const domains = Object.keys(domainBreakdown).filter(d => d !== 'unknown');
  const timestamps = flatNodes.map(n => toEpoch(n.timestamp)).filter(Boolean);
  const minTs = timestamps.length ? Math.min(...timestamps) : null;
  const maxTs = timestamps.length ? Math.max(...timestamps) : null;
  const durationMs = (minTs !== null && maxTs !== null) ? maxTs - minTs : null;
  const inferredCount = flatNodes.filter(n => n.confidence === 'inferred').length;
  const verifiedCount = flatNodes.filter(n => n.confidence === 'propagated').length;

  const entityCounts = {};
  for (const n of flatNodes) {
    if (n.entity_id) entityCounts[n.entity_id] = (entityCounts[n.entity_id] || 0) + 1;
  }
  const topEntity = Object.entries(entityCounts).sort((a, b) => b[1] - a[1])[0];

  return {
    totalNodes: flatNodes.length,
    domainBreakdown,
    domainCount: domains.length,
    durationMs,
    inferredCount,
    verifiedCount,
    topEntity: topEntity ? { id: topEntity[0], count: topEntity[1] } : null,
    entityCount: Object.keys(entityCounts).length,
  };
}

/**
 * Format a duration in ms to a human-readable string.
 */
export function formatDuration(ms) {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)}m`;
  return `${(ms / 3600000).toFixed(1)}h`;
}

/**
 * Format an ms delta for display on tree edges.
 */
export function formatDelta(ms) {
  if (ms === null || ms === undefined) return '';
  const abs = Math.abs(ms);
  if (abs < 100) return `${abs}ms`;
  if (abs < 1000) return `${abs}ms`;
  if (abs < 60000) return `${(abs / 1000).toFixed(1)}s`;
  return `${(abs / 60000).toFixed(1)}m`;
}
