#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level')
export PURGE_KEEP_DAYS=$(bashio::config 'purge_keep_days')
export REDACT_PII=$(bashio::config 'redact_pii')
export HA_TOKEN=$(bashio::config 'ha_token')
export BACKFILL_DAYS=$(bashio::config 'backfill_days')
export DB_PATH=/data/tracely.db
export FRONTEND_DIR=/app/frontend/dist

cd /app
exec python3 -m backend.main
