"""Atomic snapshot utilities for log file capture."""

from __future__ import annotations

import gzip
import base64
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


def snapshot_tail(
    filepath: str | Path,
    max_bytes: int = 200_000,
    compress: bool = True,
) -> Optional[str]:
    """
    Atomically capture the last max_bytes of a file.

    Uses seek/tell to avoid reading entire file into memory.
    Returns base64-encoded gzip if compress=True, otherwise plain text.

    Returns None if file doesn't exist or read fails.
    """
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            logger.warning("snapshot_tail.file_not_found", path=filepath)
            return None

        # Open in binary, seek to end, compute start position
        with open(filepath, "rb") as f:
            f.seek(0, 2)  # Seek to end
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()

        # Decode with error replacement for non-UTF8 bytes
        text = data.decode(errors="replace")

        if compress:
            # Compress and base64 encode
            compressed = gzip.compress(text.encode(), compresslevel=9)
            encoded = base64.b64encode(compressed).decode("ascii")
            return encoded
        else:
            return text

    except Exception as e:
        logger.exception("snapshot_tail.error", path=filepath, error=str(e))
        return None


def snapshot_tail_size(snapshot: str | None, encoded: bool = True) -> int:
    """
    Return the approximate size of a snapshot.

    If encoded=True, assumes snapshot is base64 gzip.
    Otherwise returns string length.
    """
    if not snapshot:
        return 0

    if encoded:
        try:
            compressed = base64.b64decode(snapshot)
            decompressed = gzip.decompress(compressed)
            return len(decompressed)
        except Exception:
            return len(snapshot)  # Fallback
    else:
        return len(snapshot)


def snapshot_tail_decode(snapshot: str | None, encoded: bool = True) -> str:
    """
    Decode a snapshot back to text.

    If encoded=True, assumes snapshot is base64 gzip.
    """
    if not snapshot:
        return ""

    if not encoded:
        return snapshot

    try:
        compressed = base64.b64decode(snapshot)
        decompressed = gzip.decompress(compressed)
        return decompressed.decode(errors="replace")
    except Exception as e:
        logger.exception("snapshot_tail_decode.error", error=str(e))
        return ""
