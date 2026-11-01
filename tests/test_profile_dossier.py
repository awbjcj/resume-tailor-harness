"""Dossier evidence survives extraction, caching, merge and tailoring."""

import asyncio
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from resume_tailor_harness.models.base import Source
from resume_tailor_harness.models.job import JobCriteria
from resume_tailor_harness.models.profile import Contact, ProfileFacts, Project, Skill
from resume_tailor_harness.models.resume import (
    ResumeContent,
    TailoredBullet,
    TailoredProject,
    TailoredSkill,
)
from resume_tailor_harness.profile.corpus import SourceDoc, add_source, load_manifest
from resume_tailor_harness.profile.dossier import parse_dossier
from resume_tailor_harness.profile.fragments import extract_project_fragments
from resume_tailor_harness.profile.ids import assign_fact_ids
from resume_tailor_harness.profile.matrix import build_matrix, build_skill_match_context
from resume_tailor_harness.profile.merge import merge_fragments
from resume_tailor_harness.profile.project_extractor import (
    ProjectDocFacts,
    aextract_project_facts,
)
from resume_tailor_harness.taxonomy.clusters import ClusterMap
from resume_tailor_harness.taxonomy.snapshot import EffectiveTaxonomy
from resume_tailor_harness.tailor.evidence_portfolio import build_evidence_catalog
from resume_tailor_harness.tailor.numeric_evidence import numeric_evidence_critique
from resume_tailor_harness.tailor.provenance import (
    check_provenance,
    index_facts,
    resolve_evidence,
)


DOSSIER = """---
repo_url: https://github.com/example/monorepo
---
# Project: Worker
## Summary
An archived worker. Role: contributor.
Repository: https://github.com/example/monorepo/tree/main/worker
Timeline: 2021-01 – 2022-06
## Tech stack (evidence-backed)
- Python — worker in `src/worker.py`.
## Architecture highlights
- Isolated failed requests — `src/worker.py:run` (commit `abcd1234`).
## Quantified outcomes
- Processed 42 fixtures in an offline test — `tests/test_worker.py:test_batch`.
## Skills demonstrated
### Languages
- Name: Python
  - Aliases: Python 3
  - Context: Implemented the worker and its
    regression tests.
  - Evidence:
    - Bounded in-flight requests to protect the worker —
      `src/worker.py:run` (commit `abcd1234`).
    - Tested cancellation while preserving completed results — `tests/test_worker.py:test_cancel`.
### Architecture
- Name: Concurrency
  - Context: Kept independent requests isolated.
  - Evidence:
    - Bounded in-flight requests to protect the worker — `src/worker.py:run` (commit `abcd1234`).
"""


class LossyAgent:
    """Simulate a model that omits most evidence and adds an unsupported skill."""

    def __init__(self, name="Worker"):
        self.calls = 0
        self.name = name

    def run(self, prompt):
        self.calls += 1
        return SimpleNamespace(
            content=ProjectDocFacts(
                project=Project(
                    name=self.name,
                    role="contributor",
                    end="2022-06",
                    repo_url="https://github.com/example/monorepo/tree/main/worker",
                ),
                skills={
                    "Tools": [
                        Skill(
                            name="Invented",
                            context="Unsupported",
                            evidence_fact_ids=["forged"],
                        )
                    ]
                },
            )
        )

    async def arun(self, prompt):
        return self.run(prompt)


def extract(text=DOSSIER, name="Worker", doc_id="worker"):
    return assign_fact_ids(
        asyncio.run(
            aextract_project_facts(
                text, LossyAgent(name), source=Source.manual, sem=asyncio.Semaphore(1)
            )
        ),
        doc_id,
    )


def source(doc_id, *, primary=False):
    return SourceDoc(
        id=doc_id,
        filename=f"{doc_id}.md",
        primary=primary,
        sha256="test",
        added_at="2026-11-01T00:00:00Z",
    )


