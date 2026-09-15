---
name: omophub
description: Medical terminology lookup and validation through the OMOPHub API. Use whenever medical terminology needs to be searched, resolved, validated, mapped, or translated between coding systems, including OMOP concept IDs and standard concepts, SNOMED CT, RxNorm, LOINC, ICD-10-CM, ICD-9-CM, NDC, ATC, HCPCS/CPT and FHIR codings. Also use to check whether a concept ID or code is real, to code conditions, drugs, procedures, or labs found in text, and to build concept sets with descendants. Do not answer these from memory.
allowed-tools: Bash(curl *api.omophub.com*)
---

# OMOPHub

Use OMOPHub whenever medical terminology needs to be searched, resolved, validated, mapped, or
translated between coding systems. This includes OMOP concepts and vocabularies such as SNOMED CT,
RxNorm, LOINC, ICD and related terminology. Do not invent concept IDs, mappings, or terminology
facts when they can be resolved through OMOPHub.

## Workflow: extract, ground, reason

1. **Extract** the clinical terms from the request or text and tag each with a domain.
2. **Ground** each term through OMOPHub. Default filters:

   | Term type | `vocabulary_ids` | `domain_ids` |
   |---|---|---|
   | Condition | `SNOMED` | `Condition` |
   | Drug | `RxNorm` | `Drug` |
   | Procedure | `SNOMED` | `Procedure` |
   | Lab or measurement | `LOINC` | `Measurement` |

   Keyword search first; if it has no standard match, semantic search. If both fail, report the term
   as not found in OMOPHub.
3. **Reason** with grounded IDs only: answers, code lists, SQL, concept sets.

**Validate before use.** A concept ID or code that did not come from an OMOPHub response in this
session (supplied by the user, read from a file, written earlier by a model) must be checked with
operation 2: it exists, its `domain_id` is the expected one, and for analysis it has
`standard_concept` `S`. If it is non-standard, use its `Maps to` target (operation 4).

## Calling the API

- Base URL: `https://api.omophub.com/v1`. Use `curl` (Windows: `curl.exe`). One command per call, no pipes.
- Auth: send the header file created at install:
  `-H "@$HOME/.config/omophub/auth-header.txt"` (PowerShell: `-H "@$HOME\.config\omophub\auth-header.txt"`).
  If that file does not exist and the `OMOPHUB_API_KEY` environment variable is set, use
  `-H "Authorization: Bearer $OMOPHUB_API_KEY"` instead.
- Never read, print, or copy the header file or the key.
- If neither exists, tell the user OMOPHub is not configured and to run
  `install https://raw.githubusercontent.com/ablack3/installomophub/main/install.md`.
- If OMOPHub MCP tools (`search_concepts`, `get_concept`, `map_concept`, ...) are available in this
  session, they may be used instead of curl. The workflow and answering rules still apply.

## Operations

**1. Search** by keyword, then by meaning

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" --get https://api.omophub.com/v1/search/concepts --data-urlencode "query=lisinopril" --data-urlencode "vocabulary_ids=RxNorm" --data-urlencode "domain_ids=Drug" -d page_size=10
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" --get https://api.omophub.com/v1/search/semantic --data-urlencode "query=high blood pressure" -d standard_concept=S -d page_size=10
```

Keyword search has no standard-concept filter; choose rows with `"standard_concept": "S"`.

**2. Get a concept** by OMOP ID, or by vocabulary + source code

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" https://api.omophub.com/v1/concepts/{concept_id}
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" https://api.omophub.com/v1/concepts/by-code/{vocabulary_id}/{concept_code}
```

**3. Resolve** a source code, or free text, to its standard concept in one call

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" -H "Content-Type: application/json" -d '{"vocabulary_id":"{vocabulary_id}","code":"{code}","include_quality":true}' https://api.omophub.com/v1/fhir/resolve
```

Text only: body `{"display":"<text>","resource_type":"Condition"}`. Read `data.resolution`:
`source_concept`, `standard_concept`, `mapping_type`, `target_table`, `mapping_quality`.
On Windows PowerShell, write the JSON body to a file and pass `-d "@body.json"`.

**4. Mappings** of a concept (`Maps to` by default; add `?target_vocabulary=ICD10CM` to filter)

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" https://api.omophub.com/v1/concepts/{concept_id}/mappings
```

**5. Descendants** for a concept set ("include descendants")

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" "https://api.omophub.com/v1/concepts/{concept_id}/descendants?max_levels=3&page_size=200"
```

Parameters, response fields, error codes, ancestors, relationships, and full documentation links:
[reference.md](reference.md).

## Answering

- Base every ID, code, name, and mapping on an API response. Report `concept_id`, `concept_name`,
  `vocabulary_id`, `concept_code`, `domain_id`, `standard_concept`, and state that it came from
  OMOPHub (with `meta.vocab_release`).
- "Standard OMOP concept for a drug" with no dose or form given: the RxNorm `Ingredient` concept with
  `standard_concept` `S`.
- Ambiguous term with several plausible concepts: list the top candidates with IDs and what
  distinguishes them, then ask which one is meant or state which one you picked and why.
- Validation results: say which IDs passed, and for each failure whether it does not exist, is in
  another domain, or is non-standard (with its standard target).
- Concept sets: give the root concept, the descendant count, and whether the result was truncated
  (`hierarchy_summary.truncated`).
- API error or no match: say so and show `error.code`. Do not fill in IDs or codes from memory.
  General clinical background may be given, labeled as not from OMOPHub.
