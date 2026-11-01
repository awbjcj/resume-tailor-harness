"""Profile Coach turns, approval, recap, history views, and impact builds."""

from __future__ import annotations

import logging
import uuid
from functools import partial
from pathlib import Path

from resume_tailor_harness.llm_runner import Runner, UnparsedAgentOutput
from resume_tailor_harness.profile.coach import (
    AGENDA_CAP,
    CoachTurn,
    OpeningTurn,
    ValidatedTurn,
    build_coach_agent,
    build_coach_formatter_agent,
    normalize_opening,
    normalize_recap,
    normalize_turn,
    profile_overview,
    render_agenda,
    render_transcript,
)
from resume_tailor_harness.profile.depth import depth_topics
from resume_tailor_harness.profile.coach_store import (
    apply_turn_delta,
    CoachTurnRecord,
    coach_lock,
    create_session,
    end_session,
    list_sessions,
    load_session,
    set_draft_status,
    set_impact,
)
from resume_tailor_harness.profile.corpus import load_manifest
from resume_tailor_harness.profile.conversation import (
    make_profile_tools,
    prepare_changes,
)
from resume_tailor_harness.profile.intake import add_note_source
from resume_tailor_harness.profile.interview import make_corpus_tools
from resume_tailor_harness.profile.snapshot import profile_snapshot, snapshot_diff
from resume_tailor_harness.profile.store import load_facts
from resume_tailor_harness.services.profile_build import run_corpus_build
from resume_tailor_harness.sessions.stream import Notice, NullSink, StreamSink
from resume_tailor_harness.sessions.turns import (
    TurnRejected,
    DraftRejected,
    format_with_retry,
    persona_output,
    user_visible_prose,
)

_MAX_MESSAGE_CHARS = 100_000
_EMPTY_SESSION_RECAP = (
    "You ended this session before discussing any topics, so there was nothing to "
    "recap. Start a new session whenever you're ready to add evidence."
)

logger = logging.getLogger(__name__)


def _camel_action(action: dict) -> dict:
    return {"kind": action["kind"], "target": action["target"], "why": action["why"]}


def _camel_turn(turn: dict) -> dict:
    text = turn["text"]
    if turn["role"] == "coach":
        # Older sessions may contain output from a provider that malformed the
        # metadata sentinel. Keep those transcripts clean on read as well as
        # preventing new leaks in the streaming path.
        text = user_visible_prose(text)
    return {
        "role": turn["role"],
        "kind": turn["kind"],
        "text": text,
        "topicId": turn["topic_id"],
        "at": turn["at"],
        "notice": turn.get("notice", ""),
        "researchActions": [
            _camel_action(action) for action in turn.get("research_actions", [])
        ],
    }


def session_view(profile_dir: Path | str, session_id: str) -> dict:
    session = load_session(profile_dir, session_id)
    return {
        "sessionId": session["session_id"],
        "sessionTitle": session["session_title"],
        "startedAt": session["started_at"],
        "endedAt": session["ended_at"],
        "status": session["status"],
        "archivedAt": session["archived_at"],
        "turns": [_camel_turn(turn) for turn in session["turns"]],
        "topics": [
            {
                "id": topic["id"],
                "gap": topic["gap"],
                "whyItMatters": topic["why_it_matters"],
                "relatedRef": topic["related_ref"],
                "ownerId": topic.get("owner_id", ""),
                "status": topic["status"],
                "noteDocId": topic["note_doc_id"],
            }
            for topic in session["topics"]
        ],
        "draftNotes": [
            {
                "topicId": draft["topic_id"],
                "title": draft["title"],
                "summary": draft["summary"],
                "quotes": draft["quotes"],
                "status": draft["status"],
            }
            for draft in session["draft_notes"]
        ],
        "changeDrafts": [
            {
                "id": draft["id"],
                "title": draft["title"],
                "revision": draft["revision"],
                "status": draft["status"],
                "previews": draft["previews"],
                "quotes": list(
                    dict.fromkeys(
                        quote
                        for record in draft["changes"]
                        for quote in record["change"]["quotes"]
                    )
                ),
            }
            for draft in session.get("change_drafts", [])
        ],
        "recap": (
            user_visible_prose(session["recap"])
            if session["recap"] is not None
            else None
        ),
        "impact": session["impact"],
    }


