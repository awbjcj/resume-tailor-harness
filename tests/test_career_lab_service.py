"""Career Lab orchestration tests cover commit and cancellation boundaries."""

from pathlib import Path
import json
from types import SimpleNamespace
from typing import TypedDict

import pytest

from resume_tailor_harness.career_lab.models import CareerLabContextRefs, CareerLabRoute
from resume_tailor_harness.career_lab.store import create_session, load_session
from resume_tailor_harness.career_skills.models import (
    AgentFamily,
    AgentRunMeta,
    CareerLabSkillName,
)
from resume_tailor_harness.career_skills.registry import CareerSkillRegistry
from resume_tailor_harness.services import career_lab
from resume_tailor_harness.sessions.stream import NullSink


class _Reporter:
    def __init__(self, *, cancel=False):
        self.cancel = cancel

    def begin(self, *_args, **_kwargs):
        return None

    def step(self, *_args, **_kwargs):
        return None

    def checkpoint(self):
        if self.cancel:
            raise RuntimeError("cancelled")


class _Response:
    def __init__(self, content: object) -> None:
        self.content = content


class _Persona:
    def __init__(self, meta: AgentRunMeta) -> None:
        self.run_meta = meta
        self.prompts: list[str] = []

    def run(self, prompt: str) -> _Response:
        self.prompts.append(prompt)
        return _Response("Use the offer data to prepare a careful draft.")

    async def arun(self, prompt: str) -> _Response:
        return self.run(prompt)


class _Formatter:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject

    def run(self, prompt: str) -> _Response:
        if self.reject:
            return _Response(
                SimpleNamespace(artifact_type="offer_comparison", title="", summary="")
            )
        from resume_tailor_harness.career_lab.models import CareerLabArtifactMeta

        return _Response(
            CareerLabArtifactMeta(
                artifact_type="offer_comparison",
                title="Offer comparison",
                summary="Review base, equity, and downside risk.",
            )
        )

    async def arun(self, prompt: str) -> _Response:
        return self.run(prompt)


class _Router:
    def __init__(self, responses: list[CareerLabRoute]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.run_meta = AgentRunMeta(
            agent_family=AgentFamily.CAREER_LAB,
            prompt_policy_version="career-lab-router-v2",
            model_id="test-router",
        )

    def run(self, prompt: str) -> _Response:
        self.prompts.append(prompt)
        return _Response(self.responses.pop(0))

    async def arun(self, prompt: str) -> _Response:
        return self.run(prompt)


class _TurnKwargs(TypedDict):
    reporter: _Reporter
    root: Path
    engine: None
    message: str
    goal: str
    skill: str
    context_refs: CareerLabContextRefs
    sink: NullSink
    registry: CareerSkillRegistry
    persona_agent: _Persona
    formatter_agent: _Formatter


def _skill():
    return CareerSkillRegistry.from_paths("skills", "skills-lock.json").require(
        "salary-negotiation-prep", family=AgentFamily.CAREER_LAB, use="career_lab"
    )


def _meta(skill):
    return AgentRunMeta(
        agent_family=AgentFamily.CAREER_LAB,
        prompt_policy_version="career-lab-persona-v1",
        model_id="test-model",
        skill_ref=skill.ref,
    )


def _turn_kwargs(
    tmp_path: Path,
    *,
    reporter: _Reporter | None = None,
    formatter: _Formatter | None = None,
) -> _TurnKwargs:
    skill = _skill()
    return {
        "reporter": reporter or _Reporter(),
        "root": tmp_path,
        "engine": None,
        "message": "Compare my offers.",
        "goal": "Prepare negotiation points",
        "skill": "salary-negotiation-prep",
        "context_refs": CareerLabContextRefs(offer_application_ids=[7]),
        "sink": NullSink(),
        "registry": CareerSkillRegistry.from_paths("skills", "skills-lock.json"),
        "persona_agent": _Persona(_meta(skill)),
        "formatter_agent": formatter or _Formatter(),
    }


def test_start_turn_persists_user_and_assistant_only_after_validation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        career_lab, "get_settings", lambda: SimpleNamespace(stream_enabled=False)
    )
    result = career_lab.run_start_turn(**_turn_kwargs(tmp_path))
    session = load_session(tmp_path, result["sessionId"])
    assert [turn["role"] for turn in session["turns"]] == ["user", "assistant"]
    assert session["turns"][1]["skill_ref"]["name"] == "salary-negotiation-prep"
    assert session["turns"][1]["agent_meta"]["model_id"] == "test-model"


