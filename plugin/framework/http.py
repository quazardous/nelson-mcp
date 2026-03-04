# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared HTTP utilities (sync requests, error formatting, SSL).

Used by aihordeclient, pricing, and any module needing simple HTTP.
"""

import json
import ssl
import socket
import http.client
import urllib.request
import urllib.error

from plugin.framework.constants import USER_AGENT, APP_REFERER, APP_TITLE


def get_unverified_ssl_context():
    """Create an SSL context that doesn't verify certificates."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def format_error_message(e):
    """Map common exceptions to user-friendly advice."""
    msg = str(e)
    if isinstance(e, (urllib.error.HTTPError, http.client.HTTPResponse)):
        code = e.code if hasattr(e, "code") else e.status
        reason = e.reason if hasattr(e, "reason") else ""
        if code == 401:
            return "Invalid API Key. Please check your settings."
        if code == 403:
            return "API access Forbidden. Your key may lack permissions."
        if code == 404:
            return "Endpoint not found (404). Check your URL and Model."
        if code >= 500:
            return "Server error (%d). The provider is having issues." % code
        return "HTTP Error %d: %s" % (code, reason)

    if isinstance(e, (urllib.error.URLError, socket.error)):
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        if "Connection refused" in reason or "111" in reason:
            return "Connection Refused. Is your local AI server running?"
        if "getaddrinfo failed" in reason:
            return "DNS Error. Could not resolve the endpoint URL."
        return "Connection Error: %s" % reason

    if isinstance(e, socket.timeout) or "timed out" in msg.lower():
        return "Request Timed Out. Try increasing timeout in Settings."

    if "finish_reason=error" in msg:
        return "The AI provider reported an error. Try again."

    return msg


def format_error_for_display(e):
    """Return user-friendly error string for display."""
    return "Error: %s" % format_error_message(e)


def sync_request(url, data=None, headers=None, timeout=10, parse_json=True):
    """Blocking HTTP GET or POST.

    url: str or urllib.request.Request.
    data: optional bytes for POST.
    headers: optional dict (used only if url is str).
    Returns decoded JSON if parse_json else raw bytes.
    """
    if headers is None:
        headers = {}

    has_ua = any(k.lower() == "user-agent" for k in headers.keys())
    if not has_ua:
        headers["User-Agent"] = USER_AGENT
    if "HTTP-Referer" not in headers:
        headers["HTTP-Referer"] = APP_REFERER
    if "X-Title" not in headers:
        headers["X-Title"] = APP_TITLE

    if isinstance(url, str):
        req = urllib.request.Request(url, data=data, headers=headers)
    else:
        req = url

    ctx = get_unverified_ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            if parse_json:
                return json.loads(raw.decode("utf-8"))
            return raw
    except urllib.error.HTTPError as e:
        status = e.code
        reason = e.reason
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        msg = _format_http_error_response(status, reason, err_body)
        raise Exception(msg) from e


def _format_http_error_response(status, reason, err_body):
    """Build error message including response body."""
    base = "HTTP Error %d: %s" % (status, reason)
    if not err_body or not err_body.strip():
        return base
    try:
        data = json.loads(err_body)
        err = data.get("error")
        if isinstance(err, dict):
            detail = err.get("message") or err.get("msg") or ""
        else:
            detail = str(err) if err else ""
        if detail:
            return base + ". " + detail
    except (json.JSONDecodeError, TypeError):
        pass
    snippet = err_body.strip().replace("\n", " ")[:400]
    return base + ". " + snippet
