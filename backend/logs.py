"""Log file capture and analysis for Home Assistant diagnostics."""

from __future__ import annotations

import base64
import gzip
import os
import time
from collections import deque
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# HA core log locations (based on HA installation type)
CORE_LOG_PATHS = [
    Path("/config/home-assistant.log"),  # Standard HA OS location
    Path("/config/logs/home-assistant.log"),  # Some setups
    Path("/config/core.log"),  # Alternative naming
    Path("/homeassistant/home-assistant.log"),
    Path("/usr/share/hassio/homeassistant/home-assistant.log"),
]

# Addon's own logs
ADDON_LOG_PATHS = [
    Path("/proc/1/fd/1"),  # Container stdout (pid 1 is our process)
]

_MISSING_LOG_WARN_INTERVAL_SECONDS = 300
_last_missing_log_warning_at: float = 0.0


def _warn_missing_log_throttled(paths_checked: list[str]) -> None:
    """Emit missing-log warning at most once per interval."""
    global _last_missing_log_warning_at
    now = time.time()
    if now - _last_missing_log_warning_at >= _MISSING_LOG_WARN_INTERVAL_SECONDS:
        logger.warning("logs.ha_core_log_not_found", paths_checked=paths_checked)
        _last_missing_log_warning_at = now


def _is_plausible_core_log(path: Path) -> bool:
    """Heuristic filter for HA core log candidates."""
    name = path.name.lower()
    return (
        name.endswith(".log")
        and (
            "home-assistant" in name
            or "homeassistant" in name
            or name == "core.log"
            or "hass" in name
        )
    )


def get_ha_core_log_path() -> Optional[Path]:
    """Find the HA core log file."""
    paths_checked: list[str] = []

    # 1) Explicit env override for unusual installations
    custom_raw = os.environ.get("HA_CORE_LOG_PATH")
    custom_path = Path(custom_raw).expanduser() if custom_raw else None
    if custom_path:
        paths_checked.append(str(custom_path))
        if custom_path.exists() and custom_path.is_file():
            logger.info("logs.ha_core_log_found", path=str(custom_path), source="env")
            return custom_path

    # 2) Known common locations
    for path in CORE_LOG_PATHS:
        paths_checked.append(str(path))
        if path.exists():
            logger.info("logs.ha_core_log_found", path=str(path), source="known_path")
            return path

    # 3) Recursive probe under /config for log-like names
    config_root = Path("/config")
    if config_root.exists():
        candidates: list[Path] = []
        for candidate in config_root.rglob("*.log"):
            paths_checked.append(str(candidate))
            if candidate.is_file() and _is_plausible_core_log(candidate):
                candidates.append(candidate)

        if candidates:
            newest = max(candidates, key=lambda p: p.stat().st_mtime)
            logger.info("logs.ha_core_log_found", path=str(newest), source="recursive_probe")
            return newest

    _warn_missing_log_throttled(paths_checked)
    return None


def snapshot_log_tail(
    log_path: Optional[str | Path] = None,
    max_bytes: int = 500_000,
    compress: bool = True,
) -> Optional[str]:
    """
    Capture the tail of a log file atomically.

    Args:
        log_path: Path to log file. If None, uses HA's core.log.
        max_bytes: Maximum bytes to capture from tail.
        compress: If True, return base64-encoded gzip; otherwise plain text.

    Returns:
        Snapshot string (base64 gzip or plain text), or None if unavailable.
    """
    try:
        if log_path is None:
            log_path = get_ha_core_log_path()
            if not log_path:
                logger.debug("logs.no_ha_core_log")
                return None

        log_path = Path(log_path)
        if not log_path.exists():
            logger.debug("logs.log_not_found", path=str(log_path))
            return None

        # Atomically read tail without loading entire file when seek is available.
        # Some streams (e.g. /proc/1/fd/1) are not seekable, so we keep a rolling
        # tail buffer as a fallback.
        with open(log_path, "rb") as f:
            try:
                f.seek(0, 2)  # Seek to end
                size = f.tell()
                start = max(0, size - max_bytes)
                f.seek(start)
                data = f.read()
            except (OSError, ValueError):
                chunks: deque[bytes] = deque()
                total = 0
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    while total > max_bytes and chunks:
                        removed = chunks.popleft()
                        total -= len(removed)
                data = b"".join(chunks)

        # Decode with error replacement for corrupted bytes
        text = data.decode(errors="replace")

        if compress:
            # Compress and base64 encode
            compressed = gzip.compress(text.encode(), compresslevel=6)
            encoded = base64.b64encode(compressed).decode("ascii")
            logger.debug(
                "logs.snapshot_captured",
                source_path=str(log_path),
                size=len(text),
                compressed_size=len(encoded),
            )
            return encoded
        else:
            return text

    except Exception as e:
        logger.exception("logs.snapshot_error", error=str(e))
        return None


