# OMOPHub agent-native install: POC notes

## Files

| Path | Role |
|---|---|
| `README.md` | Bootstrap document. The stable, agent-independent interface an agent reads after `install <url>`. |
| `skill/omophub/SKILL.md` | Skill: trigger description, behavioral rule, auth, 3 operations, answering rules (62 lines). |
| `skill/omophub/reference.md` | Parameters, response fields, error codes. Loaded only when needed. |
| `docs/POC.md` | This file. |

## Architecture

```
user: "install <bootstrap URL>"
  -> agent reads README.md (bootstrap, agent-independent)
  -> step 1: agent picks its user-level skills dir from a table (Claude Code: ~/.claude/skills)
  -> step 2: curl downloads skill/omophub/{SKILL.md,reference.md} from GitHub raw
  -> step 3: agent creates ~/.config/omophub/auth-header.txt with a placeholder,
             opens dashboard.omophub.com/api-keys and the file; user pastes key, replies "done"
  -> step 4: curl -H @auth-header.txt GET /v1/vocabularies/release-version -> "success":true
  -> step 5: user starts a new session

new session:
  skill listing contains omophub description
  -> terminology question matches description -> Skill(omophub) loads SKILL.md
  -> curl -H @auth-header.txt api.omophub.com/v1/{search/concepts, concepts/{id}, concepts/by-code, concepts/{id}/mappings}
  -> answer cites concept_id / vocabulary_id / vocab_release from the response
```

Design choices:
- **No scripts in the skill.** Plain `curl` exists on macOS, Linux, and Windows 10+ (`curl.exe`). Any agent that can run a shell can follow it.
- **Credential as a curl header file.** `curl -H @file` reads the header from disk, so the key is absent from argv, shell history, the transcript, and the skill. Verified locally: LF, CRLF, and no-trailing-newline files work; a UTF-8 BOM silently drops the header (API then returns `missing_api_key`).
- **Operations chosen:** keyword search, get concept (by ID and by vocabulary+code), mappings. Semantic search, relationships, and hierarchy are one line each in `reference.md`.
- **Upstream skill** `https://docs.omophub.com/skill.md` (Mintlify-generated, `name: Omop Hub`, ETL/FHIR focused, 11,879 bytes) is linked from `reference.md`, not copied.

## Claude Code mechanisms used (docs checked 2026-09-15, Claude Code 2.1.241)

