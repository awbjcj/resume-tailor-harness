"""Durable library of generated advice, including targets no longer in demand."""

from typing import cast

from sqlmodel import Session, col, select
from resume_tailor_harness.db import workspace_write

from resume_tailor_harness.api.schemas.suggestions import (
    LearningRoadmapOut,
    LearningStatus,
    SuggestionEnvelope,
    SuggestionOut,
)
from resume_tailor_harness.services.suggestions import (
    SuggestionKind,
    SuggestionTargetNotFound,
    resolve_suggestion_context,
    select_suggestion_row,
    suggestion_fingerprint,
)
from resume_tailor_harness.tracking.match_gap import DemandGraph
from resume_tailor_harness.tracking.tables import (
    LearningRoadmapProgress,
    SkillSuggestion,
)


def list_roadmaps(
    session: Session, graph: DemandGraph, coverage: set[str]
) -> list[LearningRoadmapOut]:
    progress = {
        row.suggestion_id: row.status
        for row in session.exec(select(LearningRoadmapProgress)).all()
    }
    results = []
    rows = list(
        session.exec(
            select(SkillSuggestion).order_by(
                col(SkillSuggestion.generated_at).desc(), col(SkillSuggestion.id).desc()
            )
        ).all()
    )
    rows_by_key = {(row.kind, row.key): row for row in rows}
    for row in rows:
        if row.kind not in ("skill", "domain") or row.id is None:
            continue
        kind = cast(SuggestionKind, row.kind)
        label, key, available, stale = row.key, row.key, False, True
        superseded_by_id = None
        try:
            context = resolve_suggestion_context(graph, kind=kind, key=row.key)
            selected = select_suggestion_row(rows_by_key, context)
            if selected is not None and selected.id != row.id:
                superseded_by_id = selected.id
            else:
                label, key, available = context.label, context.key, True
            stale = row.fingerprint != suggestion_fingerprint(context, coverage)
        except SuggestionTargetNotFound:
            pass
        results.append(
            LearningRoadmapOut(
                id=row.id,
                label=label,
                available=available,
                superseded_by_id=superseded_by_id,
                status=cast(LearningStatus, progress.get(row.id, "planned")),
                envelope=SuggestionEnvelope(
                    stale=stale,
                    suggestion=SuggestionOut(
                        kind=kind,
                        key=key,
                        generated_at=row.generated_at,
                        **row.payload_json,
                    ),
                ),
            )
        )
    return results


def update_roadmap(
    session: Session, suggestion_id: int, status: LearningStatus
) -> bool:
    with workspace_write(session):
        row = session.get(SkillSuggestion, suggestion_id)
        if row is None or row.kind not in ("skill", "domain"):
            return False
        progress = session.get(LearningRoadmapProgress, suggestion_id)
        if progress is None:
            progress = LearningRoadmapProgress(suggestion_id=suggestion_id)
        progress.status = status
        session.add(progress)
        session.commit()
    return True
