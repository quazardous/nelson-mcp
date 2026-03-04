# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Auto-generate and load self-signed TLS certificates."""

import logging
import os
import ssl
import subprocess

log = logging.getLogger("nelson.http.ssl")


def get_cert_dir():
    """Return the directory where TLS certificates are stored.

    Windows: %APPDATA%/mcp-certs/
    Linux:   ~/.config/libreoffice/mcp-certs/
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.join(os.path.expanduser("~"), ".config", "libreoffice")
    return os.path.join(base, "mcp-certs")


def ensure_certs():
    """Generate cert + key if not present. Returns (cert_path, key_path)."""
    cert_dir = get_cert_dir()
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "server.pem")
    key_path = os.path.join(cert_dir, "server-key.pem")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        log.info("TLS certificates found at %s", cert_dir)
        return cert_path, key_path
    _generate_self_signed(cert_path, key_path)
    return cert_path, key_path


def _generate_self_signed(cert_path, key_path):
    """Generate a self-signed certificate using openssl CLI."""
    cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", key_path, "-out", cert_path,
        "-days", "3650", "-nodes",
        "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ]
    try:
        kwargs = {"capture_output": True, "check": True, "timeout": 30}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(cmd, **kwargs)
        log.info("Generated self-signed certificate at %s", cert_path)
    except FileNotFoundError:
        raise RuntimeError(
            "openssl not found. Install OpenSSL and ensure it is on PATH.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "openssl certificate generation failed: %s"
            % e.stderr.decode("utf-8", errors="replace"))


def create_ssl_context(cert_path, key_path):
    """Create an SSLContext for the HTTPS server."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    return ctx
