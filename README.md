# installomophub

> **AI agents asked to install OMOPHub:** download
> https://raw.githubusercontent.com/ablack3/installomophub/main/install.md with `curl` and follow it.
> This README only describes project status.

Proof of concept for an agent-native install of [OMOPHub](https://omophub.com), a hosted API over the
OHDSI OMOP standardized vocabularies. The user types one prompt into an AI coding agent:

```
install https://raw.githubusercontent.com/ablack3/installomophub/main/install.md
```

The agent installs an OMOPHub skill, obtains an API key with the user's approval, saves the key to a
local file, and verifies it. In later sessions the skill makes the agent resolve medical terminology
through OMOPHub instead of answering from memory.

Status: POC v0.2. The key flow depends on an OMOPHub sign-up endpoint that does not exist yet; it is
specified in `docs/agent-signup-api.md` and implemented only as a local mock.

## Layout

| Path | Contents |
|---|---|
| `install.md` | Bootstrap instructions for agents (the install URL) |
| `skill/omophub/SKILL.md`, `reference.md` | The OMOPHub skill |
| `docs/agent-signup-api.md` | Proposed OMOPHub sign-up API |
| `mock/agent_auth_server.py` | Local mock of that API |
| `tests/test_install_flow.py` | Runs `install.md` commands against the mock |
| `docs/POC.md` | Architecture, Claude Code mechanisms, test prompts, security and platform limits, production path |

## Implemented

- **Bootstrap (`install.md`)**: agent-independent steps with sh and PowerShell commands, `curl` only.
  1. Choose the user-level skills directory (table for Claude Code, Codex, Cursor, Gemini CLI, Copilot).
  2. Download the skill (2 files).
  3. Get an API key: ask the user; start a device-grant sign-up; user signs up or signs in and approves
     in the browser; agent redeems the code and `curl -o` writes `Authorization: Bearer oh_...` to
     `~/.config/omophub/auth-header.txt` (mode 600; key never printed). If sign-up returns anything
     but 200, fall back to a manually created dashboard key.
  4. Verify with `GET /v1/vocabularies/release-version`.
  5. Tell the user to start a new session; uninstall instructions.
- **Skill (`skill/omophub/`)**: description tuned for terminology questions; the behavioral rule "use
  OMOPHub, do not invent concept IDs"; auth via `curl -H @file` (env var `OMOPHUB_API_KEY` fallback);
  operations: keyword and semantic search, get concept by ID or by vocabulary+code, mappings; answering
  rules for ambiguity and errors. `reference.md` holds parameters, response fields, error codes,
  relationships, hierarchy. `allowed-tools: Bash(curl *api.omophub.com*)` reduces Claude Code prompts.
- **Sign-up API proposal**: RFC 8628 device authorization grant, plus an `Accept: text/plain` token
  response that is the key-file line; error codes; server security requirements.
- **Mock**: Python standard library. Device code and token endpoints, approval page,
  `release-version`, and `/install.md` rewritten to point at the mock. `--issue-key-file` hands out a
  real key so a demo can reach the real API.

## Tested

**Automated** (`uv run --with pytest pytest -q tests`, 11 passed). Each test runs the sh blocks from
`install.md` against the mock:

- Key saved with mode 600 in a 700 directory, absent from stdout and stderr.
- `authorization_pending`, `access_denied`, `expired_token`, `slow_down`, and reuse of a device code (`invalid_grant`); an existing key file is kept.
- Fallback placeholder file is created once and never overwrites a key.
- Verify step: issued key succeeds, unknown key returns `invalid_api_key`.
- JSON token response for standard device-flow clients.
- Mock-served `install.md` points sign-up URLs at the mock.

**Manual checks** (2026-09-15):

| Check | Result |
|---|---|
| curl header file line endings | LF, CRLF, no trailing newline work; a UTF-8 BOM drops the header (API: `missing_api_key`) |
| Real API, placeholder key | `401 invalid_api_key` |
| Real API, no header | `401 missing_api_key` |
| Real API, `POST /v1/auth/device/code` | `401 missing_api_key` (endpoint absent; triggers fallback) |
| Skill API paths vs `https://api.omophub.com/openapi.json` | All 7 distinct paths present |
| `SKILL.md` frontmatter | Valid YAML; `name` matches directory; description 457 chars |
| GitHub raw downloads (step 2) | Byte-identical to the repo |
| Mock as a process | Bad `client_id` and `grant_type` rejected; repeat approval rejected; key file has no BOM; log has no codes or keys |
| Claude Code skill location | Reads `$CLAUDE_CONFIG_DIR/skills` (from `--debug` log, v2.1.241) |

## Not tested

- Any agent session: the install prompt in Claude Code, skill activation, and the six terminology
  prompts in `docs/POC.md`. The `claude` CLI on the development machine was not logged in.
- Real OMOPHub responses with a valid key. Response field names come from the OpenAPI spec.
- PowerShell commands, Windows, and Linux.
- Skill directories for Codex, Cursor, Gemini CLI, and Copilot (taken from vercel-labs/skills).
- Browser-opening commands (`open`, `xdg-open`, `Start-Process`).

## Lacking

- OMOPHub sign-up endpoints and dashboard approval page. Only the mock exists.
- Hosting at omophub.ai. The domain currently serves a parked page; the bootstrap lives on GitHub raw.
- Integrity: no version pinning, digests, or signatures for `install.md` or skill files.
- Credential storage: plaintext file; no OS credential store; no key scopes or expiry.
- Update and uninstall commands.
- Reconciliation with OMOPHub's published `https://docs.omophub.com/skill.md`.
- CI and automated activation evals across agents.

## Run

Tests:

```bash
uv run --with pytest pytest -q tests
```

Demo against the mock with a real key in `~/omophub-demo-key.txt` (and no
`~/.config/omophub/auth-header.txt`):

```bash
python3 mock/agent_auth_server.py --issue-key-file ~/omophub-demo-key.txt
```

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-omophub-test" claude
```

Then prompt: `install http://127.0.0.1:8765/install.md (fetch it with curl)`.
