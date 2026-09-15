"""Contract tests: the skill's commands and field references agree with the OMOPHub OpenAPI spec.

    uv run --with pytest --with openapi-core --with pyyaml pytest -q tests

Test an installed copy instead of the repo copy:

    OMOPHUB_SKILL_DIR=~/.claude/skills/omophub uv run --with pytest --with openapi-core --with pyyaml pytest -q tests/test_skill_contract.py

Opt-in live checks against api.omophub.com (need network; the second also needs
~/.config/omophub/auth-header.txt):

    OMOPHUB_CONTRACT_LIVE=1 uv run --with pytest --with openapi-core --with pyyaml pytest -q tests -k live
"""

import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import urllib.request

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fake_omophub_api as fake  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
SKILL_DIR = pathlib.Path(os.environ.get("OMOPHUB_SKILL_DIR", REPO / "skill" / "omophub")).expanduser()
SKILL_TEXT = (SKILL_DIR / "SKILL.md").read_text()
REFERENCE_TEXT = (SKILL_DIR / "reference.md").read_text()
KEY_LINE = "Authorization: Bearer oh_contract_test"
LIVE = os.environ.get("OMOPHUB_CONTRACT_LIVE") == "1"

# Placeholder values taken from the spec's own response examples, not from memory.
PLACEHOLDERS = {"{concept_id}": "201826", "{vocabulary_id}": "SNOMED", "{concept_code}": "44054006", "{code}": "44054006"}

# Response fields SKILL.md or reference.md tell the agent to read, per endpoint.
FIELDS_READ = {
    ("/search/concepts", "get"): ["data[].concept_id", "data[].standard_concept", "meta.vocab_release"],
    ("/search/semantic", "get"): ["data.results[].concept_id", "data.results[].standard_concept", "data.results[].similarity_score"],
    ("/concepts/{conceptId}", "get"): ["data.concept_id", "data.domain_id", "data.standard_concept", "data.is_valid", "data.invalid_reason"],
    ("/concepts/by-code/{vocabularyId}/{conceptCode}", "get"): ["data.concept_id", "data.standard_concept"],
    ("/fhir/resolve", "post"): ["data.resolution.source_concept", "data.resolution.standard_concept", "data.resolution.mapping_type", "data.resolution.target_table"],
    ("/concepts/{conceptId}/mappings", "get"): ["data.mappings[].target_concept_id", "data.mappings[].target_standard_concept", "data.mappings[].relationship_id"],
    ("/concepts/{conceptId}/descendants", "get"): ["data.descendants[].concept_id", "data.hierarchy_summary.truncated"],
    ("/vocabularies/release-version", "get"): ["data.version"],
}

# Fields the skill documents that the spec's response schema lacks. Strict xfail: when OMOPHub adds
# them to the spec, the test passes unexpectedly and this entry must move into FIELDS_READ.
KNOWN_SPEC_GAPS = {
    ("/fhir/resolve", "post"): ["data.resolution.mapping_quality"],  # documented only in the include_quality parameter
}


def skill_commands():
    blocks = re.findall(r"^```\n(.*?)^```", SKILL_TEXT, re.S | re.M)
    return [line.strip() for block in blocks for line in block.splitlines() if line.strip().startswith("curl ")]


def frontmatter():
    return yaml.safe_load(re.match(r"^---\n(.*?)\n---\n", SKILL_TEXT, re.S).group(1))


def schema_field_paths(spec_dict, template, method):
    def deref(node):
        while isinstance(node, dict) and "$ref" in node:
            target = spec_dict
            for part in node["$ref"].lstrip("#/").split("/"):
                target = target[part]
            node = target
        return node

    paths = set()

    def walk(node, prefix, depth=0):
        node = deref(node)
        if depth > 10 or not isinstance(node, dict):
            return
        for key in ("allOf", "oneOf", "anyOf"):
            for sub in node.get(key, []):
                walk(sub, prefix, depth + 1)
        if "items" in node:
            walk(node["items"], prefix + "[]", depth + 1)
        for name, sub in (node.get("properties") or {}).items():
            path = f"{prefix}.{name}" if prefix else name
            paths.add(path)
            walk(sub, path, depth + 1)

    walk(spec_dict["paths"][template][method]["responses"]["200"]["content"]["application/json"]["schema"], "")
    return paths


@pytest.fixture(scope="module")
def spec_dict():
    return fake.load_spec()[0]


@pytest.fixture
def api():
    server = fake.start(expected_authorization=KEY_LINE.split(": ", 1)[1])
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def home(tmp_path):
    key_file = tmp_path / ".config" / "omophub" / "auth-header.txt"
    key_file.parent.mkdir(parents=True)
    key_file.write_text(KEY_LINE + "\n")
    return tmp_path


def test_frontmatter_is_valid():
    fm = frontmatter()
    assert fm["name"] == SKILL_DIR.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"])
    assert 0 < len(fm["description"]) <= 1024
    assert fm["allowed-tools"] == "Bash(curl *api.omophub.com*)"


def test_skill_documents_the_expected_operations():
    templates = {fake.match_template(fake.load_spec()[0], urllib.request.urlparse(re.search(r"https://api\.omophub\.com(/v1/[^\s'\"?]+)", c).group(1)).path) for c in skill_commands()}
    assert templates == {template for template, _ in FIELDS_READ} - {"/vocabularies/release-version"}


