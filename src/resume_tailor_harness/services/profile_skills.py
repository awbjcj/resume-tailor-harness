"""Quick-add a skill or alias from a job's gap chip -- takes effect immediately.

Coverage on a job card is computed live from facts.json on every request
(``tracking/queries.py::_skill_tags``), so a facts.json write is the entire
"immediate effect" mechanism; the only other artifact that needs refreshing
is the derived, sha-cached ``matrix.json`` (Settings > Skill Matrix, Match/Gap
dashboard).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from resume_tailor_harness.models.profile import ProfileFacts, Skill
from resume_tailor_harness.profile.manual_skills import (
    ManualAliasEntry,
    ManualSkillEntry,
    ManualSuppressEntry,
    ManualEditEntry,
    ManualMergeEntry,
    ManualSkillsLedger,
    apply_manual_skills,
    load_manual_skills,
    manual_skills_lock,
    save_manual_skills,
)
from resume_tailor_harness.profile.matrix import rebuild_saved_matrix, load_overrides
from resume_tailor_harness.profile.store import load_facts, save_facts
from resume_tailor_harness.profile.conversation import (
    capture_skill_overrides,
    edits_path,
    load_edits,
    save_edits,
)
from resume_tailor_harness.rollback import rollback_scope
from resume_tailor_harness.tracking.match_gap import normalize_skill


class ProfileNotBuiltError(RuntimeError):
    """Raised when a skill mutation is attempted before facts.json exists."""


class SkillAlreadyExistsError(ValueError):
    """Raised when the requested skill/alias already matches a profile skill."""


class SkillNotFoundError(ValueError):
    """Raised when a skill id passed to ``add_alias`` doesn't resolve."""


