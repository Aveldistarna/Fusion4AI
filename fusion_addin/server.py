"""
Lightweight HTTP server for the Fusion4AI add-in.
Runs on a background thread; dispatches to handler modules.
Uses Python stdlib only (no Flask dependency).
"""

import json
import threading
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, Optional

# Handler registry: handler_name -> { action_name -> callable }
_handlers: Dict[str, Dict[str, Callable]] = {}


def register_handler(name: str, actions: Dict[str, Callable]) -> None:
    """Register a handler module with its action map."""
    _handlers[name] = actions


class RequestHandler(BaseHTTPRequestHandler):
    """Route POST /api/{handler}/{action} to registered handlers."""

    def do_POST(self) -> None:
        # Parse path: /api/{handler}/{action}
        parts = self.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "api":
            self._respond({"success": False, "error": f"Bad path: {self.path}"})
            return

        handler_name = parts[1]
        action_name = parts[2]

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # UnicodeDecodeError: body is not valid UTF-8 (e.g. CP932 console).
            self._respond({"success": False, "error": f"Invalid JSON body: {e}"})
            return

        params = payload.get("params", {})

        # Dispatch
        handler_actions = _handlers.get(handler_name)
        if not handler_actions:
            self._respond({"success": False, "error": f"Unknown handler: {handler_name}"})
            return

        action_func = handler_actions.get(action_name)
        if not action_func:
            self._respond(
                {"success": False, "error": f"Unknown action: {handler_name}/{action_name}"}
            )
            return

        try:
            result = action_func(params)
            self._respond({"success": True, "result": result})
        except Exception as e:
            traceback.print_exc()
            self._respond({"success": False, "error": str(e)})

    def _respond(self, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Redirect logs to Fusion's text command palette via print."""
        print(f"[Fusion4AI] {format % args}")


class Fusion4AIServer:
    """Manages the HTTP server lifecycle on a background thread."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7432) -> None:
        self.host = host
        self.port = port
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._httpd = HTTPServer((self.host, self.port), RequestHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        print(f"[Fusion4AI] HTTP server listening on {self.host}:{self.port}")

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        print("[Fusion4AI] HTTP server stopped")
