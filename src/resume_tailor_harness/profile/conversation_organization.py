"""Pure catalog edits shared by conversation previews and approved changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from resume_tailor_harness.models.profile import ProfileFacts, Skill
from resume_tailor_harness.profile.group_corrections import (
    GroupCorrection,
    GroupCorrections,
    edit_catalog,
)
from resume_tailor_harness.tracking.match_gap import normalize_skill

if TYPE_CHECKING:
    from resume_tailor_harness.profile.conversation import AppliedChange, ChangePreview


def _category_key(organization: GroupCorrections, value: str) -> str | None:
    catalog = organization.category_catalog()
    if value in catalog:
        return value
    return next(
        (
            key
            for key, item in catalog.items()
            if item.label.casefold() == value.casefold()
        ),
        None,
    )


def place_skill(
    organization: GroupCorrections,
    record: AppliedChange,
    skill: Skill,
    before: dict | None = None,
) -> None:
    """An explicit category move must be visible in the library's grouping layer."""
    category = record.change.category
    previous = normalize_skill(before.get("name", "")) if before else ""
    correction = organization.corrections.get(previous)
    if not category:
        if correction is not None:
            organization.corrections[normalize_skill(skill.name)] = (
                correction.model_copy()
            )
        return
    key = record.organization_key or _category_key(organization, category)
    if key not in organization.category_catalog():
        key = edit_catalog(organization, "category", label=category, new_key=key)
    record.organization_key = key
    groups = organization.group_catalog()
    candidates = {
        slug: group for slug, group in groups.items() if group.category == key
    }
    group = record.organization_group
    if group not in groups:
        if correction and correction.group in candidates:
            group = correction.group
        elif len(candidates) == 1:
            group = next(iter(candidates))
        else:
            label = organization.category_catalog()[key].label
            group = next(
                (slug for slug, item in candidates.items() if item.label == label), ""
            )
            if not group:
                existing = {item.label.casefold() for item in groups.values()}
                suffix = 1
                base = label
                while label.casefold() in existing:
                    suffix += 1
                    label = f"{base[:70]} ({suffix})"
                group = edit_catalog(
                    organization,
                    "group",
                    label=label,
                    category=key,
                    new_key=record.organization_group or None,
                )
    record.organization_group = group
    organization.corrections[normalize_skill(skill.name)] = GroupCorrection(group=group)


def apply_category_change(
    facts: ProfileFacts, record: AppliedChange, organization: GroupCorrections
) -> tuple[ProfileFacts, ChangePreview]:
    from resume_tailor_harness.profile.conversation import ChangePreview, _check_values

    change = record.change
    _check_values(change.values, {"name"})
    name = change.values.get("name", "")
    if change.operation != "delete" and (
        not isinstance(name, str) or not name.strip() or len(name.strip()) > 80
    ):
        raise ValueError("A category name of 1 to 80 characters is required")
    name = name.strip()
    old = change.target_id
    if change.operation == "create":
        if old:
            raise ValueError("Create category uses values.name, without target_id")
        record.organization_key = edit_catalog(
            organization, "category", label=name, new_key=f"custom-{record.record_id}"
        )
        facts.skills.setdefault(name, [])
        return facts, ChangePreview(label="Create skill category", after={"name": name})
    key = record.organization_key or _category_key(organization, old)
    if key not in organization.category_catalog():
        # Older conversation drafts addressed display buckets by their visible name.
        if old not in facts.skills:
            raise ValueError("Unknown skill category; inspect the profile again")
        key = edit_catalog(organization, "category", label=old, new_key=key)
        placement = record.model_copy(
            deep=True,
            update={
                "organization_key": key,
                "change": change.model_copy(update={"category": key}),
            },
        )
        for skill in facts.skills[old]:
            place_skill(organization, placement, skill)
        record.organization_group = placement.organization_group
    record.organization_key = key
    label = organization.category_catalog()[key].label
    groups = organization.group_catalog()
    member_tokens = {
        token
        for token, correction in organization.corrections.items()
        if correction.group in groups and groups[correction.group].category == key
    }
    record.category_members = sorted(
        member_tokens
        | {
            normalize_skill(skill.name)
            for bucket in (old, label, key)
            for skill in facts.skills.get(bucket, [])
        }
    )
    edit_catalog(
        organization,
        "category",
        key=key,
        label=name,
        delete=change.operation == "delete",
    )
    destination = "Other" if change.operation == "delete" else name
    for bucket in dict.fromkeys((old, label, key)):
        if bucket != destination and bucket in facts.skills:
            facts.skills.setdefault(destination, []).extend(facts.skills.pop(bucket))
    return facts, ChangePreview(
        label=f"{change.operation.title()} skill category",
        before={"name": label},
        after={"name": destination},
    )
