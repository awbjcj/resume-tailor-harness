# Context projections erased required evidence

## Summary

The long-task audit reproduced two deterministic input failures: interview
debriefs received competency labels instead of completed answers, and Career
Lab source JSON prefix slicing removed later sources and broke JSON framing.

## Root Cause

Practice and grading shared a lossy transcript renderer. Source serialization
and size limiting shared a raw prefix slice with no source-coverage contract.
Existing tests asserted practice collapse and conversation preservation, not the
evidence actually supplied to grading or combinations of attached sources.

## Prevention

Keep scoring projection separate from practice projection. Preserve complete
scored answers or fail explicitly. Allocate source context before serialization;
retain source identities or label omissions. A transcript cap does not bound an
overview or an assembled prompt. Reserve current input and task state first.

## Detection

Run `python -m pytest -n 0 tests/test_long_task_context.py
tests/test_mock_interview_service.py tests/test_career_lab_service.py`.
The full interview test captures the actual debrief prompt. Long-source tests
check JSON validity and each offer identity. Long-history tests exercise actual
service preparation, save, reload and subsequent continuation.

## Evidence

- `interview/agent.py::render_debrief_transcript`
- `sessions/context.py::bounded_json`, `bounded_sections`, `recent_transcript`
- `services/career_lab.py::_resolve_context`
- ADR 0014 describes preserved invariants and remaining measurement limits.
