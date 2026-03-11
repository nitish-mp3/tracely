/**
 * Events store — manages event data, pagination, filters, and live updates.
 */
import { writable, derived } from 'svelte/store';

// Raw event list from API
export const events = writable([]);

// Pagination state
export const pagination = writable({
  page: 1,
  limit: 50,
  total: 0,
});

// Active filters
export const filters = writable({
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
});

// Currently selected event (for trace view)
export const selectedEventId = writable(null);

// Tree data for trace view
export const treeData = writable(null);

// Loading states
export const loading = writable(false);
export const error = writable(null);

// SSE connection status: 'connected' | 'reconnecting' | 'disconnected'
export const sseStatus = writable('disconnected');

// Entity tag selection (for entity history drill-down)
export const selectedEntityTag = writable(null);

// Domain tag selection (for domain history drill-down)
export const selectedDomainTag = writable(null);

// View history stack — so we can go back to filtered view after trace
export const viewHistory = writable([]);

// Derived: has active filters?
export const hasActiveFilters = derived(filters, ($f) =>
  Boolean($f.entity || $f.domain || $f.area || $f.user_id || $f.event_type || $f.q || $f.from || $f.to || $f.bookmarksOnly || $f.inferredOnly)
);