def test_full_source_evidence_becomes_stable_facts_without_model_compression():
    facts = extract()
    project = facts.projects[0]
    python = facts.skills["Languages"][0]
    concurrency = facts.skills["Architecture"][0]
    assert project.tech == ["Python"]
    assert project.repo_url and project.repo_url.endswith("/tree/main/worker")
    assert project.end == "2022-06"
    assert len(project.highlights) == 4  # shared usage is one fact, not two
    assert python.aliases == ["Python 3"]
    assert python.context is not None
    assert "worker and its regression tests" in python.context
    assert "commit `abcd1234`" in python.context
    assert len(python.evidence_fact_ids) == 2
    assert concurrency.evidence_fact_ids == python.evidence_fact_ids[:1]
    assert all(
        b.source_ref == "worker" and b.source == Source.manual
        for b in project.highlights
    )
    assert not python.inferred
    assert facts == extract()
    assert assign_fact_ids(facts, "worker") == facts
    assert set(python.evidence_fact_ids) <= index_facts(facts).keys()
    assert facts.experience == facts.education == facts.certifications == []


def test_invalid_evidence_and_fenced_templates_do_not_become_skills():
    text = (
        DOSSIER
        + """
- Name: Docker
  - Context: Listed as a dependency.
  - Evidence:
    - `Dockerfile:1`
- Name: Kubernetes
  - Context: Claimed without a citation.
  - Evidence:
    - Orchestrated clusters for high availability.
```markdown
- Name: Example skill
  - Context: An illustrative template.
  - Evidence:
    - Implemented an example template — `example.py:run`.
```
"""
    )
    drops: list[str] = []
    facts = asyncio.run(
        aextract_project_facts(
            text,
            LossyAgent(),
            source=Source.github,
            sem=asyncio.Semaphore(1),
            drops=drops,
        )
    )
    assert {s.name for values in facts.skills.values() for s in values} == {
        "Python",
        "Concurrency",
    }
    assert any("Docker" in drop for drop in drops)
    assert any("Kubernetes" in drop for drop in drops)
    assert all("Example skill" not in drop for drop in drops)


@pytest.mark.parametrize("explanation", ["Tested cancellation", "Automatisiert", "验证取消"])
def test_short_cited_applications_retain_skill_and_evidence(explanation):
    example = f"{explanation} — `tests/test_worker.py:test_cancel`."
    text = "\n".join(
        [
            "# Project: Worker",
            "## Skills demonstrated",
            "### Testing",
            "- Name: pytest",
            "  - Context: Verified cancellation releases worker resources.",
            "  - Evidence:",
            f"    - {example}",
        ]
    )
    dossier = parse_dossier(text)
    assert dossier is not None and not dossier.drops
    facts = extract(text)
    skill = facts.skills["Testing"][0]
    highlight = facts.projects[0].highlights[0]
    assert skill.name == "pytest"
    assert highlight.text == example
    assert skill.evidence_fact_ids == [highlight.id]
    assert skill.context and example in skill.context


def test_freeform_project_documents_keep_existing_extractor_behavior():
    assert (
        parse_dossier("# Project: Legacy\n## Skills demonstrated\nLanguages: Python")
        is None
    )
    assert parse_dossier("```markdown\n" + DOSSIER + "\n```") is None


def test_wrapped_aliases_and_repository_symbol_spelling_survive():
    text = DOSSIER.replace("Aliases: Python 3", "Aliases: Python 3,\n    CPython")
    text = text.replace("src/worker.py:run", "src/worker.py:Worker.run()")
    text = text.replace(
        "tests/test_worker.py:test_cancel", "tests/test_worker.py:20–28"
    )
    facts = extract(text)
    skill = facts.skills["Languages"][0]
    assert skill.aliases == ["Python 3", "CPython"]
    assert len(skill.evidence_fact_ids) == 2
    assert (
        skill.context and "Worker.run()" in skill.context and "20–28" in skill.context
    )


def test_repository_dossier_retains_every_labeled_skill_and_usage_example():
    text = (Path(__file__).parents[1] / "resume-tailor-harness-dossier.md").read_text(
        encoding="utf-8"
    )
    facts = extract(text)
    names = re.findall(r"^- Name: (.+)$", text, flags=re.MULTILINE)
    examples = re.findall(r"^    - (.+)$", text, flags=re.MULTILINE)
    skills = [s for values in facts.skills.values() for s in values]
    assert {s.name for s in skills} == set(names)
    assert len(skills) >= 30
    assert len(examples) >= 80
    assert set(examples) <= {b.text for b in facts.projects[0].highlights}
    index = index_facts(facts)
    for skill in skills:
        assert skill.context and skill.evidence_fact_ids
        assert all(index[fid].text in skill.context for fid in skill.evidence_fact_ids)
    dossier = parse_dossier(text)
    assert dossier is not None and not dossier.drops
    assert "Evidence revision:" in dossier.extraction_text
    assert "Role: sole author" in dossier.extraction_text
    assert "## Skills demonstrated" not in dossier.extraction_text
    assert "## Quantified outcomes" not in dossier.extraction_text


