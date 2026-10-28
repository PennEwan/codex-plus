"""Client for the recharge backend (docs/recharge-api.md). Standard library only.

Error types tell the caller what is known about the request:
  NotSent   — it certainly never reached the backend (refused, DNS, TLS handshake);
  Unknown   — it may have been processed (timeout or connection lost after sending);
  HttpError — the backend answered with an error code.
No exception ever carries the CDK, the binding token or a request body.
"""
from __future__ import annotations

import http.client
import json
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

from . import __version__

CLIENT = f"codex-cdk-recharge/{__version__}"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class InsecureUrl(ValueError):
    """Base URL that is neither https nor a local address."""


class ApiError(Exception):
    pass


class NotSent(ApiError):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind  # refused / dns / tls / timeout / other


class Unknown(ApiError):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


class BadResponse(ApiError):
    def __init__(self, status: int):
        super().__init__(f"bad response ({status})")
        self.status = status


class HttpError(ApiError):
    def __init__(self, status: int, code: str, message: str | None, retry_after: int | None):
        super().__init__(f"{status} {code}")
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after


def check_base_url(base_url: str) -> str:
    parts = urlsplit(base_url or "")
    try:
        parts.port
    except ValueError:
        raise InsecureUrl("充值服务地址格式不对（端口无效）") from None
    if parts.scheme == "https" and parts.hostname:
        return base_url.rstrip("/")
    if parts.scheme == "http" and parts.hostname in LOCAL_HOSTS:
        return base_url.rstrip("/")
    raise InsecureUrl("充值服务地址必须是 https://（本机调试地址除外）")


def is_local(base_url: str | None) -> bool:
    return bool(base_url) and urlsplit(base_url).hostname in LOCAL_HOSTS


def _not_sent_kind(reason: object) -> str | None:
    if isinstance(reason, ConnectionRefusedError):
        return "refused"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"  # raised while connecting / sending a tiny body
    if isinstance(reason, OSError) and getattr(reason, "winerror", None) in (10051, 10065):
        return "unreachable"  # network / host unreachable
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: urllib would carry the Authorization header to any Location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then raises HTTPError for the 3xx


class Api:
    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = check_base_url(base_url)
        self.timeout = timeout
        # A local (mock) backend is always reached directly; remote ones honour the system proxy.
        handlers = [urllib.request.ProxyHandler({})] if is_local(self.base_url) else []
        self._opener = urllib.request.build_opener(_NoRedirect, *handlers)

    def bind(self, chatgpt_account_id: str, email: str) -> dict:
        return self._call("POST", "/v1/bindings", None,
                          {"chatgpt_account_id": chatgpt_account_id, "email": email})

    def redeem(self, token: str, cdk: str, chatgpt_account_id: str) -> dict:
        return self._call("POST", "/v1/redemptions", token,
                          {"cdk": cdk, "chatgpt_account_id": chatgpt_account_id})

    def get_redemption(self, token: str, redemption_id: str) -> dict:
        return self._call("GET", "/v1/redemptions/" + quote(redemption_id, safe=""), token, None)

    def _call(self, method: str, path: str, token: str | None, body: dict | None) -> dict:
        headers = {"Accept": "application/json", "X-Cdkr-Client": CLIENT}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                return self._parse_ok(resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                # A redirected POST may already have been processed; a redirected GET is just unusable.
                raise (Unknown("redirect") if method == "POST" else BadResponse(exc.code)) from None
            raise self._http_error(exc) from None
        except urllib.error.URLError as exc:
            # urllib wraps errors raised while connecting and sending the request.
            kind = _not_sent_kind(exc.reason)
            if kind:
                raise NotSent(kind) from None
            raise Unknown("send_failed") from None
        except (TimeoutError, socket.timeout):
            raise Unknown("timeout") from None
        except (ConnectionError, http.client.HTTPException, OSError):
            raise Unknown("connection_lost") from None

    @staticmethod
    def _parse_ok(status: int, raw: bytes) -> dict:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise BadResponse(status) from None
        if not isinstance(value, dict):
            raise BadResponse(status)
        return value

    @staticmethod
    def _http_error(exc: urllib.error.HTTPError) -> HttpError:
        try:
            raw = exc.read()
        except (OSError, http.client.HTTPException):
            raw = b""
        code, message = "", None
        try:
            err = json.loads(raw.decode("utf-8")).get("error") or {}
            code = str(err.get("code") or "")
            message = err.get("message") if isinstance(err.get("message"), str) else None
        except (UnicodeDecodeError, ValueError, AttributeError):
            pass
        if not code:
            code = "rate_limited" if exc.code == 429 else ("server_error" if exc.code >= 500 else "http_error")
        retry_after = None
        value = exc.headers.get("Retry-After") if exc.headers else None
        if value and value.strip().isdigit():
            retry_after = int(value.strip())
        return HttpError(exc.code, code, message, retry_after)