| Need | Mechanism | Source |
|---|---|---|
| Persistent user skill | `~/.claude/skills/<name>/SKILL.md`; follows `CLAUDE_CONFIG_DIR` (verified in `--debug` log: `Loading skills from: ... user=$CLAUDE_CONFIG_DIR/skills`) | code.claude.com/docs/en/skills |
| Auto-activation | Model matches `description` (+`when_to_use`, 1,536-char cap) | skills, frontmatter reference |
| Fewer prompts | `allowed-tools: Bash(curl *api.omophub.com*)`; grant lasts for the invoking turn, clears at the next user message | skills; permissions#wildcard-patterns |
| Pick-up of new skill | Live detection, except a top-level skills dir created after session start needs restart | skills#live-change-detection |
| Fetch instructions | WebFetch (returns a small model's extraction, not raw text) or `curl` via Bash | tools-reference#webfetch-tool-behavior |
| Write approval | `.claude` is a protected path: writes prompt in `default`/`acceptEdits`; allow rules cannot pre-approve | permission-modes#protected-paths |

Not available in Claude Code (documented or absent from docs):
- No "install skill from URL" command. `install <url>` works only because the model follows the fetched document.
- No third-party secret store. `apiKeyHelper` is for Anthropic/gateway credentials; `headersHelper` and OAuth apply only to MCP servers.
- Plugin marketplaces (`/plugin marketplace add owner/repo`) provide versioned install, but are Claude-specific and are not used here.

## Test

### Clean install (interactive)

A separate config dir isolates the test from existing user skills and `~/.claude/CLAUDE.md`. It needs one `/login` (the Claude credential is keyed per config dir; verified: `Not logged in · Please run /login`).

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-omophub-test" claude
```

In the session: `/login` if prompted, then:

```
install https://raw.githubusercontent.com/ablack3/installomophub/main/README.md
```

Expected prompts: Bash approvals for `mkdir`/`curl` into `$HOME/.claude-omophub-test/skills/omophub`, key-file creation, `open`. One user step: create key, paste into file, reply `done`. Exit, then start a fresh session with the same command.

### Terminology prompts (fresh session)

| # | Prompt | Expect |
|---|---|---|
| 1 | `What is the standard OMOP concept for metformin?` | Skill `omophub`; `search/concepts` RxNorm; Ingredient with `standard_concept` S |
| 2 | `What does SNOMED CT code 22298006 mean, and what is its OMOP concept_id?` | `concepts/by-code/SNOMED/22298006` |
| 3 | `Find the RxNorm concept for atorvastatin 20 MG oral tablet and the OMOP concept ID of its ingredient.` | search + get concept/relationships |
| 4 | `I need the OMOP concept for "cold" from a patient problem list.` | Multiple candidates listed; asks or states pick |
| 5 | `Map ICD-10-CM code I10 to its standard OMOP concept.` | `by-code/ICD10CM/I10` then `mappings` |
| 6 | `Write a Python function that checks whether a string is a palindrome.` | No `omophub` skill, no OMOPHub call |

### Headless activation check

```bash
CLAUDE_CONFIG_DIR="$HOME/.claude-omophub-test" claude -p "What is the standard OMOP concept for metformin?" --output-format stream-json --verbose > t1.jsonl
```

```bash
grep -c '"skill":"omophub"' t1.jsonl; grep -c 'api.omophub.com' t1.jsonl
```

Both counts > 0 for prompts 1-5; both 0 for prompt 6.

## Security limitations

- Key is plaintext in `~/.config/omophub/auth-header.txt` (mode 600 on macOS/Linux; default profile ACL on Windows), same class as `~/.netrc` or `~/.npmrc`. Any process running as the user can read it, including the agent. "Never read the file" is an instruction, not enforcement.
- Skill and bootstrap are served from mutable `main` over HTTPS with no digest or signature. Whoever controls the repo or URL controls the instructions an agent executes. The user's permission prompts are the only gate.
- `allowed-tools: Bash(curl *api.omophub.com*)` pre-approves, for one turn, any curl command whose text contains `api.omophub.com`, including one that also sends data elsewhere. Remove the line to require a prompt per call.
- The `OMOPHUB_API_KEY` fallback expands the key into curl's argv (visible to local `ps`).
- Search terms go to a third party (OMOPHub). Do not send patient data.
- If a user pastes the key into chat, it is stored in the local transcript and sent to the model provider; the bootstrap tells the agent to have the key rotated.

## Platform limitations

- Activation is model judgment over the skill description. It is not guaranteed, and competing skills or instructions (e.g. another OMOP vocabulary skill or a CLAUDE.md rule naming one) can win.
- WebFetch passes the page through a small model, so an agent that reads the bootstrap with WebFetch may see a paraphrase. The document is short and says to download skill files with curl.
- Writes under `~/.claude` always prompt in default modes.
- After the invoking turn, follow-up curl calls prompt unless the user picks "don't ask again" (saved per repository in `.claude/settings.local.json`).
- Tested: Claude Code on macOS only. Codex, Cursor, Gemini CLI, Copilot paths come from vercel-labs/skills and are unverified. PowerShell snippets are untested (no `pwsh` on the test machine).
- `omophub.ai` currently serves a parked Namecheap page (HTTP 302 to www); HTTPS on the apex timed out.

## Mocked or POC-only

- Bootstrap URL is a GitHub raw README, standing in for omophub.ai.
- Skill is hosted in this repo, not by OMOPHub, and is not reconciled with `docs.omophub.com/skill.md`.
- Auth is a manually created dashboard key in a file. No device flow, scopes, or expiry (OMOPHub docs state keys do not expire).
- No versioning, update, integrity check, or uninstall command.
- Verification is one `release-version` call.

## Shortest path to production

1. Serve `README.md` at a stable OMOPHub URL (e.g. `https://omophub.com/install.md`, and at `/` for `Accept: text/markdown`, which WebFetch sends), linked from `llms.txt`.
2. Publish this skill through OMOPHub's existing `/.well-known/agent-skills/index.json` (discovery RFC v0.2.0) with a valid name (`omophub`), a versioned URL, and a sha256 digest; have the bootstrap pin that version and check the digest.
3. Replace the key file with OAuth 2.0 device authorization (RFC 8628) issuing scoped, expiring tokens stored in the OS credential store by a small cross-platform helper. Alternative for Claude Code: add OAuth to the hosted MCP server `mcp.omophub.com` (its OAuth metadata endpoints return 404 today); Claude Code documents OAuth and secure token storage for remote MCP servers. The skill keeps the "when to use" behavior either way.
4. Offer a Claude Code plugin marketplace entry for versioned updates, keeping the curl path for other agents.
5. Run the six test prompts headless per agent in CI and track activation rate.
