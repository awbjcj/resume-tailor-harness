"""Apply only the exact reviewed conversation draft, outside the agent loop."""

from __future__ import annotations

import hashlib
from pathlib import Path

from resume_tailor_harness.profile.coach_store import (
    coach_dir,
    coach_lock,
    load_session,
    mutate_session,
)
from resume_tailor_harness.profile.conversation import (
    CoachChangeDraft,
    ProfileEdits,
    apply_change,
    current_facts,
    edits_path,
    load_edits,
    profile_revision,
    save_edits,
    capture_skill_overrides,
)
from resume_tailor_harness.profile.manual_skills import manual_skills_lock
from resume_tailor_harness.profile.group_corrections import (
    corrections_path,
    load_group_corrections,
    save_group_corrections,
)
from resume_tailor_harness.profile.matrix import rebuild_saved_matrix
from resume_tailor_harness.profile.store import save_facts
from resume_tailor_harness.rollback import rollback_scope


class StaleProfileDraft(ValueError):
    """The reviewed draft is no longer based on the saved profile revision."""


def resolve_changes(
    profile_dir: Path | str,
    session_id: str,
    draft_id: str,
    *,
    decision: str,
    revision: str,
) -> None:
    root = Path(profile_dir)
    if decision not in {"apply", "discard"}:
        raise ValueError("Unknown draft decision")
    with coach_lock(), manual_skills_lock(root):
        session = load_session(root, session_id)
        stored = next(
            (d for d in session.get("change_drafts", []) if d["id"] == draft_id), None
        )
        if stored is None:
            raise ValueError("Unknown profile change draft")
        draft = CoachChangeDraft.model_validate(stored)
        if revision != draft.revision:
            raise StaleProfileDraft(
                "The draft revision does not match the reviewed changes"
            )
        status = "applied" if decision == "apply" else "discarded"
        if draft.status == status:
            return  # Retry after an uncertain response never applies twice.
        if draft.status != "pending":
            raise ValueError("Draft already resolved")

        def mark_resolved(current: dict) -> None:
            item = next(d for d in current["change_drafts"] if d["id"] == draft_id)
            if item["status"] != "pending":
                raise ValueError("Draft already resolved")
            item["status"] = status

        if decision == "discard":
            mutate_session(root, session_id, mark_resolved)
            return
        if session.get("archived_at"):
            raise ValueError("Cannot apply changes from an archived session")
        if profile_revision(root) != draft.revision:
            raise StaleProfileDraft(
                "Your profile changed. Ask the coach to prepare a fresh draft before applying it."
            )
        source = next(
            (
                turn["text"]
                for turn in session["turns"]
                if turn["role"] == "user"
                and hashlib.sha256(turn["text"].encode()).hexdigest()
                == draft.source_text_hash
            ),
            None,
        )
        if source is None:
            raise ValueError("The draft's original user message is unavailable")
        normalized = " ".join(source.split()).casefold()
        for record in draft.changes:
            if any(
                not quote.strip()
                or " ".join(quote.split()).casefold() not in normalized
                for quote in record.change.quotes
            ):
                raise ValueError("The draft's user evidence no longer matches")
        apply_workspace_draft(
            root,
            draft,
            source,
            receipt_paths=(coach_dir(root) / f"session-{session_id}.json",),
            on_applied=lambda: mutate_session(root, session_id, mark_resolved),
        )


def apply_workspace_draft(
    root: Path,
    draft: CoachChangeDraft,
    source: str,
    *,
    receipt_paths: tuple[Path, ...] = (),
    on_applied=None,
) -> None:
    """Apply a host-approved draft; this function is never exposed as an agent tool."""
    with manual_skills_lock(root):
        if profile_revision(root) != draft.revision:
            raise StaleProfileDraft("Profile changed; request a fresh proposal")
        if hashlib.sha256(source.encode()).hexdigest() != draft.source_text_hash:
            raise ValueError("Original user evidence no longer matches")
        normalized = " ".join(source.split()).casefold()
        for item in draft.changes:
            if any(
                not q.strip() or " ".join(q.split()).casefold() not in normalized
                for q in item.change.quotes
            ):
                raise ValueError("Profile changes require current user evidence")
        facts = current_facts(root)
        facts = facts.model_copy(deep=True) if facts else None
        ledger = load_edits(root)
        organization = load_group_corrections(corrections_path(root), strict=True)
        original_organization = organization.model_dump()
        for record in draft.changes:
            before = facts
            facts, _ = apply_change(facts, record, organization=organization)
            if (
                record.change.entity == "profile"
                and record.change.operation == "delete"
            ):
                from resume_tailor_harness.tailor.provenance import index_facts
                from resume_tailor_harness.profile.corpus import load_manifest

                index = index_facts(before) if before else {}
                if before and before.github_profile is not None:
                    index[before.github_profile.id] = before.github_profile
                refs = {item.source_ref for item in index.values() if item.source_ref}
                refs.update(doc.id for doc in load_manifest(root).docs)
                ledger = ProfileEdits(
                    reset_sources=True,
                    deleted=True,
                    excluded_source_refs=sorted(refs),
                    excluded_fact_ids=sorted(index),
                )
            else:
                ledger.deleted = False
                ledger.changes.append(record)
        if facts is not None:
            capture_skill_overrides(facts, ledger, records=draft.changes)
        paths = (
            edits_path(root),
            root / "facts.json",
            root / "matrix.json",
            root / "manual_skills.json",
            corrections_path(root),
            *receipt_paths,
        )
        with rollback_scope(paths):
            save_edits(root, ledger)
            if organization.model_dump() != original_organization:
                save_group_corrections(organization, corrections_path(root))
            if facts is None:
                (root / "facts.json").unlink(missing_ok=True)
                (root / "matrix.json").unlink(missing_ok=True)
                (root / "manual_skills.json").unlink(missing_ok=True)
            else:
                save_facts(facts, root / "facts.json")
                rebuild_saved_matrix(root, facts)
            if on_applied is not None:
                on_applied()
