"""Structured, user-supplied application answers, separate from resume evidence."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from resume_tailor_harness.api.schemas.base import CamelModel

ApplicationAnswer = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=4000)
]
RequiredAnswer = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class AnswerRecord(CamelModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ApplicationName(AnswerRecord):
    given_name: ApplicationAnswer = ""
    middle_name: ApplicationAnswer = ""
    family_name: ApplicationAnswer = ""
    suffix: ApplicationAnswer = ""


class MailingAddress(AnswerRecord):
    line1: ApplicationAnswer = ""
    line2: ApplicationAnswer = ""
    city: ApplicationAnswer = ""
    region: ApplicationAnswer = ""
    postal_code: ApplicationAnswer = ""
    country: ApplicationAnswer = ""


class DatedAnswerRecord(AnswerRecord):
    confirmed_on: date


class EmployerScope(AnswerRecord):
    employer: RequiredAnswer
    requisition: ApplicationAnswer = ""
    country: ApplicationAnswer = ""


class AlternateEmail(DatedAnswerRecord):
    email: Annotated[
        str,
        StringConstraints(
            min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
        ),
    ]
    employer: ApplicationAnswer = ""
    requisition: ApplicationAnswer = ""
    country: ApplicationAnswer = ""
    # An alias is not automatically permission to substitute the contact email.
    permitted: StrictBool | None = None

    @model_validator(mode="after")
    def _require_employer_for_requisition(self) -> AlternateEmail:
        if self.requisition and not self.employer:
            raise ValueError("A requisition-scoped email requires an employer")
        return self


class WorkEligibility(DatedAnswerRecord):
    country: RequiredAnswer
    immigration_status: ApplicationAnswer = ""
    authorized_to_work: StrictBool | None = None
    sponsorship_now: StrictBool | None = None
    sponsorship_future: StrictBool | None = None
    can_verify_authorization: StrictBool | None = None
    currently_on_opt: StrictBool | None = None
    stem_opt_extension_eligible: StrictBool | None = None


class ExperienceRange(DatedAnswerRecord):
    specialty: RequiredAnswer
    minimum_years: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    maximum_years: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def _ordered_range(self) -> ExperienceRange:
        if (self.minimum_years is None) != (self.maximum_years is None):
            raise ValueError("Supply both experience bounds or leave both unknown")
        if (
            self.minimum_years is not None
            and self.maximum_years is not None
            and self.minimum_years > self.maximum_years
        ):
            raise ValueError("minimum_years cannot exceed maximum_years")
        return self


class EmployerAnswer(EmployerScope, DatedAnswerRecord):
    category: Literal[
        "general",
        "referral",
        "employment",
        "contractor",
        "relationship",
        "previous_application",
        "degree_category",
        "role_requirement",
    ] = "general"
    question: RequiredAnswer
    answer: ApplicationAnswer | None = None
    timeframe: ApplicationAnswer = ""
    valid_until: date | None = None

    @field_validator("answer", mode="before")
    @classmethod
    def _blank_is_unknown(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _valid_dates(self) -> EmployerAnswer:
        if self.valid_until and self.valid_until < self.confirmed_on:
            raise ValueError("valid_until cannot precede confirmed_on")
        return self
