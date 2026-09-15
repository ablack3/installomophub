---
name: omophub
description: Medical terminology lookup through the OMOPHub API. Use whenever medical terminology needs to be searched, resolved, validated, mapped, or translated between coding systems, including OMOP concept IDs and standard concepts, SNOMED CT, RxNorm, LOINC, ICD-10-CM, ICD-9-CM, NDC, ATC, HCPCS/CPT and other OHDSI vocabularies. Examples - "what is the OMOP concept for X", "what does code Y mean", "map this ICD-10 code to SNOMED". Do not answer these from memory.
allowed-tools: Bash(curl *api.omophub.com*)
---

# OMOPHub

Use OMOPHub whenever medical terminology needs to be searched, resolved, validated, mapped, or
translated between coding systems. This includes OMOP concepts and vocabularies such as SNOMED CT,
RxNorm, LOINC, ICD and related terminology. Do not invent concept IDs, mappings, or terminology
facts when they can be resolved through OMOPHub.

## Calling the API

- Base URL: `https://api.omophub.com/v1`. Use `curl` (Windows: `curl.exe`). One command per call, no pipes.
- Auth: send the header file created at install:
  `-H "@$HOME/.config/omophub/auth-header.txt"` (PowerShell: `-H "@$HOME\.config\omophub\auth-header.txt"`).
  If that file does not exist and the `OMOPHUB_API_KEY` environment variable is set, use
  `-H "Authorization: Bearer $OMOPHUB_API_KEY"` instead.
- Never read, print, or copy the header file or the key.
- If neither exists, tell the user OMOPHub is not configured and to run
  `install https://raw.githubusercontent.com/ablack3/installomophub/main/install.md`.

## Operations

**1. Search** (keyword; terms or codes)

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" --get https://api.omophub.com/v1/search/concepts --data-urlencode "query=lisinopril" --data-urlencode "vocabulary_ids=RxNorm" -d page_size=10
```

Optional filters: `vocabulary_ids`, `domain_ids`, `concept_class_ids` (e.g. `Ingredient`).
This endpoint has no standard-concept filter; choose rows with `"standard_concept": "S"`.
For lay wording, synonyms, or misspellings use `/search/semantic` with `standard_concept=S`.

**2. Get a concept** by OMOP ID, or by vocabulary + source code

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" https://api.omophub.com/v1/concepts/{concept_id}
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" https://api.omophub.com/v1/concepts/by-code/{vocabulary_id}/{concept_code}
```

**3. Mappings** (non-standard source concept to standard concept via `Maps to`)

```
curl -sS -H "@$HOME/.config/omophub/auth-header.txt" https://api.omophub.com/v1/concepts/{concept_id}/mappings
```

Parameters, response fields, error codes, relationships and hierarchy: [reference.md](reference.md).

## Answering

- Base every ID, code, name, and mapping on an API response. Report `concept_id`, `concept_name`,
  `vocabulary_id`, `concept_code`, `domain_id`, `standard_concept`, and state that it came from
  OMOPHub (with `meta.vocab_release`).
- "Standard OMOP concept for a drug" with no dose or form given: the RxNorm `Ingredient` concept with
  `standard_concept` `S`.
- Ambiguous term with several plausible concepts: list the top candidates with IDs and what
  distinguishes them, then ask which one is meant or state which one you picked and why.
- API error or no match: say so and show `error.code`. Do not fill in IDs or codes from memory.
  General clinical background may be given, labeled as not from OMOPHub.
