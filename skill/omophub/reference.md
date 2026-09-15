# OMOPHub API reference (subset)

Load this file only when SKILL.md is not enough.

Base URL: `https://api.omophub.com/v1`. Every call sends the auth header file described in SKILL.md.

## Full documentation (fetch with curl, load only the part needed)

| Source | Use |
|---|---|
| `https://api.omophub.com/openapi.json` | Complete machine-readable spec: every path, parameter, schema. No key needed. |
| `https://docs.omophub.com/llms.txt` | Index of all docs pages (small). |
| `https://docs.omophub.com/<page>.md` | Raw markdown of any docs page, e.g. `/api-reference/search/semantic-search.md`. |
| `https://docs.omophub.com/skill.md` | Vendor's ETL/FHIR-oriented agent guide (medium). |
| `https://docs.omophub.com/llms-full.txt` | All docs in one file (about 1.3 MB). Search it; do not load it whole. |

## Response envelope

```json
{"success": true, "data": {}, "meta": {"request_id": "...", "timestamp": "...", "vocab_release": "..."}}
```

Errors: `{"success": false, "error": {"code": "...", "message": "..."}}`.

| HTTP | `error.code` | Meaning / action |
|---|---|---|
| 401 | `missing_api_key` | Header file missing, lost the `Authorization: Bearer ` prefix, or saved with a UTF-8 BOM. Ask the user to fix the file; do not read it. |
| 401 | `invalid_api_key` | File still contains `PASTE_KEY_HERE`, or the key is revoked or mistyped. User creates a key at https://dashboard.omophub.com/api-keys and saves it in the file. |
| 404 | `concept_not_found` or other | Concept or code not found. Report "not found in OMOPHub"; do not substitute a remembered ID. |
| 429 | | Rate limited (free tier 2 req/s, 3,000 calls/month). Wait `retry-after` seconds, retry once. |

## Endpoints

### Keyword search: `GET /search/concepts`

| Param | Notes |
|---|---|
| `query` | Required, 3-500 chars. Terms or codes. |
| `vocabulary_ids` | Comma-separated, case-sensitive: `SNOMED`, `RxNorm`, `RxNorm Extension`, `LOINC`, `ICD10CM`, `ICD9CM`, `NDC`, `ATC`, `HCPCS`, `CPT4`. |
| `domain_ids` | `Condition`, `Drug`, `Measurement`, `Procedure`, `Observation`, `Device`. |
| `concept_class_ids` | e.g. `Ingredient`, `Clinical Finding`, `Lab Test`. |
| `page_size` | Default 20, max 200. Use 10. |
| `exact_match`, `include_synonyms`, `include_invalid` | Booleans. |

No `standard_concept` filter: filter on `standard_concept == "S"` in the results.
`data[]` fields: `concept_id, concept_name, concept_code, vocabulary_id, domain_id, concept_class_id, standard_concept, match_score, match_type, valid_start_date, valid_end_date`.

### Semantic search: `GET /search/semantic`

For lay wording, synonyms, or misspellings.
Params: `query`, `standard_concept` (`S`/`C`/`N`), `vocabulary_ids`, `domain_ids`, `concept_class_id`, `threshold` (default 0.5), `page_size` (max 100).
`data.results[]` fields: `concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, standard_concept, concept_code, similarity_score, matched_text`.
Free tier gets a reduced ("Basic") semantic search.

### Get concept: `GET /concepts/{concept_id}`

Params: `include_synonyms`, `include_relationships`, `include_hierarchy` (default false).
`data` fields: `concept_id, concept_name, concept_code, vocabulary_id, domain_id, concept_class_id, standard_concept, valid_start_date, valid_end_date, invalid_reason, is_valid, is_standard`.
`include_invalid` defaults to true, so check `is_valid` / `invalid_reason`.

### Get concept by source code: `GET /concepts/by-code/{vocabulary_id}/{concept_code}`

Example: `/concepts/by-code/SNOMED/44054006`. Same `data` fields as above.

### Resolve code or text: `POST /fhir/resolve`

JSON body, one of:
- `{"vocabulary_id": "ICD10CM", "code": "..."}`
- `{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "..."}` (FHIR system URI)
- `{"display": "free text"}` (semantic search fallback)

Optional: `resource_type` (`Condition`, `Observation`, `MedicationRequest`, `MedicationStatement`, `Procedure`, ...), `include_quality` (adds `mapping_quality`: `high`, `medium`, `low`, `manual_review`), `on_unmapped` (`error` default, or `sentinel`), `include_recommendations`.

`data.resolution`: `source_concept{...}`, `standard_concept{...}`, `mapping_type` (`direct`, `mapped`, `semantic_match`, `unmapped`), `target_table` (e.g. `condition_occurrence`), `domain_resource_alignment`.
A code that exists but has no standard `Maps to` target returns `standard_concept.concept_id = 0`.
No match at all: `404 concept_not_found`. Batch: `POST /fhir/resolve/batch`.

### Mappings: `GET /concepts/{concept_id}/mappings`

Params: `target_vocabulary` (e.g. `ICD10CM`), `relationship_ids` (default `Maps to`; add `Maps to value`), `include_invalid` (default true), `page_size` (max 200).
`data.mappings[]` fields: `source_concept_id, source_concept_name, target_concept_id, target_concept_name, target_concept_code, target_vocabulary_id, target_domain_id, target_standard_concept, relationship_id, invalid_reason`.
OMOP `Maps to` runs non-standard to standard. For standard to ICD10CM, the vendor docs disagree
(`docs.omophub.com/skill.md` says it returns empty; `/ai/integration-guide` calls
`mappings?target_vocabulary=ICD10CM` on a SNOMED concept). Try it; if empty, search ICD10CM concepts and
check their `Maps to`. Multi-source: `POST /concepts/map` with `source_codes` and `target_vocabulary`.

### Hierarchy

- `GET /concepts/{id}/descendants` and `/ancestors`. Params: `max_levels` (1-20, default 10), `vocabulary_ids`, `domain_ids`, `include_distance`, `include_invalid` (default false), `max_results` (1-5000), `page_size` (max 200).
  `data.descendants[]` / `data.ancestors[]` with `concept_id, concept_name, vocabulary_id, domain_id, standard_concept, min_levels_of_separation`; `data.hierarchy_summary.truncated` flags a cut-off set.
- `GET /concepts/{id}/relationships?relationship_ids=Has%20ingredient`: `data.relationships[]` with `relationship_id, concept_1{...}, concept_2{...}`.

### Install check: `GET /vocabularies/release-version`

Cheapest authenticated call. `data.version` is the vocabulary release.