def decode_log_snapshot(snapshot: str, encoded: bool = True) -> Optional[str]:
    """
    Decode a log snapshot back to original text.

    Args:
        snapshot: The snapshot string (base64 gzip or plain).
        encoded: If True, snapshot is base64-encoded gzip; otherwise plain text.

    Returns:
        Decoded log text, or None if decoding fails.
    """
    try:
        if encoded:
            decoded = base64.b64decode(snapshot)
            text = gzip.decompress(decoded).decode(errors="replace")
            return text
        else:
            return snapshot
    except Exception as e:
        logger.exception("logs.decode_error", error=str(e))
        return None


def parse_log_lines(
    snapshot: str,
    encoded: bool = True,
    limit: int = 100,
) -> list[dict[str, str]]:
    """
    Parse log snapshot into structured lines.

    Args:
        snapshot: The snapshot string.
        encoded: If True, snapshot is base64-encoded gzip.
        limit: Maximum number of lines to return.

    Returns:
        List of log entries with timestamp, level, message.
    """
    text = decode_log_snapshot(snapshot, encoded=encoded)
    if not text:
        return []

    lines = text.strip().split("\n")[-limit:]
    entries = []

    for line in lines:
        if not line.strip():
            continue

        # Try to parse ISO log format: "2026-03-18 11:32:03 [level] message"
        # or standard format: "2026-03-18T11:32:03..."
        try:
            # Simple split on first space between timestamp and level indicator
            if "[" in line:
                ts_part, rest = line.split("[", 1)
                level, msg = rest.split("]", 1)
                entries.append(
                    {
                        "timestamp": ts_part.strip(),
                        "level": level.lower(),
                        "message": msg.strip(),
                    }
                )
            else:
                # Fallback: treat entire line as message
                entries.append(
                    {
                        "timestamp": "",
                        "level": "info",
                        "message": line,
                    }
                )
        except Exception:
            # If parsing fails, just add the raw line
            entries.append(
                {
                    "timestamp": "",
                    "level": "unknown",
                    "message": line,
                }
            )

    return entries


def get_log_summary(max_bytes: int = 100_000) -> dict[str, any]:
    """
    Get a summary of log state for health/diagnostics.

    Returns dict with:
        - latest_tail: base64 gzip snapshot of tail
        - size_bytes: size of uncompressed tail
        - error_count: approximate count of [error] lines in tail
        - warning_count: approximate count of [warning] lines in tail
        - last_entry: last log entry timestamp (if parseable)
    """
    try:
        source = "ha_core_log"
        snapshot = snapshot_log_tail(max_bytes=max_bytes, compress=True)

        # Fallback to addon stdout if core log file is unavailable.
        if not snapshot:
            for addon_log in ADDON_LOG_PATHS:
                snapshot = snapshot_log_tail(addon_log, max_bytes=max_bytes, compress=True)
                if snapshot:
                    source = "addon_stdout"
                    break

        if not snapshot:
            return {
                "available": False,
                "error": "No log file found or access denied",
            }

        # Parse to extract summary
        text = decode_log_snapshot(snapshot, encoded=True)
        if not text:
            return {
                "available": False,
                "error": "Could not decode snapshot",
            }

        lines = text.split("\n")
        error_count = sum(1 for line in lines if "[error" in line.lower())
        warning_count = sum(1 for line in lines if "[warning" in line.lower())

        # Extract last timestamp from last line
        last_entry = ""
        if lines:
            last_line = lines[-1]
            if "[" in last_line:
                last_entry = last_line.split("[")[0].strip()

        return {
            "available": True,
            "source": source,
            "snapshot": snapshot,
            "size_bytes": len(text),
            "line_count": len([l for l in lines if l.strip()]),
            "error_count": error_count,
            "warning_count": warning_count,
            "last_entry_ts": last_entry,
        }

    except Exception as e:
        logger.exception("logs.summary_error", error=str(e))
        return {
            "available": False,
            "error": str(e),
        }
