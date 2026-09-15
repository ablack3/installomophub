# OMOPHub agent-native install: POC notes

## Files

| Path | Role |
|---|---|
| `install.md` | Bootstrap document. The stable, agent-independent interface an agent reads after `install <url>`. |
| `skill/omophub/SKILL.md` | Skill: trigger description, behavioral rule, auth, 3 operations, answering rules. |
| `skill/omophub/reference.md` | Parameters, response fields, error codes. Loaded only when needed. |
| `docs/agent-signup-api.md` | Proposed OMOPHub sign-up endpoints (RFC 8628 device grant). Not deployed. |
| `mock/agent_auth_server.py` | Stdlib mock of the proposed endpoints, approval page, and `release-version`. |
| `tests/test_install_flow.py` | Runs install.md's sh blocks (steps 3a, 3c, 3e, fallback, 4) against the mock. |
| `docs/POC.md` | This file. |

## Architecture

```
user: "install <bootstrap URL>"
  -> agent reads install.md
  -> step 1: pick user-level skills dir (Claude Code: ~/.claude/skills or $CLAUDE_CONFIG_DIR/skills)
  -> step 2: curl downloads skill/omophub/{SKILL.md,reference.md}
  -> step 3: key
       3a  key file exists? -> skip to 4
       3b  agent asks the user for permission
       3c  POST /v1/auth/device/code            -> device_code, user_code, verification_uri_complete
       3d  agent opens browser; user signs in or signs up, checks user_code, clicks Approve
       3e  POST /v1/auth/device/token (Accept: text/plain) -> curl -o ~/.config/omophub/auth-header.txt
           (umask 077; body is "Authorization: Bearer oh_..."; only the path is printed)
       fallback (3c not 200): placeholder file + dashboard page; user pastes key
  -> step 4: curl -H @auth-header.txt GET /v1/vocabularies/release-version
  -> step 5: user starts a new session

new session:
  terminology question matches skill description -> Skill(omophub)
  -> curl -H @auth-header.txt api.omophub.com/v1/{search/concepts, concepts/{id}, concepts/by-code, concepts/{id}/mappings}
```

Design choices:
- **No scripts in the skill or installer.** Only `curl`, which exists on macOS, Linux, and Windows 10+ (`curl.exe`).
- **Device grant for sign-up.** A published standard; sign-up, consent, and captcha stay in the browser; the agent never handles a password.
- **`Accept: text/plain` token response** is the key-file line, so `curl -o` writes it with no JSON parsing and the key never reaches the terminal or transcript.
- **Key file as a curl header file.** Verified: LF, CRLF, and no-trailing-newline work; a UTF-8 BOM drops the header (API returns `missing_api_key`).
- **Operations:** keyword search, get concept (by ID and by vocabulary+code), mappings.

## Claude Code mechanisms used (docs checked 2026-09-15, Claude Code 2.1.241)

| Need | Mechanism | Source |
|---|---|---|
| Persistent user skill | `~/.claude/skills/<name>/SKILL.md`; follows `CLAUDE_CONFIG_DIR` (verified in `--debug` log) | code.claude.com/docs/en/skills |
| Auto-activation | Model matches `description` (1,536-char cap with `when_to_use`) | skills |
| Fewer prompts | `allowed-tools: Bash(curl *api.omophub.com*)`, valid for the invoking turn | skills; permissions#wildcard-patterns |
| New skill pick-up | Live detection, except a skills dir created after session start needs restart | skills#live-change-detection |
| Fetch instructions | WebFetch (small-model extraction; HTTP upgraded to HTTPS) or `curl` | tools-reference#webfetch-tool-behavior |
| Write approval | `.claude` is a protected path; writes prompt in `default`/`acceptEdits` | permission-modes#protected-paths |

Not available in Claude Code: an "install skill from URL" command, and a secret store for third-party
credentials (`apiKeyHelper` covers Anthropic/gateway credentials; `headersHelper` and OAuth cover MCP servers).

## Test

### Automated (no OMOPHub key, no Claude login)

```bash
uv run --with pytest pytest -q tests
```

Covers: key saved with mode 600 in a 700 dir and never printed; pending, denied, expired, slow_down,
single-use device code; existing key kept; fallback placeholder created once; verify with valid and
invalid keys; JSON token response; mock-served install.md rewrite. PowerShell blocks are not covered.

### Demo against the mock (Claude Code, before OMOPHub ships the endpoints)

