# Tracely — Quickstart Guide

## What is Tracely?

Tracely is a **fully offline** Home Assistant add-on that automatically captures every event happening in your smart home and presents them as **human-readable, searchable, interactive causal trees and timelines**. No cloud, no backend setup, no manual mapping required.

## Installation

### From the Add-on Store

1. Open Home Assistant → **Settings** → **Add-ons** → **Add-on Store**
2. Click the three-dot menu (⋮) → **Repositories**
3. Add this repository URL: `https://github.com/nky001/tracely`
4. Find **Tracely** in the store and click **Install**
5. Click **Start**
6. Open the **Tracely** panel from the sidebar

### That's it!

Tracely automatically discovers your Home Assistant instance, starts capturing events, and builds causal trees. **No configuration required.**

## Configuration (Optional)

All settings have sensible defaults. You can adjust them in **Settings** → **Add-ons** → **Tracely** → **Configuration**:

| Setting | Default | Description |
|---|---|---|
| `purge_keep_days` | `30` | How many days of event history to retain |
| `log_level` | `info` | Logging verbosity: `debug`, `info`, `warning`, `error` |
| `redact_pii` | `true` | Redact user identifiers from debug logs |
| `ha_token` | *(empty)* | Only needed for non-Supervisor installs — leave blank for normal use |

## Features

### Timeline View
- See all events in chronological order
- Color-coded by category (device, automation, user action, system)
- Click any event to see its full causal tree
- Live updates via real-time streaming

### Trace View
- Interactive causal tree showing cause → effect chains
- Expand/collapse nodes
- View raw event payloads with syntax highlighting
- Export trees as JSON for debugging

### Search
- Full-text search across all events
- Search by entity name, domain, or any text in event payloads

### Filters
- Filter by entity, domain, area, user, or date range
- Toggle to show only inferred or bookmarked events

### Bookmarks
- Star important events for quick reference
- Add notes to bookmarked events

## How It Works

1. **Capture**: Tracely connects to Home Assistant's WebSocket API and listens for all events (state changes, service calls, automations, scripts, etc.)
2. **Normalize**: Each event is enriched with human-readable names, entity info, areas, and integrations
3. **Link**: Events are linked into causal trees using Home Assistant's context propagation system, supplemented by heuristic linking for events without explicit parent references
4. **Store**: Everything is stored locally in a SQLite database with full-text search
5. **Display**: The web UI presents events as interactive timelines and causal trees

## API

Tracely exposes a REST API for programmatic access:

- `GET /api/events` — Paginated event timeline with filters
- `GET /api/events/{id}` — Single event with its full causal tree
- `GET /api/search?q=...` — Full-text search
- `GET /api/trees` — Tree index
- `GET /api/entities` — Entity cache
- `GET /health` — Health check
- `GET /metrics` — Prometheus metrics

## Privacy & Security

- **100% offline** — no data ever leaves your network
- All data stored locally at `/data/tracely.db`
- PII redaction enabled by default in logs
- Admin-only access enforced via Home Assistant's authentication
- All database queries use parameterized statements (no SQL injection risk)

## Troubleshooting

### Tracely panel is blank
- Wait 30 seconds after first start for initial event capture
- Check the add-on logs for connection errors

### "Not connected" indicator
- Ensure Home Assistant is running
- For non-Supervisor installs, set `ha_token` in configuration

### High memory usage
- Reduce `purge_keep_days` to retain fewer events
- Tracely targets ≤150 MB memory usage under normal conditions

## Support

File issues at: `https://github.com/nky001/tracely/issues`
