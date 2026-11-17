"""Validated historical H-1B evidence contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

H1BCountBasis = Literal["fiscal_year_to_date_determinations"]
H1B_CUMULATIVE_COUNT_BASIS: H1BCountBasis = "fiscal_year_to_date_determinations"
_FISCAL_PERIOD = re.compile(r"FY(\d{4})[ -]Q([1-4])")
HISTORICAL_ONLY_CAVEAT = (
    "Historical H-1B filings do not confirm current sponsorship for this role "
    "or current employer policy."
)
H1B_DISABLED_MESSAGE = (
    "H-1B research is disabled for this workspace. Enable H1B_MCP_ENABLED and "
    "configure an MCP command or URL."
)
H1B_NO_EVIDENCE_MESSAGE = "No H-1B evidence has been checked for this job yet."
H1B_MCP_UNAVAILABLE_REASON = (
    "The H-1B MCP service could not be reached. Check the configured command or URL."
)
H1B_AGENT_UNAVAILABLE_REASON = (
    "The H-1B research agent did not return valid evidence for this company."
)


class H1BCompanyResolution(BaseModel):
    """Validated company-name rewrite used before historical H-1B lookup."""

    status: Literal["resolved", "unchanged", "uncertain"]
    legal_name: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="before")
    @classmethod
    def _unwrap_schema_echo(cls, data: Any) -> Any:
        """Tolerate a provider that echoes the JSON-Schema shape it was given.

        Observed live on DeepSeek (whose ``strict`` flag validates the request
        schema, not the generation -- see llm_runner.py's DeepSeek notes): the
        real answer arrived wrapped as ``{"description": ..., "properties":
        {"status": ..., "legal_name": ..., "confidence": ...}}``, mirroring the
        JSON Schema definition instead of filling it in. Unwrapping here lets
        the first parse attempt succeed instead of burning both retries on a
        shape no amount of JSON-repair fixes.
        """
        if (
            isinstance(data, dict)
            and "status" not in data
            and isinstance(data.get("properties"), dict)
        ):
            return data["properties"]
        return data


class H1BWageSummary(BaseModel):
    """The four aggregates supplied by the historical H-1B tools.

    Explicit nullable fields give structured-output providers a closed object
    schema. Missing statistics remain unknown, while cache/API serialization
    keeps the existing sparse numeric dictionary contract.
    """

    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None

    @model_serializer
    def serialize_metrics(self) -> dict[str, float]:
        return {
            name: value
            for name in type(self).model_fields
            if (value := getattr(self, name)) is not None
        }


class H1BPeriodStat(BaseModel):
    """One historical disclosure snapshot for a company."""

    period: str = Field(min_length=1, max_length=32)
    filing_count: int | None = Field(default=None, ge=0)
    certified_count: int | None = Field(default=None, ge=0)
    denied_count: int | None = Field(default=None, ge=0)
    wage_summary: H1BWageSummary | None = None

    @model_validator(mode="after")
    def validate_outcome_counts(self) -> H1BPeriodStat:
        if (
            self.filing_count is not None
            and self.certified_count is not None
            and self.denied_count is not None
            and self.certified_count + self.denied_count > self.filing_count
        ):
            raise ValueError(
                "certified_count + denied_count cannot exceed filing_count"
            )
        return self


def _period_key(period: str) -> tuple[int, int]:
    match = _FISCAL_PERIOD.fullmatch(period)
    if match is None:
        raise ValueError("H1B cumulative snapshots need a reported fiscal year and quarter")
    return int(match[1]), int(match[2])


class H1BSponsorshipEvidence(BaseModel):
    status: Literal["matched", "no_match", "unavailable"]
    normalized_company: str = Field(min_length=1)
    display_company: str | None = None
    fiscal_periods: list[str] = Field(default_factory=list)
    count_basis: H1BCountBasis | None = None
    filing_count: int | None = Field(default=None, ge=0)
    certified_count: int | None = Field(default=None, ge=0)
    denied_count: int | None = Field(default=None, ge=0)
    periods: list[H1BPeriodStat] = Field(default_factory=list, max_length=12)
    wage_summary: H1BWageSummary | None = None
    source_url: str | None = None
    data_version: str | None = None
    retrieved_at: datetime | None = None
    expires_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    caveat: str
    unavailable_reason: str | None = None

    @field_validator("periods", mode="before")
    @classmethod
    def _cap_periods(cls, value: Any) -> Any:
        """Keep the newest twelve quarters instead of rejecting an over-long list.

        The agent is instructed to return at most twelve quarters, newest first,
        but a provider that over-reports should not lose an otherwise-valid
        response to the ``max_length`` constraint below -- truncate instead.
        """
        if isinstance(value, list) and len(value) > 12:
            return value[:12]
        return value

    @field_validator("retrieved_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        # Both fields are always overwritten with real timestamps by
        # `enrich_companies` after the agent call returns (see h1b/service.py),
        # so an agent that leaves them blank -- most do, since it has no real
        # clock to report from -- must not fail validation over it.
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("H1B timestamps must be timezone-aware")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("H1B source_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("H1B source_url must not contain credentials")
        return value

    @model_validator(mode="after")
    def validate_historical_contract(self) -> H1BSponsorshipEvidence:
        if self.periods:
            labels = [period.period for period in self.periods]
            if len(set(labels)) != len(labels):
                raise ValueError("H1B evidence periods must have unique labels")
            if self.count_basis == H1B_CUMULATIVE_COUNT_BASIS:
                keys = [_period_key(period.period) for period in self.periods]
                if len(set(keys)) != len(keys):
                    raise ValueError("H1B evidence must not repeat a disclosure snapshot")
                self.periods.sort(key=lambda period: _period_key(period.period), reverse=True)
                latest = self.periods[0]
                # A snapshot already contains earlier cases from its fiscal
                # year. Use one coherent observation, not a sum or mix of rows.
                self.filing_count = latest.filing_count
                self.certified_count = latest.certified_count
                self.denied_count = latest.denied_count
                self.wage_summary = latest.wage_summary
        if (
            self.expires_at is not None
            and self.retrieved_at is not None
            and self.expires_at <= self.retrieved_at
        ):
            raise ValueError("H1B evidence must expire after retrieval")
        if self.caveat != HISTORICAL_ONLY_CAVEAT:
            raise ValueError("H1B evidence must use the application caveat")
        if self.certified_count is not None and self.filing_count is not None:
            if self.certified_count > self.filing_count:
                raise ValueError("certified_count cannot exceed filing_count")
        if self.denied_count is not None and self.filing_count is not None:
            if self.denied_count > self.filing_count:
                raise ValueError("denied_count cannot exceed filing_count")
        if (
            self.filing_count is not None
            and self.certified_count is not None
            and self.denied_count is not None
            and self.certified_count + self.denied_count > self.filing_count
        ):
            raise ValueError(
                "certified_count + denied_count cannot exceed filing_count"
            )
        return self

    def has_supported_count_basis(self) -> bool:
        return self.status == "unavailable" or self.count_basis == H1B_CUMULATIVE_COUNT_BASIS

    def is_fresh(self, now: datetime) -> bool:
        """Whether this evidence is still inside its cache TTL at ``now``.

        The single definition of "fresh" -- every caller that needs to decide
        whether to reuse cached evidence or label it stale for display goes
        through this instead of re-deriving the ``expires_at`` comparison.
        Evidence with no ``expires_at`` (only possible on the transient,
        not-yet-persisted object an agent call returns) is never fresh.
        """
        return self.expires_at is not None and self.expires_at > now


class H1BEnrichmentReport(BaseModel):
    by_company: dict[str, H1BSponsorshipEvidence]
    cache_hits: int = Field(default=0, ge=0)
    researched: int = Field(default=0, ge=0)
    unavailable: int = Field(default=0, ge=0)