def sessions_view(
    profile_dir: Path | str,
    *,
    include_archived: bool = False,
    status: str | None = None,
) -> dict:
    rows = list_sessions(profile_dir, include_archived=include_archived)
    if status is not None:
        rows = [row for row in rows if row["status"] == status]
    return {
        "sessions": [
            {
                "sessionId": session["session_id"],
                "sessionTitle": session["session_title"],
                "startedAt": session["started_at"],
                "endedAt": session["ended_at"],
                "status": session["status"],
                "archivedAt": session["archived_at"],
                "topicCount": len(session["topics"]),
                "savedNoteCount": sum(
                    draft["status"] == "saved" for draft in session["draft_notes"]
                ),
            }
            for session in rows
        ]
    }


def _overview(profile_dir: Path, engine) -> str:
    if engine is None:
        return profile_overview(profile_dir)
    from resume_tailor_harness.db import get_session

    with get_session(engine) as database_session:
        return profile_overview(profile_dir, database_session)


def _agents(
    profile_dir: Path, coach_agent, formatter_agent, schema, *, user_text: str = ""
):
    return (
        coach_agent
        or build_coach_agent(
            [
                *make_corpus_tools(profile_dir),
                *make_profile_tools(profile_dir, user_text=user_text),
            ]
        ),
        formatter_agent or build_coach_formatter_agent(schema),
    )


def run_opening_turn(
    reporter,
    *,
    profile_dir: Path,
    engine=None,
    coach_agent: Runner | None = None,
    formatter_agent: Runner | None = None,
    sink: StreamSink | None = None,
) -> dict:
    root = Path(profile_dir)
    reporter.begin(1, "Reviewing your profile")
    coach, formatter = _agents(root, coach_agent, formatter_agent, OpeningTurn)
    facts_path = root / "facts.json"
    seeded = (
        depth_topics(load_facts(facts_path), cap=AGENDA_CAP)
        if facts_path.exists()
        else []
    )
    seeded_context = (
        "SEEDED DEPTH AGENDA (deterministic; already included in the session):\n"
        + "\n".join(
            f"- {topic.id} [{topic.owner_id}] {topic.gap} — {topic.why_it_matters}"
            for topic in seeded
        )
        + "\nDo not repeat these in model-proposed topics. You may add only new, "
        "bounded topics after them, and may ask about a seeded topic by id."
        if seeded
        else ""
    )
    prompt = (
        f"{_overview(root, engine)}\n\n"
        f"{seeded_context}\n\n"
        "This is the opening turn. Propose the highest-value bounded agenda and ask the first question."
    )
    output_sink = sink or NullSink()
    prose, notes = persona_output(
        coach, prompt, output_sink, reporter, source="coach notes"
    )
    topics, validated = format_with_retry(
        formatter,
        notes,
        OpeningTurn,
        partial(normalize_opening, seeded=seeded),
        label="COACH NOTES",
    )
    validated.coach_turn = validated.coach_turn.model_copy(
        update={
            "text": user_visible_prose(prose or validated.coach_turn.text),
            "agent_meta": getattr(coach, "run_meta", None),
        }
    )
    reporter.step(1)
    session_id = uuid.uuid4().hex
    create_session(root, session_id, topics, validated.coach_turn)
    return session_view(root, session_id)


