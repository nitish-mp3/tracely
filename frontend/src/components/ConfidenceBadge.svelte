<script>
  export let confidence = 'propagated';

  const labels = {
    propagated: 'Verified',
    inferred: 'Inferred',
  };

  const tooltips = {
    propagated: 'Link verified via HA context propagation',
    inferred: 'Link inferred by Tracely heuristics (time + entity matching)',
  };
</script>

<span
  class="badge"
  class:verified={confidence === 'propagated'}
  class:inferred={confidence === 'inferred'}
  title={tooltips[confidence] || ''}
  role="status"
>
  <span class="dot" />
  {labels[confidence] || confidence}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: var(--text-2xs);
    padding: 2px 9px 2px 7px;
    border-radius: var(--radius-full);
    font-weight: 600;
    white-space: nowrap;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    transition: all var(--duration-fast);
  }

  .dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .verified {
    background: var(--color-success-soft);
    color: var(--color-success);
  }
  .verified .dot {
    background: var(--color-success);
    box-shadow: 0 0 4px rgba(34, 197, 94, 0.4);
  }

  .inferred {
    background: var(--color-warning-soft);
    color: var(--color-warning);
  }
  .inferred .dot {
    background: var(--color-warning);
    box-shadow: 0 0 4px rgba(251, 191, 36, 0.4);
  }
</style>
