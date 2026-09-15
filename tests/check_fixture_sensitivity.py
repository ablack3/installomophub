"""Check that the skill contract tests fail when the skill is broken.

Copies skill/omophub to a temp dir, applies one deliberate break per run, and runs
tests/test_skill_contract.py against the copy through OMOPHUB_SKILL_DIR. Exits 1 if the unchanged
copy fails, a break's target text no longer exists, or any break goes uncaught.

    uv run --with pytest --with openapi-core --with pyyaml python tests/check_fixture_sensitivity.py
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SKILL = REPO / "skill" / "omophub"
CONTRACT_TESTS = REPO / "tests" / "test_skill_contract.py"

# name -> list of (file, old text, new text); an empty list is the unchanged control
BREAKS = {
    "unchanged copy": [],
    "query parameter renamed (vocabulary_ids -> vocabulary_id)": [("SKILL.md", '"vocabulary_ids=RxNorm"', '"vocabulary_id=RxNorm"')],
    "endpoint renamed (/descendants -> /children)": [("SKILL.md", "/descendants?", "/children?")],
    "invalid standard_concept value": [("SKILL.md", "-d standard_concept=S", "-d standard_concept=standard")],
    "out-of-range max_levels": [("SKILL.md", "max_levels=3", "max_levels=99")],
    "wrong resolve body key": [("SKILL.md", '"code":"{code}"', '"concept_code":"{code}"')],
    "pipe added to a command": [("SKILL.md", '--data-urlencode "domain_ids=Drug" -d page_size=10', '--data-urlencode "domain_ids=Drug" -d page_size=10 | jq .')],
    "allowed-tools host changed": [("SKILL.md", "allowed-tools: Bash(curl *api.omophub.com*)", "allowed-tools: Bash(curl *omophub.example*)")],
    "key file path typo": [("SKILL.md", 'auth-header.txt" https://api.omophub.com/v1/concepts/{concept_id}/mappings', 'auth-headers.txt" https://api.omophub.com/v1/concepts/{concept_id}/mappings')],
    "skill no longer mentions a field it reads": [("SKILL.md", "truncated", "cut off"), ("reference.md", "truncated", "cut off")],
    "description over 1024 characters": [("SKILL.md", "Do not answer these from memory.", "Do not answer these from memory." + " padding" * 80)],
}


def run_contract_tests(skill_dir):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider", str(CONTRACT_TESTS)],
        cwd=REPO, env=dict(os.environ, OMOPHUB_SKILL_DIR=str(skill_dir)), capture_output=True, text=True,
    )


def main():
    problems = 0
    with tempfile.TemporaryDirectory() as tmp:
        for index, (name, edits) in enumerate(BREAKS.items()):
            copy = pathlib.Path(tmp) / str(index) / "omophub"
            shutil.copytree(SKILL, copy)
            for filename, old, new in edits:
                path = copy / filename
                text = path.read_text()
                if old not in text:
                    print(f"STALE   {name}: text not found in {filename}: {old!r}")
                    problems += 1
                    break
                path.write_text(text.replace(old, new))
            else:
                result = run_contract_tests(copy)
                failing = sorted({line.split("::")[1].split("[")[0].split(" ")[0] for line in result.stdout.splitlines() if line.startswith("FAILED")})
                ok = result.returncode == 0 if not edits else result.returncode != 0
                problems += not ok
                label = ("PASS" if ok else "FAIL") if not edits else ("CAUGHT" if ok else "MISSED")
                print(f"{label:7} {name}" + (f"  [{', '.join(failing)}]" if failing else ""))
    print(f"{len(BREAKS) - 1} breaks, {problems} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
