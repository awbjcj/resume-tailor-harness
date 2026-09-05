"""Version-checked review storage within the caller's workspace DB session."""

import json

from sqlalchemy import update
from sqlmodel import Session, select

from .contracts import Draft, FieldName, JobFacts, Observation, OverridePatch, Snapshot
from .identity import normalize_board_url
from .tables import (
    ScrapeDraftRow,
    ScrapeObservationRow,
    ScrapeOverrideHistoryRow,
    ScrapeOverrideRow,
    ScrapeRevisionRow,
    ScrapeSnapshotRow,
    ScrapeSourceRow,
)


class RevisionConflict(ValueError):
    pass


class ScrapeStore:
    def __init__(self, session: Session):
        self.session = session

    def get_draft(self, draft_id: str) -> Draft:
        row = self.session.get(ScrapeDraftRow, draft_id)
        if row is None:
            raise KeyError(draft_id)
        return Draft.model_validate_json(row.payload)

    def save_draft(self, draft: Draft) -> Draft:
        current = self.session.get(ScrapeDraftRow, draft.id)
        if current is None:
            if draft.revision != 0:
                raise RevisionConflict("draft no longer exists")
            self.session.add(
                ScrapeDraftRow(id=draft.id, revision=0, payload=draft.model_dump_json())
            )
            self.session.flush()
            return draft
        saved = draft.model_copy(update={"revision": draft.revision + 1})
        result = self.session.execute(
            update(ScrapeDraftRow)
            .where(
                ScrapeDraftRow.id == draft.id,
                ScrapeDraftRow.revision == draft.revision,
                ScrapeDraftRow.approved_from.is_(None),
            )
            .values(revision=saved.revision, payload=saved.model_dump_json())
        )
        if result.rowcount != 1:
            raise RevisionConflict("draft changed; reload before editing")
        self.session.flush()
        return saved

    def approve(self, draft_id: str, expected_revision: int) -> Draft:
        row = self.session.get(ScrapeDraftRow, draft_id)
        if row is None:
            raise KeyError(draft_id)
        if row.approved_from is not None:
            if row.approved_from != expected_revision:
                raise RevisionConflict("approval revision changed")
            return Draft.model_validate_json(row.payload)
        draft = Draft.model_validate_json(row.payload)
        if draft.revision != expected_revision:
            raise RevisionConflict("draft changed; reload before approval")
        if (
            not draft.validation.valid
            or draft.state != "validated"
            or draft.plan is None
        ):
            raise ValueError("only a validated extraction plan can be approved")
        source = self.session.get(ScrapeSourceRow, draft.source_id)
        source_revision = source.revision if source else 0
        approved = draft.model_copy(
            update={"state": "approved", "revision": source_revision + 1}
        )
        payload = approved.model_dump_json()
        result = self.session.execute(
            update(ScrapeDraftRow)
            .where(
                ScrapeDraftRow.id == draft.id,
                ScrapeDraftRow.revision == expected_revision,
                ScrapeDraftRow.approved_from.is_(None),
            )
            .values(
                payload=payload,
                revision=approved.revision,
                approved_from=expected_revision,
            )
        )
        if result.rowcount != 1:
            raise RevisionConflict("draft approval raced another change")
        if source:
            result = self.session.execute(
                update(ScrapeSourceRow)
                .where(
                    ScrapeSourceRow.id == source.id,
                    ScrapeSourceRow.revision == source_revision,
                )
                .values(revision=approved.revision, payload=payload)
            )
            if result.rowcount != 1:
                raise RevisionConflict("source changed during approval")
        else:
            self.session.add(
                ScrapeSourceRow(
                    id=draft.source_id,
                    url=normalize_board_url(draft.url),
                    revision=approved.revision,
                    payload=payload,
                )
            )
        self.session.add(
            ScrapeRevisionRow(
                source_id=draft.source_id, revision=approved.revision, payload=payload
            )
        )
        self.session.flush()
        return approved

    def list_sources(self) -> list[ScrapeSourceRow]:
        return list(self.session.exec(select(ScrapeSourceRow)).all())

    def save_observation(self, value: Observation) -> None:
        if self.session.get(ScrapeObservationRow, value.id) is None:
            self.session.add(
                ScrapeObservationRow(
                    id=value.id,
                    job_key=value.job_key,
                    source_id=value.source_id,
                    payload=value.model_dump_json(),
                )
            )
            self.session.flush()

    def save_snapshot(self, value: Snapshot) -> None:
        if self.session.get(ScrapeSnapshotRow, value.id) is None:
            self.session.add(
                ScrapeSnapshotRow(id=value.id, payload=value.model_dump_json())
            )
            self.session.flush()

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        row = self.session.get(ScrapeSnapshotRow, snapshot_id)
        if row is None:
            raise KeyError(snapshot_id)
        return Snapshot.model_validate_json(row.payload)

    def set_override(self, job_key: str, patch: OverridePatch) -> int:
        # Validate a single field without inventing values for other fields.
        JobFacts.model_validate(
            {"source_url": "https://example.com/", patch.field: patch.value}
        )
        return self._override(
            job_key,
            patch.field,
            patch.expected_revision,
            json.dumps(patch.value),
            False,
        )

    def remove_override(
        self, job_key: str, field: FieldName, expected_revision: int
    ) -> int:
        return self._override(job_key, field, expected_revision, "null", True)

    def _override(
        self, job_key: str, field: str, expected: int, value: str, removed: bool
    ) -> int:
        current = self.session.get(ScrapeOverrideRow, (job_key, field))
        revision = expected + 1
        if current is None:
            if expected != 0:
                raise RevisionConflict("override no longer exists")
            self.session.add(
                ScrapeOverrideRow(
                    job_key=job_key,
                    field=field,
                    revision=revision,
                    value=value,
                    removed=removed,
                )
            )
        else:
            result = self.session.execute(
                update(ScrapeOverrideRow)
                .where(
                    ScrapeOverrideRow.job_key == job_key,
                    ScrapeOverrideRow.field == field,
                    ScrapeOverrideRow.revision == expected,
                )
                .values(revision=revision, value=value, removed=removed)
            )
            if result.rowcount != 1:
                raise RevisionConflict("override changed; reload before editing")
        self.session.add(
            ScrapeOverrideHistoryRow(
                job_key=job_key,
                field=field,
                revision=revision,
                value=value,
                removed=removed,
            )
        )
        self.session.flush()
        return revision

    def override_history(self, job_key: str) -> list[ScrapeOverrideHistoryRow]:
        return list(
            self.session.exec(
                select(ScrapeOverrideHistoryRow)
                .where(ScrapeOverrideHistoryRow.job_key == job_key)
                .order_by(ScrapeOverrideHistoryRow.revision)
            ).all()
        )

    def effective_facts(self, observation: Observation) -> JobFacts:
        data = observation.facts.model_dump(mode="json")
        if observation.job_key:
            rows = self.session.exec(
                select(ScrapeOverrideRow).where(
                    ScrapeOverrideRow.job_key == observation.job_key
                )
            ).all()
            for row in rows:
                if not row.removed:
                    data[row.field] = json.loads(row.value)
        return JobFacts.model_validate(data)
