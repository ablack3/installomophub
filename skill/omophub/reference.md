# OMOPHub API reference (subset)

Load this file only when SKILL.md is not enough. Full spec: https://api.omophub.com/openapi.json.
Longer vendor guide: https://docs.omophub.com/skill.md.

Base URL: `https://api.omophub.com/v1`. Every call sends the auth header file described in SKILL.md.

## Response envelope

```json
{"success": true, "data": {}, "meta": {"request_id": "...", "timestamp": "...", "vocab_release": "..."}}
```

Errors: `{"success": false, "error": {"code": "...", "message": "..."}}`.

| HTTP | `error.code` | Meaning / action |
|---|---|---|
| 401 | `missing_api_key` | Header file missing, lost the `Authorization: Bearer ` prefix, or saved with a UTF-8 BOM. Ask the user to fix the file; do not read it. |
| 401 | `invalid_api_key` | File still contains `PASTE_KEY_HERE`, or the key is revoked or mistyped. User creates a key at https://dashboard.omophub.com/api-keys and saves it in the file. |
| 404 | | Concept or code not found. Report "not found in OMOPHub"; do not substitute a remembered ID. |
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

No `standard_concept` filter here: filter on `standard_concept == "S"` in the results.
`data[]` fields: `concept_id, concept_name, concept_code, vocabulary_id, domain_id, concept_class_id, standard_concept, match_score, match_type, valid_start_date, valid_end_date`.

### Semantic search: `GET /search/semantic`

For lay wording, synonyms, or misspellings ("heart attack", "sugar pill for diabetes").
Params: `query`, `standard_concept` (`S`/`C`/`N`), `vocabulary_ids`, `domain_ids`, `concept_class_id`, `threshold` (default 0.5), `page_size` (max 100).
`data.results[]` fields: `concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, standard_concept, concept_code, similarity_score, matched_text`.
Free tier gets a reduced ("Basic") semantic search.

### Get concept: `GET /concepts/{concept_id}`

Params: `include_synonyms`, `include_relationships`, `include_hierarchy` (default false).
`data` fields: `concept_id, concept_name, concept_code, vocabulary_id, domain_id, concept_class_id, standard_concept, valid_start_date, valid_end_date, invalid_reason, is_valid, is_standard`.
`include_invalid` defaults to true, so check `is_valid` / `invalid_reason`.

### Get concept by source code: `GET /concepts/by-code/{vocabulary_id}/{concept_code}`

Example: `/concepts/by-code/SNOMED/44054006`, `/concepts/by-code/ICD10CM/E11.9`. Same `data` fields as above.

### Mappings: `GET /concepts/{concept_id}/mappings`

Params: `relationship_ids` (default `Maps to`; add `Maps to value`), `target_vocabulary`, `include_invalid`.
`data.mappings[]` fields: `source_concept_id, source_concept_name, target_concept_id, target_concept_name, target_concept_code, target_vocabulary_id, target_domain_id, target_standard_concept, relationship_id, invalid_reason`.
OMOP maps non-standard to standard. A standard concept (e.g. SNOMED) usually has no outgoing `Maps to`
other than to itself; to go SNOMED to ICD10CM, search ICD10CM concepts and check their `Maps to`.

### Relationships and hierarchy

- `GET /concepts/{id}/relationships?relationship_ids=Has%20ingredient` : `data.relationships[]` with `relationship_id, concept_1{...}, concept_2{...}`.
- `GET /concepts/{id}/ancestors?max_levels=2` and `/descendants?max_levels=2` : `data.ancestors[]` / `data.descendants[]` with `concept_id, concept_name, vocabulary_id, min_levels_of_separation`.

### Install check: `GET /vocabularies/release-version`

Cheapest authenticated call. `data.version` is the vocabulary release.