@pytest.mark.parametrize("command", skill_commands())
def test_command_is_preapproved_and_has_no_shell_operators(command):
    rule = frontmatter()["allowed-tools"][len("Bash("):-1]
    assert re.fullmatch(".*".join(re.escape(part) for part in rule.split("*")), command)
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    operators = {token for token in lexer if token and set(token) <= set("|&;<>()")}
    assert not operators, f"shell operators {operators} split the command and defeat allowed-tools"


@pytest.mark.parametrize("command", skill_commands())
def test_command_satisfies_the_spec(command, api, home):
    filled = command.replace(fake.REAL_HOST, api.base_url)
    for placeholder, value in PLACEHOLDERS.items():
        filled = filled.replace(placeholder, value)
    assert "{" not in re.sub(r"'\{.*\}'", "", filled), f"unfilled placeholder in: {filled}"

    out = subprocess.run(["sh", "-c", filled], env={"HOME": str(home), "PATH": os.environ["PATH"]},
                         capture_output=True, text=True, timeout=30)

    assert out.returncode == 0, out.stderr
    assert len(api.calls) == 1
    call = api.calls[0]
    assert call["error"] is None, call["error"]
    assert json.loads(out.stdout)["success"] is True


@pytest.mark.parametrize("key", list(fake.PROSE_CONSTRAINTS), ids=lambda k: f"{k[0]} {k[2]}")
def test_prose_constraints_still_match_spec_descriptions(key, spec_dict):
    template, method, name = key
    item = spec_dict["paths"][template]
    params = item.get("parameters", []) + item[method].get("parameters", [])
    description = next(p for p in params if p["name"] == name).get("description", "")
    assert fake.PROSE_CONSTRAINTS[key][0] in description, f"spec description changed: {description!r}"


@pytest.mark.parametrize("endpoint", list(FIELDS_READ), ids=lambda e: f"{e[1]} {e[0]}")
def test_fields_the_skill_reads_exist_in_response_schema(endpoint, spec_dict):
    available = schema_field_paths(spec_dict, *endpoint)
    missing = [f for f in FIELDS_READ[endpoint] if f not in available]
    assert not missing, f"not in response schema: {missing}"
    for field in FIELDS_READ[endpoint]:
        leaf = re.split(r"[.\[\]]+", field.rstrip("[]"))[-1]
        assert f"`{leaf}`" in SKILL_TEXT or leaf in REFERENCE_TEXT, f"{leaf} no longer mentioned by the skill; update FIELDS_READ"


@pytest.mark.parametrize("endpoint", list(KNOWN_SPEC_GAPS), ids=lambda e: f"{e[1]} {e[0]}")
@pytest.mark.xfail(strict=True, reason="documented by OMOPHub parameter text but absent from the response schema")
def test_known_spec_gaps(endpoint, spec_dict):
    available = schema_field_paths(spec_dict, *endpoint)
    assert all(f in available for f in KNOWN_SPEC_GAPS[endpoint])


@pytest.mark.parametrize("endpoint", list(FIELDS_READ), ids=lambda e: f"{e[1]} {e[0]}")
def test_spec_examples_match_their_schemas(endpoint, spec_dict):
    from openapi_core.testing import MockRequest, MockResponse

    template, method = endpoint
    example = spec_dict["paths"][template][method]["responses"]["200"]["content"]["application/json"]["example"]
    path = fake.BASE_PATH + template.replace("{conceptId}", "201826").replace("{vocabularyId}", "SNOMED").replace("{conceptCode}", "44054006")
    body = json.dumps({"vocabulary_id": "SNOMED", "code": "44054006"}) if method == "post" else None
    request = MockRequest(fake.REAL_HOST, method, path, args={"query": "metformin"} if "search" in template else {},
                          headers={"Authorization": "Bearer oh_contract_test"}, data=body)
    fake.load_spec()[1].validate_response(request, MockResponse(json.dumps(example).encode(), status_code=200))


@pytest.mark.skipif(not LIVE, reason="set OMOPHUB_CONTRACT_LIVE=1")
def test_live_vendored_spec_is_current():
    live = urllib.request.urlopen(f"{fake.REAL_HOST}/openapi.json", timeout=30).read()
    vendored = fake.SPEC_PATH.read_bytes()
    assert hashlib.sha256(live).hexdigest() == hashlib.sha256(vendored).hexdigest(), \
        "api.omophub.com/openapi.json changed; re-vendor tests/fixtures/omophub-openapi.json and re-run"


@pytest.mark.skipif(not (LIVE and (pathlib.Path.home() / ".config/omophub/auth-header.txt").exists()),
                    reason="set OMOPHUB_CONTRACT_LIVE=1 and create ~/.config/omophub/auth-header.txt")
@pytest.mark.parametrize("command", skill_commands())
def test_live_command_returns_schema_valid_response(command):
    from openapi_core.testing import MockRequest, MockResponse

    filled = command
    for placeholder, value in PLACEHOLDERS.items():
        filled = filled.replace(placeholder, value)
    out = subprocess.run(["sh", "-c", filled], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["success"] is True, payload.get("error")

    url = re.search(r"https://api\.omophub\.com(/v1/[^\s'\"?]+)", filled).group(1)
    method = "post" if " -d '" in filled else "get"
    body = re.search(r"-d '(.*?)'", filled).group(1) if method == "post" else None
    request = MockRequest(fake.REAL_HOST, method, url, args={"query": "x"} if "/search/" in url else {},
                          headers={"Authorization": "Bearer oh_live"}, data=body)
    fake.load_spec()[1].validate_response(request, MockResponse(out.stdout.encode(), status_code=200))
