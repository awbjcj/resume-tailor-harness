"""Profile documents CRUD (+ profile build run, added in a later task)."""

from __future__ import annotations

import re
import tempfile
from urllib.parse import quote
from pathlib import Path
from typing import cast

import httpx
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from resume_tailor_harness.api.deps import (
    get_config_store,
    get_document_store,
    get_profile_dir,
    get_run_manager,
    get_settings_dep,
)
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.uploads import UploadTooLargeError, read_upload_async
from resume_tailor_harness.api.runs.launch import launch
from resume_tailor_harness.api.runs.manager import RunManager
from resume_tailor_harness.api.schemas.config import ProfileConfigDoc
from resume_tailor_harness.api.schemas.profile import (
    AddAliasIn,
    AddSkillIn,
    DocumentOut,
    ManualEntryOut,
    MatrixOut,
    MatrixRowOut,
    NoteIn,
    SetGroupIn,
    SkeletonEntryOut,
    SkillEntryOut,
    SourceOut,
    GithubRepositoryOut,
    SourcePatch,
    SkillGroupOut,
    SkillCategoryOut,
    SuppressedSkillOut,
    UrlIn,
)
from resume_tailor_harness.api.schemas.runs import RunOut
from resume_tailor_harness.llm_runner import model_access_available
from resume_tailor_harness.profile.corpus import (
    _UNSET,
    SourceMode,
    MANIFEST_NAME,
    add_source,
    doc_path,
    load_manifest,
    remove_source,
    replace_source,
    restore_github_sources,
    source_lock,
    update_source,
)
from resume_tailor_harness.profile.fragments import fragment_cache_status
from resume_tailor_harness.profile.github_harvest import sync_github_sources
from resume_tailor_harness.profile.intake import add_note_source, add_url_source
from resume_tailor_harness.profile.matrix import load_matrix
from resume_tailor_harness.profile.group_corrections import (
    load_group_corrections,
    corrections_path,
)
from resume_tailor_harness.profile.store import load_facts
from resume_tailor_harness.profile.synthesis import profile_skeleton
from resume_tailor_harness.services import (
    profile_build,
    profile_groups,
    profile_skills,
    profile_github,
)
from resume_tailor_harness.services.profile_documents import (
    DocumentError,
    DocumentStore,
)
from resume_tailor_harness.api.routers.profile_skills import (
    router as skill_library_router,
)

router = APIRouter()
router.include_router(skill_library_router)


def _docs(request: Request) -> DocumentStore:
    return get_document_store(request)


@router.get("/profile/documents", response_model=list[DocumentOut])
def list_documents(request: Request):
    return [DocumentOut.model_validate(rec) for rec in _docs(request).list()]


@router.post("/profile/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form(..., alias="docType"),
):
    try:
        content = await read_upload_async(file, max_bytes=_MAX_SOURCE_BYTES)
    except UploadTooLargeError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    try:
        record = _docs(request).add(file.filename or "upload", content, doc_type)
    except DocumentError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    return DocumentOut.model_validate(record)


