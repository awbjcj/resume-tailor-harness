"""Durable user corrections for derived skill-group assignments."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import Field

from resume_tailor_harness.models.base import ExtensibleModel
from resume_tailor_harness.taxonomy.vocabulary import (
    LEGACY_GROUP_REMAP,
    SKILL_GROUPS,
    SOFT_CATEGORY_SLUGS,
)
from resume_tailor_harness.tracking.match_gap import normalize_skill


def corrections_path(profile_dir: str | Path) -> Path:
    return Path(profile_dir) / "group_corrections.json"


class GroupCorrection(ExtensibleModel):
    group: str
    corrected_at: str = ""


class SkillCategoryDefinition(ExtensibleModel):
    label: str = Field(min_length=1, max_length=80)


class SkillGroupDefinition(ExtensibleModel):
    label: str = Field(min_length=1, max_length=80)
    category: str = "technical"
    custom_label: bool = False


class GroupCorrections(ExtensibleModel):
    corrections: dict[str, GroupCorrection] = Field(default_factory=dict)
    categories: dict[str, SkillCategoryDefinition] = Field(default_factory=dict)
    groups: dict[str, SkillGroupDefinition] = Field(default_factory=dict)
    removed_categories: list[str] = Field(default_factory=list)
    removed_groups: list[str] = Field(default_factory=list)
    automatic: dict[str, str] = Field(default_factory=dict)

    def category_catalog(self) -> dict[str, SkillCategoryDefinition]:
        catalog = {
            key: SkillCategoryDefinition(label=label)
            for key, label in (
                ("technical", "Technical skills"),
                ("people", "People & delivery"),
                ("industry", "Industry knowledge"),
                ("other", "Other"),
            )
        }
        catalog.update(self.categories)
        return {
            k: v
            for k, v in catalog.items()
            if k not in self.removed_categories or k == "other"
        }

    def group_catalog(self) -> dict[str, SkillGroupDefinition]:
        catalog = {
            slug: SkillGroupDefinition(
                label=label,
                category="other"
                if slug == "other"
                else "industry"
                if slug == "domain-knowledge"
                else "people"
                if slug in SOFT_CATEGORY_SLUGS
                else "technical",
            )
            for slug, label in SKILL_GROUPS.items()
        }
        catalog.update(self.groups)
        categories = self.category_catalog()
        return {
            key: value.model_copy(
                update={
                    "category": value.category
                    if value.category in categories
                    else "other"
                }
            )
            for key, value in catalog.items()
            if key not in self.removed_groups or key == "other"
        }

    def as_map(self) -> dict[str, str]:
        return {token: entry.group for token, entry in self.corrections.items()}


def load_group_corrections(
    path: str | Path, *, strict: bool = False
) -> GroupCorrections:
    try:
        ledger = GroupCorrections.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return GroupCorrections()
    except (OSError, ValueError):
        if strict:
            raise
        return GroupCorrections()

    clean: dict[str, GroupCorrection] = {}
    for raw_token, entry in ledger.corrections.items():
        token = normalize_skill(raw_token)
        entry.group = LEGACY_GROUP_REMAP.get(entry.group, entry.group)
        if token and entry.group in ledger.group_catalog():
            clean.setdefault(token, entry)
    ledger.corrections = clean
    return ledger


def save_group_corrections(ledger: GroupCorrections, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(ledger.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
