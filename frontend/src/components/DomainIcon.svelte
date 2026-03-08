<script>
  export let domain = '';

  const icons = {
    light: '💡',
    switch: '🔌',
    sensor: '🌡️',
    binary_sensor: '🔘',
    automation: '⚙️',
    script: '📜',
    scene: '🎬',
    climate: '🌡️',
    fan: '🌀',
    cover: '🪟',
    lock: '🔒',
    camera: '📷',
    media_player: '🔊',
    person: '👤',
    device_tracker: '📍',
    input_boolean: '☑️',
    input_number: '🔢',
    input_select: '📋',
    timer: '⏱️',
    counter: '🔢',
    alert: '🚨',
    homeassistant: '🏠',
    persistent_notification: '🔔',
    update: '⬆️',
    weather: '☀️',
    sun: '☀️',
    zone: '📍',
    vacuum: '🤖',
    water_heater: '🚿',
  };
</script>

<span class="domain-icon" aria-hidden="true" title={domain}>
  {icons[domain] || '📦'}
</span>

<style>
  .domain-icon {
    font-size: 1em;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    filter: saturate(0.85) brightness(1.05);
  }
</style>
