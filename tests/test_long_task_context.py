import json

import pytest

from resume_tailor_harness.sessions.context import (
    ContextBudgetExceeded,
    bounded_json,
    bounded_sections,
    recent_transcript,
)
from resume_tailor_harness.career_lab.continuation import (
    MemoryItem,
    MemorySelection,
    prepare,
    validated,
)
from resume_tailor_harness.interview.agent import render_debrief_transcript


def test_sources_remain_structured_and_each_offer_is_represented():
    raw = {
        "profile": "large " * 10000,
        "job": {"description": "jd " * 10000},
        "resume": {"content": "resume " * 10000},
        "offers": [{"application_id": i, "notes": "offer " * 10000} for i in range(10)],
    }
    text = bounded_json(raw, 12000)
    result = json.loads(text)
    assert len(text) <= 12000
    assert set(result) == set(raw)
    assert result["profile"]["omitted"]
    assert result["resume"]["content"]["omitted"]
    assert [offer["application_id"] for offer in result["offers"]] == list(range(10))
    assert all(offer["notes"]["omitted"] for offer in result["offers"])


def test_excerpts_account_for_json_escaping_and_unicode():
    text = bounded_json({"source": '\n"你好' * 5000, "id": 7}, 500)
    assert len(text) <= 500
    assert json.loads(text)["id"] == 7
    with pytest.raises(ContextBudgetExceeded):
        bounded_json({str(i): "a" * 100 for i in range(100)}, 500)


def test_current_request_is_not_sliced_by_whole_prompt_budget():
    request = "Correction: remote only."
    text = bounded_sections(
        ["overview" * 10000, "history" * 10000, request], limit=1000, required=(2,)
    )
    assert len(text) <= 1000 and text.endswith(request) and "elided" in text
    with pytest.raises(ContextBudgetExceeded):
        bounded_sections(["context", "x" * 1001], limit=1000, required=(1,))


def test_summary_saturation_keeps_newest_prior_answer_tail():
    text = recent_transcript(
        "TRANSCRIPT:\n",
        ["old summary " * 1000],
        ["answer " * 1000 + "LATEST_SENTINEL"],
        500,
    )
    assert len(text) <= 500
    assert text.endswith("LATEST_SENTINEL")
    assert "elided" in text


def test_debrief_includes_completed_answers_but_not_maintenance():
    session = {
        "plan": [{"id": "q1", "status": "done"}],
        "turns": [
            {"role": "candidate", "question_id": "q1", "text": "ANSWER_SENTINEL"},
            {
                "role": "candidate",
                "question_id": "q1",
                "text": "MAINTENANCE",
                "workspace_request": True,
            },
        ],
    }
    assert "ANSWER_SENTINEL" in render_debrief_transcript(session)
    assert "MAINTENANCE" not in render_debrief_transcript(session)
    with pytest.raises(ContextBudgetExceeded):
        render_debrief_transcript(session, char_cap=10)


def _session():
    return {
        "turns": [
            {"turn_id": "t1", "role": "user", "text": "Remote work is mandatory."},
            {"turn_id": "t2", "role": "assistant", "text": "Draft comparison."},
            {"turn_id": "t3", "role": "user", "text": "Compare the offers."},
            {"turn_id": "t4", "role": "assistant", "text": "Recent draft."},
        ]
    }


def test_continuation_survives_reload_and_preserves_prior_corrections():
    session = _session()

    def select(_chunk):
        return MemorySelection(
            items=[
                MemoryItem(
                    kind="constraint", turn_id="t1", quote="Remote work is mandatory."
                )
            ]
        ), "fake"

    state = prepare(session, select)
    session["continuation"] = json.loads(state.model_dump_json())
    assert validated(session) == state
    session["turns"] += [
        {"turn_id": "t5", "role": "user", "text": "Hybrid is now acceptable."},
        {"turn_id": "t6", "role": "assistant", "text": "Updated draft."},
    ]
    second = prepare(
        session,
        lambda chunk: (
            MemorySelection(
                items=[
                    MemoryItem(
                        kind="open_task", turn_id="t3", quote="Compare the offers."
                    )
                ]
            ),
            "fake",
        ),
    )
    assert second.items[0] == state.items[0]
    assert second.through_turn == 4
    session["turns"][0]["text"] = "Changed source"
    with pytest.raises(ContextBudgetExceeded, match="no longer matches"):
        validated(session)


@pytest.mark.parametrize(
    "items",
    [[], [MemoryItem(kind="decision", turn_id="other", quote="Invented approval")]],
)
def test_bad_memory_never_advances_checkpoint(items):
    session = _session()
    with pytest.raises(ContextBudgetExceeded):
        prepare(session, lambda chunk: (MemorySelection(items=items), "fake"))
    assert "continuation" not in session
