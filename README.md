# Install OMOPHub for AI coding agents

> **Humans:** in your AI coding agent (Claude Code, Codex, Cursor, Gemini CLI, ...) type:
> `install https://raw.githubusercontent.com/ablack3/installomophub/main/README.md`

OMOPHub (https://omophub.com) is a hosted REST API over the OHDSI OMOP standardized vocabularies:
11M+ concepts across SNOMED CT, RxNorm, LOINC, ICD-10-CM, NDC, ATC and 120+ other vocabularies.
It needs a free API key. Installing it gives your agent a skill that resolves medical terminology
through OMOPHub instead of guessing concept IDs.

Status: proof of concept, version 0.1. Tested with Claude Code on macOS.

---

## Instructions for AI agents

Follow the steps in order. Use your normal tools and permission prompts, and tell the user what
each step does before running it. Commands are given for macOS/Linux (sh) and Windows (PowerShell).
On Windows always call `curl.exe`, not `curl`.

**Rules**
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

### Step 3. Set up the API key (user action, about 1 minute)

The key lives in one file, outside the skill: `~/.config/omophub/auth-header.txt`, containing a
single line `Authorization: Bearer oh_...`. Tools send it with `curl -H @file`, so the key never
appears in the chat or in commands.

3a. Create the file with a placeholder, only if it does not already exist:

sh:
```sh
f="$HOME/.config/omophub/auth-header.txt"; if [ -f "$f" ]; then echo "key file exists"; else mkdir -p "$(dirname "$f")" && printf 'Authorization: Bearer PASTE_KEY_HERE\n' > "$f" && chmod 600 "$f" && echo "created $f"; fi
```

PowerShell:
```powershell
$f = "$HOME\.config\omophub\auth-header.txt"; if (Test-Path $f) { "key file exists" } else { New-Item -ItemType Directory -Force (Split-Path $f) | Out-Null; [IO.File]::WriteAllText($f, "Authorization: Bearer PASTE_KEY_HERE`n"); "created $f" }
```

If the file already existed, skip to step 4.

3b. Open the key page and the file for the user (if a command fails, give the user the URL and path):
- macOS: `open https://dashboard.omophub.com/api-keys` and `open -t "$HOME/.config/omophub/auth-header.txt"`
- Linux: `xdg-open https://dashboard.omophub.com/api-keys` and `xdg-open "$HOME/.config/omophub/auth-header.txt"`
- Windows: `Start-Process https://dashboard.omophub.com/api-keys` and `notepad "$HOME\.config\omophub\auth-header.txt"`

3c. Show the user this message, with the real file path, and wait for their reply:

> 1. On https://dashboard.omophub.com/api-keys, sign in (free account) and create an API key. It starts with `oh_`.
> 2. In `<path to auth-header.txt>`, replace `PASTE_KEY_HERE` with the key. Keep `Authorization: Bearer ` in front of it. Save the file.
> 3. Reply "done". Do not paste the key here.

If the user pastes the key into the chat anyway, do not use it. Tell them to delete that key on the
dashboard, create a new one, and put it in the file.

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
| `invalid_api_key` | The file still has `PASTE_KEY_HERE`, or the key is wrong or revoked. Put a valid key in the file and save. |
| `missing_api_key` | The file is missing, lost the `Authorization: Bearer ` prefix, or was saved as "UTF-8 with BOM". Fix the line and re-save as plain UTF-8. |

### Step 5. Finish

Tell the user:
- OMOPHub is installed: skill at `SKILLS_DIR/omophub`, key at `~/.config/omophub/auth-header.txt`.
- Start a new agent session so the skill loads (Claude Code: exit and run `claude` again).
- Then ask a terminology question, such as "What is the standard OMOP concept for metformin?"
- To uninstall, delete both paths.

---

## For maintainers

- `README.md`: this bootstrap document, the stable interface agents read.
- `skill/omophub/SKILL.md`: the skill; `reference.md` is loaded only when needed.
- `docs/POC.md`: architecture, test prompts, limitations, production path.
