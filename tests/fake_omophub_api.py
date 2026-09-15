"""Spec-driven fake of the OMOPHub REST API for skill contract tests.

Each request is validated against the vendored OpenAPI spec with openapi-core (path, method,
parameter types and enums, request body, bearer auth). Query parameters the spec does not declare
are rejected, since openapi-core ignores them. Valid requests get the spec's 200 example.
"""

import json
import pathlib
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

from openapi_core import OpenAPI
from openapi_core.testing import MockRequest

SPEC_PATH = pathlib.Path(__file__).parent / "fixtures" / "omophub-openapi.json"
REAL_HOST = "https://api.omophub.com"
BASE_PATH = "/v1"

# Constraints the spec states only in parameter descriptions, not in schemas, so openapi-core cannot
# enforce them. Each entry: (text that must appear in the description, check on the raw value).
# tests/test_skill_contract.py verifies the description text is still present.
PROSE_CONSTRAINTS = {
    ("/search/semantic", "get", "standard_concept"): ("Values: S (Standard), C (Classification), N", lambda v: v in {"S", "C", "N"}),
    ("/concepts/{conceptId}/descendants", "get", "max_levels"): ("Range: 1-20", lambda v: v.isdigit() and 1 <= int(v) <= 20),
}


def load_spec():
    return json.loads(SPEC_PATH.read_text()), OpenAPI.from_file_path(str(SPEC_PATH))


def match_template(spec_dict, path):
    """Return the spec path template for a concrete path under /v1, preferring literal segments."""
    relative = path[len(BASE_PATH):] if path.startswith(BASE_PATH) else path
    candidates = []
    for template in spec_dict["paths"]:
        pattern = "^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template)) + "$"
        if re.match(pattern, relative):
            literals = sum(1 for part in template.split("/") if part and not part.startswith("{"))
            candidates.append((literals, template))
    return max(candidates)[1] if candidates else None


def declared_query_params(spec_dict, template, method):
    item = spec_dict["paths"][template]
    params = item.get("parameters", []) + item.get(method, {}).get("parameters", [])
    return {p["name"] for p in params if p.get("in") == "query"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.handle_call("get")

    def do_POST(self):
        self.handle_call("post")

    def handle_call(self, method):
        server = self.server
        url = urlparse(self.path)
        args = dict(parse_qsl(url.query, keep_blank_values=True))
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        call = {"method": method, "path": url.path, "args": args, "body": body.decode() if body else None,
                "authorization": self.headers.get("Authorization"), "template": None, "error": None}
        server.calls.append(call)

        template = match_template(server.spec_dict, url.path)
        call["template"] = template
        try:
            request = MockRequest(REAL_HOST, method, url.path, args=args, headers=dict(self.headers),
                                  data=body, content_type=self.headers.get("Content-Type", "application/json"))
            server.spec.validate_request(request)
            if template is None:
                raise ValueError(f"no spec path for {url.path}")
            undeclared = set(args) - declared_query_params(server.spec_dict, template, method)
            if undeclared:
                raise ValueError(f"query parameters not in spec: {sorted(undeclared)}")
            for name, value in args.items():
                constraint = PROSE_CONSTRAINTS.get((template, method, name))
                if constraint and not constraint[1](value):
                    raise ValueError(f"{name}={value!r} violates spec description: {constraint[0]}")
            if call["authorization"] != server.expected_authorization:
                raise ValueError("Authorization header does not match the key file")
        except Exception as exc:  # report every contract violation to the test
            call["error"] = f"{type(exc).__name__}: {exc}"
            return self.send_json(400, {"success": False, "error": {"code": "contract_violation", "message": call["error"]}})

        example = server.spec_dict["paths"][template][method]["responses"]["200"]["content"]["application/json"]["example"]
        self.send_json(200, example)

    def send_json(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(expected_authorization):
    """Start the fake on an ephemeral port. Returns the server; call shutdown() when done."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.spec_dict, server.spec = load_spec()
    server.expected_authorization = expected_authorization
    server.calls = []
    server.base_url = "http://%s:%s" % server.server_address[:2]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