@router.delete("/profile/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, request: Request):
    if not _docs(request).delete(doc_id):
        raise ApiException(404, "NOT_FOUND", f"No document '{doc_id}'")


@router.post("/profile/build", response_model=RunOut, status_code=202)
def launch_profile_build(request: Request, mgr: RunManager = Depends(get_run_manager)):
    from resume_tailor_harness.profile.conversation import can_rebuild_without_resume

    profile_dir = _profile_dir(request)
    conversation_only = can_rebuild_without_resume(profile_dir) and not any(
        doc.primary and doc.mode == "literal" for doc in load_manifest(profile_dir).docs
    )
    settings = get_settings_dep(request)
    if not conversation_only and not model_access_available(
        settings.mid_model, settings=settings
    ):
        raise ApiException(
            400,
            "SETUP_INCOMPLETE",
            "No funded LLM key is available. Add one in Settings > API Keys.",
        )
    return _launch_build(request, mgr)


def _launch_build(
    request: Request,
    mgr: RunManager,
    *,
    singleton_conflict: str = "join",
) -> RunOut:
    profile_dir = _profile_dir(request)
    from resume_tailor_harness.profile.conversation import can_rebuild_without_resume

    conversational = can_rebuild_without_resume(profile_dir)
    manifest = load_manifest(profile_dir)
    if not manifest.docs and not conversational:
        if (profile_dir / MANIFEST_NAME).exists():
            raise ApiException(
                400,
                "SETUP_INCOMPLETE",
                "Add a resume source before rebuilding the profile",
            )
        resume_path = _docs(request).latest_resume_path()
        if resume_path is None:
            raise ApiException(
                400,
                "SETUP_INCOMPLETE",
                "Upload a resume document before building the profile",
            )
        # One-time migration mirroring the CLI's migrate_legacy: the wizard's
        # newest resume becomes the corpus primary.
        add_source(profile_dir, resume_path, primary=True)
    elif not any(doc.primary for doc in manifest.docs) and not conversational:
        raise ApiException(
            400,
            "SETUP_INCOMPLETE",
            "Add a primary resume source before rebuilding the profile",
        )
    profile_cfg = cast(ProfileConfigDoc, get_config_store(request).get("profile"))
    github_username = profile_cfg.github_username
    facts_out = get_profile_dir(request) / "facts.json"

    def work(reporter):
        return profile_build.run_corpus_build(
            reporter,
            profile_dir=profile_dir,
            github_username=github_username,
            facts_out=facts_out,
            github_allow=tuple(profile_cfg.github_repo_allow),
            github_deny=tuple(profile_cfg.github_repo_deny),
            github_limit=profile_cfg.github_repo_limit,
            github_branches=profile_cfg.github_repo_branches,
        )

    return launch(
        mgr,
        "profile-build",
        work,
        singleton_key="profile-build",
        singleton_conflict=singleton_conflict,
    )


_MAX_SOURCE_BYTES = 15 * 1024 * 1024
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _profile_dir(request: Request) -> Path:
    return get_profile_dir(request)


def _source_out(profile_dir: Path, doc) -> SourceOut:
    return SourceOut(
        id=doc.id,
        filename=doc.filename,
        mode=doc.mode,
        primary=doc.primary,
        anchor=doc.anchor,
        added_at=doc.added_at,
        fragment_status=fragment_cache_status(profile_dir, doc),
        origin=doc.origin,
        file_exists=doc_path(profile_dir, doc).is_file(),
        repo_url=doc.repo_url,
        github_branch=doc.github_branch,
    )


@router.get("/profile/sources", response_model=list[SourceOut])
def list_sources(request: Request):
    profile_dir = _profile_dir(request)
    with source_lock(profile_dir):
        return [
            _source_out(profile_dir, doc) for doc in load_manifest(profile_dir).docs
        ]


@router.get("/profile/sources/github-exclusions", response_model=list[str])
def get_github_exclusions(request: Request):
    return load_manifest(_profile_dir(request)).excluded_github_sources


@router.delete("/profile/sources/github-exclusions", status_code=204)
def clear_github_exclusions(request: Request):
    restore_github_sources(_profile_dir(request))


@router.post("/profile/sources", response_model=SourceOut, status_code=201)
async def upload_source(
    request: Request,
    file: UploadFile = File(...),
    mode: SourceMode | None = Form(None),
    anchor: str | None = Form(None),
    primary: bool = Form(False),
):
    try:
        content = await read_upload_async(file, max_bytes=_MAX_SOURCE_BYTES)
    except UploadTooLargeError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    name = _UNSAFE_CHARS.sub("_", Path(file.filename or "upload").name) or "upload"
    profile_dir = _profile_dir(request)
    try:
        # add_source copies the staged file into sources/ under its original name.
        with tempfile.TemporaryDirectory() as scratch:
            staged = Path(scratch) / name
            staged.write_bytes(content)
            doc = add_source(
                profile_dir,
                staged,
                primary=primary,
                mode=mode,
                anchor=anchor,  # type: ignore[arg-type]
            )
    except ValueError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    return _source_out(profile_dir, doc)


@router.put("/profile/sources/{doc_id}/file", response_model=SourceOut)
async def replace_source_file(
    doc_id: str,
    request: Request,
    file: UploadFile = File(...),
):
    try:
        content = await read_upload_async(file, max_bytes=_MAX_SOURCE_BYTES)
        name = _UNSAFE_CHARS.sub("_", Path(file.filename or "upload").name) or "upload"
        profile_dir = _profile_dir(request)
        with tempfile.TemporaryDirectory() as scratch:
            staged = Path(scratch) / name
            staged.write_bytes(content)
            doc = replace_source(profile_dir, doc_id, staged)
    except (UploadTooLargeError, ValueError) as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    if doc is None:
        raise ApiException(404, "NOT_FOUND", f"No source '{doc_id}'")
    return _source_out(profile_dir, doc)


@router.get("/profile/sources/{doc_id}/file", response_class=Response)
def download_source_file(doc_id: str, request: Request):
    profile_dir = _profile_dir(request)
    with source_lock(profile_dir):
        doc = next((d for d in load_manifest(profile_dir).docs if d.id == doc_id), None)
        if doc is None:
            raise ApiException(404, "NOT_FOUND", f"No source '{doc_id}'")
        try:
            content = doc_path(profile_dir, doc).read_bytes()
        except (OSError, ValueError) as exc:
            raise ApiException(404, "NOT_FOUND", "Source file is unavailable") from exc
        return Response(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.filename, safe='')}",
                "X-Content-Type-Options": "nosniff",
            },
        )


