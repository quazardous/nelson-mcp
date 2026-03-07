# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared HTTP client utilities for provider modules.

Centralizes endpoint parsing, connection management, and JSON
request/response handling used across image providers.
"""

import http.client
import json
import logging
import ssl
import urllib.parse
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("nelson.http_client")


class ParsedEndpoint:
    """Parsed HTTP endpoint with host, port, base path, and SSL flag."""

    __slots__ = ("host", "port", "base_path", "use_ssl")

    def __init__(self, host: str, port: int, base_path: str, use_ssl: bool):
        self.host = host
        self.port = port
        self.base_path = base_path
        self.use_ssl = use_ssl

    def __repr__(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        return "%s://%s:%d%s" % (scheme, self.host, self.port, self.base_path)


def parse_endpoint(url: str, default_port: int = 80) -> ParsedEndpoint:
    """Parse an endpoint URL into components.

    Args:
        url: Full URL like ``http://127.0.0.1:7860/prefix``.
        default_port: Port to use when none is specified in the URL.

    Returns:
        ParsedEndpoint with host, port, base_path, use_ssl.
    """
    parsed = urllib.parse.urlparse(url)
    use_ssl = parsed.scheme == "https"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if use_ssl else default_port)
    base_path = (parsed.path or "").rstrip("/")
    return ParsedEndpoint(host, port, base_path, use_ssl)


def http_request(
    endpoint: str,
    method: str,
    path: str,
    body: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    default_port: int = 80,
) -> Tuple[int, bytes]:
    """Send an HTTP request and return (status_code, response_body).

    Handles connection lifecycle with proper cleanup on all code paths.

    Args:
        endpoint: Base URL (e.g. ``http://127.0.0.1:7860``).
        method: HTTP method (GET, POST, etc.).
        path: Request path appended after the endpoint's base path.
        body: Request body — dict (JSON-encoded) or bytes.
        headers: Extra headers. Content-Type defaults to application/json
                 when body is a dict.
        timeout: Connection timeout in seconds.
        default_port: Port to use when none is specified in the URL.

    Returns:
        (status_code, response_bytes) tuple.

    Raises:
        Exception: On connection or protocol errors.
    """
    ep = parse_endpoint(endpoint, default_port=default_port)

    if ep.use_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(ep.host, ep.port, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(ep.host, ep.port, timeout=timeout)

    req_headers = dict(headers) if headers else {}
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        else:
            data = body

    try:
        conn.request(method, ep.base_path + path, body=data, headers=req_headers)
        resp = conn.getresponse()
        status = resp.status
        resp_body = resp.read()
    finally:
        conn.close()

    return status, resp_body


def http_json(
    endpoint: str,
    method: str,
    path: str,
    body: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    default_port: int = 80,
) -> Tuple[int, Any]:
    """Like http_request but JSON-decodes the response body.

    Returns:
        (status_code, parsed_json) tuple. parsed_json is the raw
        response string if JSON decoding fails.
    """
    status, raw = http_request(
        endpoint, method, path, body=body, headers=headers,
        timeout=timeout, default_port=default_port,
    )
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return status, raw.decode("utf-8", errors="replace")