class SuppressedSkillNotFoundError(ValueError):
    """Raised when a requested skill is not suppressed."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _facts_path(profile_dir: str | Path) -> Path:
    return Path(profile_dir) / "facts.json"


def _ledger_path(profile_dir: str | Path) -> Path:
    return Path(profile_dir) / "manual_skills.json"


def _load_facts_or_raise(profile_dir: str | Path) -> ProfileFacts:
    try:
        return load_facts(_facts_path(profile_dir))
    except FileNotFoundError as exc:
        raise ProfileNotBuiltError("Build your profile before adding skills") from exc


def _known_tokens(facts: ProfileFacts) -> set[str]:
    return {
        normalize_skill(alias)
        for skills in facts.skills.values()
        for skill in skills
        for alias in (skill.name, *skill.aliases)
    }


def _publish(
    profile_dir: str | Path,
    facts: ProfileFacts,
    ledger: ManualSkillsLedger,
    *,
    group: str | None = None,
    skill_key: str = "",
    restoring_token: str = "",
) -> None:
    from resume_tailor_harness.profile.group_corrections import (
        corrections_path,
        load_group_corrections,
        save_group_corrections,
        GroupCorrection,
    )

    directory = Path(profile_dir)
    organization_path = corrections_path(directory)
    edits = load_edits(directory)
    capture_skill_overrides(facts, edits, restoring_token=restoring_token)
    with rollback_scope(
        (
            directory / "facts.json",
            directory / "manual_skills.json",
            directory / "matrix.json",
            organization_path,
            edits_path(directory),
        )
    ):
        if group is not None:
            organization = load_group_corrections(organization_path, strict=True)
            if group:
                if group not in organization.group_catalog():
                    raise ValueError("Choose an existing skill group")
                organization.corrections[normalize_skill(skill_key)] = GroupCorrection(
                    group=group, corrected_at=_utcnow()
                )
            else:
                for skill in _resolve_skills(directory, facts, skill_key):
                    for name in (skill.name, *skill.aliases):
                        organization.corrections.pop(normalize_skill(name), None)
            save_group_corrections(organization, organization_path)
        save_facts(facts, directory / "facts.json")
        save_manual_skills(ledger, directory / "manual_skills.json")
        if edits_path(directory).exists():
            save_edits(directory, edits)
        rebuild_saved_matrix(directory, facts)


def _resolve_skills(
    profile_dir: str | Path, facts: ProfileFacts, key: str
) -> list[Skill]:
    from resume_tailor_harness.profile.effective import build_effective_taxonomy

    taxonomy = build_effective_taxonomy(profile_dir)
    token = normalize_skill(key)
    canonical = taxonomy.cluster_map.aliases.get(token, token)
    matched = [
        skill
        for skills in facts.skills.values()
        for skill in skills
        if skill.id == key
        or any(
            taxonomy.cluster_map.aliases.get(t, t) == canonical
            for name in (skill.name, *skill.aliases)
            if (t := normalize_skill(name))
        )
    ]
    if not matched:
        raise SkillNotFoundError(f"No skill '{key}'")
    return matched


def update_skill(
    profile_dir: str | Path,
    key: str,
    name: str,
    aliases: list[str],
    category: Literal["hard", "soft", "domain"] | None,
    *,
    group: str | None = None,
) -> None:
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        selected = _resolve_skills(profile_dir, facts, key)
        name = name.strip()
        if not normalize_skill(name):
            raise ValueError("Skill name is required")
        selected_ids = {s.id for s in selected}
        other_tokens = {
            normalize_skill(n)
            for skills in facts.skills.values()
            for s in skills
            if s.id not in selected_ids
            for n in (s.name, *s.aliases)
        }
        if any(normalize_skill(n) in other_tokens for n in (name, *aliases)):
            raise SkillAlreadyExistsError(
                "A name or alias already belongs to another skill. Merge the skills instead."
            )
        if category is None and any(s.inferred for s in selected):
            raise ValueError("Choose a skill type for an inferred skill")
        ledger = load_manual_skills(_ledger_path(profile_dir))
        if len(selected) > 1:
            ledger.entries.append(
                ManualMergeEntry(
                    tokens=[normalize_skill(s.name) for s in selected],
                    target_token=normalize_skill(selected[0].name),
                    added_at=_utcnow(),
                )
            )
        # The previous names remain aliases so future source builds can reattach edits.
        names = list(
            dict.fromkeys(
                [
                    *aliases,
                    *(
                        s.name
                        for s in selected
                        if normalize_skill(s.name) != normalize_skill(name)
                    ),
                ]
            )
        )
        for skill in selected[:1]:
            ledger.entries.append(
                ManualEditEntry(
                    target_token=normalize_skill(skill.name),
                    name=name,
                    aliases=names,
                    category=category,
                    added_at=_utcnow(),
                )
            )
        updated, _ = apply_manual_skills(facts, ledger)
        _publish(profile_dir, updated, ledger, group=group, skill_key=name)


def merge_skills(profile_dir: str | Path, keys: list[str], into: str) -> None:
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        target = _resolve_skills(profile_dir, facts, into)[0]
        selected = {
            s.id: s
            for key in [into, *keys]
            for s in _resolve_skills(profile_dir, facts, key)
        }
        if len(selected) < 2:
            raise ValueError("Choose at least two different skills to merge")
        ledger = load_manual_skills(_ledger_path(profile_dir))
        ledger.entries.append(
            ManualMergeEntry(
                tokens=[normalize_skill(s.name) for s in selected.values()],
                target_token=normalize_skill(target.name),
                added_at=_utcnow(),
            )
        )
        updated, _ = apply_manual_skills(facts, ledger)
        _publish(profile_dir, updated, ledger)


def cleanup_skills(profile_dir: str | Path, *, apply: bool = False):
    from resume_tailor_harness.profile.effective import build_effective_taxonomy
    from resume_tailor_harness.profile.skill_cleanup import clean_skills

    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        ledger = load_manual_skills(_ledger_path(profile_dir))
        taxonomy = build_effective_taxonomy(profile_dir)
        updated, report = clean_skills(
            facts,
            ledger,
            aliases=taxonomy.cluster_map.aliases,
            added_at=_utcnow(),
            forbid_alias=load_overrides(
                Path(profile_dir) / "overrides.yaml"
            ).forbid_alias,
        )
        if apply:
            _publish(profile_dir, updated, ledger)
        return report


def set_cleanup_policy(profile_dir: str | Path, enabled: bool) -> None:
    with manual_skills_lock(profile_dir):
        ledger = load_manual_skills(_ledger_path(profile_dir))
        ledger.auto_cleanup = enabled
        save_manual_skills(ledger, _ledger_path(profile_dir))


def list_skills(profile_dir: str | Path) -> list[dict[str, str | None]]:
    facts = _load_facts_or_raise(profile_dir)
    return [
        {"id": skill.id, "name": skill.name, "category": skill.category}
        for skills in facts.skills.values()
        for skill in skills
    ]


def add_skill(
    profile_dir: str | Path,
    name: str,
    category: Literal["hard", "soft", "domain"] | None,
    *,
    aliases: list[str] | None = None,
    group: str | None = None,
) -> ManualSkillEntry:
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        token = normalize_skill(name)
        if not token:
            raise ValueError("skill name is required")

        ledger = load_manual_skills(_ledger_path(profile_dir))
        # Re-adding a currently-suppressed skill restores it rather than erroring:
        # dropping the suppress entry lets the name reappear on the next rebuild.
        was_suppressed = any(
            e.kind == "suppress" and normalize_skill(e.token) == token
            for e in ledger.entries
        )
        if token in _known_tokens(facts) and not was_suppressed:
            raise SkillAlreadyExistsError(f"'{name}' is already in your profile")
        ledger.entries = [
            e
            for e in ledger.entries
            if not (e.kind == "suppress" and normalize_skill(e.token) == token)
        ]
        known = _known_tokens(facts)
        if any(normalize_skill(alias) in known for alias in aliases or []):
            raise SkillAlreadyExistsError("An alias already belongs to another skill")
        entry = ManualSkillEntry(
            name=name.strip(),
            category=category,
            aliases=aliases or [],
            added_at=_utcnow(),
        )
        ledger.entries.append(entry)
        updated_facts, _warnings = apply_manual_skills(facts, ledger)
        _publish(profile_dir, updated_facts, ledger, group=group, skill_key=name)
        return entry


def add_alias(profile_dir: str | Path, skill_id: str, alias: str) -> ManualAliasEntry:
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        target = next(
            (
                skill
                for skills in facts.skills.values()
                for skill in skills
                if skill.id == skill_id
            ),
            None,
        )
        if target is None:
            raise SkillNotFoundError(f"No skill '{skill_id}'")
        alias = alias.strip()
        if not alias:
            raise ValueError("alias text is required")
        if normalize_skill(alias) in _known_tokens(facts):
            raise SkillAlreadyExistsError(f"'{alias}' is already in your profile")

        entry = ManualAliasEntry(
            target_skill_token=normalize_skill(target.name),
            target_skill_display=target.name,
            alias_text=alias,
            added_at=_utcnow(),
        )
        ledger = load_manual_skills(_ledger_path(profile_dir))
        ledger.entries.append(entry)
        updated_facts, _warnings = apply_manual_skills(facts, ledger)
        _publish(profile_dir, updated_facts, ledger)
        return entry


def list_suppressed(profile_dir: str | Path) -> list[ManualSuppressEntry]:
    """Return the durable suppress entries (deleted skills awaiting restore)."""
    ledger = load_manual_skills(_ledger_path(profile_dir))
    return [e for e in ledger.entries if isinstance(e, ManualSuppressEntry)]


def delete_skill(profile_dir: str | Path, key: str) -> None:
    """Durably delete any live skill by matrix key / normalized token or alias.

    Appends a suppress entry keyed on the matched skill's canonical name token
    (so it can be listed and restored), removes the skill from live facts, and
    rebuilds the saved matrix. Any additive ``new_skill`` entry for the same
    token is intentionally left in place: ``apply_manual_skills`` always replays
    suppressions last, so the pair yields the deleted state now while keeping the
    add entry so ``restore_skill`` can bring a manually-added skill back.
    """
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        matches = _resolve_skills(profile_dir, facts, key)
        match = matches[0]
        # Key the suppression on the skill's own name, not the (possibly alias)
        # lookup token — replay matches skills by name, and restore uses this token.
        token = normalize_skill(match.name)
        ledger = load_manual_skills(_ledger_path(profile_dir))
        if not any(
            e.kind == "suppress" and normalize_skill(e.token) == token
            for e in ledger.entries
        ):
            ledger.entries.append(
                ManualSuppressEntry(
                    token=token, display=match.name, skills=matches, added_at=_utcnow()
                )
            )
        updated_facts, _warnings = apply_manual_skills(facts, ledger)
        _publish(profile_dir, updated_facts, ledger)


def restore_skill(profile_dir: str | Path, token: str) -> None:
    """Lift a suppression so the skill reappears on the next profile build."""
    with manual_skills_lock(profile_dir):
        facts = _load_facts_or_raise(profile_dir)
        norm = normalize_skill(token)
        ledger = load_manual_skills(_ledger_path(profile_dir))
        if not any(
            e.kind == "suppress" and normalize_skill(e.token) == norm
            for e in ledger.entries
        ):
            raise SuppressedSkillNotFoundError(f"'{token}' is not suppressed")
        removed = [
            e
            for e in ledger.entries
            if isinstance(e, ManualSuppressEntry) and normalize_skill(e.token) == norm
        ]
        for entry in removed:
            for saved in entry.skills:
                if normalize_skill(saved.name) not in _known_tokens(facts):
                    facts.skills.setdefault(saved.category or "hard", []).append(
                        saved.model_copy(deep=True)
                    )
        ledger.cleanup_exempt = list(dict.fromkeys([*ledger.cleanup_exempt, norm]))
        ledger.entries = [e for e in ledger.entries if e not in removed]
        updated_facts, _warnings = apply_manual_skills(facts, ledger)
        _publish(
            profile_dir, updated_facts, ledger, restoring_token=token
        )
