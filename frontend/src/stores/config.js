/**
 * Config store — app configuration and theme state.
 */
import { writable } from 'svelte/store';

// Current view: 'timeline' | 'trace' | 'search'
export const currentView = writable('timeline');

// Sidebar / filter drawer open
export const filtersOpen = writable(false);

// Health status
export const healthStatus = writable(null);

// Available entities (for filter dropdowns)
export const availableEntities = writable([]);

// Toast notifications
export const toasts = writable([]);

let toastId = 0;

export function addToast(message, type = 'info', duration = 4000) {
  const id = ++toastId;
  toasts.update((t) => [...t, { id, message, type }]);
  if (duration > 0) {
    setTimeout(() => removeToast(id), duration);
  }
}

export function removeToast(id) {
  toasts.update((t) => t.filter((x) => x.id !== id));
}
