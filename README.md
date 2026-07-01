# CareGuide Agent

CareGuide Agent is a Vietnamese multi-agent health triage and personalized care plan assistant.

The project uses LangGraph to orchestrate specialized agents for symptom parsing, medical term normalization, follow-up questioning, red-flag detection, triage classification, medical RAG, care plan generation, doctor report generation, safety checking and Vietnamese response generation.

## Scope

CareGuide Agent supports initial symptom screening only. It does not replace doctors, does not provide a final diagnosis and does not prescribe medication.

Core documents:

- `docs/scope.md`
- `docs/triage_labels.md`
- `docs/safety_policy.md`

## Current Project Structure

```text
data/
  raw/
  processed/
  test_cases/
docs/
reports/
src/
  app/
  careguide/
    agents/
    graph/
    rag/
    safety/
    schemas/
    triage/
    utils/
tests/
```

## Initial Test Data

The first evaluation files are:

- `data/test_cases/vietnamese_triage_cases.jsonl`
- `data/test_cases/safety_cases.jsonl`

These files are used to test whether the system can:

- Extract symptoms, negations, vitals and duration.
- Detect red flags.
- Classify triage level into `self_care`, `routine_visit`, `urgent_visit` and `emergency`.
- Avoid unsafe medical responses such as certain diagnosis, prescriptions and delayed emergency escalation.

## Triage Labels

```text
self_care      = monitor and self-care at home
routine_visit  = schedule a non-urgent visit
urgent_visit   = seek medical care soon
emergency      = seek emergency help now
```

## Next Steps

1. Implement schemas for test cases and agent state.
2. Build `Symptom Parser Agent`.
3. Build `Medical Term Normalizer Agent`.
4. Build `Red-Flag Agent`.
5. Build `Triage Agent`.
6. Add evaluation scripts for the JSONL test cases.