@router.post("/profile/sources/note", response_model=SourceOut, status_code=201)
def add_note(payload: NoteIn, request: Request):
    profile_dir = _profile_dir(request)
    try:
        doc = add_note_source(profile_dir, payload.title, payload.text)
    except ValueError as error:
        raise ApiException(422, "VALIDATION_ERROR", str(error)) from error
    return _source_out(profile_dir, doc)


@router.post("/profile/sources/url", response_model=SourceOut, status_code=201)
def add_url(payload: UrlIn, request: Request):
    profile_dir = _profile_dir(request)
    try:
        doc = add_url_source(profile_dir, str(payload.url))
    except (httpx.HTTPError, ValueError) as error:
        raise ApiException(
            422, "VALIDATION_ERROR", f"URL intake failed: {error}"
        ) from error
    return _source_out(profile_dir, doc)


@router.post("/profile/sync-github", response_model=RunOut, status_code=202)
def launch_github_sync(
    request: Request,
    mgr: RunManager = Depends(get_run_manager),
):
    profile_config = cast(ProfileConfigDoc, get_config_store(request).get("profile"))
    github_username = profile_config.github_username
    if not github_username:
        raise ApiException(
            400,
            "SETUP_INCOMPLETE",
            "Set a GitHub username in Settings > Profile first",
        )
    profile_dir = _profile_dir(request)

    def work(_reporter):
        report = sync_github_sources(
            profile_dir,
            github_username,
            allow=tuple(profile_config.github_repo_allow),
            deny=tuple(profile_config.github_repo_deny),
            limit=profile_config.github_repo_limit,
            branches=profile_config.github_repo_branches,
        )
        return {
            "written": report.written,
            "removed": report.removed,
            "superseded": report.superseded,
            "failures": report.failures,
            "warnings": report.warnings,
        }

    return launch(mgr, "github-sync", work, singleton_key="github-sync")


