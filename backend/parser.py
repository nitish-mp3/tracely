"""HA log file parser with multiline traceback grouping."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Exact regex from spec
LOG_LINE_PATTERN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"\[(?P<component>[^\]]+)\]\s+"
    r"(?P<msg>.*)$"
)


@dataclass
class LogEvent:
    """Parsed log event with optional multiline continuation."""

    timestamp: str  # ISO8601
    level: str
    component: str
    message: str
    raw: str  # Full multiline text


class LogParser:
    """Parse HA log file into structured events."""

    def __init__(self) -> None:
        self.buffer: list[str] = []  # Current multiline block
        self.events: list[LogEvent] = []

    def parse_line(self, line: str) -> Optional[LogEvent]:
        """
        Parse a single line.

        If it matches the header pattern, flush previous buffer and start new event.
        Otherwise, append to current buffer (continuation/traceback).

        Returns the flushed event (if any).
        """
        match = LOG_LINE_PATTERN.match(line.rstrip("\n"))

        if match:
            # Flush previous block if any
            flushed = None
            if self.buffer:
                flushed = self._flush_buffer()

            # Start new block
            self.buffer = [line]
            return flushed
        else:
            # Continuation line
            if self.buffer:
                self.buffer.append(line)
            else:
                # Orphaned continuation - treat as standalone
                self.buffer = [line]
            return None

    def finalize(self) -> Optional[LogEvent]:
        """Flush any remaining buffered content."""
        if self.buffer:
            return self._flush_buffer()
        return None

    def _flush_buffer(self) -> LogEvent:
        """Convert buffered lines into a LogEvent."""
        raw = "".join(self.buffer).rstrip("\n")
        self.buffer = []

        # Try to parse the first line
        if not raw:
            return LogEvent(
                timestamp="",
                level="UNKNOWN",
                component="",
                message="(empty block)",
                raw=raw,
            )

        first_line = raw.split("\n")[0]
        match = LOG_LINE_PATTERN.match(first_line)

        if match:
            ts_str = match.group("ts")
            # Convert to ISO8601 format
            try:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                timestamp = dt.isoformat() + "Z"
            except (ValueError, AttributeError):
                timestamp = ts_str

            return LogEvent(
                timestamp=timestamp,
                level=match.group("level"),
                component=match.group("component"),
                message=match.group("msg"),
                raw=raw,
            )
        else:
            # Could not parse - store as raw
            return LogEvent(
                timestamp="",
                level="UNKNOWN",
                component="",
                message=raw[:100],
                raw=raw,
            )


def parse_log_file(filepath: str) -> list[LogEvent]:
    """
    Parse entire log file and return list of events.

    Handles missing file gracefully.
    """
    from pathlib import Path

    parser = LogParser()
    events = []

    try:
        if not Path(filepath).exists():
            logger.warning("parse_log_file.not_found", path=filepath)
            return []

        with open(filepath, "r", errors="replace") as f:
            for line in f:
                event = parser.parse_line(line)
                if event:
                    events.append(event)

        # Finalize any remaining
        if last := parser.finalize():
            events.append(last)

        logger.info("parse_log_file.complete", path=filepath, count=len(events))
        return events

    except Exception as e:
        logger.exception("parse_log_file.error", path=filepath, error=str(e))
        return []
