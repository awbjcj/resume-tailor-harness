"""Replay observed selectors, retaining partial results and source evidence."""

from urllib.parse import urljoin
from hashlib import sha256
from typing import Any, Literal, cast

from bs4 import BeautifulSoup

from resume_tailor_harness.llm_runner import Runner
from resume_tailor_harness.security.browser_gateway import CrawlStopped

from .browser_worker import BrowserUnavailable, snapshot_from_html
from .contracts import BrowserAction, Draft, Evidence, FieldIssue, FieldRule, PullReport
from .extract import extract_observation
from .identity import observed_job_key
from .pacing import BudgetExceeded, CrawlBudget
from .store import ScrapeStore
from .validate import validate_evidence


def _anonymous_card_key(source_id: str, card: Any) -> str:
    """Keep an inline/panel card replayable even before extraction finds its ID."""
    return sha256(f"{source_id}\ncard:{card}".encode()).hexdigest()


def replay(
    draft: Draft,
    worker: Any,
    store: ScrapeStore,
    agent: Runner | None,
    *,
    preview: bool = False,
    refresh: bool = False,
    budget: CrawlBudget | None = None,
) -> PullReport:
    report = PullReport()
    plan = draft.plan
    if plan is None:
        return PullReport(
            terminal_reason="review_required", messages=["No approved extraction rules"]
        )
    budget = budget or CrawlBudget(draft.limits)
    seen = set()
    try:
        budget.charge_listing()
        listing = worker.snapshot(draft.url, budget)
        while True:
            store.save_snapshot(listing)
            store.cache_snapshot(f"{draft.source_id}:listing", listing)
            cards = BeautifulSoup(listing.html, "html.parser").select(
                plan.card_selector
            )
            new_count = 0
            for index, card in enumerate(cards):
                link = (
                    card.select_one(plan.link_selector) if plan.link_selector else None
                )
                url = (
                    urljoin(listing.final_url, str(link.get("href")))
                    if link and link.get("href")
                    else None
                )
                posting_id = card.get("data-job-id")
                identity = observed_job_key(
                    draft.source_id, str(posting_id) if posting_id else None, url
                )
                if identity is None and plan.detail_mode != "link":
                    identity = _anonymous_card_key(draft.source_id, card)
                if identity is not None and identity in seen:
                    continue
                if identity:
                    seen.add(identity)
                new_count += 1
                report.discovered += 1
                if preview and report.inspected >= 3:
                    report.terminal_reason = "partial_limit"
                    return report
                budget.charge_detail()
                detail = None
                opened = False
                try:
                    if plan.detail_mode == "link":
                        if not url:
                            raise ValueError("Missing public detail URL")
                        cache_key = f"{draft.source_id}:detail:{url}"
                        detail = None if refresh else store.cached_snapshot(cache_key)
                        stale = store.cached_snapshot(cache_key, allow_stale=True)
                        gateway = getattr(worker, "gateway", None)
                        if (
                            detail is None
                            and not refresh
                            and stale
                            and not stale.dynamic
                            and gateway
                            and (stale.etag or stale.last_modified)
                        ):
                            headers = (
                                {"if-none-match": stale.etag}
                                if stale.etag
                                else {"if-modified-since": stale.last_modified}
                            )
                            response = gateway.document(url, budget, headers=headers)
                            if response.status == 304:
                                detail = stale
                                store.cache_snapshot(cache_key, stale)
                            elif response.status == 200:
                                gateway.prefetched[response.final_url] = response
                            else:
                                raise ValueError(
                                    f"Detail refresh returned HTTP {response.status}"
                                )
                        if detail is None:
                            opened = True
                            detail = worker.act(
                                BrowserAction(kind="open_detail", url=url), budget
                            )
                            if not worker.errors:
                                store.cache_snapshot(cache_key, detail)
                    elif plan.detail_mode == "panel":
                        # Playwright's nth-match syntax applies to the complete card selector.
                        selector = f":nth-match({plan.card_selector}, {index + 1}) {plan.open_selector}"
                        opened = True
                        detail = worker.act(
                            BrowserAction(kind="open_detail", selector=selector), budget
                        )
                    else:
                        detail = snapshot_from_html(listing.final_url, str(card))
                    report.inspected += 1
                    store.save_snapshot(detail)
                    extraction_key = f"observation:{draft.source_id}:{draft.revision}:{sha256(plan.model_dump_json().encode()).hexdigest()}:{detail.id}"
                    observation = (
                        None if refresh else store.cached_observation(extraction_key)
                    )
                    if observation is None:
                        observation = extract_observation(
                            detail,
                            draft.source_id,
                            draft.revision,
                            agent,
                            plan.field_rules,
                        )
                        if observation.accepted:
                            store.cache_observation(extraction_key, observation)
                    if plan.detail_mode != "link":
                        observation.job_key = observed_job_key(
                            draft.source_id,
                            observation.facts.posting_id
                            or (str(posting_id) if posting_id else None),
                            url,
                        )
                    if observation.job_key:
                        seen.add(observation.job_key)
                    if not observation.job_key:
                        observation.accepted = False
                        observation.issues.append(
                            FieldIssue(
                                kind="extraction_failed",
                                message="Inline posting has no stable identity",
                            )
                        )
                    soup = BeautifulSoup(detail.html, "html.parser")
                    if plan.detail_selector and not soup.select(plan.detail_selector):
                        observation.accepted = False
                        observation.issues.append(
                            FieldIssue(
                                field="jd_text",
                                kind="invalid_evidence",
                                message="Saved description rule no longer matches",
                            )
                        )
                    rules = (
                        [FieldRule(field="jd_text", selector=plan.detail_selector)]
                        if plan.detail_selector
                        else []
                    ) + plan.field_rules
                    for rule in rules:
                        nodes = soup.select(rule.selector)
                        if not nodes:
                            continue
                        text = "\n".join(
                            str(node.get(rule.attribute, ""))
                            if rule.attribute
                            else node.get_text(" ", strip=True)
                            for node in nodes
                        )
                        if rule.field == "locations":
                            value = [node.get_text(" ", strip=True) for node in nodes]
                        elif rule.field == "remote_policy":
                            normalized = text.casefold().strip()
                            value = (
                                normalized
                                if normalized in {"remote", "hybrid", "onsite"}
                                else None
                            )
                        elif rule.field == "salary_bands":
                            # Salary stays typed and evidence-checked; never coerce arbitrary text into numbers.
                            continue
                        elif rule.field in {"source_url", "posting_id"}:
                            continue
                        else:
                            value = (
                                urljoin(detail.final_url, text)
                                if rule.field == "application_url"
                                else text
                            )
                        setattr(observation.facts, rule.field, value)
                        observation.evidence = [
                            item
                            for item in observation.evidence
                            if item.field != rule.field
                        ]
                        observation.evidence.append(
                            Evidence(
                                field=rule.field,
                                snapshot_id=detail.id,
                                quote=text,
                                selector=rule.selector,
                            )
                        )
                        observation.issues = [
                            item
                            for item in observation.issues
                            if item.field != rule.field
                        ]
                    validation = validate_evidence(observation, [detail])
                    observation.issues.extend(validation.issues)
                    observation.accepted = validation.valid and not any(
                        item.kind
                        in {"conflict", "invalid_evidence", "extraction_failed"}
                        for item in observation.issues
                    )
                    if worker.errors:
                        observation.accepted = False
                        observation.issues.append(
                            FieldIssue(
                                kind="extraction_failed",
                                message="Some page resources could not be inspected",
                            )
                        )
                    store.save_observation(observation)
                    report.observations.append(observation)
                    if not observation.accepted:
                        report.review_needed += 1
                    if worker.errors:
                        report.messages.extend(worker.errors)
                        report.terminal_reason = "review_required"
                except (BudgetExceeded, CrawlStopped, BrowserUnavailable):
                    raise
                except Exception as exc:
                    report.failed += 1
                    report.messages.append(str(exc))
                finally:
                    if opened:
                        worker.act(
                            BrowserAction(
                                kind="close_detail", selector=plan.close_selector
                            ),
                            budget,
                        )
            if not cards:
                report.terminal_reason = "review_required"
                report.messages.append(
                    "No matching cards; cannot confirm an empty board"
                )
                break
            if plan.pagination == "none":
                break
            if new_count == 0:
                report.terminal_reason = "review_required"
                report.messages.append(
                    "Pagination repeated previously observed results"
                )
                break
            if plan.pagination != "infinite":
                control = BeautifulSoup(listing.html, "html.parser").select_one(
                    plan.control_selector or ""
                )
                if (
                    control is None
                    or control.has_attr("disabled")
                    or control.get("aria-disabled") == "true"
                ):
                    break
            budget.charge_listing()
            kind = "scroll" if plan.pagination == "infinite" else "next"
            listing = worker.act(
                BrowserAction(kind=kind, selector=plan.control_selector), budget
            )
    except CrawlStopped as exc:
        report.terminal_reason = cast(Literal["blocked", "throttled"], exc.reason)
        report.messages.append(str(exc))
    except BrowserUnavailable as exc:
        report.terminal_reason = "capability_unavailable"
        report.messages.append(str(exc))
    except BudgetExceeded as exc:
        report.terminal_reason = (
            "cancelled" if str(exc) == "cancelled" else "partial_limit"
        )
        report.messages.append(str(exc))
    except Exception as exc:
        report.terminal_reason = "failed"
        report.messages.append(str(exc))
    if report.terminal_reason == "complete" and (report.failed or report.review_needed):
        report.terminal_reason = "review_required"
    return report
