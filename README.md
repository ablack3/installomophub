# Install OMOPHub for AI coding agents

> **Humans:** in your AI coding agent (Claude Code, Codex, Cursor, Gemini CLI, ...) type:
> `install https://raw.githubusercontent.com/ablack3/installomophub/main/README.md`

OMOPHub (https://omophub.com) is a hosted REST API over the OHDSI OMOP standardized vocabularies:
11M+ concepts across SNOMED CT, RxNorm, LOINC, ICD-10-CM, NDC, ATC and 120+ other vocabularies.
Installing it gives your agent a skill that resolves medical terminology through OMOPHub instead of
guessing concept IDs. The install creates a free OMOPHub account and API key with your approval.

Status: proof of concept, version 0.2. Tested with Claude Code on macOS. The sign-up endpoints in
step 3 are a proposal (`docs/agent-signup-api.md`); if they return 404, use the step 3 fallback.

---

## Instructions for AI agents

Follow the steps in order. Use your normal tools and permission prompts, and tell the user what
each step does before running it. Commands are given for macOS/Linux (sh) and Windows (PowerShell).
On Windows always call `curl.exe`, not `curl`.

**Rules**
- Ask the user before starting sign-up (step 3b).
- Never ask the user to paste the API key into the chat. Never read, print, or copy the key file.
- Keep the key out of the skill directory, repositories, and commands.
- Download files with `curl`. Do not copy them through a web-fetch tool that summarizes content.
- Run only the commands in this document.

### Step 1. Choose the skills directory

This installs an [Agent Skill](https://agentskills.io) (a folder with `SKILL.md`). Use your
user-level skills directory:

| Agent | `SKILLS_DIR` |
|---|---|
| Claude Code | `~/.claude/skills` (if `CLAUDE_CONFIG_DIR` is set: `$CLAUDE_CONFIG_DIR/skills`) |
| Codex | `~/.codex/skills` |
| Cursor | `~/.cursor/skills` |
| Gemini CLI | `~/.gemini/skills` |
| GitHub Copilot | `~/.copilot/skills` |
| Other agents that read `~/.agents/skills` | `~/.agents/skills` |

Only Claude Code has been tested; the other paths come from
[vercel-labs/skills](https://github.com/vercel-labs/skills#supported-agents). If your agent does
not support skills, stop and tell the user.

### Step 2. Install the skill

The skill is two files. Replace `SKILLS_DIR` with the directory from step 1.

sh:
```sh
mkdir -p SKILLS_DIR/omophub
curl -fsSL -o SKILLS_DIR/omophub/SKILL.md https://raw.githubusercontent.com/ablack3/installomophub/main/skill/omophub/SKILL.md
curl -fsSL -o SKILLS_DIR/omophub/reference.md https://raw.githubusercontent.com/ablack3/installomophub/main/skill/omophub/reference.md
```

PowerShell:
```powershell
New-Item -ItemType Directory -Force "SKILLS_DIR\omophub" | Out-Null
curl.exe -fsSL -o "SKILLS_DIR\omophub\SKILL.md" https://raw.githubusercontent.com/ablack3/installomophub/main/skill/omophub/SKILL.md
curl.exe -fsSL -o "SKILLS_DIR\omophub\reference.md" https://raw.githubusercontent.com/ablack3/installomophub/main/skill/omophub/reference.md
```

Check: `SKILLS_DIR/omophub/SKILL.md` exists and its first lines include `name: omophub`.

### Step 3. Get an API key

The key is saved to one file outside the skill, `~/.config/omophub/auth-header.txt`, as the single
line `Authorization: Bearer oh_...`. Tools send it with `curl -H @file`, so the key never appears in
the chat or in commands.

#### 3a. Check for an existing key

sh:
```sh
test -f "$HOME/.config/omophub/auth-header.txt" && echo "key file exists" || echo "no key file"
```

PowerShell:
```powershell
if (Test-Path "$HOME\.config\omophub\auth-header.txt") { "key file exists" } else { "no key file" }
```

If the key file exists, go to step 4.

#### 3b. Ask permission

Ask the user, and continue only if they agree:

> OMOPHub needs an API key. I will start an OMOPHub sign-up request and open your browser, where you
> sign in or create a free account and approve it. I will then save the key to
> `~/.config/omophub/auth-header.txt`. Continue?

#### 3c. Start sign-up

Replace `AGENT_NAME` with your product name, e.g. `Claude Code`.

sh:
```sh
curl -sS -d client_id=omophub-agent-install --data-urlencode "key_name=AGENT_NAME" -w '\nHTTP %{http_code}\n' https://api.omophub.com/v1/auth/device/code
```

PowerShell:
```powershell
curl.exe -sS -d client_id=omophub-agent-install --data-urlencode "key_name=AGENT_NAME" -w '\nHTTP %{http_code}\n' https://api.omophub.com/v1/auth/device/code
```

`HTTP 200`: note `device_code`, `user_code`, and `verification_uri_complete` from the JSON.
`HTTP 404`: the endpoint is not available; use the fallback at the end of step 3.

#### 3d. User approves in the browser

Open `verification_uri_complete` (macOS `open URL`, Linux `xdg-open URL`, Windows `Start-Process URL`)
and show the user:

> In your browser, sign in or create a free OMOPHub account, check that the code shown is `<user_code>`,
> and click Approve. Then reply "approved". The link expires in 15 minutes.

#### 3e. Save the key

After the user replies, replace `DEVICE_CODE` and run. The response is written straight to the key
file; only its path is printed.

sh:
```sh
(umask 077; f="$HOME/.config/omophub/auth-header.txt"; mkdir -p "$(dirname "$f")"; code=$(curl -sS -o "$f.tmp" -w '%{http_code}' -H 'Accept: text/plain' -d grant_type=urn:ietf:params:oauth:grant-type:device_code -d client_id=omophub-agent-install -d device_code=DEVICE_CODE https://api.omophub.com/v1/auth/device/token); if [ "$code" = 200 ]; then mv "$f.tmp" "$f" && echo "saved key to $f"; else echo "HTTP $code: $(cat "$f.tmp")"; rm -f "$f.tmp"; fi)
```

PowerShell:
```powershell
$f = "$HOME\.config\omophub\auth-header.txt"; New-Item -ItemType Directory -Force (Split-Path $f) | Out-Null; $code = curl.exe -sS -o "$f.tmp" -w '%{http_code}' -H 'Accept: text/plain' -d grant_type=urn:ietf:params:oauth:grant-type:device_code -d client_id=omophub-agent-install -d device_code=DEVICE_CODE https://api.omophub.com/v1/auth/device/token; if ($code -eq '200') { Move-Item -Force "$f.tmp" $f; "saved key to $f" } else { "HTTP ${code}: $(Get-Content -Raw "$f.tmp")"; Remove-Item "$f.tmp" }
```

| Output | Action |
|---|---|
| `saved key to ...` | Go to step 4. |
| `HTTP 400: authorization_pending` | Not approved yet. Ask the user to finish in the browser, then rerun 3e. |
| `HTTP 400: slow_down` | Wait 5 seconds and rerun 3e. |
| `HTTP 400: access_denied` | The user clicked Deny. Stop and tell the user. |
| `HTTP 400: expired_token` or `invalid_grant` | Start again at 3c. |

#### Fallback: sign-up endpoint not available

Create the key file with a placeholder (skip if it exists), open the key page and the file, and ask
the user to paste a key into the file and reply "done". Then go to step 4.

sh:
```sh
f="$HOME/.config/omophub/auth-header.txt"; if [ -f "$f" ]; then echo "key file exists"; else mkdir -p "$(dirname "$f")" && printf 'Authorization: Bearer PASTE_KEY_HERE\n' > "$f" && chmod 600 "$f" && echo "created $f"; fi
```

PowerShell:
```powershell
$f = "$HOME\.config\omophub\auth-header.txt"; if (Test-Path $f) { "key file exists" } else { New-Item -ItemType Directory -Force (Split-Path $f) | Out-Null; [IO.File]::WriteAllText($f, "Authorization: Bearer PASTE_KEY_HERE`n"); "created $f" }
```

Open `https://dashboard.omophub.com/api-keys` and the file (macOS `open -t`, Linux `xdg-open`,
Windows `notepad`). Tell the user: create a key (starts with `oh_`), replace `PASTE_KEY_HERE` with it,
keep `Authorization: Bearer ` in front, save, reply "done", and do not paste the key in the chat.

### Step 4. Verify

sh:
```sh
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" https://api.omophub.com/v1/vocabularies/release-version
```

PowerShell:
```powershell
curl.exe -sS -H "@$HOME\.config\omophub\auth-header.txt" https://api.omophub.com/v1/vocabularies/release-version
```

Success: the response contains `"success":true`. Report the vocabulary release version to the user.

On failure, tell the user the `error.code` and the fix, then repeat this step after they reply:

| `error.code` | Fix |
|---|---|
| `invalid_api_key` | The key is wrong or revoked, or the file still has `PASTE_KEY_HERE`. Delete the file and redo step 3. |
| `missing_api_key` | The file is missing, lost the `Authorization: Bearer ` prefix, or was saved as "UTF-8 with BOM". Delete the file and redo step 3. |

### Step 5. Finish

Tell the user:
- OMOPHub is installed: skill at `SKILLS_DIR/omophub`, key at `~/.config/omophub/auth-header.txt`.
- Start a new agent session so the skill loads (Claude Code: exit and run `claude` again).
- Then ask a terminology question, such as "What is the standard OMOP concept for metformin?"
- To uninstall, delete both paths and revoke the key at https://dashboard.omophub.com/api-keys.

---

## For maintainers

- `README.md`: this bootstrap document, the stable interface agents read.
- `skill/omophub/`: the skill; `reference.md` is loaded only when needed.
- `docs/agent-signup-api.md`: proposed OMOPHub sign-up endpoints used in step 3.
- `mock/agent_auth_server.py`: local mock of those endpoints. `tests/`: runs this document's sh commands against it.
- `docs/POC.md`: architecture, test prompts, limitations, production path.
