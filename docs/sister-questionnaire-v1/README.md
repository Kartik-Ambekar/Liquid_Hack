# Sister implementation pack — SAMPLE questionnaire v0.1

Start with IMPLEMENTATION.md. This package supplies an implementable proposed questionnaire and deterministic routing reference for a **synthetic hackathon demo**, not a clinically validated triage system. It does not change the existing Liquid_Hack repository.

## Files

- QUESTIONNAIRE.md: readable exact questions and conditions.
- questionnaire.json: 41 candidate questions, definitions, branch conditions and provenance.
- IMPLEMENTATION.md: routing precedence, integration contract, correction/unknown policies and repository mapping.
- controller.py: standard-library reference selector and semantic extraction validator.
- schemas/extraction.schema.json: model output contract.
- prompts/extractor_system.txt: exact extraction system prompt.
- prompts/repair_system.txt: single bounded repair prompt.
- prompts/question_renderer_system.txt: optional exact-copy renderer; stored text is the default.
- examples.json: 14 complete synthetic input/expected-output pairs, including the field dictionary. These are test labels, not measured model results.
- actions.json: fixed proposed messages and simulation banner; local review required.
- SOURCES.md: primary-source links, adaptation labels and review requirements.
- test_controller.py: 15 routing/validation regression checks.

Run from this folder:

```sh
python3 -m unittest -v test_controller.py
```

The checks passed during packaging. The Liquid model, Dragonwing hardware, clinical wording and real patient performance have not been tested here.

Use all files together. Do not treat the presence of a prompt or source citation as clinical approval. Positive reports in the proposed screen stop the interview; no branch concludes that staying home is safe. Incomplete and out-of-scope flows retain the help route.

This v0.1 extraction contract deliberately replaces the earlier chat sketch: yes/no is an explicit string value with status answered, while unknown/declined/ambiguous carry null. Do not mix versions. Clinical decisions and state fields never come from the model.
