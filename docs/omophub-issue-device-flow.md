# Agent sign-up: device authorization endpoints for API keys (RFC 8628)

Proposal: two unauthenticated API endpoints and one dashboard page so an AI coding agent (Claude Code, Codex, Cursor, ...) can obtain an OMOPHub API key for a user during install. The user signs in or signs up and approves in the browser. The agent never handles a password; the user never copies a key. Based on the OAuth 2.0 Device Authorization Grant ([RFC 8628](https://www.rfc-editor.org/rfc/rfc8628)).

Mock implementation, agent install doc, and tests: https://github.com/ablack3/installomophub
- Spec: `docs/agent-signup-api.md`
- Mock: `mock/agent_auth_server.py`
- Install doc using it: `install.md` step 3
- Tests: `tests/test_install_flow.py` (11 passing against the mock)

## Current state (checked 2026-09-15)

- API keys can only be created at https://dashboard.omophub.com/api-keys in a signed-in session.
- `https://api.omophub.com/openapi.json`: 58 paths, none for key creation or auth. Only security scheme is `bearerAuth`.
- `POST https://api.omophub.com/v1/auth/device/code` returns `401 missing_api_key`: auth runs before routing.

## Flow

1. Agent: `POST /v1/auth/device/code` returns `device_code`, `user_code`, `verification_uri_complete`.
2. Agent opens `verification_uri_complete`. User signs in or signs up, checks `user_code`, clicks Approve.
3. Agent: `POST /v1/auth/device/token` with `device_code` returns the API key.

## `POST https://api.omophub.com/v1/auth/device/code`

Body `application/x-www-form-urlencoded`:

| Field | Required | Notes |
|---|---|---|
| `client_id` | yes | `omophub-agent-install` (public client, no secret) |
| `key_name` | no | Label for the created key, e.g. `Claude Code`. Max 100 chars. Shown on the approval page and dashboard. |

Response `200 application/json`:

```json
{
  "device_code": "<opaque, single use>",
  "user_code": "WDJB-MJHT",
  "verification_uri": "https://dashboard.omophub.com/device",
  "verification_uri_complete": "https://dashboard.omophub.com/device?user_code=WDJB-MJHT",
  "expires_in": 900,
  "interval": 5
}
```

## `GET https://dashboard.omophub.com/device?user_code=...`

- Not signed in: sign in or sign up (free plan), then return to this page.
- Show `key_name`, `user_code`, account; buttons Approve and Deny.
- Approve: create a normal API key named `key_name` and bind it to the grant.
- Then show "Return to your agent."

## `POST https://api.omophub.com/v1/auth/device/token`

Body `application/x-www-form-urlencoded`: `grant_type=urn:ietf:params:oauth:grant-type:device_code`, `client_id`, `device_code`.

Success `200`:
- `Accept: text/plain`: body is exactly `Authorization: Bearer oh_...` plus `\n`, UTF-8, no BOM. Agents save it with `curl -o ~/.config/omophub/auth-header.txt` and send it with `curl -H @file`, so the key never appears in the terminal, transcript, or command line. Works with `curl`/`curl.exe` on macOS, Linux, Windows without JSON parsing.
- Otherwise JSON: `{"access_token": "oh_...", "token_type": "Bearer"}` (standard RFC 8628 clients).

Errors `400`. Body is the code alone with `Accept: text/plain`, else `{"error": "<code>"}`:

| Code | Meaning |
|---|---|
| `authorization_pending` | Not approved yet |
| `slow_down` | Polled faster than `interval`; wait 5 s more |
| `access_denied` | User clicked Deny |
| `expired_token` | `expires_in` passed |
| `invalid_grant` | Unknown or already redeemed `device_code` |
| `invalid_client`, `unsupported_grant_type` | Wrong `client_id` or `grant_type` |

## Requirements

- Both `/v1/auth/device/*` endpoints skip API-key authentication.
- `device_code`: at least 128 bits random, single use, stored hashed.
- `user_code`: 8 characters from `BCDFGHJKLMNPQRSTVWXZ` (RFC 8628 section 6.1), displayed `XXXX-XXXX`, case-insensitive.
- Grant lifetime 15 minutes; key returned at most once.
- Rate-limit code requests per IP and `user_code` entry on the approval page (RFC 8628 section 5.1).
- Approval requires a signed-in session with CSRF protection; `key_name` and `user_code` shown to counter remote phishing (RFC 8628 section 5.4).
- Keys created this way listed at `/api-keys` with `key_name` and "created by agent sign-up", revocable.
- `device_code` and keys never logged. `Cache-Control: no-store` on both endpoints.
- Existing sign-up abuse controls (email verification, captcha) apply on the approval page.

## Why a device flow

- A direct `POST /signup {email}` returning a key creates accounts for unverified emails and lets scripts mint free-tier keys.
- Sign-up, consent, and captcha stay in the browser; existing device-flow client libraries work unchanged.
- One OMOPHub-specific addition: the `text/plain` key-file response.
