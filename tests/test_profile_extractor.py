import pytest
import asyncio

from resume_tailor_harness.llm_runner import AgentRunner

from resume_tailor_harness.models.profile import Contact, ProfileFacts
from resume_tailor_harness.profile.extractor import (
    build_extractor_agent,
    extract_profile_facts,
)
from resume_tailor_harness.profile.extractor import aextract_profile_facts
from resume_tailor_harness.models.importance import FactImportanceSignals
from resume_tailor_harness.models.profile import Bullet, Experience


class _FakeResult:
    def __init__(self, content):
        self.content = content


class _FakeAgent:
    def __init__(self, content):
        self._content = content
        self.received = None

    def run(self, prompt):
        self.received = prompt
        return _FakeResult(self._content)

    async def arun(self, prompt):
        return self.run(prompt)


def test_sync_and_async_extraction_retain_assessments_and_compute_the_same_score():
    rating = FactImportanceSignals(
        significance=4, essentiality=3, impact=2, ownership=2
    )
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        experience=[
            Experience(
                company="Acme",
                title="Engineer",
                bullets=[
                    Bullet(text="Implemented a service", importance=rating),
                ],
            )
        ],
    )
    sync = extract_profile_facts("Resume", _FakeAgent(facts))
    async_result = asyncio.run(
        aextract_profile_facts(
            "Resume",
            _FakeAgent(facts),
            sem=asyncio.Semaphore(1),
        )
    )
    assert sync == async_result
    assert sync.experience[0].bullets[0].importance == rating
    assert sync.experience[0].bullets[0].importance_score is not None
    assert facts.experience[0].bullets[0].importance_score is None


def test_extract_returns_profilefacts_and_passes_text():
    facts = ProfileFacts(contact=Contact(name="Ada"))
    agent = _FakeAgent(facts)
    result = extract_profile_facts("raw resume text", agent)
    assert result == facts
    assert result is not facts
    assert agent.received == "raw resume text"


def test_extract_rejects_wrong_type():
    agent = _FakeAgent("not a ProfileFacts")
    with pytest.raises(TypeError):
        extract_profile_facts("x", agent)


def test_build_extractor_agent_is_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    agent = build_extractor_agent(model_id="claude-haiku-4-5-20251001")
    assert isinstance(agent, AgentRunner)


def test_extractor_defaults_to_mid_tier(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    captured = {}

    import resume_tailor_harness.profile.extractor as extractor_mod

    def _fake_build_model(model_id, api_key=None, **kwargs):
        captured["id"] = model_id
        return object()

    class _FakeAgent:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(extractor_mod, "build_model", _fake_build_model)
    monkeypatch.setattr(extractor_mod, "Agent", _FakeAgent)

    extractor_mod.build_extractor_agent()
    assert captured["id"] == extractor_mod.get_settings().mid_model
