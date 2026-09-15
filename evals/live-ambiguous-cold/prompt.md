---
tags: [live]
max_turns: 20
timeout_seconds: 420
allowed_tools: [Skill, Read]
append_system_prompt: 'Eval harness: the OMOPHub header file does not exist in this environment. The API key is in the environment variable EVAL_OMOPHUB_API_KEY. Send it with -H "Authorization: Bearer $EVAL_OMOPHUB_API_KEY" in place of the header file. Never print it.'
description: Real API. Ambiguous term; expect candidates or a clarifying question.
---

I need the OMOP concept for "cold" from a patient problem list.