@router.get("/profile/github/repositories", response_model=list[GithubRepositoryOut])
def get_github_repositories(request: Request):
    config = cast(ProfileConfigDoc, get_config_store(request).get("profile"))
    if not config.github_username:
        raise ApiException(
            400,
            "SETUP_INCOMPLETE",
            "Save a GitHub username before choosing repositories",
        )
    try:
        return profile_github.list_repositories(
            config.github_username,
            _profile_dir(request),
            allow=tuple(config.github_repo_allow),
            deny=tuple(config.github_repo_deny),
            limit=config.github_repo_limit,
            branches=config.github_repo_branches,
        )
    except (httpx.HTTPError, ValueError) as error:
        raise ApiException(
            422,
            "GITHUB_UNAVAILABLE",
            "Could not load repositories. Check the username and GitHub access, then retry.",
        ) from error


@router.get(
    "/profile/github/repositories/{owner}/{repo}/branches", response_model=list[str]
)
def get_github_branches(owner: str, repo: str):
    try:
        return profile_github.list_branches(owner, repo)
    except (httpx.HTTPError, ValueError) as error:
        raise ApiException(
            422,
            "GITHUB_UNAVAILABLE",
            "Could not load branches. Check repository access, then retry.",
        ) from error


@router.get("/profile/matrix", response_model=MatrixOut)
def get_profile_matrix(request: Request):
    matrix = load_matrix(_profile_dir(request) / "matrix.json")
    organization = load_group_corrections(corrections_path(_profile_dir(request)))
    return MatrixOut(
        generated_at=matrix.generated_at if matrix is not None else "",
        groups=[
            SkillGroupOut(
                slug=slug,
                label=group.label,
                category=group.category,
                customized=group.custom_label,
            )
            for slug, group in organization.group_catalog().items()
        ],
        categories=[
            SkillCategoryOut(
                slug=slug,
                label=category.label,
                customized=slug in organization.categories,
            )
            for slug, category in organization.category_catalog().items()
        ],
        rows=[MatrixRowOut.model_validate(row) for row in matrix.rows]
        if matrix is not None
        else [],
    )


@router.patch("/profile/sources/{doc_id}", response_model=SourceOut)
def patch_source(doc_id: str, payload: SourcePatch, request: Request):
    profile_dir = _profile_dir(request)
    anchor = payload.anchor if "anchor" in payload.model_fields_set else _UNSET
    try:
        doc = update_source(
            profile_dir,
            doc_id,
            mode=payload.mode,  # type: ignore[arg-type]
            anchor=anchor,
            primary=payload.primary,
        )
    except ValueError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    if doc is None:
        raise ApiException(404, "NOT_FOUND", f"No source '{doc_id}'")
    return _source_out(profile_dir, doc)


@router.delete("/profile/sources/{doc_id}", status_code=204)
def delete_source(doc_id: str, request: Request, purge: bool = False):
    try:
        doc = remove_source(
            _profile_dir(request), doc_id, purge=purge, exclude_github=True
        )
    except ValueError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    if doc is None:
        raise ApiException(404, "NOT_FOUND", f"No source '{doc_id}'")


def _manual_entry_out(entry) -> ManualEntryOut:
    if entry.kind == "new_skill":
        return ManualEntryOut(
            id=entry.id,
            kind=entry.kind,
            added_at=entry.added_at,
            name=entry.name,
            category=entry.category,
        )
    return ManualEntryOut(
        id=entry.id,
        kind=entry.kind,
        added_at=entry.added_at,
        alias_text=entry.alias_text,
        target_skill_display=entry.target_skill_display,
    )


@router.get("/profile/skills", response_model=list[SkillEntryOut])
def get_profile_skills(request: Request):
    try:
        facts = profile_skills._load_facts_or_raise(_profile_dir(request))
    except profile_skills.ProfileNotBuiltError:
        return []
    return [
        SkillEntryOut.model_validate(skill)
        for skills in facts.skills.values()
        for skill in skills
    ]


@router.post("/profile/skills", response_model=ManualEntryOut, status_code=201)
def post_profile_skill(payload: AddSkillIn, request: Request):
    try:
        entry = profile_skills.add_skill(
            _profile_dir(request),
            payload.name,
            payload.category,
            aliases=payload.aliases,
            group=payload.group,
        )
    except profile_skills.ProfileNotBuiltError as exc:
        raise ApiException(400, "SETUP_INCOMPLETE", str(exc)) from exc
    except ValueError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    return _manual_entry_out(entry)


