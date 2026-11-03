import asyncio
import json
from types import SimpleNamespace

import pytest

from resume_tailor_harness.config import Settings
from resume_tailor_harness.decisions import DecisionClient, DOMAIN_CONFIDENCE
from resume_tailor_harness.taxonomy.classification import (
    ClassificationBudget,
    classify_incrementally,
)
from resume_tailor_harness.taxonomy.clusters import ClusterMap
from resume_tailor_harness.taxonomy.decision_classification import select_domains
from resume_tailor_harness.taxonomy.embeddings import CandidateContext
from resume_tailor_harness.tracking.canonicalize import (
    IncrementalDomainGroup,
    IncrementalSkillDomains,
)


class FakeDecisions(DecisionClient):
    def __init__(self):
        super().__init__(
            Settings(
                _env_file=None,  # type: ignore[call-arg]
                openai_decisions_enabled=True,
                openai_decisions_api_key="test",
            )
        )
        self.requests = []

    async def choose(self, questions, *, evidence="", family="", before_request=None):
        if not questions:
            return {}
        if before_request:
            before_request(100)
        self.calls += 1
        self.requests.append((questions, evidence))
        if "categories" in family:
            return {q.key: "languages" for q in questions}
        return {q.key: "lang" for q in questions if q.key == "rust"}


class Standard:
    def __init__(self, *, fail=False):
        self.prompts = []
        self.fail = fail

    def run(self, prompt):
        self.prompts.append(json.loads(prompt))
        if self.fail:
            raise RuntimeError("provider unavailable")
        return SimpleNamespace(
            content=IncrementalSkillDomains(
                domains=[
                    IncrementalDomainGroup(
                        new_label="Novel Tools",
                        new_category="tools-platforms",
                        confidence="high",
                        skills=["novel"],
                    )
                ]
            )
        )

    async def arun(self, prompt):
        return self.run(prompt)


async def classify(client, standard, budget=None):
    return await classify_incrementally(
        demanded_tokens={"rust", "novel"},
        existing=ClusterMap(
            aliases={"rust": "rust", "novel": "novel"},
            domain_label={"lang": "Languages", "unrelated": "Storage"},
            category_of={"lang": "languages", "unrelated": "databases-storage"},
        ),
        canonicalizer=standard,
        themer=standard,
        decisions=client,
        batch_size=60,
        concurrency=2,
        category_cap=12,
        reconcile_batch_size=150,
        candidate_context=CandidateContext(
            domain_candidates={"rust": ("unrelated",), "novel": ("unrelated",)},
            canonical_candidates={},
            peer_candidates={},
            mode="embedding",
        ),
        skill_context={"rust": ["Uses Rust for systems programming"]},
        budget=budget,
    )


async def test_complete_category_directory_and_only_ambiguous_tail_goes_to_standard():
    client, standard = FakeDecisions(), Standard()
    result = await classify(client, standard)
    assert result.additions.domain_of["rust"] == "lang"
    assert result.additions.domain_of["novel"] == "novel-tools"
    assert not result.failures
    assert len(standard.prompts) == 1
    assert standard.prompts[0]["new"] == ["novel"]
    assert standard.prompts[0]["category_hints"] == {"novel": "languages"}
    domain_questions, evidence = client.requests[1]
    assert all(
        question.options == {"lang": "Languages (Programming Languages)"}
        for question in domain_questions
    )
    assert all(
        question.confidence == DOMAIN_CONFIDENCE for question in domain_questions
    )
    assert "Rust for systems programming" in evidence


async def test_paid_siblings_survive_budget_deferred_fallback():
    client, standard = FakeDecisions(), Standard()
    budget = ClassificationBudget(max_calls=3, max_prompt_bytes=200)
    result = await classify(client, standard, budget)
    assert result.additions.domain_of == {"rust": "lang"}
    assert result.deferred_tokens == {"novel"}
    assert not result.failures and not standard.prompts
    assert budget.calls == 2 and result.metrics.prompt_bytes == 200


async def test_last_call_budget_is_kept_for_standard_placement():
    client, standard = FakeDecisions(), Standard()
    budget = ClassificationBudget(max_calls=1, max_prompt_bytes=100_000)
    result = await classify(client, standard, budget)
    assert client.calls == 0
    assert len(standard.prompts) == 1
    assert result.additions.domain_of["novel"] == "novel-tools"


async def test_paid_siblings_survive_standard_provider_failure():
    result = await classify(FakeDecisions(), Standard(fail=True))
    assert result.additions.domain_of == {"rust": "lang"}
    assert len(result.failures) == 1
    assert result.failures[0].tokens == ("novel",)
    assert result.failures[0].kind == "call"
    assert not result.fallback_categories


