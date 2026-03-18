"""Real-time log file tailer (non-blocking async)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

import structlog

from .parser import LogEvent, LogParser

logger = structlog.get_logger(__name__)


class LogTailer:
    """
    Continuously tail a log file and emit parsed events.

    Non-blocking, async operation. Handles file rotation gracefully.
    """

    def __init__(
        self,
        filepath: str | Path,
        on_event: Callable[[LogEvent], None],
        check_interval: float = 1.0,
    ) -> None:
        self.filepath = Path(filepath)
        self.on_event = on_event
        self.check_interval = check_interval
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._file_pos = 0  # Byte offset in current file
        self._inode: int | None = None  # For detecting file rotation
        self._parser = LogParser()

    async def start(self) -> None:
        """Start tailing in background."""
        self._running = True
        self._task = asyncio.create_task(self._tail_loop())
        logger.info("log_tailer.started", path=self.filepath)

    async def stop(self) -> None:
        """Stop tailing."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("log_tailer.stopped", path=self.filepath)

    async def _tail_loop(self) -> None:
        """Main tail loop."""
        while self._running:
            try:
                await self._read_new_content()
            except Exception:
                logger.exception("log_tailer.error")

            await asyncio.sleep(self.check_interval)

    async def _read_new_content(self) -> None:
        """Read any new content added to the file."""
        if not self.filepath.exists():
            return

        # Check for file rotation (inode change on Unix)
        try:
            stat = self.filepath.stat()
            if self._inode is not None and self._inode != stat.st_ino:
                # File was rotated
                logger.info("log_tailer.file_rotated", path=self.filepath)
                self._file_pos = 0
                self._inode = stat.st_ino
                self._parser = LogParser()
                return

            self._inode = stat.st_ino
        except (OSError, AttributeError):
            # Windows or missing inode info
            pass

        try:
            with open(self.filepath, "r", errors="replace") as f:
                # Check if file shrank (truncation)
                current_size = f.seek(0, 2)
                if current_size < self._file_pos:
                    logger.info("log_tailer.file_truncated", path=self.filepath)
                    self._file_pos = 0
                    self._parser = LogParser()

                # Seek to last known position
                f.seek(self._file_pos)
                new_lines = f.readlines()
                self._file_pos = f.tell()

                # Parse new lines
                for line in new_lines:
                    event = self._parser.parse_line(line)
                    if event:
                        self.on_event(event)

        except Exception as e:
            logger.exception(
                "log_tailer.read_error",
                path=self.filepath,
                error=str(e),
            )
