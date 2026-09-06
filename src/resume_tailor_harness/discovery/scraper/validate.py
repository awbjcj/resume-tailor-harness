"""Observable checks separate schema validity from extraction correctness."""

import json

from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

from .contracts import (
    BoardPlan,
    Evidence,
    FieldIssue,
    Observation,
    Snapshot,
    ValidationResult,
)


def evidence_text(evidence: Evidence, snapshot: Snapshot) -> str:
    if evidence.snapshot_id != snapshot.id:
        return ""
    if evidence.json_path:
        value = snapshot.json_ld
        try:
            for part in evidence.json_path.split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, IndexError, TypeError, ValueError):
            return ""
        return (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )
    if evidence.selector:
        try:
            nodes = BeautifulSoup(snapshot.html, "html.parser").select(
                evidence.selector
            )
        except SelectorSyntaxError:
            return ""
        return "\n".join(node.get_text(" ", strip=True) for node in nodes)
    return snapshot.visible_text


def validate_evidence(
    observation: Observation, snapshots: list[Snapshot]
) -> ValidationResult:
    issues = []
    by_id = {snapshot.id: snapshot for snapshot in snapshots}
    for field, value in observation.facts.model_dump().items():
        if value is None or field == "source_url":
            continue
        candidates = [item for item in observation.evidence if item.field == field]
        if not any(
            item.snapshot_id in by_id
            and " ".join(item.quote.split())
            in " ".join(evidence_text(item, by_id[item.snapshot_id]).split())
            for item in candidates
        ):
            issues.append(
                FieldIssue(
                    field=field,
                    kind="invalid_evidence",
                    message="No matching source evidence",
                )
            )
    if not observation.job_key:
        issues.append(
            FieldIssue(kind="extraction_failed", message="No stable posting identity")
        )
    for field in ("title", "jd_text"):
        if not getattr(observation.facts, field):
            issues.append(
                FieldIssue(
                    field=field,
                    kind="extraction_failed",
                    message="Required job content is missing",
                )
            )
    return ValidationResult(valid=not issues, issues=issues)


def validate_plan(
    plan: BoardPlan, listing: Snapshot, details: list[Snapshot]
) -> ValidationResult:
    issues = []
    try:
        soup = BeautifulSoup(listing.html, "html.parser")
        cards = soup.select(plan.card_selector)
        if not cards:
            issues.append(
                FieldIssue(
                    kind="invalid_evidence",
                    message="Card selector matches no observed results",
                )
            )
        if not details:
            issues.append(
                FieldIssue(
                    kind="invalid_evidence",
                    message="Inspect a job detail before approval",
                )
            )
        for detail in details:
            if not plan.detail_selector or not BeautifulSoup(
                detail.html, "html.parser"
            ).select(plan.detail_selector):
                issues.append(
                    FieldIssue(
                        field="jd_text",
                        kind="invalid_evidence",
                        message="Description rule does not match an observed detail",
                    )
                )
        for rule in plan.field_rules:
            soup.select(
                rule.selector
            )  # Syntax validation; optional absence is legitimate.
    except SelectorSyntaxError as exc:
        issues.append(
            FieldIssue(kind="invalid_evidence", message=f"Invalid selector: {exc}")
        )
    return ValidationResult(valid=not issues, issues=issues)