def test_formatter_retry_exhaustion_degrades_to_visible_persona(tmp_path, monkeypatch):
    monkeypatch.setattr(
        career_lab, "get_settings", lambda: SimpleNamespace(stream_enabled=False)
    )
    result = career_lab.run_start_turn(
        **_turn_kwargs(tmp_path, formatter=_Formatter(reject=True))
    )
    session = load_session(tmp_path, result["sessionId"])
    assistant = session["turns"][1]
    assert assistant["text"].startswith("Use the offer data")
    assert assistant["notice"]
    assert assistant["artifact"] is None


def test_cancel_before_commit_keeps_transcript_byte_identical(tmp_path, monkeypatch):
    monkeypatch.setattr(
        career_lab, "get_settings", lambda: SimpleNamespace(stream_enabled=False)
    )
    create_session(tmp_path, session_id="s1")
    path = tmp_path / "session-s1.json"
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="cancelled"):
        career_lab.run_message_turn(
            reporter=_Reporter(cancel=True),
            root=tmp_path,
            engine=None,
            session_id="s1",
            message="draft this",
            skill="salary-negotiation-prep",
            context_refs=CareerLabContextRefs(),
            sink=NullSink(),
            registry=CareerSkillRegistry.from_paths("skills", "skills-lock.json"),
            persona_agent=_Persona(_meta(_skill())),
            formatter_agent=_Formatter(),
        )
    assert path.read_bytes() == before


def test_ambiguous_request_asks_then_reroutes_from_the_same_transcript(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        career_lab, "get_settings", lambda: SimpleNamespace(stream_enabled=False)
    )
    skill = _skill()
    router = _Router(
        [
            CareerLabRoute(
                needs_selection=True,
                reason="Several outcomes are possible.",
                question="What should the company research help you accomplish?",
            ),
            CareerLabRoute(
                skill=CareerLabSkillName.SALARY_NEGOTIATION_PREP,
                needs_selection=False,
                reason="The user wants negotiation preparation.",
            ),
        ]
    )
    registry = CareerSkillRegistry.from_paths("skills", "skills-lock.json")

    started = career_lab.run_start_turn(
        reporter=_Reporter(),
        root=tmp_path,
        engine=None,
        message="Research Acme.",
        goal="Research Acme.",
        context_refs=CareerLabContextRefs(),
        sink=NullSink(),
        registry=registry,
        router_agent=router,
    )
    session_id = started["sessionId"]
    assert started["turns"][-1]["text"].endswith("help you accomplish?")
    assert started["turns"][-1]["skillRef"] is None

    completed = career_lab.run_message_turn(
        reporter=_Reporter(),
        root=tmp_path,
        engine=None,
        session_id=session_id,
        message="Help me prepare to negotiate an offer.",
        context_refs=CareerLabContextRefs(),
        sink=NullSink(),
        registry=registry,
        router_agent=router,
        persona_agent=_Persona(_meta(skill)),
        formatter_agent=_Formatter(),
    )

    assert completed["sessionId"] == session_id
    assert len(completed["turns"]) == 4
    assert completed["turns"][-1]["skillRef"]["name"] == ("salary-negotiation-prep")
    assert '"text": "Research Acme."' in router.prompts[1]
    assert '"text": "What should the company research' in router.prompts[1]


def _conversation(prompt: str) -> dict:
    encoded = prompt.split("CONVERSATION (UNTRUSTED DATA):\n", 1)[1]
    return json.JSONDecoder().raw_decode(encoded)[0]