@router.post(
    "/profile/skills/{skill_id}/aliases", response_model=ManualEntryOut, status_code=201
)
def post_profile_skill_alias(skill_id: str, payload: AddAliasIn, request: Request):
    try:
        entry = profile_skills.add_alias(_profile_dir(request), skill_id, payload.alias)
    except profile_skills.ProfileNotBuiltError as exc:
        raise ApiException(400, "SETUP_INCOMPLETE", str(exc)) from exc
    except profile_skills.SkillNotFoundError as exc:
        raise ApiException(404, "NOT_FOUND", str(exc)) from exc
    except profile_skills.SkillAlreadyExistsError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    return _manual_entry_out(entry)


@router.delete("/profile/skills/{key}", status_code=204)
def delete_profile_skill(key: str, request: Request):
    try:
        profile_skills.delete_skill(_profile_dir(request), key)
    except profile_skills.ProfileNotBuiltError as exc:
        raise ApiException(400, "SETUP_INCOMPLETE", str(exc)) from exc
    except profile_skills.SkillNotFoundError as exc:
        raise ApiException(404, "NOT_FOUND", str(exc)) from exc


@router.get("/profile/suppressed-skills", response_model=list[SuppressedSkillOut])
def get_suppressed_skills(request: Request):
    return [
        SuppressedSkillOut(
            token=e.token, display=e.display, added_at=e.added_at, reason=e.reason
        )
        for e in profile_skills.list_suppressed(_profile_dir(request))
    ]


@router.post("/profile/suppressed-skills/{token}/restore", status_code=204)
def restore_suppressed_skill(token: str, request: Request):
    try:
        profile_skills.restore_skill(_profile_dir(request), token)
    except profile_skills.ProfileNotBuiltError as exc:
        raise ApiException(400, "SETUP_INCOMPLETE", str(exc)) from exc
    except profile_skills.SuppressedSkillNotFoundError as exc:
        raise ApiException(404, "NOT_FOUND", str(exc)) from exc


@router.put("/profile/skills/{key}/group", response_model=MatrixRowOut)
def put_skill_group(key: str, payload: SetGroupIn, request: Request):
    try:
        row = profile_groups.set_group(_profile_dir(request), key, payload.group)
    except profile_groups.UnknownGroupError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    except profile_skills.ProfileNotBuiltError as exc:
        raise ApiException(400, "SETUP_INCOMPLETE", str(exc)) from exc
    except profile_skills.SkillNotFoundError as exc:
        raise ApiException(404, "NOT_FOUND", str(exc)) from exc
    return MatrixRowOut.model_validate(row)


@router.delete("/profile/skills/{key}/group", status_code=204)
def delete_skill_group(key: str, request: Request):
    try:
        profile_groups.clear_group(_profile_dir(request), key)
    except profile_skills.ProfileNotBuiltError as exc:
        raise ApiException(400, "SETUP_INCOMPLETE", str(exc)) from exc
    except (
        profile_groups.GroupCorrectionNotFoundError,
        profile_skills.SkillNotFoundError,
    ) as exc:
        raise ApiException(404, "NOT_FOUND", str(exc)) from exc


@router.get("/profile/skeleton", response_model=list[SkeletonEntryOut])
def get_skeleton(request: Request):
    facts_path = _profile_dir(request) / "facts.json"
    if not facts_path.exists():
        return []
    facts = load_facts(facts_path)
    rows: list[SkeletonEntryOut] = []
    for row in profile_skeleton(facts):
        label = (
            f"{row['company']}: {row['title']}"
            if row["kind"] == "experience"
            else row["name"]
        )
        rows.append(SkeletonEntryOut(id=row["id"], kind=row["kind"], label=label))
    return rows
