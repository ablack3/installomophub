#!/usr/bin/env python3
"""Local mock of the proposed OMOPHub agent sign-up API (docs/agent-signup-api.md).

Test fixture and demo aid. Not part of OMOPHub. Standard library only.

    python3 mock/agent_auth_server.py
        Issues fake oh_mock_... keys. Serves /install.md with auth and verify URLs pointed at the mock.

    python3 mock/agent_auth_server.py --issue-key-file ~/omophub-demo-key.txt
        Hands out the real key in that file on approval, so the installed skill works against the
        real API. /install.md then points only the auth URLs at the mock.
"""

import argparse
import html
import json
import pathlib
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CLIENT_ID = "omophub-agent-install"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"  # RFC 8628 section 6.1
HEADER_RE = re.compile(r"^Authorization: Bearer oh_\S+$")
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REAL_API = "https://api.omophub.com"


def new_user_code():
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


class DeviceStore:
    """In-memory device grants: pending -> approved | denied -> redeemed."""

    def __init__(self, expires_in, interval, issued_header):
        self.expires_in = expires_in
        self.interval = interval
        self.issued_header = issued_header
        self.lock = threading.Lock()
        self.grants = {}  # device_code -> grant
        self.user_codes = {}  # user_code -> device_code
        self.valid_headers = set()

    def start(self, key_name):
        with self.lock:
            device_code = secrets.token_urlsafe(32)
            user_code = new_user_code()
            self.grants[device_code] = {
                "user_code": user_code,
                "key_name": key_name,
                "status": "pending",
                "expires_at": time.monotonic() + self.expires_in,
                "last_poll": None,
            }
            self.user_codes[user_code] = device_code
            return device_code, user_code

    def _pending(self, user_code):
        grant = self.grants.get(self.user_codes.get(user_code, ""))
        if grant and grant["status"] == "pending" and time.monotonic() < grant["expires_at"]:
            return grant
        return None

    def key_name_for(self, user_code):
        with self.lock:
            grant = self._pending(user_code)
            return grant["key_name"] if grant else None

    def decide(self, user_code, approve):
        with self.lock:
            grant = self._pending(user_code)
            if grant is None:
                return False
            grant["status"] = "approved" if approve else "denied"
            return True

    def redeem(self, device_code):
        """Return (error_code, header_line); exactly one is None."""
        with self.lock:
            grant = self.grants.get(device_code)
            if grant is None or grant["status"] == "redeemed":
                return "invalid_grant", None
            now = time.monotonic()
            if now >= grant["expires_at"]:
                return "expired_token", None
            if grant["status"] == "denied":
                return "access_denied", None
            if grant["status"] == "pending":
                too_fast = grant["last_poll"] is not None and now - grant["last_poll"] < self.interval
                grant["last_poll"] = now
                return ("slow_down" if too_fast else "authorization_pending"), None
            grant["status"] = "redeemed"
            header = self.issued_header or f"Authorization: Bearer oh_mock_{secrets.token_hex(16)}"
            self.valid_headers.add(header)
            return None, header


def device_page(user_code, key_name):
    if key_name is None:
        return "<p>Unknown, expired, or already used code.</p>"
    code, name = html.escape(user_code), html.escape(key_name)
    return f"""<!doctype html><title>OMOPHub (mock): approve agent</title>
<h1>OMOPHub (mock)</h1>
<p>Mock approval page. The real page first signs you in or creates a free account.</p>
<p><b>{name}</b> requests an OMOPHub API key.</p>
<p>Check that your agent shows this code: <b>{code}</b></p>
<form method="post" action="/device">
<input type="hidden" name="user_code" value="{code}">
<button name="action" value="approve">Approve</button>
<button name="action" value="deny">Deny</button>
</form>"""


def rewrite_install_doc(base_url, rewrite_verify):
    text = (REPO_ROOT / "install.md").read_text()
    text = text.replace(f"{REAL_API}/v1/auth/", f"{base_url}/v1/auth/")
    if rewrite_verify:
        text = text.replace(f"{REAL_API}/v1/vocabularies/", f"{base_url}/v1/vocabularies/")
    return text