def run_message_turn(
    reporter,
    *,
    profile_dir: Path,
    session_id: str,
    message: str,
    engine=None,
    coach_agent: Runner | None = None,
    formatter_agent: Runner | None = None,
    sink: StreamSink | None = None,
) -> dict:
    root = Path(profile_dir)
    text = message.strip()
    if not text:
        raise ValueError("message is empty")
    if len(text) > _MAX_MESSAGE_CHARS:
        raise ValueError("message is too large")
    session = load_session(root, session_id)
    if session["status"] != "active":
        raise ValueError("session ended")
    reporter.begin(1, "Preparing a response")
    coach, formatter = _agents(
        root, coach_agent, formatter_agent, CoachTurn, user_text=text
    )
    prompt = "\n\n".join(
        [
            _overview(root, engine),
            render_transcript(session),
            render_agenda(session),
            _change_context(session),
            f"USER'S LATEST MESSAGE (UNTRUSTED):\n{text}",
        ]
    )
    output_sink = sink or NullSink()
    prose, notes = persona_output(
        coach, prompt, output_sink, reporter, source="coach notes"
    )
    preview = {
        **session,
        "turns": [
            *session["turns"],
            {
                "role": "user",
                "kind": "",
                "text": text,
                "topic_id": "",
                "at": "",
                "research_actions": [],
            },
        ],
    }

    def validate(turn: CoachTurn, strict: bool) -> ValidatedTurn:
        validated = normalize_turn(turn, preview, strict=strict)
        if validated.profile_changes is not None:
            try:
                validated.change_draft = prepare_changes(
                    root,
                    validated.profile_changes,
                    text,
                    source_ref=f"coach:{session_id}:{len(session['turns'])}",
                )
            except ValueError as exc:
                raise DraftRejected(str(exc)) from exc
        return validated

    try:
        validated = format_with_retry(
            formatter,
            notes,
            CoachTurn,
            validate,
            label="COACH NOTES",
        )
    except (TurnRejected, UnparsedAgentOutput) as exc:
        fallback_text = prose or getattr(exc, "fallback_text", "")
        if not fallback_text:
            raise
        if isinstance(exc, UnparsedAgentOutput):
            logger.warning("Coach formatter returned unusable output: %s", exc)
        validated = _degraded_turn(session, fallback_text)
    validated.coach_turn = validated.coach_turn.model_copy(
        update={
            "text": user_visible_prose(prose or validated.coach_turn.text),
            "agent_meta": getattr(coach, "run_meta", None),
        }
    )
    reporter.step(1)
    apply_turn_delta(
        root,
        session_id,
        user_text=text,
        coach_turn=validated.coach_turn,
        new_topics=validated.new_topics,
        skipped_topic_ids=validated.skipped_topic_ids,
        draft=validated.draft,
        change_draft=validated.change_draft,
    )
    if validated.notice:
        output_sink.emit(Notice(validated.notice))
    return session_view(root, session_id)


def _degraded_turn(session: dict, prose: str) -> ValidatedTurn:
    open_ids = {topic["id"] for topic in session["topics"] if topic["status"] == "open"}
    topic_id = next(
        (
            turn["topic_id"]
            for turn in reversed(session["turns"])
            if turn["topic_id"] in open_ids
        ),
        next(
            (topic["id"] for topic in session["topics"] if topic["status"] == "open"),
            "",
        ),
    )
    notice = "Some turn details could not be read, so no note or profile changes were prepared."
    return ValidatedTurn(
        coach_turn=CoachTurnRecord(
            role="coach",
            kind="question",
            text=prose,
            topic_id=topic_id,
            notice=notice,
        ),
        notice=notice,
    )


def _primary_exists(profile_dir: Path) -> bool:
    return any(
        doc.primary and doc.mode == "literal" for doc in load_manifest(profile_dir).docs
    )


def _change_context(session: dict) -> str:
    return (
        "PROFILE CHANGE DRAFTS (host status; only applied drafts changed the profile):\n"
        + "\n".join(
            f"- {draft['id']} [{draft['status']}] {draft['title']}"
            for draft in session.get("change_drafts", [])[-20:]
        )
    )


def render_note_body(summary: str, quotes: list[str]) -> str:
    cleaned = [quote.strip() for quote in quotes if quote.strip()]
    if not summary.strip():
        raise ValueError("empty note")
    if not cleaned:
        raise ValueError("at least one quote is required")
    quoted = "\n>\n".join(
        "\n".join(f"> {line}" for line in quote.splitlines()) for quote in cleaned
    )
    return f"{summary.strip()}\n\n## In your own words\n\n{quoted}"


