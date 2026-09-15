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
| `tests/test_skill_contract.py`, `tests/fake_omophub_api.py` | Skill contract tests against a spec-driven fake OMOPHub API |
| `tests/fixtures/omophub-openapi.json` | Vendored copy of `https://api.omophub.com/openapi.json` (2026-09-15, sha256 `bf8296bb...`) |
| `tests/check_fixture_sensitivity.py` | Breaks copies of the skill on purpose and confirms the contract tests fail |
| `.claude-plugin/plugin.json`, `evals/` | Plugin manifest (exposes `skill/`) and `claude plugin eval` suite for agent behavior |
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
- **Skill (`skill/omophub/`)**: description covering lookup, validation, mapping, coding text, and
  concept sets; the behavioral rule "use OMOPHub, do not invent concept IDs"; the extract-ground-reason
  workflow and validate-before-use check from OMOPHub's AI integration guide; auth via `curl -H @file`
  (env var `OMOPHUB_API_KEY` fallback); operations: keyword and semantic search, get concept by ID or
  by vocabulary+code, resolve code or text to standard concept (`/fhir/resolve`), mappings,
  descendants; answering rules for ambiguity, validation, concept sets, and errors; OMOPHub MCP tools
  used when present. `reference.md` holds parameters, response fields, error codes, and links to the
  full docs. `allowed-tools: Bash(curl *api.omophub.com*)` reduces Claude Code prompts.
- **Sign-up API proposal**: RFC 8628 device authorization grant, plus an `Accept: text/plain` token
  response that is the key-file line; error codes; server security requirements.
- **Skill test fixture**:
  - Contract tests run every curl command in `SKILL.md` from a temp HOME with a key file against a fake
    OMOPHub API. The fake validates each request with openapi-core against the vendored spec (path,
    parameter types, request body, bearer auth), rejects query parameters the spec does not declare and
    values outside constraints the spec states only in descriptions, checks the bearer value came from
    the key file, and returns the spec's example. Other checks: frontmatter; each command matches
    `allowed-tools` and has no shell operators; response fields the skill reads exist in the response
    schema; spec examples validate. `OMOPHUB_SKILL_DIR` points the tests at an installed copy.
  - Behavior evals (`evals/`, 8 cases for `claude plugin eval`). Offline, no key: the skill fires, calls
    the right endpoint, reports that OMOPHub is not configured, and gives no concept ID from memory
    (metformin, SNOMED code, ID validation, ICD-10-CM resolve). Negative: an unrelated coding request
    loads no skill and makes no OMOPHub call. Live, key via `EVAL_OMOPHUB_API_KEY`: grounded metformin
    answer, ambiguous "cold", concept set with descendants.
- **Mock**: Python standard library. Device code and token endpoints, approval page,
  `release-version`, and `/install.md` rewritten to point at the mock. `--issue-key-file` hands out a
  real key so a demo can reach the real API.

## Tested

**Automated** (`uv run --with pytest --with openapi-core --with pyyaml pytest -q tests`): 45 passed,
8 skipped (opt-in live checks), 1 xfailed (known spec gap).

Install flow (11 tests) runs the sh blocks from `install.md` against the mock:

- Key saved with mode 600 in a 700 directory, absent from stdout and stderr.
- `authorization_pending`, `access_denied`, `expired_token`, `slow_down`, and reuse of a device code (`invalid_grant`); an existing key file is kept.
- Fallback placeholder file is created once and never overwrites a key.
- Verify step: issued key succeeds, unknown key returns `invalid_api_key`.
- JSON token response for standard device-flow clients.
- Mock-served `install.md` points sign-up URLs at the mock.

Skill contract (34 tests on the repo copy):

- All 7 curl commands in `SKILL.md` are accepted by the spec-driven fake and match `allowed-tools`.
- Every response field the skill reads exists in its endpoint's response schema; spec examples validate against their schemas.
- Known spec gap, tracked as a strict xfail: `data.resolution.mapping_quality` is described by the `include_quality` parameter but absent from the `/fhir/resolve` response schema.
- `standard_concept` values (S, C, N) and the `max_levels` range (1-20) appear only in spec descriptions; a test checks that text so the fake's extra rules stay in sync.

Fixture sensitivity (`tests/check_fixture_sensitivity.py`): the unchanged copy passes and 10 of 10
deliberate breaks fail the contract tests (renamed query parameter, renamed endpoint, invalid
`standard_concept`, out-of-range `max_levels`, wrong resolve body key, added pipe, changed
`allowed-tools` host, key file path typo, dropped field mention, description over 1024 characters).
The first run missed the invalid `standard_concept` value and an added pipe; both checks were fixed.

**Manual checks** (2026-09-15):

| Check | Result |
|---|---|
| curl header file line endings | LF, CRLF, no trailing newline work; a UTF-8 BOM drops the header (API: `missing_api_key`) |
| Real API, placeholder key | `401 invalid_api_key` |
| Real API, no header | `401 missing_api_key` |
| Real API, `POST /v1/auth/device/code` | `401 missing_api_key` (endpoint absent; triggers fallback) |
| Skill API paths and parameters vs `https://api.omophub.com/openapi.json` | All 11 paths and all checked parameters present |
| `SKILL.md` frontmatter | Valid YAML; `name` matches directory; description 518 chars; 105 lines |
| GitHub raw downloads (step 2) | Byte-identical to the repo |
| Mock as a process | Bad `client_id` and `grant_type` rejected; repeat approval rejected; key file has no BOM; log has no codes or keys |
| Claude Code skill location | Reads `$CLAUDE_CONFIG_DIR/skills` (from `--debug` log, v2.1.241) |

## Not tested

- Any agent session: the install prompt in Claude Code, skill activation, and the nine terminology
  prompts in `docs/POC.md`. The `claude` CLI on the development machine was not logged in.
- Real OMOPHub responses with a valid key, including the opt-in live contract tests. Response field names come from the OpenAPI spec.
- The `evals/` suite. `claude plugin eval` returned `plugin eval is currently in early access` on Claude Code 2.1.241 (the docs require 2.1.269 or later). The CLI has not parsed the case files, and grader patterns and offline expectations are unverified.
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
- CI. Behavior evals exist for Claude Code only and have not run.

## Run

Install flow and skill contract tests:

```bash
uv run --with pytest --with openapi-core --with pyyaml pytest -q tests
```

Contract tests against an installed copy of the skill:

```bash
OMOPHUB_SKILL_DIR=~/.claude/skills/omophub uv run --with pytest --with openapi-core --with pyyaml pytest -q tests/test_skill_contract.py
```

Confirm the contract tests still catch deliberate breaks:

```bash
uv run --with pytest --with openapi-core --with pyyaml python tests/check_fixture_sensitivity.py
```

Opt-in live contract checks (spec drift; real responses when `~/.config/omophub/auth-header.txt` exists):

```bash
OMOPHUB_CONTRACT_LIVE=1 uv run --with pytest --with openapi-core --with pyyaml pytest -q tests -k live
```

Agent behavior evals (Claude Code 2.1.269 or later with `plugin eval` access). Offline cases need no key:

```bash
claude plugin eval . --tag offline --allow-tools "Bash(curl *api.omophub.com*)"
```

Live cases read the key from the key file into an `EVAL_*` variable, the only kind an eval run inherits:

```bash
export EVAL_OMOPHUB_API_KEY="$(sed -n 's/^Authorization: Bearer //p' ~/.config/omophub/auth-header.txt)"
```

```bash
claude plugin eval . --tag live --allow-tools "Bash(curl *api.omophub.com*)" "WebFetch(domain:api.omophub.com)"
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
