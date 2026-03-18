"""Tests for snapshot functionality."""

import tempfile
from pathlib import Path

import pytest

from backend.snapshot import snapshot_tail, snapshot_tail_size, snapshot_tail_decode


class TestSnapshot:
    """Test atomic log snapshot capture."""

    def test_snapshot_tail_basic(self):
        """snapshot_tail should capture file tail."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("line 1\nline 2\nline 3\nline 4\n")
            filepath = f.name

        try:
            snapshot = snapshot_tail(filepath, max_bytes=100, compress=False)
            assert snapshot is not None
            assert "line 3" in snapshot
            assert "line 4" in snapshot
        finally:
            Path(filepath).unlink()

    def test_snapshot_tail_large_file(self):
        """snapshot_tail should not read entire large file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            # Write 1MB of content
            for i in range(10000):
                f.write(f"log line {i}\n")
            filepath = f.name

        try:
            snapshot = snapshot_tail(filepath, max_bytes=10000, compress=False)
            assert snapshot is not None
            # Should only contain last ~10KB, not the first lines
            assert "log line 0" not in snapshot
            assert "log line 9999" in snapshot
        finally:
            Path(filepath).unlink()

    def test_snapshot_tail_compressed(self):
        """snapshot_tail with compression should produce base64 gzip."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("important log data\n" * 100)
            filepath = f.name

        try:
            snapshot = snapshot_tail(filepath, compress=True)
            assert snapshot is not None
            # Should be valid base64 gzip
            import base64
            import gzip

            try:
                decoded = base64.b64decode(snapshot)
                decompressed = gzip.decompress(decoded)
                assert b"important log data" in decompressed
            except Exception as e:
                pytest.fail(f"Snapshot is not valid base64 gzip: {e}")
        finally:
            Path(filepath).unlink()

    def test_snapshot_nonexistent_file(self):
        """snapshot_tail should return None for missing file."""
        snapshot = snapshot_tail("/nonexistent/file.log")
        assert snapshot is None

    def test_snapshot_size(self):
        """snapshot_tail_size should return correct size."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            content = "test data\n" * 100
            f.write(content)
            filepath = f.name

        try:
            snapshot = snapshot_tail(filepath, compress=True)
            size = snapshot_tail_size(snapshot, encoded=True)
            assert size > 0
            # Should be close to original size
            assert size < len(content) * 1.2  # Allow for compression variance
        finally:
            Path(filepath).unlink()

    def test_snapshot_decode(self):
        """snapshot_tail_decode should restore original content."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            original = "line1\nline2\nline3\n"
            f.write(original)
            filepath = f.name

        try:
            snapshot = snapshot_tail(filepath, compress=True)
            decoded = snapshot_tail_decode(snapshot, encoded=True)
            assert "line1" in decoded
            assert "line3" in decoded
        finally:
            Path(filepath).unlink()

    def test_snapshot_uncompressed(self):
        """snapshot_tail_size and decode should work with uncompressed."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content\n")
            filepath = f.name

        try:
            snapshot = snapshot_tail(filepath, compress=False)
            size = snapshot_tail_size(snapshot, encoded=False)
            assert size > 0
            decoded = snapshot_tail_decode(snapshot, encoded=False)
            assert "test content" in decoded
        finally:
            Path(filepath).unlink()

    def test_snapshot_empty_file(self):
        """snapshot_tail should handle empty files."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            filepath = f.name

        try:
            snapshot = snapshot_tail(filepath, compress=False)
            assert snapshot == ""
        finally:
            Path(filepath).unlink()