def test_evidence_links_survive_cache_and_cross_project_skill_merge(tmp_path):
    source_path = tmp_path / "worker-dossier.md"
    source_path.write_text(DOSSIER, encoding="utf-8")
    directory = tmp_path / "profile"
    doc = add_source(directory, source_path, mode="project")
    agent = LossyAgent()
    first = extract_project_fragments(directory, load_manifest(directory), agent)
    cached = extract_project_fragments(directory, load_manifest(directory), agent)
    assert agent.calls == 1 and cached.status[doc.id] == "cached"
    assert first.fragments == cached.fragments
    other = extract(DOSSIER.replace("worker", "scheduler"), "Scheduler", "scheduler")
    other.projects[
        0
    ].repo_url = "https://github.com/example/monorepo/tree/main/scheduler"
    merged, report = merge_fragments(
        [
            (
                source("resume", primary=True),
                ProfileFacts(contact=Contact(name="Ada")),
            ),
            (doc, cached.fragments[doc.id]),
            (source("scheduler"), other),
        ]
    )
    assert len(merged.projects) == 2
    python = merged.skills["Languages"][0]
    assert python.context is not None
    assert "Worker:" in python.context and "Scheduler:" in python.context
    assert set(python.source_refs) == {doc.id, "scheduler"}
    assert len(python.evidence_fact_ids) == 4
    assert set(python.evidence_fact_ids) <= index_facts(merged).keys()
    assert not any("context" in conflict for conflict in report.conflicts)


def test_duplicate_project_merge_relinks_evidence_to_retained_highlights():
    first = extract(doc_id="first")
    second = extract(doc_id="second")
    merged, _ = merge_fragments(
        [
            (source("first", primary=True), first),
            (source("second"), second),
        ]
    )
    assert len(merged.projects) == 1 and len(merged.projects[0].highlights) == 4
    skill = merged.skills["Languages"][0]
    assert skill.evidence_fact_ids == first.skills["Languages"][0].evidence_fact_ids
    assert set(skill.evidence_fact_ids) <= index_facts(merged).keys()
    assert len(second.projects[0].highlights) == 4  # inputs remain untouched


def test_broad_skill_links_drive_project_match_and_reviewer_evidence():
    facts = extract()
    taxonomy = EffectiveTaxonomy.from_parts(ClusterMap.empty())
    matrix = build_matrix(facts, taxonomy, today=date(2026, 11, 1))
    row = next(row for row in matrix.rows if row.key == "concurrency")
    skill = facts.skills["Architecture"][0]
    assert row.last_used == "2022-06"
    assert set(row.evidence_fact_ids) == {skill.id, *skill.evidence_fact_ids}
    assert row.strength > 1  # explicit skill plus its dated application
    criteria = JobCriteria(must_have_skills=["Concurrency"])
    context = build_skill_match_context(criteria, matrix, taxonomy.cluster_map)
    catalog = build_evidence_catalog(facts, criteria, context)
    assert catalog.owners[0].direct_requirements == ["Concurrency"]
    content = ResumeContent(
        contact=facts.contact,
        skills={
            "Architecture": [TailoredSkill(name="Concurrency", provenance=skill.id)]
        },
    )
    assert check_provenance(content, facts).ok
    evidence = resolve_evidence(content, facts)
    assert "src/worker.py:run" in evidence[skill.evidence_fact_ids[0]]["text"]


def test_individual_dossier_fact_allows_only_its_evidenced_numbers():
    facts = extract()
    project = facts.projects[0]
    metric = next(b for b in project.highlights if "42 fixtures" in b.text)
    bullet = TailoredBullet(text="Processed 42 fixtures", provenance=metric.id)
    content = ResumeContent(
        contact=facts.contact,
        projects=[
            TailoredProject(name=project.name, provenance=project.id, bullets=[bullet])
        ],
    )
    assert check_provenance(content, facts).ok
    assert numeric_evidence_critique(content, facts).passed
    bullet.text = "Processed 999 fixtures"
    assert not numeric_evidence_critique(content, facts).passed
