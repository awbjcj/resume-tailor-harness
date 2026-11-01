"""Lossless projection of the labeled project-resume-dossier evidence format.

These are source claims, not an independent audit of the cited repository.
No paths or commands in a dossier are executed. Older/freeform documents still
use the project extractor; the labeled format makes evidence retention mechanical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from resume_tailor_harness.models.profile import Bullet, ProfileFacts, Skill


@dataclass
class DossierSkill:
    name: str
    group: str
    context: str = ""
    aliases: list[str] = field(default_factory=list)
    alias_text: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class Dossier:
    extraction_text: str = ""
    skills: list[DossierSkill] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    tech: list[str] = field(default_factory=list)
    drops: list[str] = field(default_factory=list)


def _lines(text: str) -> list[str]:
    """Ignore fenced examples rather than ingesting a template as personal facts."""
    result: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            result.append(line)
    return result


def _items(lines: list[str]) -> list[str]:
    """Top-level markdown bullets, joining soft-wrapped source lines only."""
    items: list[str] = []
    for line in lines:
        match = re.match(r"^[-*] +(.+)", line)
        if match:
            items.append(match[1].strip())
        elif items and line[:1].isspace() and line.strip():
            items[-1] += " " + line.strip()
    return items


def _has_cited_application(text: str) -> bool:
    # A repository-relative path, optionally qualified by symbol/lines. Bare
    # hashes, URLs, commands and a file path alone are not usage evidence.
    citations = re.findall(r"`([^`]+)`", text)
    path = re.compile(
        r"^(?!/|\\|\.\./)(?:[\w.-]+/)*(?:[\w.-]+\.[\w-]+|Dockerfile|Makefile)"
        r"(?::[^\s`]+)?$"
    )
    explained = re.sub(r"`[^`]+`", "", text).split("—", 1)[0].strip(" -:.,()")
    return (
        any(path.fullmatch(value) for value in citations)
        and any(character.isalpha() for character in explained)
    )


def parse_dossier(text: str) -> Dossier | None:
    """Recognize labeled skill entries; never guess at freeform skill lists."""
    sections: dict[str, list[str]] = {}
    section = ""
    has_project = False
    metadata_lines: list[str] = []
    for line in _lines(text):
        if line.startswith("# Project:"):
            has_project = True
        if line.startswith("## "):
            section = line[3:].strip().casefold().split(" (")[0]
            sections.setdefault(section, [])
        else:
            sections.setdefault(section, []).append(line)
        if section in ("", "summary", "tech stack"):
            metadata_lines.append(line)
    skill_lines = sections.get("skills demonstrated", [])
    if not has_project or not any(
        re.match(r"^[-*] Name:", line) for line in skill_lines
    ):
        return None

    dossier = Dossier(extraction_text="\n".join(metadata_lines))
    group = "Other"
    current: DossierSkill | None = None
    active = ""
    for line in skill_lines:
        if line.startswith("### "):
            group = line[4:].strip()
            current = None
            active = ""
            continue
        name = re.match(r"^[-*] Name:\s*(.*)", line)
        if name:
            current = DossierSkill(name=name[1].strip(), group=group)
            dossier.skills.append(current)
            active = ""
            continue
        if current is None:
            continue
        label = re.match(r"^  [-*] (Context|Aliases|Evidence):\s*(.*)", line)
        if label:
            active = label[1].casefold()
            if active == "context":
                current.context = label[2].strip()
            elif active == "aliases":
                current.alias_text = label[2].strip()
            continue
        example = re.match(r"^    [-*] (.+)", line)
        if active == "evidence" and example:
            current.evidence.append(example[1].strip())
        elif line[:1].isspace() and line.strip():
            if active == "context":
                current.context += " " + line.strip()
            elif active == "aliases":
                current.alias_text += " " + line.strip()
            elif active == "evidence" and current.evidence:
                current.evidence[-1] += " " + line.strip()

    valid: list[DossierSkill] = []
    for skill in dossier.skills:
        skill.aliases = list(
            dict.fromkeys(
                value.strip() for value in skill.alias_text.split(",") if value.strip()
            )
        )
        examples = list(dict.fromkeys(skill.evidence))
        skill.evidence = [
            example for example in examples if _has_cited_application(example)
        ]
        if len(skill.evidence) != len(examples):
            dossier.drops.append(
                f"{skill.name}: omitted evidence without an explained repository citation"
            )
        if not skill.name or not skill.context.strip() or not skill.evidence:
            dossier.drops.append(
                f"{skill.name or 'Unnamed skill'}: requires a usage context and cited evidence"
            )
        else:
            valid.append(skill)
    dossier.skills = valid
    for heading in ("architecture highlights", "quantified outcomes"):
        dossier.highlights.extend(
            item
            for item in _items(sections.get(heading, []))
            if item.casefold().rstrip(".") != "none evidenced"
        )
    for item in _items(sections.get("tech stack", [])):
        name = re.split(r"\s+[—–-]\s+", item, maxsplit=1)[0].strip()
        if name and name not in dossier.tech:
            dossier.tech.append(name)
    return dossier


def retain_dossier_evidence(facts: ProfileFacts, dossier: Dossier) -> ProfileFacts:
    """Replace lossy model summaries with the source's complete evidence bank."""
    output = facts.model_copy(deep=True)
    project = output.projects[0]
    project.tech = list(dossier.tech)
    project.highlights = []
    by_text: dict[str, Bullet] = {}

    def retain(text: str) -> Bullet:
        key = " ".join(text.split()).casefold()
        if key not in by_text:
            bullet = Bullet(text=text, source=project.source)
            by_text[key] = bullet
            project.highlights.append(bullet)
        return by_text[key]

    for text in dossier.highlights:
        retain(text)
    # The recognized roster is authoritative. Do not reintroduce omitted or
    # invented skills from the model response, or copy model-generated IDs.
    output.skills = {}
    for entry in dossier.skills:
        examples = [retain(text) for text in entry.evidence]
        skill = Skill(
            name=entry.name,
            aliases=entry.aliases,
            context=f"{project.name}: {entry.context}\nEvidence:\n"
            + "\n".join(f"- {text}" for text in entry.evidence),
            source=project.source,
            evidence_fact_ids=[example.id for example in examples],
        )
        output.skills.setdefault(entry.group, []).append(skill)
    return output
