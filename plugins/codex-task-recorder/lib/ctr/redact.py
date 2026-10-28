"""Remove credentials from anything before it is written to disk.

Redaction favours privacy over fidelity: a false positive costs a few
characters of a recorded command, a false negative leaks a secret.
"""
from __future__ import annotations

import json
import re
from collections import Counter

SENSITIVE_FILE_PLACEHOLDER = "[REDACTED:sensitive_file]"

# Order matters: specific token formats first, then generic header/URL/assignment rules.
_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
]

_AUTH_HEADER = re.compile(
    r"(?i)\b(authorization|proxy-authorization|set-cookie|cookie|x-api-key)(\s*:\s*)([^\r\n\"']+)")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{16,}=*")
_URL_CREDENTIALS = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:)([^/\s@]+)(@)")
_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key"
    r"|private[_-]?key|client[_-]?secret|credential)[A-Za-z0-9_.-]*)"
    r"(\s*[:=]\s*)(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s\"',;()\[\]{}]+)")
_NOT_A_SECRET = {"str", "int", "bool", "none", "null", "true", "false", "string",
                 "required", "optional", "any", "bytes", "float", "undefined"}

_KEY_SUBSTRINGS = ("password", "passwd", "secret", "api_key", "apikey", "api-key", "access_key",
                   "accesskey", "private_key", "privatekey", "authorization", "cookie",
                   "credential", "session_key", "bearer")
_KEY_EXACT = {"pwd", "token", "auth", "auth_token", "access_token", "refresh_token",
              "id_token", "session_token"}

_SENSITIVE_FILE = re.compile(
    r"(?i)(?:^|[\\/\s\"'=:(])"
    r"(auth\.json|\.env(?:\.[\w.-]+)?|id_(?:rsa|ed25519|ecdsa|dsa)[\w.-]*|[\w.-]+\.(?:pem|pfx|p12)"
    r"|cap_sid|credentials(?:\.json)?|\.netrc|\.git-credentials|\.npmrc|\.pypirc)"
    r"(?=$|[\s\"'\\/;|&),])")


def _assignment_value_is_secret(raw: str) -> bool:
    value = raw.strip("\"'")
    if len(value) < 4 or value.startswith(("[REDACTED", "$", "%", "${")):
        return False
    if value.isdigit() or value.lower() in _NOT_A_SECRET:
        return False
    return True


def redact_text(text: str) -> tuple[str, Counter]:
    counts: Counter = Counter()
    for kind, pattern in _VALUE_PATTERNS:
        text, n = pattern.subn(f"[REDACTED:{kind}]", text)
        if n:
            counts[kind] += n

    def header(m: re.Match[str]) -> str:
        counts["auth_header"] += 1
        return f"{m.group(1)}{m.group(2)}[REDACTED:auth_header]"

    text = _AUTH_HEADER.sub(header, text)
    text, n = _BEARER.subn("Bearer [REDACTED:bearer]", text)
    if n:
        counts["bearer"] += n
    text, n = _URL_CREDENTIALS.subn(r"\1[REDACTED:url_password]\3", text)
    if n:
        counts["url_password"] += n

    def assignment(m: re.Match[str]) -> str:
        if not _assignment_value_is_secret(m.group(3)):
            return m.group(0)
        counts["assignment"] += 1
        return f"{m.group(1)}{m.group(2)}[REDACTED:assignment]"

    text = _ASSIGNMENT.sub(assignment, text)
    return text, counts


def _sensitive_key(key: str) -> bool:
    k = key.lower()
    return (k in _KEY_EXACT or k.endswith("_token") or k.endswith("-token")
            or any(s in k for s in _KEY_SUBSTRINGS))


def redact_obj(obj: object) -> tuple[object, Counter]:
    """Return a redacted deep copy of a JSON-like value and per-kind counts."""
    counts: Counter = Counter()

    def walk(value: object) -> object:
        if isinstance(value, str):
            out, c = redact_text(value)
            counts.update(c)
            return out
        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                if isinstance(k, str) and isinstance(v, str) and v and _sensitive_key(k):
                    counts["key"] += 1
                    result[k] = "[REDACTED:key]"
                else:
                    result[k] = walk(v)
            return result
        if isinstance(value, (list, tuple)):
            return [walk(v) for v in value]
        return value

    return walk(obj), counts


def mentions_sensitive_file(obj: object) -> bool:
    """True when a tool input refers to a credential file (its output is then dropped)."""
    if obj is None:
        return False
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    return _SENSITIVE_FILE.search(text) is not None
