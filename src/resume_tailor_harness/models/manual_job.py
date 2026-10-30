"""Explicit posting details supplied by a person or browser agent."""

from datetime import date
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from resume_tailor_harness.models.job import (
    EmploymentType,
    JobCriteria,
    SalaryRange,
    Seniority,
    SponsorshipSignal,
)

ShortText = Annotated[str, Field(max_length=1000)]
Skill = Annotated[str, Field(min_length=1, max_length=200)]


def posting_url(value: str | None) -> str | None:
    """Validate a stored link without fetching it or requiring a public page."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(char.isspace() for char in value)
    ):
        raise ValueError("Use an HTTP or HTTPS URL without credentials")
    return value


class ManualJobDetails(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    remote_policy: Literal["remote", "hybrid", "onsite"] | None = None
    remote_restrictions: ShortText | None = None
    attendance: ShortText | None = None
    seniority: Seniority | None = None
    employment_type: EmploymentType | None = None
    sponsorship_signal: SponsorshipSignal | None = None
    industry: ShortText | None = None
    company_size: ShortText | None = None
    yoe_min: int | None = Field(default=None, ge=0, le=100)
    tech_stack: list[Skill] = Field(default_factory=list, max_length=200)
    must_have_skills: list[Skill] = Field(default_factory=list, max_length=200)
    nice_to_have_skills: list[Skill] = Field(default_factory=list, max_length=200)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_period: Literal["year", "month", "week", "day", "hour"] | None = None
    posting_id: ShortText | None = None
    closes_at: date | None = None
    application_url: str | None = Field(default=None, max_length=4096)
    source_url: str | None = Field(default=None, max_length=4096)

    _urls = field_validator("application_url", "source_url")(posting_url)

    @model_validator(mode="after")
    def validate_salary(self) -> Self:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("Salary minimum must not exceed maximum")
        if self.salary_min is not None or self.salary_max is not None:
            if not self.salary_currency or not self.salary_period:
                raise ValueError("Salary amounts require a currency and pay period")
        return self

    def apply(self, criteria: JobCriteria) -> JobCriteria:
        """Override only supplied facts; unknown fields remain extractable."""
        values = criteria.model_dump(mode="json")
        supplied = {
            key: value
            for key, value in self.model_dump(mode="json").items()
            if value is not None and value != "" and value != []
        }
        for name in JobCriteria.model_fields:
            if name in supplied:
                values[name] = supplied[name]
        if self.salary_min is not None or self.salary_max is not None:
            values["salary_range"] = SalaryRange(
                minimum=self.salary_min,
                maximum=self.salary_max,
                currency=self.salary_currency or "USD",
                period=self.salary_period or "year",
            ).model_dump(mode="json")
        values["manual_details"] = supplied
        return JobCriteria.model_validate(values)


def preserve_manual_details(stored: dict | None, criteria: JobCriteria) -> JobCriteria:
    supplied = (stored or {}).get("manual_details")
    if not supplied:
        return criteria
    return ManualJobDetails.model_validate(supplied).apply(criteria)


def reset_extracted_criteria(stored: dict | None) -> dict | None:
    """Discard derived criteria without discarding manually supplied source facts."""
    if not (stored or {}).get("manual_details"):
        return None
    return preserve_manual_details(stored, JobCriteria()).model_dump(mode="json")