def test_complete_history_is_shared_across_skills_after_reload(tmp_path):
    from resume_tailor_harness.career_lab.store import append_turns

    registry = CareerSkillRegistry.from_paths("skills", "skills-lock.json")
    first_skill = _skill()
    next_skill = registry.require(
        "offer-comparison-analyzer", family=AgentFamily.CAREER_LAB, use="career_lab"
    )
    create_session(tmp_path, session_id="shared", goal="Evaluate offers", job_id=7)
    create_session(tmp_path, session_id="other", goal="Other conversation", job_id=8)
    for index in range(5):
        append_turns(
            tmp_path,
            "shared",
            user_text=f"Preference {index}: remote only. " + "detail " * 1000,
            context_refs=CareerLabContextRefs(job_id=7),
            assistant_text=f"Earlier specialist response {index}",
            skill_ref=first_skill.ref,
            agent_meta=_meta(first_skill),
        )
    append_turns(
        tmp_path,
        "other",
        user_text="PRIVATE OTHER THREAD",
        context_refs=CareerLabContextRefs(job_id=8),
        assistant_text="Other answer",
        skill_ref=first_skill.ref,
        agent_meta=_meta(first_skill),
    )
    before = load_session(tmp_path, "shared")
    router = _Router(
        [CareerLabRoute(skill=CareerLabSkillName.OFFER_COMPARISON_ANALYZER)]
    )
    persona = _Persona(_meta(next_skill))
    current = "Correction: hybrid is acceptable. Compare those offers."
    # A fresh service call reloads the on-disk session; no agent memory is reused.
    result = career_lab.run_message_turn(
        reporter=_Reporter(),
        root=tmp_path,
        engine=None,
        session_id="shared",
        message=current,
        context_refs=CareerLabContextRefs(job_id=9),
        registry=registry,
        router_agent=router,
        persona_agent=persona,
        formatter_agent=_Formatter(),
        sink=NullSink(),
    )
    routed = _conversation(router.prompts[0])
    drafted = _conversation(persona.prompts[0])
    assert routed == drafted
    assert [row["text"] for row in routed["history"]] == [
        row["text"] for row in before["turns"]
    ]
    assert len(router.prompts[0]) > 24_000
    assert routed["history"][0]["context_refs"]["job_id"] == 7
    assert routed["history"][1]["skill_ref"]["name"] == first_skill.ref.name
    assert routed["current_turn"]["context_refs"]["job_id"] == 9
    assert routed["current_turn"]["text"] == current
    assert router.prompts[0].count(current) == persona.prompts[0].count(current) == 1
    assert "PRIVATE OTHER THREAD" not in router.prompts[0] + persona.prompts[0]
    assert result["sessionId"] == "shared"
    assert result["turns"][-1]["skillRef"]["name"] == next_skill.ref.name


@pytest.mark.parametrize("explicit_skill", [False, True])
def test_oversize_context_fails_before_agents_and_preserves_session(
    tmp_path, monkeypatch, explicit_skill
):
    from resume_tailor_harness.career_lab import context

    create_session(tmp_path, session_id="s1")
    path = tmp_path / "session-s1.json"
    before = path.read_bytes()
    router = _Router([CareerLabRoute(skill=CareerLabSkillName.SALARY_NEGOTIATION_PREP)])
    persona = _Persona(_meta(_skill()))
    monkeypatch.setattr(context, "MAX_CONVERSATION_BYTES", 100)
    with pytest.raises(
        context.ConversationContextTooLarge, match="too long to send in full"
    ):
        career_lab.run_message_turn(
            reporter=_Reporter(),
            root=tmp_path,
            engine=None,
            session_id="s1",
            message="x" * 200,
            skill="salary-negotiation-prep" if explicit_skill else None,
            registry=CareerSkillRegistry.from_paths("skills", "skills-lock.json"),
            router_agent=router,
            persona_agent=persona,
            formatter_agent=_Formatter(),
        )
    assert router.prompts == persona.prompts == []
    assert path.read_bytes() == before


def test_oversize_start_does_not_create_session(tmp_path, monkeypatch):
    from resume_tailor_harness.career_lab import context

    monkeypatch.setattr(context, "MAX_CONVERSATION_BYTES", 100)
    with pytest.raises(context.ConversationContextTooLarge):
        career_lab.run_start_turn(**_turn_kwargs(tmp_path))
    assert list(tmp_path.glob("session-*.json")) == []
