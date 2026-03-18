"""Tests for masking functionality."""

import pytest
from backend.masking import mask_secrets, MaskingAuditor


class TestMasking:
    """Test secret masking patterns."""

    def test_mask_bearer_token(self):
        """Bearer tokens should be masked."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        masked = mask_secrets(text)
        assert "eyJhbGc" not in masked
        assert "***REDACTED***" in masked

    def test_mask_api_key_equals(self):
        """API keys with = should be masked."""
        text = "api_key=sk_live_abc123def456xyz789"
        masked = mask_secrets(text)
        assert "sk_live" not in masked
        assert "***REDACTED***" in masked

    def test_mask_api_key_colon(self):
        """API keys with : should be masked."""
        text = "api-key: super_secret_token_1234567890"
        masked = mask_secrets(text)
        assert "super_secret" not in masked
        assert "***REDACTED***" in masked

    def test_mask_password(self):
        """Passwords should be masked."""
        text = "password=MySecurePassword123"
        masked = mask_secrets(text)
        assert "MySecurePassword" not in masked
        assert "***REDACTED***" in masked

    def test_mask_long_hex(self):
        """Long hex strings (>32 chars) should be masked."""
        text = "token=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        masked = mask_secrets(text)
        assert "a1b2c3d4" not in masked
        assert "***REDACTED***" in masked

    def test_mask_uuid(self):
        """UUIDs should be masked."""
        text = "session=550e8400-e29b-41d4-a716-446655440000"
        masked = mask_secrets(text)
        assert "550e8400" not in masked
        assert "***REDACTED***" in masked

    def test_auditor_tracking(self):
        """Auditor should track masked patterns."""
        auditor = MaskingAuditor()
        text = "Bearer mytoken and password=secret"
        masked = mask_secrets(text, auditor)

        report = auditor.report()
        assert report["total_masked"] >= 2
        assert report["patterns"]["bearer_token"] >= 1
        assert report["patterns"]["password"] >= 1

    def test_no_false_positives(self):
        """Normal text should not be masked."""
        text = "This is a normal log message with no secrets"
        masked = mask_secrets(text)
        assert masked == text

    def test_multiple_patterns(self):
        """Multiple patterns in one text should all be masked."""
        text = (
            "Auth: Bearer token123456789abcdef123456789abcdef "
            "api_key=secret123456789abcdef password=pass123"
        )
        masked = mask_secrets(text)
        assert "token123456789abcdef" not in masked
        assert "secret123456789abcdef" not in masked
        assert "pass123" not in masked
        assert masked.count("***REDACTED***") >= 3

    def test_empty_string(self):
        """Empty string should be handled gracefully."""
        masked = mask_secrets("")
        assert masked == ""

    def test_none_value(self):
        """None should be handled gracefully."""
        masked = mask_secrets(None)
        assert masked == ""
