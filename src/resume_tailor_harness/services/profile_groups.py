"""Set or clear durable skill-group corrections and refresh matrix.json."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from resume_tailor_harness.models.profile import ProfileFacts
from resume_tailor_harness.models.base import new_id
from resume_tailor_harness.profile.group_corrections import (
    GroupCorrection,
    corrections_path,
    load_group_corrections,
    save_group_corrections,
    GroupCorrections,
    SkillCategoryDefinition,
    SkillGroupDefinition,
)
from resume_tailor_harness.profile.manual_skills import manual_skills_lock
from resume_tailor_harness.profile.matrix import (
    MatrixRow,
    SkillMatrix,
    build_decorated_matrix,
    rebuild_saved_matrix,
)
from resume_tailor_harness.profile.store import load_facts
from resume_tailor_harness.services.profile_skills import (
    ProfileNotBuiltError,
    SkillNotFoundError,
)
from resume_tailor_harness.rollback import rollback_scope
from resume_tailor_harness.tracking.match_gap import normalize_skill


class UnknownGroupError(ValueError):
    """Raised when a group slug is outside the fixed vocabulary."""


class GroupCorrectionNotFoundError(ValueError):
    """Raised when the requested skill has no correction to clear."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_facts_or_raise(profile_dir: str | Path) -> ProfileFacts:
    try:
        return load_facts(Path(profile_dir) / "facts.json")
    except FileNotFoundError as exc:
        raise ProfileNotBuiltError(
            "Build your profile before editing skill groups"
        ) from exc


def _resolve_row(matrix: SkillMatrix, key: str) -> MatrixRow:
    token = normalize_skill(key)
    for row in matrix.rows:
        lookup_tokens = {
            row.key,
            normalize_skill(row.display),
            *(normalize_skill(alias) for alias in row.aliases),
        }
        if token in lookup_tokens:
            return row
    raise SkillNotFoundError(f"No skill '{key}'")


def set_group(profile_dir: str | Path, key: str, group: str) -> MatrixRow:
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        row = _resolve_row(build_decorated_matrix(profile_dir, facts), key)
        path = corrections_path(profile_dir)
        ledger = load_group_corrections(path, strict=True)
        if group not in ledger.group_catalog():
            raise UnknownGroupError(f"Unknown group '{group}'")
        ledger.corrections[row.key] = GroupCorrection(
            group=group,
            corrected_at=_utcnow(),
        )
        with rollback_scope((path, Path(profile_dir) / "matrix.json")):
            save_group_corrections(ledger, path)
            return _resolve_row(rebuild_saved_matrix(profile_dir, facts), row.key)


def clear_group(profile_dir: str | Path, key: str) -> None:
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        path = corrections_path(profile_dir)
        ledger = load_group_corrections(path, strict=True)
        token = normalize_skill(key)
        if token not in ledger.corrections:
            token = _resolve_row(build_decorated_matrix(profile_dir, facts), key).key
        if token not in ledger.corrections:
            raise GroupCorrectionNotFoundError(f"No group correction for '{key}'")
        del ledger.corrections[token]
        with rollback_scope((path, Path(profile_dir) / "matrix.json")):
            save_group_corrections(ledger, path)
            rebuild_saved_matrix(profile_dir, facts)


def edit_organization(
    profile_dir: str | Path,
    kind: str,
    *,
    key: str | None = None,
    label: str = "",
    category: str = "other",
    delete: bool = False,
) -> GroupCorrections:
    """CRUD a display category/group without changing the fact-lock skill types."""
    with manual_skills_lock(profile_dir):
        directory = Path(profile_dir)
        path = corrections_path(directory)
        ledger = load_group_corrections(path, strict=True)
        catalog = (
            ledger.group_catalog() if kind == "group" else ledger.category_catalog()
        )
        if key is not None and key not in catalog:
            raise UnknownGroupError(f"Unknown {kind} '{key}'")
        if delete:
            if key == "other":
                raise ValueError("Other is the fallback and cannot be deleted")
            assert key is not None
            if kind == "group":
                ledger.removed_groups.append(key)
                ledger.groups.pop(key, None)
                ledger.corrections = {
                    k: v for k, v in ledger.corrections.items() if v.group != key
                }
                ledger.automatic = {
                    k: v for k, v in ledger.automatic.items() if v != key
                }
            else:
                for slug, definition in ledger.group_catalog().items():
                    if definition.category == key:
                        ledger.groups[slug] = definition.model_copy(
                            update={"category": "other"}
                        )
                ledger.removed_categories.append(key)
                ledger.categories.pop(key, None)
        else:
            label = label.strip()
            if not label or len(label) > 80:
                raise ValueError("Enter a name between 1 and 80 characters")
            if any(
                k != key and v.label.casefold() == label.casefold()
                for k, v in catalog.items()
            ):
                raise ValueError(f"A {kind} with this name already exists")
            key = key or f"custom-{new_id()}"
            if kind == "group":
                if category not in ledger.category_catalog():
                    raise UnknownGroupError(f"Unknown category '{category}'")
                ledger.groups[key] = SkillGroupDefinition(
                    label=label, category=category, custom_label=True
                )
            else:
                ledger.categories[key] = SkillCategoryDefinition(label=label)
        with rollback_scope((path, directory / "matrix.json")):
            save_group_corrections(ledger, path)
            if (directory / "facts.json").is_file():
                rebuild_saved_matrix(directory, load_facts(directory / "facts.json"))
        return ledger
