# Proposed OMOPHub agent sign-up API

Status: proposal, not deployed. `mock/agent_auth_server.py` implements it for tests and demos.

Lets an AI agent obtain an OMOPHub API key for a user. The user signs up or signs in and approves in
a browser; the agent receives the key and saves it. Built on the OAuth 2.0 Device Authorization Grant
([RFC 8628](https://www.rfc-editor.org/rfc/rfc8628)), so standard device-flow clients also work. The
agent never handles a password and the user never copies a key.

## Flow

1. Agent: `POST /v1/auth/device/code` returns `device_code`, `user_code`, `verification_uri_complete`.
2. Agent opens `verification_uri_complete`. User signs in or creates a free account, checks `user_code`, clicks Approve.
3. Agent: `POST /v1/auth/device/token` with `device_code` returns the API key.

## `POST https://api.omophub.com/v1/auth/device/code`

Request body `application/x-www-form-urlencoded`:

| Field | Required | Notes |
|---|---|---|
| `client_id` | yes | `omophub-agent-install` (public client, no secret) |
| `key_name` | no | Label for the created key, e.g. `Claude Code`. Max 100 chars. Shown on the approval page and in the dashboard. |

Response `200 application/json` (RFC 8628 section 3.2):

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

## Approval page `GET https://dashboard.omophub.com/device?user_code=...`

- Not signed in: sign in or sign up (free plan), then return to this page.
- Show `key_name`, `user_code`, and the account; buttons Approve and Deny.
- Approve: create a normal API key named `key_name` on the account and bind it to the grant.
- Then show "Return to your agent."

## `POST https://api.omophub.com/v1/auth/device/token`

Request body `application/x-www-form-urlencoded`:
`grant_type=urn:ietf:params:oauth:grant-type:device_code`, `client_id`, `device_code`.

Success `200`:
- With `Accept: text/plain`: the body is exactly `Authorization: Bearer oh_...` plus `\n` (UTF-8, no BOM).
  Agents save it with `curl -o` as `~/.config/omophub/auth-header.txt`, so the key never reaches the terminal.
- Otherwise JSON: `{"access_token": "oh_...", "token_type": "Bearer"}`.

Errors `400` (RFC 8628 section 3.5). Body is the code alone with `Accept: text/plain`, else `{"error": "<code>"}`.

| Code | Meaning |
|---|---|
| `authorization_pending` | User has not approved yet |
| `slow_down` | Polled faster than `interval`; wait 5 s more |
| `access_denied` | User clicked Deny |
| `expired_token` | `expires_in` passed; start again |
| `invalid_grant` | Unknown or already redeemed `device_code` |
| `invalid_client`, `unsupported_grant_type` | Wrong `client_id` or `grant_type` |

## Server requirements

- `device_code`: at least 128 bits of randomness, single use, stored hashed.
- `user_code`: 8 characters from `BCDFGHJKLMNPQRSTVWXZ` (RFC 8628 section 6.1), displayed `XXXX-XXXX`, case-insensitive.
- Grant lifetime 15 minutes; the key is returned at most once.
- Rate-limit code requests per IP and `user_code` entry on the approval page (RFC 8628 section 5.1).
- Approval needs a signed-in session with CSRF protection. Showing `key_name` and `user_code` counters remote phishing (RFC 8628 section 5.4).
- Keys created this way appear at `dashboard.omophub.com/api-keys` labeled with `key_name` and "created by agent sign-up", and are revocable there.
- Never log `device_code` or keys. Send `Cache-Control: no-store`.
- Normal sign-up abuse controls (email verification, captcha) apply on the approval page.

## Why the device flow

A direct `POST /signup {email}` returning a key would create accounts for unverified emails, let
scripts mint unlimited free-tier keys, and route account credentials through the agent. The device
flow keeps sign-up, consent, and captcha in the browser, follows a published standard with existing
client libraries, and adds one OMOPHub-specific convenience: the `text/plain` header-line response.
