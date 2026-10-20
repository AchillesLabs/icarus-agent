"""Ephemeral loopback HTTP callback listener for local CLI OAuth flows."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("icarus.integrations.loopback")

SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Icarus Authorization Complete</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .card { background: #1e293b; padding: 40px; border-radius: 12px; border: 1px solid #334155; text-align: center; max-width: 480px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
    h1 { color: #38bdf8; font-size: 24px; margin-bottom: 12px; }
    p { color: #94a3b8; font-size: 15px; line-height: 1.5; margin-bottom: 24px; }
    .badge { display: inline-block; background: #065f46; color: #34d399; padding: 6px 14px; border-radius: 20px; font-weight: 600; font-size: 13px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">✓ Authorization Received</div>
    <h1>Account Connected to Icarus</h1>
    <p>Your authentication token was safely processed. You may now close this browser tab and return to your terminal session.</p>
  </div>
</body>
</html>
"""

ERROR_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Icarus Authorization Failed</title>
  <style>
    body { font-family: sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .card { background: #1e293b; padding: 40px; border-radius: 12px; border: 1px solid #ef4444; text-align: center; max-width: 480px; }
    h1 { color: #ef4444; font-size: 22px; }
    p { color: #94a3b8; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Authorization Failed</h1>
    <p>__ERROR_MSG__</p>
  </div>
</body>
</html>
"""


class LoopbackCallbackServer:
    """Manages an ephemeral loopback HTTP server bound to 127.0.0.1 to capture OAuth redirects."""

    def __init__(self, expected_state: str, timeout: float = 120.0) -> None:
        self.expected_state = expected_state
        self.timeout = timeout
        self.received_code: str | None = None
        self.received_error: str | None = None
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._event = threading.Event()
        self.port: int = 0

    def start(self) -> str:
        """Start server on an available local port and return the redirect_uri."""
        outer = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                # Suppress noisy standard server logging
                pass

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if not parsed.path.startswith("/callback"):
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not Found")
                    return

                params = parse_qs(parsed.query)
                error_param = params.get("error", [None])[0]
                if error_param:
                    outer.received_error = error_param
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    html = ERROR_HTML_TEMPLATE.replace("__ERROR_MSG__", f"Provider reported error: {error_param}")
                    self.wfile.write(html.encode("utf-8"))
                    outer._event.set()
                    return

                state_param = params.get("state", [None])[0]
                code_param = params.get("code", [None])[0]

                if not state_param or state_param != outer.expected_state:
                    outer.received_error = "OAuth state mismatch or missing (potential CSRF attempt)."
                    self.send_response(403)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    html = ERROR_HTML_TEMPLATE.replace("__ERROR_MSG__", "Security Error: OAuth state mismatch.")
                    self.wfile.write(html.encode("utf-8"))
                    outer._event.set()
                    return

                if not code_param:
                    outer.received_error = "Missing authorization code in provider callback."
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    html = ERROR_HTML_TEMPLATE.replace("__ERROR_MSG__", "Missing authorization code.")
                    self.wfile.write(html.encode("utf-8"))
                    outer._event.set()
                    return

                outer.received_code = code_param
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(SUCCESS_HTML.encode("utf-8"))
                outer._event.set()

        # Bind to 127.0.0.1 on ephemeral port 0
        self._server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
        self.port = self._server.server_address[1]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        return f"http://127.0.0.1:{self.port}/callback"

    def wait_for_code(self) -> str:
        """Block until callback is received or timeout expires."""
        finished = self._event.wait(timeout=self.timeout)
        self.shutdown()

        if not finished:
            raise TimeoutError(f"OAuth callback timed out after {self.timeout} seconds waiting for authorization.")

        if self.received_error:
            raise ValueError(f"OAuth authorization failed: {self.received_error}")

        if not self.received_code:
            raise ValueError("No authorization code captured from loopback redirect.")

        return self.received_code

    def shutdown(self) -> None:
        """Cleanly terminate loopback HTTP listener."""
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
