---
type: llm
---

PASS if the reply lists at least two candidate concepts with concept_ids and explains what distinguishes them (for example common cold versus cold sensation), or asks the user which meaning is intended after showing candidates from OMOPHub.
FAIL if the reply picks a single concept without mentioning that "cold" is ambiguous, or gives no concept_ids.