class Handler(BaseHTTPRequestHandler):
    server_version = "omophub-agent-auth-mock/0.2"

    def log_message(self, fmt, *args):
        # Log method and path only; query strings and bodies carry codes.
        print(f"{self.command} {urlparse(self.path).path}", flush=True)

    @property
    def store(self):
        return self.server.store

    @property
    def base_url(self):
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def send(self, status, body, content_type):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, obj):
        self.send(status, json.dumps(obj), "application/json")

    def form(self):
        length = int(self.headers.get("Content-Length") or 0)
        fields = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
        return {k: v[0] for k, v in fields.items()}

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/device":
            user_code = parse_qs(url.query).get("user_code", [""])[0]
            return self.send(200, device_page(user_code, self.store.key_name_for(user_code)), "text/html; charset=utf-8")
        if url.path == "/v1/vocabularies/release-version":
            header = self.headers.get("Authorization")
            if not header:
                return self.send_json(401, {"success": False, "error": {"code": "missing_api_key", "message": "Missing API key in the authorization header"}})
            if f"Authorization: {header}" not in self.store.valid_headers:
                return self.send_json(401, {"success": False, "error": {"code": "invalid_api_key", "message": "Invalid API key"}})
            return self.send_json(200, {"success": True, "data": {"version": "mock"}})
        if url.path == "/install.md":
            body = rewrite_install_doc(self.base_url, rewrite_verify=self.store.issued_header is None)
            return self.send(200, body, "text/markdown; charset=utf-8")
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        url = urlparse(self.path)
        fields = self.form()
        if url.path == "/v1/auth/device/code":
            if fields.get("client_id") != CLIENT_ID:
                return self.send_json(400, {"error": "invalid_client"})
            key_name = fields.get("key_name", "").strip()[:100] or "AI agent"
            device_code, user_code = self.store.start(key_name)
            verification_uri = f"{self.base_url}/device"
            return self.send_json(200, {
                "device_code": device_code,
                "user_code": user_code,
                "verification_uri": verification_uri,
                "verification_uri_complete": f"{verification_uri}?user_code={user_code}",
                "expires_in": self.store.expires_in,
                "interval": self.store.interval,
            })
        if url.path == "/v1/auth/device/token":
            if fields.get("grant_type") != DEVICE_GRANT:
                error, header = "unsupported_grant_type", None
            elif fields.get("client_id") != CLIENT_ID:
                error, header = "invalid_client", None
            else:
                error, header = self.store.redeem(fields.get("device_code", ""))
            if "text/plain" in (self.headers.get("Accept") or ""):
                if error:
                    return self.send(400, error, "text/plain; charset=utf-8")
                return self.send(200, header + "\n", "text/plain; charset=utf-8")
            if error:
                return self.send_json(400, {"error": error})
            return self.send_json(200, {"access_token": header.removeprefix("Authorization: Bearer "), "token_type": "Bearer"})
        if url.path == "/device":
            ok = self.store.decide(fields.get("user_code", ""), fields.get("action") == "approve")
            message = "Done. Return to your agent." if ok else "Unknown, expired, or already used code."
            return self.send(200 if ok else 400, f"<p>{html.escape(message)}</p>", "text/html; charset=utf-8")
        self.send_json(404, {"error": "not_found"})


def build_server(host="127.0.0.1", port=8765, expires_in=900, interval=5, issued_header=None):
    server = ThreadingHTTPServer((host, port), Handler)
    server.store = DeviceStore(expires_in, interval, issued_header)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--issue-key-file", type=pathlib.Path, help="file with one line 'Authorization: Bearer oh_...' to hand out on approval")
    args = parser.parse_args()
    issued = None
    if args.issue_key_file:
        issued = args.issue_key_file.expanduser().read_text().strip()
        if not HEADER_RE.match(issued):
            raise SystemExit(f"{args.issue_key_file}: expected one line 'Authorization: Bearer oh_...'")
    server = build_server(port=args.port, issued_header=issued)
    base = "http://%s:%s" % server.server_address[:2]
    print(f"mock OMOPHub sign-up API on {base}")
    print(f"agent prompt: install {base}/install.md (fetch it with curl)")
    server.serve_forever()


if __name__ == "__main__":
    main()
