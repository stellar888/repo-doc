from __future__ import annotations

import re
from pathlib import PurePosixPath

SUSPICIOUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"(print|reveal|exfiltrate).{0,40}(secret|token|environment)", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"curl\s+https?://", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
)

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def scan_untrusted_text(text: str) -> list[str]:
    flags: list[str] = []
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            flags.append(f"suspicious_input:{pattern.pattern}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            flags.append("possible_secret_in_input")
    return list(dict.fromkeys(flags))


def path_is_allowed(path: str, allowed: tuple[str, ...]) -> bool:
    normalized = str(PurePosixPath(path))
    if normalized.startswith("../") or normalized.startswith("/"):
        return False

    for item in allowed:
        candidate = str(PurePosixPath(item))
        if normalized == candidate:
            return True
        if not candidate.endswith(".md") and normalized.startswith(candidate.rstrip("/") + "/"):
            return True
    return False


def validate_proposal_paths(paths: list[str], allowed: tuple[str, ...]) -> list[str]:
    return [path for path in paths if not path_is_allowed(path, allowed)]


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)