Put an existing real key in a file outside the install path, e.g. `~/omophub-demo-key.txt`
(`Authorization: Bearer oh_...`), and make sure `~/.config/omophub/auth-header.txt` does not exist.

```bash
python3 mock/agent_auth_server.py --issue-key-file ~/omophub-demo-key.txt
```

In another terminal:

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-omophub-test" claude
```

`/login` once if prompted, then:

```
install http://127.0.0.1:8765/install.md (fetch it with curl)
```

WebFetch upgrades HTTP to HTTPS, so the prompt asks for curl. Without `--issue-key-file` the mock
issues fake keys, verification runs against the mock, and later terminology calls to the real API fail.

### Clean install against the real bootstrap

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-omophub-test" claude
```

```
install https://raw.githubusercontent.com/ablack3/installomophub/main/install.md
```

Today step 3c gets `401 missing_api_key` and the agent uses the fallback (manual key).

### Terminology prompts (fresh session)

| # | Prompt | Expect |
|---|---|---|
| 1 | `What is the standard OMOP concept for metformin?` | Skill `omophub`; RxNorm Ingredient with `standard_concept` S |
| 2 | `What does SNOMED CT code 22298006 mean, and what is its OMOP concept_id?` | `concepts/by-code/SNOMED/22298006` |
| 3 | `Find the RxNorm concept for atorvastatin 20 MG oral tablet and the OMOP concept ID of its ingredient.` | search + get concept/relationships |
| 4 | `I need the OMOP concept for "cold" from a patient problem list.` | Candidates listed; asks or states pick |
| 5 | `Map ICD-10-CM code I10 to its standard OMOP concept.` | `by-code/ICD10CM/I10` then `mappings` |
| 6 | `Write a Python function that checks whether a string is a palindrome.` | No `omophub` skill, no OMOPHub call |

Headless check:

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-omophub-test" claude -p "What is the standard OMOP concept for metformin?" --output-format stream-json --verbose > t1.jsonl
```

```bash
grep -c '"skill":"omophub"' t1.jsonl; grep -c 'api.omophub.com' t1.jsonl
```

## Security limitations

- Key is plaintext in `~/.config/omophub/auth-header.txt` (600 on macOS/Linux; profile ACL on Windows). Any process running as the user can read it, including the agent.
- `device_code` appears in the agent's commands and transcript. It is single use and expires in 15 minutes; whoever redeems it first after approval gets the key.
- Remote phishing: an attacker can send a user a `verification_uri_complete` link. The approval page must show `key_name` and `user_code` (RFC 8628 section 5.4).
- Skill and bootstrap are served from mutable `main` with no digest or signature.
- `allowed-tools: Bash(curl *api.omophub.com*)` pre-approves, for one turn, any curl command containing that host.
- The `OMOPHUB_API_KEY` fallback in SKILL.md expands the key into curl's argv.
- Search terms go to OMOPHub. Do not send patient data.
- The mock is HTTP on 127.0.0.1 with in-memory state and no authentication on its approval page.

## Platform limitations

- Skill activation is model judgment over the description; competing skills or CLAUDE.md rules can win.
- An agent reading the bootstrap through WebFetch sees a paraphrase.
- Writes under `~/.claude` always prompt in default modes.
- After the invoking turn, curl calls prompt unless the user picks "don't ask again".
- Tested: Claude Code on macOS only (and the sh blocks via pytest). Other agents' skill paths and all PowerShell blocks are unverified.
- `omophub.ai` currently serves a parked Namecheap page.

## Mocked or POC-only

- Sign-up endpoints and approval page exist only in `mock/`; the real API returns `401 missing_api_key` for them.
- Bootstrap URL is GitHub raw install.md, standing in for omophub.ai.
- Skill hosted in this repo; not reconciled with `docs.omophub.com/skill.md`.
- No versioning, update, integrity check, or uninstall command.

## Shortest path to production

1. OMOPHub implements `docs/agent-signup-api.md`: two unauthenticated endpoints, a dashboard `/device` page, key labeling and revocation.
2. Serve `install.md` at a stable OMOPHub URL (and `/` for `Accept: text/markdown`), linked from `llms.txt`; remove the fallback once sign-up is live.
3. Publish the skill through `/.well-known/agent-skills/index.json` (discovery RFC v0.2.0) with a versioned URL and sha256 digest; the bootstrap pins and checks it.
4. Optional: OS credential store instead of the key file, via a small cross-platform helper.
5. Run the six prompts headless per agent in CI and track activation rate.
