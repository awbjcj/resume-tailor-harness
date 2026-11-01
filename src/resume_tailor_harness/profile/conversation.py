"""Typed, side-effect-free profile edits and their durable rebuild overlay.

The agent can inspect or preview these operations. Only the approval service
may persist the resulting ledger, facts and matrix.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor_harness.models.base import FactItem, Source, new_id
from resume_tailor_harness.models.profile import (
    Award,
    Bullet,
    Certification,
    Contact,
    Education,
    Experience,
    Language,
    Link,
    ProfileFacts,
    Project,
    Publication,
    Skill,
    Volunteer,
)
from resume_tailor_harness.profile.store import load_facts
from resume_tailor_harness.profile.group_corrections import (
    GroupCorrections,
    corrections_path,
    load_group_corrections,
)
from resume_tailor_harness.rollback import restore_file
from resume_tailor_harness.tracking.match_gap import normalize_skill

Section = Literal[
    "experience",
    "education",
    "projects",
    "certifications",
    "publications",
    "awards",
    "languages",
    "volunteer",
    "bullets",
    "highlights",
]
FACT_MODELS: dict[str, type[FactItem]] = {
    "experience": Experience,
    "education": Education,
    "projects": Project,
    "certifications": Certification,
    "publications": Publication,
    "awards": Award,
    "languages": Language,
    "volunteer": Volunteer,
    "bullets": Bullet,
    "highlights": Bullet,
}
_HOST_FIELDS = {
    "id",
    "source",
    "source_ref",
    "source_refs",
    "synthesized",
    "schema_version",
}
_NESTED_FACTS = {"bullets", "highlights"}
_FILES = (
    "facts.json",
    "conversation_edits.json",
    "manual_skills.json",
    "overrides.yaml",
    "group_corrections.json",
)


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileChange(ClosedModel):
    entity: Literal["profile", "fact", "skill", "skill_category"]
    operation: Literal["create", "update", "delete"]
    section: Section | None = None
    target_id: str = Field(default="", max_length=200)
    parent_id: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=100)
    values: dict[str, Any] = Field(default_factory=dict)
    quotes: list[str] = Field(min_length=1, max_length=20)


class ProfileChangeSet(ClosedModel):
    title: str = Field(min_length=1, max_length=200)
    changes: list[ProfileChange] = Field(min_length=1, max_length=20)


class AppliedChange(ClosedModel):
    change: ProfileChange
    record_id: str = ""
    source_ref: str = ""
    category_members: list[str] = Field(default_factory=list)
    organization_key: str = ""
    organization_group: str = ""


class SavedSkill(ClosedModel):
    bucket: str
    skill: Skill


class ProfileEdits(ClosedModel):
    # A full removal fences old corpus evidence. Explicit recreation starts
    # from a blank base, so a later build cannot resurrect the removed profile.
    reset_sources: bool = False
    deleted: bool = False
    excluded_source_refs: list[str] = Field(default_factory=list)
    excluded_fact_ids: list[str] = Field(default_factory=list)
    changes: list[AppliedChange] = Field(default_factory=list)
    skill_overrides: dict[str, SavedSkill | None] = Field(default_factory=dict)


class ChangePreview(ClosedModel):
    label: str
    entity: str = ""
    operation: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class CoachChangeDraft(ClosedModel):
    id: str = Field(default_factory=new_id)
    title: str
    revision: str
    source_text_hash: str
    changes: list[AppliedChange]
    previews: list[ChangePreview]
    status: Literal["pending", "applied", "discarded"] = "pending"


def edits_path(root: Path) -> Path:
    return root / "conversation_edits.json"


def load_edits(root: Path) -> ProfileEdits:
    path = edits_path(root)
    if not path.exists():
        return ProfileEdits()
    # Corruption must never silently erase the user's corrections.
    return ProfileEdits.model_validate_json(path.read_text(encoding="utf-8"))


def save_edits(root: Path, ledger: ProfileEdits) -> None:
    restore_file(edits_path(root), (ledger.model_dump_json(indent=2) + "\n").encode())


def profile_revision(root: Path) -> str:
    digest = hashlib.sha256()
    for name in _FILES:
        path = root / name
        digest.update(name.encode())
        digest.update(
            b"present\0" + path.read_bytes() if path.exists() else b"absent\0"
        )
    return digest.hexdigest()


def current_facts(root: Path) -> ProfileFacts | None:
    path = root / "facts.json"
    return load_facts(path) if path.exists() else None


def can_rebuild_without_resume(root: Path) -> bool:
    ledger = load_edits(root)
    return (
        not ledger.deleted and bool(ledger.changes) and (root / "facts.json").is_file()
    )


def _fields(model: type[BaseModel]) -> set[str]:
    fields = set(model.model_fields) - _HOST_FIELDS - _NESTED_FACTS
    if model is Skill:
        fields -= {"inferred", "evidence_fact_ids"}
    return fields


def _check_values(values: dict, allowed: set[str]) -> None:
    unknown = values.keys() - allowed
    if unknown:
        raise ValueError(f"Unsupported fields: {', '.join(sorted(unknown))}")
    if len(json.dumps(values, ensure_ascii=False)) > 20_000:
        raise ValueError("Change values are too large")


def change_schema(entity: str, section: str = "") -> dict:
    """Expose only editable fields, without granting arbitrary JSON writes."""
    if entity == "profile":
        return {
            "fields": ["contact", "summary", "interests"],
            "contactFields": sorted(_fields(Contact)),
            "note": "Create requires contact.name; delete removes the whole profile. "
            "Sources and conversation history are retained. Recreation uses a blank base.",
        }
    if entity == "skill_category":
        return {
            "fields": ["name"],
            "note": "Categories use the same display catalog as the skill library, separate "
            "from hard/soft/domain. Inspect skill_categories for exact ids. Names are limited "
            "to 80 characters. Deleting a category moves its groups and skills to Other.",
        }
    model = Skill if entity == "skill" else FACT_MODELS.get(section)
    if model is None:
        raise ValueError("Unknown entity or fact section")
    schema = model.model_json_schema()
    return {
        "fields": {name: schema["properties"][name] for name in sorted(_fields(model))},
        "definitions": schema.get("$defs", {}),
        "note": "Update/delete require an exact saved id. Add bullets separately "
        "with their parent_id. Skill category values are hard, soft, domain or null; "
        "the outer category selects a skill-library category id or its exact label.",
    }


def _fact_list(facts: ProfileFacts, change: ProfileChange) -> list:
    if change.section in _NESTED_FACTS:
        owners = facts.experience if change.section == "bullets" else facts.projects
        owner = next((item for item in owners if item.id == change.parent_id), None)
        if owner is None:
            raise ValueError("Unknown parent fact; inspect the profile again")
        return getattr(owner, change.section)
    if change.section not in FACT_MODELS or change.parent_id:
        raise ValueError(
            "A valid fact section is required; parent_id is only for bullets/highlights"
        )
    return getattr(facts, change.section)


def _manual(item: FactItem, record: AppliedChange) -> None:
    item.id = record.record_id or item.id
    item.source = Source.manual
    item.source_ref = record.source_ref
    item.synthesized = False


def _clean_evidence(
    facts: ProfileFacts, invalidated_ids: set[str] | None = None
) -> None:
    from resume_tailor_harness.tailor.provenance import index_facts

    known = set(index_facts(facts)) - (invalidated_ids or set())
    for bucket in facts.skills.values():
        for skill in bucket[:]:
            if skill.inferred:
                skill.evidence_fact_ids = [
                    key for key in skill.evidence_fact_ids if key in known
                ]
                if not skill.evidence_fact_ids:
                    bucket.remove(skill)


def apply_change(
    facts: ProfileFacts | None,
    record: AppliedChange,
    *,
    replay: bool = False,
    organization: GroupCorrections | None = None,
) -> tuple[ProfileFacts | None, ChangePreview]:
    """Apply one validated operation to an owned in-memory copy only."""
    change = record.change
    if change.entity != "fact" and (change.section is not None or change.parent_id):
        raise ValueError("Only fact changes may specify section or parent_id")
    if change.entity != "skill" and change.category:
        raise ValueError("Only skill changes may select an outer category")
    if change.operation == "delete" and change.values:
        raise ValueError("Delete changes cannot contain replacement values")
    if change.entity == "profile":
        if change.target_id:
            raise ValueError(
                "The profile is scoped to the active workspace, with no target id"
            )
        _check_values(change.values, {"contact", "summary", "interests"})
        if change.operation != "delete" and not change.values:
            raise ValueError("Create/update requires changed fields")
        if "contact" in change.values:
            contact = change.values["contact"]
            if not isinstance(contact, dict):
                raise ValueError("contact must be an object")
            _check_values(contact, _fields(Contact))
            if contact.get("links") is not None and not isinstance(
                contact["links"], list
            ):
                raise ValueError("links must be a list")
            for link in contact.get("links") or []:
                if not isinstance(link, dict):
                    raise ValueError("links must contain label/url objects")
                _check_values(link, _fields(Link))
        before = facts.model_dump(mode="json") if facts else None
        if change.operation == "delete":
            if facts is None and not replay:
                raise ValueError("No profile exists")
            return None, ChangePreview(
                label="Remove profile (sources and chats are retained)", before=before
            )
        if change.operation == "create" and facts is not None and not replay:
            raise ValueError("A profile already exists; use update")
        if facts is None and change.operation != "create":
            raise ValueError("Create a profile first")
        data = facts.model_dump() if facts is not None else {}
        values = dict(change.values)
        if "contact" in values and facts is not None:
            values["contact"] = {**facts.contact.model_dump(), **values["contact"]}
        facts = ProfileFacts.model_validate({**data, **values})
        if change.operation == "create" and not facts.contact.name.strip():
            raise ValueError("A name is required to create a profile")
        after = facts.model_dump(mode="json")
        # Present only changed fields, so an approval card is a readable diff.
        if change.operation == "update":
            before = {key: before[key] for key in change.values} if before else None
            after = {key: after[key] for key in change.values}
            if "contact" in change.values:
                if before:
                    before["contact"] = {
                        key: before["contact"][key] for key in change.values["contact"]
                    }
                after["contact"] = {
                    key: after["contact"][key] for key in change.values["contact"]
                }
        return facts, ChangePreview(
            label=f"{change.operation.title()} profile", before=before, after=after
        )
    if facts is None:
        raise ValueError("Create a profile first")
    if change.entity == "skill_category":
        if organization is not None:
            from resume_tailor_harness.profile.conversation_organization import (
                apply_category_change,
            )

            return apply_category_change(facts, record, organization)
        _check_values(change.values, {"name"})
        name = change.values.get("name", "")
        if change.operation != "delete" and (
            not isinstance(name, str) or not name.strip() or len(name) > 100
        ):
            raise ValueError("A category name of 1 to 100 characters is required")
        name = name.strip()
        old = change.target_id
        if change.operation == "create":
            if old:
                raise ValueError("Create category uses values.name, without target_id")
            if name in facts.skills and not replay:
                raise ValueError("Category already exists")
            facts.skills.setdefault(name, [])
            return facts, ChangePreview(
                label="Create skill category", after={"name": name}
            )
        if old not in facts.skills:
            if replay:
                if change.operation == "update":
                    facts.skills.setdefault(name, [])
                return facts, ChangePreview(
                    label="Category already replaced or removed"
                )
            raise ValueError("Unknown skill category; inspect the profile again")
        if not replay:
            record.category_members = [
                normalize_skill(skill.name) for skill in facts.skills[old]
            ]
        if change.operation == "delete":
            name = "Other"
            if old == name and facts.skills[old]:
                raise ValueError(
                    "Move or remove the skills in Other before removing it"
                )
        elif name in facts.skills and name != old:
            raise ValueError("Destination category already exists")
        members = facts.skills.pop(old)
        if change.operation != "delete" or members:
            facts.skills.setdefault(name, []).extend(members)
        return facts, ChangePreview(
            label=f"{change.operation.title()} skill category",
            before={"name": old},
            after={"name": name} if members or change.operation != "delete" else None,
        )
    model: type[FactItem]
    items: list[Any]
    if change.entity == "fact":
        model = FACT_MODELS.get(change.section or "", FactItem)
        items = _fact_list(facts, change)
    else:
        model = Skill
        items = [skill for bucket in facts.skills.values() for skill in bucket]
    _check_values(change.values, _fields(model))
    if (
        not change.values
        and change.operation != "delete"
        and not (
            change.entity == "skill"
            and change.operation == "update"
            and change.category
        )
    ):
        raise ValueError("Create/update requires changed fields")
    if change.operation == "create":
        if change.target_id:
            raise ValueError(
                "Create cannot choose a target id; ids are assigned by the host"
            )
        if replay and any(item.id == record.record_id for item in items):
            return facts, ChangePreview(label="Already present")
        item = model.model_validate(change.values)
        before = None
        if isinstance(item, Skill):
            if any(
                normalize_skill(item.name) == normalize_skill(s.name) for s in items
            ):
                if replay:
                    return facts, ChangePreview(label="Already present")
                raise ValueError("Skill already exists")
            facts.skills.setdefault(
                change.category or item.category or "hard", []
            ).append(item)
        else:
            items.append(item)
    else:
        if not change.target_id:
            raise ValueError("Update/delete requires an exact saved target id")
        item = next((item for item in items if item.id == change.target_id), None)
        # Skills are rebuilt with fresh ids; the host records their normalized
        # name as an additional stable selector, never an alias guess.
        if item is None and change.entity == "skill" and record.record_id:
            item = next(
                (s for s in items if normalize_skill(s.name) == record.record_id), None
            )
        if item is None:
            if replay and change.operation == "delete":
                return facts, ChangePreview(label="Already removed")
            raise ValueError("Unknown target fact; inspect the profile again")
        before = item.model_dump(mode="json")
        if change.entity == "skill":
            if not replay:
                record.record_id = normalize_skill(item.name)
            original_bucket = next(
                name for name, bucket in facts.skills.items() if item in bucket
            )
            before["display_bucket"] = original_bucket
            for bucket in facts.skills.values():
                if item in bucket:
                    bucket.remove(item)
            if change.operation != "delete":
                updated = {
                    **item.model_dump(),
                    **change.values,
                }
                replacement = Skill.model_validate(updated)
                if any(
                    normalize_skill(s.name) == normalize_skill(replacement.name)
                    and s.id != item.id
                    for s in items
                ):
                    raise ValueError("Skill name already exists")
                bucket_name = change.category or original_bucket
                facts.skills.setdefault(
                    bucket_name or replacement.category or "hard", []
                ).append(replacement)
                item = replacement
        else:
            index = items.index(item)
            if change.operation == "delete":
                items.pop(index)
            else:
                item = model.model_validate({**item.model_dump(), **change.values})
                items[index] = item
        if change.operation == "delete":
            _clean_evidence(facts)
            return facts, ChangePreview(
                label=f"Remove {change.section or 'skill'}", before=before
            )
    # Updated records keep their addressable id; only creates mint a new id.
    original_id = item.id
    _manual(item, record)
    if change.operation != "create":
        item.id = original_id
    if change.operation == "update" and (
        (change.entity == "fact" and change.values.keys() - {"aspect"})
        or (change.entity == "skill" and change.values.keys() & {"name", "context"})
    ):
        # Existing pointers were inferred from the old content, even though its
        # addressable id remains stable. They cannot certify the corrected claim.
        _clean_evidence(facts, {item.id})
    after = item.model_dump(mode="json")
    if isinstance(item, Skill):
        if organization is not None:
            from resume_tailor_harness.profile.conversation_organization import (
                place_skill,
            )

            place_skill(organization, record, item, before)
        after["display_bucket"] = next(
            name for name, bucket in facts.skills.items() if item in bucket
        )
    return facts, ChangePreview(
        label=f"{change.operation.title()} {change.section or 'skill'}",
        before=before,
        after=after,
    )


def prepare_changes(
    root: Path, proposal: ProfileChangeSet, user_text: str, *, source_ref: str
) -> CoachChangeDraft:
    normalized = " ".join(user_text.split()).casefold()
    revision = profile_revision(root)
    facts = current_facts(root)
    facts = facts.model_copy(deep=True) if facts else None
    organization = load_group_corrections(corrections_path(root), strict=True)
    records: list[AppliedChange] = []
    previews: list[ChangePreview] = []
    if (
        any(c.entity == "profile" and c.operation == "delete" for c in proposal.changes)
        and len(proposal.changes) != 1
    ):
        raise ValueError("Profile removal must be reviewed by itself")
    for change in proposal.changes:
        if not change.quotes or any(
            not q.strip() or " ".join(q.split()).casefold() not in normalized
            for q in change.quotes
        ):
            raise ValueError(
                "Every change needs an exact quote from the current user message"
            )
        record = AppliedChange(
            change=change.model_copy(deep=True),
            record_id=new_id() if change.operation == "create" else "",
            source_ref=source_ref,
        )
        facts, preview = apply_change(facts, record, organization=organization)
        records.append(record)
        previews.append(
            preview.model_copy(
                update={
                    "entity": change.section or change.entity,
                    "operation": change.operation,
                }
            )
        )
    if profile_revision(root) != revision:
        raise ValueError("Profile changed while preparing the draft; inspect it again")
    return CoachChangeDraft(
        title=proposal.title,
        revision=revision,
        source_text_hash=hashlib.sha256(user_text.encode()).hexdigest(),
        changes=records,
        previews=previews,
    )


def replay_edits(
    facts: ProfileFacts, ledger: ProfileEdits
) -> tuple[ProfileFacts, list[str]]:
    if ledger.deleted:
        raise ValueError(
            "The profile was removed. Create a profile in conversation before rebuilding."
        )
    result: ProfileFacts | None = facts.model_copy(deep=True)
    if ledger.reset_sources:
        result.contact = Contact(name="")
        result.summary = None
        result.interests = []
        excluded_refs = set(ledger.excluded_source_refs)
        excluded_ids = set(ledger.excluded_fact_ids)

        def retained(item: FactItem) -> bool:
            return item.id not in excluded_ids and item.source_ref not in excluded_refs

        for section in FACT_MODELS.keys() - _NESTED_FACTS:
            setattr(
                result,
                section,
                [item for item in getattr(result, section) if retained(item)],
            )
        for owner in result.experience:
            owner.bullets = [item for item in owner.bullets if retained(item)]
        for owner in result.projects:
            owner.highlights = [item for item in owner.highlights if retained(item)]
        for bucket in result.skills.values():
            bucket[:] = [item for item in bucket if retained(item)]
        for section in result.additional_sections:
            section.entries = [item for item in section.entries if retained(item)]
        if result.github_profile is not None and not retained(result.github_profile):
            result.github_profile = None
    warnings: list[str] = []
    for record in ledger.changes:
        if record.change.entity == "skill_category" and record.organization_key:
            # The reviewed catalog mutation is already durable; member snapshots
            # below retain legacy display buckets when source ids change.
            continue
        try:
            candidate = result.model_copy(deep=True) if result else None
            result, _ = apply_change(candidate, record, replay=True)
        except ValueError as exc:
            warnings.append(f"Conversation edit needs review: {exc}")
    if result is None:
        raise ValueError("Conversation edits did not produce a profile")
    apply_skill_overrides(result, ledger)
    return result, warnings


def apply_skill_overrides(facts: ProfileFacts, ledger: ProfileEdits) -> None:
    """Keep the latest explicit skill edits when rebuilding only derived skills."""
    for token, saved in ledger.skill_overrides.items():
        for bucket in facts.skills.values():
            bucket[:] = [
                skill for skill in bucket if normalize_skill(skill.name) != token
            ]
        if saved is not None:
            facts.skills.setdefault(saved.bucket, []).append(
                saved.skill.model_copy(deep=True)
            )
    _clean_evidence(facts)


def capture_skill_overrides(
    facts: ProfileFacts,
    ledger: ProfileEdits,
    *,
    records: Sequence[AppliedChange] = (),
) -> None:
    """Let later explicit skill edits on either surface supersede earlier ones.

    Only skills touched by conversation are captured; newly extracted skills
    remain free to appear. Renames and restores keep their latest saved snapshot.
    """
    tokens = set(ledger.skill_overrides)
    if ledger.reset_sources:
        tokens.update(
            normalize_skill(skill.name)
            for bucket in facts.skills.values()
            for skill in bucket
        )
    for record in records:
        tokens.update(record.category_members)
        if record.change.entity != "skill":
            continue
        if record.change.operation != "create":
            tokens.add(record.record_id)
        name = record.change.values.get("name")
        if isinstance(name, str):
            tokens.add(normalize_skill(name))
    # The library keeps a previous name as an alias after renaming or merging.
    # Follow it so a conversation-created skill survives a later source rebuild.
    for bucket in facts.skills.values():
        for skill in bucket:
            if tokens.intersection(map(normalize_skill, skill.aliases)):
                tokens.add(normalize_skill(skill.name))
    for token in tokens - {""}:
        found = next(
            (
                (name, skill)
                for name, bucket in facts.skills.items()
                for skill in bucket
                if normalize_skill(skill.name) == token
            ),
            None,
        )
        ledger.skill_overrides[token] = (
            SavedSkill(bucket=found[0], skill=found[1].model_copy(deep=True))
            if found
            else None
        )


def make_profile_tools(root: Path, *, user_text: str = "") -> list:
    """Bounded read/compute tools; none can persist state or approve a draft."""

    def inspect_profile(
        section: str = "profile",
        offset: int = 0,
        limit: int = 20,
        parent_id: str = "",
        query: str = "",
    ) -> dict:
        """Read saved profile fields or search facts/skills by query. Page exact ids before editing."""
        facts = current_facts(root)
        if facts is None:
            return {"exists": False, "revision": profile_revision(root)}
        if section == "profile":
            organization = load_group_corrections(corrections_path(root), strict=True)
            return {
                "exists": True,
                "revision": profile_revision(root),
                "contact": facts.contact.model_dump(mode="json"),
                "summary": facts.summary,
                "interests": facts.interests,
                "sections": {
                    key: len(getattr(facts, key))
                    for key in FACT_MODELS
                    if key not in _NESTED_FACTS
                },
                "skillCategories": [
                    {"id": key, "name": item.label}
                    for key, item in list(organization.category_catalog().items())[:30]
                ],
                "organizationNote": "Page skill_categories or skill_groups for the full display catalog.",
            }
        if section == "skills":
            from resume_tailor_harness.profile.matrix import build_decorated_matrix

            organization = load_group_corrections(corrections_path(root), strict=True)
            catalog = organization.group_catalog()
            matrix = build_decorated_matrix(root, facts)
            groups_by_id = {
                fid: row.group or "other"
                for row in matrix.rows
                for fid in row.evidence_fact_ids
            }
            rows = [
                {
                    **s.model_dump(mode="json"),
                    "bucket": key,
                    "group": groups_by_id.get(s.id, "other"),
                    "display_category": catalog[
                        groups_by_id.get(s.id, "other")
                    ].category,
                }
                for key, values in facts.skills.items()
                for s in values
            ]
        elif section in {"skill_categories", "skill_groups"}:
            organization = load_group_corrections(corrections_path(root), strict=True)
            definitions = (
                organization.category_catalog()
                if section == "skill_categories"
                else organization.group_catalog()
            )
            rows = [
                {"id": key, **item.model_dump()} for key, item in definitions.items()
            ]
        elif section in _NESTED_FACTS:
            owners = facts.experience if section == "bullets" else facts.projects
            owner = next((owner for owner in owners if owner.id == parent_id), None)
            if owner is None:
                raise ValueError("Unknown parent fact")
            rows = [value.model_dump(mode="json") for value in getattr(owner, section)]
        elif section in FACT_MODELS:
            rows = [value.model_dump(mode="json") for value in getattr(facts, section)]
        else:
            raise ValueError("Unknown profile section")
        if len(query) > 200:
            raise ValueError("Search query is too long")
        if query.strip():
            needle = query.strip().casefold()
            rows = [
                row
                for row in rows
                if needle in json.dumps(row, ensure_ascii=False).casefold()
            ]
        start = max(0, offset)
        page = rows[start : start + max(1, min(limit, 30))]
        # Bound each response even for unusually large imported records.
        for index, row in enumerate(page):
            if len(json.dumps(row, ensure_ascii=False)) > 20_000:
                page[index] = {
                    "id": row["id"],
                    "truncated": True,
                    "name": str(row.get("name", row.get("title", "")))[:200],
                    "note": "Read bullets/highlights separately using this parent_id.",
                }
        while len(page) > 1 and len(json.dumps(page, ensure_ascii=False)) > 30_000:
            page.pop()
        return {
            "total": len(rows),
            "offset": start,
            "records": page,
            "nextOffset": start + len(page)
            if page and start + len(page) < len(rows)
            else None,
        }

    def get_profile_change_schema(
        entity: Literal["profile", "fact", "skill", "skill_category"], section: str = ""
    ) -> dict:
        """Get editable fields for an entity/section; source, evidence ids and record ids are host-owned."""
        return change_schema(entity, section)

    def preview_profile_changes(proposal: ProfileChangeSet) -> dict:
        """Validate and preview quoted profile changes without saving. Approval happens outside this tool loop."""
        try:
            draft = prepare_changes(root, proposal, user_text, source_ref="preview")
            return {
                "valid": True,
                "saved": False,
                "previews": [p.model_dump(mode="json") for p in draft.previews],
            }
        except ValueError as exc:
            return {"valid": False, "saved": False, "error": str(exc)}

    return [inspect_profile, get_profile_change_schema, preview_profile_changes]
