<script>
  import { toasts, removeToast } from '../stores/config.js';
</script>

{#if $toasts.length > 0}
  <div class="toast-container" role="alert" aria-live="polite">
    {#each $toasts as toast (toast.id)}
      <div class="toast" class:is-success={toast.type === 'success'} class:is-error={toast.type === 'error'} class:is-warning={toast.type === 'warning'} class:is-info={toast.type === 'info' || !toast.type}>
        <div class="toast-accent" />
        <div class="toast-icon">
          {#if toast.type === 'success'}
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 8.5l3 3 5-6" /></svg>
          {:else if toast.type === 'error'}
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="8" cy="8" r="5.5" /><path d="M6 6l4 4M10 6l-4 4" /></svg>
          {:else if toast.type === 'warning'}
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 3L2 13h12L8 3zM8 7v3M8 11.5v.5" /></svg>
          {:else}
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="8" cy="8" r="5.5" /><path d="M8 5v4M8 10.5v.5" /></svg>
          {/if}
        </div>
        <span class="toast-message">{toast.message}</span>
        <button class="toast-close" on:click={() => removeToast(toast.id)} aria-label="Dismiss notification">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
        </button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .toast-container {
    position: fixed;
    bottom: var(--sp-5);
    right: var(--sp-5);
    z-index: 9999;
    display: flex;
    flex-direction: column-reverse;
    gap: var(--sp-2);
    max-width: 400px;
    pointer-events: none;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    padding: var(--sp-3) var(--sp-4);
    border-radius: var(--radius-lg);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border);
    box-shadow: var(--shadow-lg);
    animation: slideInUp var(--duration-normal) var(--ease-out);
    font-size: var(--text-sm);
    pointer-events: auto;
    overflow: hidden;
    position: relative;
  }

  .toast-accent {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
  }
  .is-success .toast-accent { background: var(--color-success); }
  .is-error .toast-accent { background: var(--color-error); }
  .is-warning .toast-accent { background: var(--color-warning); }
  .is-info .toast-accent { background: var(--color-info); }

  .toast-icon {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
  }
  .toast-icon svg {
    width: 20px;
    height: 20px;
  }
  .is-success .toast-icon { color: var(--color-success); }
  .is-error .toast-icon { color: var(--color-error); }
  .is-warning .toast-icon { color: var(--color-warning); }
  .is-info .toast-icon { color: var(--color-info); }

  .toast-message {
    flex: 1;
    color: var(--color-text);
    font-weight: 500;
  }

  .toast-close {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
    color: var(--color-text-muted);
    transition: all var(--duration-fast);
  }
  .toast-close svg {
    width: 12px;
    height: 12px;
  }
  .toast-close:hover {
    color: var(--color-text);
    background: var(--color-surface-hover);
  }

  @keyframes slideInUp {
    from { transform: translateY(16px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }
</style>