def approve_draft(
    profile_dir: Path | str,
    session_id: str,
    topic_id: str,
    *,
    title: str,
    summary: str,
    quotes: list[str],
) -> str:
    root = Path(profile_dir)
    body = render_note_body(summary, quotes)
    if not _primary_exists(root):
        raise ValueError("upload a primary resume before saving coach notes")
    with coach_lock():
        session = load_session(root, session_id)
        draft = next(
            (row for row in session["draft_notes"] if row["topic_id"] == topic_id),
            None,
        )
        if draft is None:
            raise ValueError(f"unknown draft: {topic_id}")
        if draft["status"] != "pending":
            raise ValueError("draft already resolved")
        topic = next((row for row in session["topics"] if row["id"] == topic_id), None)
        anchor = (topic or {}).get("owner_id") or None
        doc = add_note_source(
            root, f"Coach: {title.strip() or topic_id}", body, anchor=anchor
        )
        set_draft_status(root, session_id, topic_id, "saved", note_doc_id=doc.id)
        return doc.id


def discard_draft(profile_dir: Path | str, session_id: str, topic_id: str) -> None:
    set_draft_status(Path(profile_dir), session_id, topic_id, "discarded")


def run_recap_turn(
    reporter,
    *,
    profile_dir: Path,
    session_id: str,
    coach_agent: Runner | None = None,
    formatter_agent: Runner | None = None,
    sink: StreamSink | None = None,
) -> dict:
    root = Path(profile_dir)
    session = load_session(root, session_id)
    if session["status"] != "active":
        raise ValueError("session ended")
    # A session the user never answered has no evidence to recap; asking the LLM
    # to summarize an empty conversation yields an empty message that
    # normalize_recap rejects ("empty message"). Close it deterministically.
    if not any(turn["role"] == "user" for turn in session["turns"]):
        reporter.begin(1, "Closing your session")
        end_session(root, session_id, _EMPTY_SESSION_RECAP)
        reporter.step(1)
        return session_view(root, session_id)
    reporter.begin(1, "Writing your recap")
    coach, formatter = _agents(root, coach_agent, formatter_agent, CoachTurn)
    pending = [
        draft["title"]
        for draft in session["draft_notes"]
        if draft["status"] == "pending"
    ]
    prompt = "\n\n".join(
        [
            render_agenda(session),
            render_transcript(session),
            _change_context(session),
            "Write the session recap: topics covered, saved notes, open gaps, and one suggested next focus."
            + (f" Mention unsaved drafts: {', '.join(pending)}." if pending else ""),
        ]
    )
    output_sink = sink or NullSink()
    prose, notes = persona_output(
        coach, prompt, output_sink, reporter, source="coach notes"
    )
    notice = ""
    try:
        recap = format_with_retry(
            formatter,
            notes,
            CoachTurn,
            lambda turn, strict: normalize_recap(turn, session, strict),
            label="COACH NOTES",
        )
    except TurnRejected as exc:
        fallback_text = prose or exc.fallback_text
        if not fallback_text:
            raise
        recap = fallback_text
        notice = "Some recap details could not be read."
    if prose:
        recap = prose
    recap = user_visible_prose(recap)
    reporter.step(1)
    end_session(
        root,
        session_id,
        recap,
        notice=notice,
        agent_meta=getattr(coach, "run_meta", None),
    )
    if notice:
        output_sink.emit(Notice(notice))
    return session_view(root, session_id)


def run_build_with_impact(
    reporter,
    *,
    profile_dir: Path,
    session_id: str,
    facts_out,
    github_username: str | None,
    github_allow: tuple[str, ...] = (),
    github_deny: tuple[str, ...] = (),
    github_limit: int = 20,
    github_branches: dict[str, str] | None = None,
) -> dict:
    root = Path(profile_dir)
    before = profile_snapshot(root)
    try:
        raw_report = run_corpus_build(
            reporter,
            profile_dir=root,
            github_username=github_username,
            facts_out=facts_out,
            github_allow=github_allow,
            github_deny=github_deny,
            github_limit=github_limit,
            github_branches=github_branches,
        )
    except Exception as exc:
        set_impact(root, session_id, {"error": str(exc)})
        raise
    impact = snapshot_diff(before, profile_snapshot(root))
    set_impact(root, session_id, impact)
    return {**raw_report, "impact": impact}
