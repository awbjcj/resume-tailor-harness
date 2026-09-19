"""Shared API schema base: camelCase wire format + the pagination envelope."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """All request/response models use camelCase and explicit UTC instants.

    Python field names stay snake_case; the alias generator maps them to camelCase.
    `populate_by_name` lets construction work with either spelling;
    `from_attributes` lets `model_validate(dto)` read snake_case dataclass attrs.

    SQLite returns persisted UTC values as naive ``datetime`` objects.  Treating
    those as browser-local values shifts job, run, and log timestamps for every
    user outside UTC, so every datetime emitted by the API carries an explicit
    UTC offset.  Browsers can then convert the same instant to the current
    user's IANA timezone consistently.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_utc(self, value):
        if not isinstance(value, datetime):
            return value
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Pagination(CamelModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class Page(CamelModel, Generic[T]):
    data: list[T]
    pagination: Pagination


class BoardPage(Page[T], Generic[T]):
    facets: dict[str, dict[str, int]] | None
    total: int
