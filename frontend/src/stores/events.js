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

// --- Filter persistence helpers ---
const FILTER_STORAGE_KEY = 'tracely_filters';

const defaultFilters = {
  entity: '',
  domain: '',
  area: '',
  user_id: '',
  event_type: '',
  integration: '',
  from: '',
  to: '',
  q: '',
  bookmarksOnly: false,
  inferredOnly: false,
};

function loadFilters() {
  try {
    const raw = sessionStorage.getItem(FILTER_STORAGE_KEY);
    if (raw) {
      const stored = JSON.parse(raw);
      // Merge with defaults so new keys are always present
      return { ...defaultFilters, ...stored };
    }
  } catch { /* ignore corrupt storage */ }
  return { ...defaultFilters };
}

function saveFilters(f) {
  try {
    sessionStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(f));
  } catch { /* quota etc */ }
}

// Active filters — restored from sessionStorage, auto-saved on change
function createPersistentFilters() {
  const { subscribe, set, update } = writable(loadFilters());
  return {
    subscribe,
    set(value) {
      saveFilters(value);
      set(value);
    },
    update(fn) {
      update((current) => {
        const next = fn(current);
        saveFilters(next);
        return next;
      });
    },
    reset() {
      const fresh = { ...defaultFilters };
      saveFilters(fresh);
      set(fresh);
    },
  };
}

export const filters = createPersistentFilters();

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

// Monitor navigation target: { eventId, entityId, timestamp, view }
export const monitorTarget = writable(null);

// View history stack — so we can go back to filtered view after trace
export const viewHistory = writable([]);

// Derived: has active filters?
export const hasActiveFilters = derived(filters, ($f) =>
  Boolean($f.entity || $f.domain || $f.area || $f.user_id || $f.event_type || $f.integration || $f.q || $f.from || $f.to || $f.bookmarksOnly || $f.inferredOnly)
);
