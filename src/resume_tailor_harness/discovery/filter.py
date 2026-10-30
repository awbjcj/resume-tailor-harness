from pydantic import Field

from resume_tailor_harness.discovery.search_config import SearchConfig
from resume_tailor_harness.models.base import ExtensibleModel
from resume_tailor_harness.models.job import JobCriteria, SponsorshipSignal
from resume_tailor_harness.salary import annual_usd_amount


class FilterDecision(ExtensibleModel):
    keep: bool
    reject_reason: str | None = None
    flags: list[str] = Field(default_factory=list)


def apply_filters(criteria: JobCriteria, config: SearchConfig) -> FilterDecision:
    """Deterministic hard filter. Sponsorship 'silent' is kept but flagged."""
    flags: list[str] = []

    if config.sponsorship_required:
        if criteria.sponsorship_signal == SponsorshipSignal.denied:
            return FilterDecision(keep=False, reject_reason="sponsorship not available")
        if criteria.sponsorship_signal == SponsorshipSignal.silent:
            flags.append("sponsorship_uncertain")

    salary = criteria.salary_range
    comparable_salary = (
        annual_usd_amount(salary.maximum, salary.currency, salary.period)
        if salary is not None
        else None
    )
    if (
        config.min_salary is not None
        and comparable_salary is not None
        and comparable_salary < config.min_salary
    ):
        return FilterDecision(keep=False, reject_reason="salary below minimum")

    if (
        config.yoe_max is not None
        and criteria.yoe_min is not None
        and criteria.yoe_min > config.yoe_max
    ):
        return FilterDecision(
            keep=False, reject_reason="requires more experience than yoe_max"
        )

    return FilterDecision(keep=True, flags=flags)
