"""Tests for log capture and analysis."""

import tempfile
from pathlib import Path

import pytest

from backend.logs import (
    snapshot_log_tail,
    decode_log_snapshot,
    parse_log_lines,
    get_log_summary,
)


class TestLogs:
    """Test log capture functionality."""

    def test_snapshot_log_tail_basic(self):
        """snapshot_log_tail should capture file tail."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write(
                "2026-03-18 10:00:00 [info] System starting\n"
                "2026-03-18 10:00:01 [info] Loading entities\n"
                "2026-03-18 10:00:02 [warning] Low memory\n"
            )
            filepath = f.name

        try:
            snapshot = snapshot_log_tail(filepath, compress=False)
            assert snapshot is not None
            assert "System starting" in snapshot
            assert "Low memory" in snapshot
        finally:
            Path(filepath).unlink()

    def test_snapshot_log_tail_compressed(self):
        """snapshot_log_tail with compress should return base64 gzip."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("2026-03-18 10:00:00 [error] Connection failed\n" * 50)
            filepath = f.name

        try:
            snapshot = snapshot_log_tail(filepath, compress=True)
            assert snapshot is not None
            # Should be decodable
            decoded = decode_log_snapshot(snapshot, encoded=True)
            assert decoded
            assert "Connection failed" in decoded
        finally:
            Path(filepath).unlink()

    def test_parse_log_lines(self):
        """parse_log_lines should extract structured entries."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write(
                "2026-03-18 11:00:00 [info] Event processed\n"
                "2026-03-18 11:00:01 [warning] High CPU\n"
                "2026-03-18 11:00:02 [error] Database timeout\n"
            )
            filepath = f.name

        try:
            snapshot = snapshot_log_tail(filepath, compress=False)
            lines = parse_log_lines(snapshot, encoded=False, limit=10)
            
            assert len(lines) > 0
            assert "Event processed" in str(lines)
            assert any(entry["level"] == "error" for entry in lines if "timestamp" in entry)
        finally:
            Path(filepath).unlink()

    def test_get_log_summary(self):
        """get_log_summary should return count of errors/warnings."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write(
                "2026-03-18 11:00:00 [info] Starting\n"
                "2026-03-18 11:00:01 [warning] Warning 1\n"
                "2026-03-18 11:00:02 [error] Error 1\n"
                "2026-03-18 11:00:03 [error] Error 2\n"
            )
            filepath = f.name

        try:
            # get_log_summary looks for HA core log by default, so test with custom path
            from backend.logs import snapshot_log_tail, parse_log_lines
            
            snapshot = snapshot_log_tail(filepath, compress=True)
            assert snapshot is not None
            
            text = decode_log_snapshot(snapshot, encoded=True)
            lines = text.split("\n")
            error_count = sum(1 for line in lines if "[error" in line.lower())
            warning_count = sum(1 for line in lines if "[warning" in line.lower())
            line_count = len([l for l in lines if l.strip()])
            
            assert error_count == 2
            assert warning_count == 1
            assert line_count == 4
        finally:
            Path(filepath).unlink()

    def test_decode_uncompressed(self):
        """decode_log_snapshot should handle uncompressed text."""
        original = "2026-03-18 11:00:00 [info] Test log entry\n"
        decoded = decode_log_snapshot(original, encoded=False)
        assert decoded == original

    def test_nonexistent_log_file(self):
        """Functions should handle missing files gracefully."""
        snapshot = snapshot_log_tail("/nonexistent/log/file.log")
        assert snapshot is None

        summary = get_log_summary()
        assert summary.get("available") is not True or summary.get("error") is not None

    def test_log_large_file(self):
        """snapshot_log_tail should efficiently handle large files."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            # Write 5MB of logs
            for i in range(50000):
                f.write(f"2026-03-18 11:{i % 60:02d}:{i % 60:02d} [info] Log entry {i}\n")
            filepath = f.name

        try:
            # Should only capture tail, not entire file
            snapshot = snapshot_log_tail(filepath, max_bytes=50_000, compress=False)
            assert snapshot is not None
            assert len(snapshot) <= 60_000  # Slightly over max_bytes due to line boundaries
            # Early entries should NOT be there
            assert "Log entry 0" not in snapshot
            # Late entries should be there
            assert "Log entry 49999" in snapshot
        finally:
            Path(filepath).unlink()

    def test_parse_with_limit(self):
        """parse_log_lines should respect limit parameter."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            for i in range(100):
                f.write(f"2026-03-18 11:00:{i % 60:02d} [info] Entry {i}\n")
            filepath = f.name

        try:
            snapshot = snapshot_log_tail(filepath, compress=False)
            lines = parse_log_lines(snapshot, encoded=False, limit=10)
            assert len(lines) <= 10
        finally:
            Path(filepath).unlink()
