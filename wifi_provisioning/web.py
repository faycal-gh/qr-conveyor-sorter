"""Unprivileged setup-only HTTP frontend, with no access to saved secrets."""

import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .ipc import LIMIT, call, decode_request

HOST = "192.168.4.1:8080"
TOKEN = secrets.token_urlsafe(32)
STATIC = Path(__file__).parent / "static"


def allowed_request(host, origin, token, expected):
    return (
        host == HOST
        and origin == "http://" + HOST
        and isinstance(token, str)
        and hmac.compare_digest(token, expected)
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, body, content_type="application/json"):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.headers.get("Host") != HOST:
            self.respond(403, "{}")
            return
        files = {
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        if self.path in files:
            filename, content_type = files[self.path]
            self.respond(
                200, (STATIC / filename).read_text(encoding="utf-8"), content_type
            )
        elif self.path == "/api/status":
            try:
                self.respond(
                    200, json.dumps({**call({"action": "status"}), "token": TOKEN})
                )
            except (OSError, ValueError):
                self.respond(
                    503,
                    '{"error":"Network service busy. Reconnect to setup Wi-Fi and retry."}',
                )
        else:
            self.respond(404, "{}")

    def do_POST(self):
        if not allowed_request(
            self.headers.get("Host"),
            self.headers.get("Origin"),
            self.headers.get("X-Setup-Token"),
            TOKEN,
        ):
            self.respond(403, "{}")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= LIMIT or self.path != "/api/action":
                raise ValueError("Invalid request")
            if self.headers.get("Content-Type") != "application/json":
                raise ValueError("Expected JSON")
            request = decode_request(self.rfile.read(length))
            reply = call(request)
            self.respond(400 if reply.get("error") else 202, json.dumps(reply))
        except ValueError:
            self.respond(400, '{"error":"Invalid request"}')
        except OSError:
            self.respond(503, '{"error":"Network service busy. Please retry."}')

    def setup(self):
        super().setup()
        self.connection.settimeout(5)


if __name__ == "__main__":
    HTTPServer(("192.168.4.1", 8080), Handler).serve_forever()
