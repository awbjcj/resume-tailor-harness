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
        return "\n".join(
            " ".join(
                [
                    node.get_text(" ", strip=True),
                    *[
                        str(node.get(key, ""))
                        for key in ("href", "content", "datetime", "data-job-id", "id")
                    ],
                ]
            )
            for node in nodes
        )
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
            and _supports_value(
                field, value, evidence_text(item, by_id[item.snapshot_id])
            )
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


def _supports_value(field: str, value, text: str) -> bool:
    normalized = " ".join(
        BeautifulSoup(text, "html.parser").get_text(" ", strip=True).split()
    ).casefold()
    if field in {
        "title",
        "company",
        "jd_text",
        "posting_id",
        "application_url",
        "posted_at",
        "closes_at",
    }:
        return " ".join(str(value).split()).casefold() in normalized
    if field == "remote_policy":
        terms = {
            "remote": ("remote", "telecommute"),
            "hybrid": ("hybrid",),
            "onsite": ("onsite", "on-site", "on site", "in office"),
        }
        if any(
            phrase in normalized
            for phrase in (
                f"not {value}",
                f"no {value}",
                f"not a {value}",
                f"{value} not available",
            )
        ):
            return False
        return any(term in normalized for term in terms.get(value, ()))
    if field == "locations":
        return all(
            all(part.strip().casefold() in normalized for part in location.split(","))
            for location in value
        )
    if field == "salary_bands":
        for band in value:
            raw = " ".join(str(band.get("raw_text", "")).split()).casefold()
            if not raw or raw not in normalized:
                return False
            local = raw.replace(",", "")
            for key in ("minimum", "maximum", "currency", "period"):
                fact = band.get(key)
                if fact is None:
                    continue
                alternatives = [str(fact).casefold()]
                if key in {"minimum", "maximum"}:
                    amount = float(fact)
                    alternatives.extend([f"{amount:g}", f"{amount / 1000:g}k"])
                if not any(item in local for item in alternatives):
                    return False
            if any(
                location.casefold() not in raw for location in band.get("locations", [])
            ):
                return False
        return True
    return " ".join(str(value).split()).casefold() in normalized


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