@pytest.mark.parametrize(
    "domains",
    [
        [],
        [{"id": "general-languages", "label": "General"}],
        [{"id": str(i), "label": str(i)} for i in range(255)],
    ],
)
async def test_no_truncation_or_general_domain_confirmation(domains):
    client = FakeDecisions()
    assignments, categories = await select_domains(
        client,
        ["rust"],
        [{"slug": "languages", "label": "Languages", "domains": domains}],
        {},
        lambda _: None,
    )
    assert not assignments and categories == {"rust": "languages"}
    assert len(client.requests) == 1


async def test_disabled_feature_retains_standard_classifier():
    client, standard = FakeDecisions(), Standard()
    client.settings.openai_decisions_enabled = False
    await classify(client, standard)
    assert not client.requests
    assert standard.prompts[0]["new"] == ["novel", "rust"]


async def test_low_yield_probe_bypasses_remaining_batches_before_fanout():
    client, standard = FakeDecisions(), Standard()
    tokens = {f"skill-{i:03}" for i in range(180)}
    result = await classify_incrementally(
        demanded_tokens=tokens,
        existing=ClusterMap(
            aliases={token: token for token in tokens},
            domain_label={"lang": "Languages"},
            category_of={"lang": "languages"},
        ),
        canonicalizer=standard,
        themer=standard,
        decisions=client,
        batch_size=60,
        concurrency=8,
        category_cap=12,
        reconcile_batch_size=150,
    )
    assert client.domain_bypass is True
    assert client.calls == 2
    assert len(standard.prompts) == 3
    assert result.metrics.domain_batches == 3


async def test_settlement_failure_aborts_instead_of_buying_recovery(monkeypatch):
    from resume_tailor_harness.tenancy.usage import UsageSettlementError
    from resume_tailor_harness.taxonomy import classification

    async def fail(*args):
        raise UsageSettlementError("ledger unavailable")

    monkeypatch.setattr(classification, "select_domains", fail)
    standard = Standard()
    with pytest.raises(UsageSettlementError):
        await classify(FakeDecisions(), standard)
    assert not standard.prompts


async def test_oversized_decision_prompt_leaves_smaller_standard_prompt_admissible():
    client, standard = FakeDecisions(), Standard()
    budget = ClassificationBudget(max_calls=3, max_prompt_bytes=100_000)

    async def oversized(questions, *, before_request=None, **kwargs):
        assert before_request is not None
        before_request(100_001)
        pytest.fail("oversized optional request was admitted")

    client.choose = oversized
    result = await classify(client, standard, budget)
    assert result.additions.domain_of["novel"] == "novel-tools"
    assert not result.deferred_tokens and budget.calls == 1


async def test_second_decision_admission_failure_still_runs_standard_fallback():
    client, standard = FakeDecisions(), Standard()
    original = client.choose
    budget = ClassificationBudget(max_calls=3, max_prompt_bytes=100_000)

    async def choose(questions, *, family="", before_request=None, **kwargs):
        assert before_request is not None
        if "domains" in family:
            before_request(100_001)
            pytest.fail("oversized domain request was admitted")
        return await original(
            questions, family=family, before_request=before_request, **kwargs
        )

    client.choose = choose
    result = await classify(client, standard, budget)
    assert result.additions.domain_of["novel"] == "novel-tools"
    assert not result.deferred_tokens and budget.calls == 2


async def test_queued_batches_recheck_call_headroom_after_acquiring_semaphore():
    class CompleteDecisions(FakeDecisions):
        async def choose(self, questions, *, family="", before_request=None, **kwargs):
            if before_request is not None:
                before_request(100)
            self.calls += 1
            await asyncio.sleep(0)
            return {
                q.key: "languages" if "categories" in family else "lang"
                for q in questions
            }

    tokens = {f"skill-{i}" for i in range(6)}
    client, standard = CompleteDecisions(), Standard()
    budget = ClassificationBudget(max_calls=6, max_prompt_bytes=100_000)
    result = await classify_incrementally(
        demanded_tokens=tokens,
        existing=ClusterMap(
            aliases={token: token for token in tokens},
            domain_label={"lang": "Languages"},
            category_of={"lang": "languages"},
        ),
        canonicalizer=standard,
        themer=standard,
        decisions=client,
        batch_size=2,
        concurrency=1,
        category_cap=12,
        reconcile_batch_size=150,
        budget=budget,
    )
    assert client.calls == 4
    assert budget.calls == 5
    assert len(standard.prompts) == 1
    assert not result.deferred_tokens
