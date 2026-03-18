"""Secret masking utilities for log sanitization."""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Patterns that match sensitive data
BEARER_TOKEN = re.compile(r'Bearer\s+[a-zA-Z0-9\-_.]+', re.IGNORECASE)
API_KEY = re.compile(r'api[_-]?key\s*[:=]\s*[a-zA-Z0-9\-_.]+', re.IGNORECASE)
PASSWORD = re.compile(r'password\s*[:=]\s*[^,\s]+', re.IGNORECASE)
HEX_STRING = re.compile(r'\b[a-f0-9]{32,}\b')  # 32+ char hex (common token length)
UUID_LIKE = re.compile(r'\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b')


class MaskingAuditor:
    """Track what was masked for security auditing."""

    def __init__(self) -> None:
        self.mask_count = 0
        self.patterns_matched: dict[str, int] = {
            "bearer_token": 0,
            "api_key": 0,
            "password": 0,
            "hex_string": 0,
            "uuid": 0,
        }

    def record(self, pattern_name: str) -> None:
        """Record a masked pattern."""
        self.mask_count += 1
        if pattern_name in self.patterns_matched:
            self.patterns_matched[pattern_name] += 1

    def report(self) -> dict[str, Any]:
        """Return audit summary."""
        return {
            "total_masked": self.mask_count,
            "patterns": self.patterns_matched,
            "note": "Secrets were masked but not stored. See patterns for audit trail.",
        }


def mask_secrets(text: str | None, auditor: MaskingAuditor | None = None) -> str:
    """
    Mask sensitive data in text.

    Patterns masked:
    - Bearer tokens (Bearer <token>)
    - API keys (api_key=... or api-key:...)
    - Passwords (password=...)
    - Long hex strings (>32 chars)
    - UUIDs that look like tokens
    """
    if not text:
        return text or ""

    if auditor is None:
        auditor = MaskingAuditor()

    # Mask Bearer tokens
    def replace_bearer(match: re.Match[str]) -> str:
        auditor.record("bearer_token")
        return "Bearer ***REDACTED***"

    text = BEARER_TOKEN.sub(replace_bearer, text)

    # Mask API keys
    def replace_api_key(match: re.Match[str]) -> str:
        auditor.record("api_key")
        prefix = text[match.start() : match.start() + match.group().find("=")]
        return prefix + "***REDACTED***"

    text = API_KEY.sub(replace_api_key, text)

    # Mask passwords
    def replace_password(match: re.Match[str]) -> str:
        auditor.record("password")
        return "password=***REDACTED***"

    text = PASSWORD.sub(replace_password, text)

    # Mask hex strings >32 chars
    def replace_hex(match: re.Match[str]) -> str:
        auditor.record("hex_string")
        return "***REDACTED***"

    text = HEX_STRING.sub(replace_hex, text)

    # Mask UUIDs
    def replace_uuid(match: re.Match[str]) -> str:
        auditor.record("uuid")
        return "***REDACTED***"

    text = UUID_LIKE.sub(replace_uuid, text)

    return text


def mask_file_content(
    content: str,
    enabled: bool = True,
    auditor: MaskingAuditor | None = None,
) -> tuple[str, MaskingAuditor]:
    """
    Mask file content if enabled.

    Returns: (masked_content, auditor_report)
    """
    if auditor is None:
        auditor = MaskingAuditor()

    if enabled:
        content = mask_secrets(content, auditor)

    return content, auditor
