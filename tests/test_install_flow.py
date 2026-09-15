"""Run the README's sh commands for steps 3 and 4 against the mock sign-up API.

    uv run --with pytest pytest -q tests
"""

import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mock"))
import agent_auth_server as mock  # noqa: E402

KEY_FILE = pathlib.Path(".config/omophub/auth-header.txt")


def sh_blocks(heading_prefix):
    """Return the ```sh blocks under the README heading whose text starts with heading_prefix."""
    blocks, heading, buf = [], None, None
    for line in (REPO / "README.md").read_text().splitlines():
        if buf is not None:
            if line.startswith("```"):
                if heading.startswith(heading_prefix):
                    blocks.append("\n".join(buf))
                buf = None
            else:
                buf.append(line)
        elif line.startswith("#"):
            heading = line.lstrip("#").strip()
        elif line.strip() == "```sh":
            buf = []
    assert blocks, f"no sh block under heading {heading_prefix!r}"
    return blocks


@pytest.fixture
def make_server():
    servers = []

    def start(**kwargs):
        server = mock.build_server(port=0, interval=0, **kwargs)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def server(make_server):
    return make_server()


def base_url(server):
    return "http://%s:%s" % server.server_address[:2]


def run(block, server, home, **placeholders):
    """Run a README block the way an agent would: fill placeholders, point API calls at the mock."""
    command = block.replace(mock.REAL_API, base_url(server))
    for name, value in placeholders.items():
        command = command.replace(name, value)
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    return subprocess.run(["sh", "-c", command], env=env, capture_output=True, text=True, timeout=30)


def start_signup(server, home):
    out = run(sh_blocks("3c.")[0], server, home, AGENT_NAME="Test Agent")
    assert out.returncode == 0, out.stderr
    body, status = out.stdout.rsplit("HTTP ", 1)
    assert status.strip() == "200"
    return json.loads(body)


def decide(server, user_code, action):
    data = urllib.parse.urlencode({"user_code": user_code, "action": action}).encode()
    urllib.request.urlopen(base_url(server) + "/device", data=data).read()


def save_key(server, home, grant):
    return run(sh_blocks("3e.")[0], server, home, DEVICE_CODE=grant["device_code"])


def test_happy_path_saves_key_without_printing_it(server, tmp_path):
    assert run(sh_blocks("3a.")[0], server, tmp_path).stdout.strip() == "no key file"

    grant = start_signup(server, tmp_path)
    assert re.fullmatch(r"[BCDFGHJKLMNPQRSTVWXZ]{4}-[BCDFGHJKLMNPQRSTVWXZ]{4}", grant["user_code"])
    assert grant["verification_uri_complete"] == f"{base_url(server)}/device?user_code={grant['user_code']}"
    page = urllib.request.urlopen(grant["verification_uri_complete"]).read().decode()
    assert "Test Agent" in page and grant["user_code"] in page

    decide(server, grant["user_code"], "approve")
    out = save_key(server, tmp_path, grant)

    key_path = tmp_path / KEY_FILE
    assert out.stdout.strip() == f"saved key to {key_path}"
    assert "oh_" not in out.stdout + out.stderr
    assert re.fullmatch(r"Authorization: Bearer oh_mock_[0-9a-f]{32}\n", key_path.read_text())
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(key_path.parent.stat().st_mode) == 0o700
    assert sorted(p.name for p in key_path.parent.iterdir()) == ["auth-header.txt"]

    assert run(sh_blocks("3a.")[0], server, tmp_path).stdout.strip() == "key file exists"
    verify = run(sh_blocks("Step 4.")[0], server, tmp_path)
    assert json.loads(verify.stdout) == {"success": True, "data": {"version": "mock"}}


@pytest.mark.parametrize("action, expected", [(None, "authorization_pending"), ("deny", "access_denied")])
def test_unapproved_grant_writes_no_file(server, tmp_path, action, expected):
    grant = start_signup(server, tmp_path)
    if action:
        decide(server, grant["user_code"], action)
    out = save_key(server, tmp_path, grant)
    assert out.stdout.strip() == f"HTTP 400: {expected}"
    assert list((tmp_path / KEY_FILE).parent.iterdir()) == []


def test_pending_then_approved(server, tmp_path):
    grant = start_signup(server, tmp_path)
    assert save_key(server, tmp_path, grant).stdout.strip() == "HTTP 400: authorization_pending"
    decide(server, grant["user_code"], "approve")
    assert save_key(server, tmp_path, grant).stdout.startswith("saved key to ")


def test_device_code_is_single_use_and_keeps_existing_key(server, tmp_path):
    grant = start_signup(server, tmp_path)
    decide(server, grant["user_code"], "approve")
    save_key(server, tmp_path, grant)
    first = (tmp_path / KEY_FILE).read_text()
    assert save_key(server, tmp_path, grant).stdout.strip() == "HTTP 400: invalid_grant"
    assert (tmp_path / KEY_FILE).read_text() == first


def test_expired_grant(make_server, tmp_path):
    server = make_server(expires_in=0)
    grant = start_signup(server, tmp_path)
    with pytest.raises(urllib.error.HTTPError):
        decide(server, grant["user_code"], "approve")
    assert save_key(server, tmp_path, grant).stdout.strip() == "HTTP 400: expired_token"


def test_polling_faster_than_interval_gets_slow_down(make_server, tmp_path):
    server = make_server()
    server.store.interval = 60
    grant = start_signup(server, tmp_path)
    assert save_key(server, tmp_path, grant).stdout.strip() == "HTTP 400: authorization_pending"
    assert save_key(server, tmp_path, grant).stdout.strip() == "HTTP 400: slow_down"


def test_verify_reports_invalid_key(server, tmp_path):
    key_path = tmp_path / KEY_FILE
    key_path.parent.mkdir(parents=True)
    key_path.write_text("Authorization: Bearer oh_not_issued\n")
    verify = run(sh_blocks("Step 4.")[0], server, tmp_path)
    assert json.loads(verify.stdout)["error"]["code"] == "invalid_api_key"


def test_json_token_response_for_standard_clients(server, tmp_path):
    grant = start_signup(server, tmp_path)
    decide(server, grant["user_code"], "approve")
    data = urllib.parse.urlencode({"grant_type": mock.DEVICE_GRANT, "client_id": mock.CLIENT_ID, "device_code": grant["device_code"]}).encode()
    token = json.load(urllib.request.urlopen(base_url(server) + "/v1/auth/device/token", data=data))
    assert token["token_type"] == "Bearer" and token["access_token"].startswith("oh_mock_")


def test_fallback_creates_placeholder_once(server, tmp_path):
    block = sh_blocks("Fallback")[0]
    key_path = tmp_path / KEY_FILE
    assert run(block, server, tmp_path).stdout.strip() == f"created {key_path}"
    assert key_path.read_text() == "Authorization: Bearer PASTE_KEY_HERE\n"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    key_path.write_text("Authorization: Bearer oh_real\n")
    assert run(block, server, tmp_path).stdout.strip() == "key file exists"
    assert key_path.read_text() == "Authorization: Bearer oh_real\n"


def test_served_readme_points_auth_at_mock(server):
    text = urllib.request.urlopen(base_url(server) + "/README.md").read().decode()
    assert f"{base_url(server)}/v1/auth/device/code" in text
    assert f"{mock.REAL_API}/v1/auth/" not in text
