"""Adapters for profile skill editing, cleanup, organization and rebuild runs."""

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Request

from resume_tailor_harness.api.deps import (
    get_profile_dir,
    get_run_manager,
    get_settings_dep,
)
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.runs.launch import launch
from resume_tailor_harness.api.runs.manager import RunManager
from resume_tailor_harness.api.schemas.profile import (
    MergeProfileSkillsIn,
    RebuildProfileSkillsIn,
    SkillCleanupOut,
    SkillCleanupPolicyIn,
    SkillOrganizationIn,
    UpdateProfileSkillIn,
)
from resume_tailor_harness.api.schemas.runs import RunOut
from resume_tailor_harness.llm_runner import model_access_available
from resume_tailor_harness.services import profile_groups, profile_skills
from resume_tailor_harness.services.profile_skill_build import rebuild_profile_skills

router = APIRouter()


@contextmanager
def _errors():
    try:
        yield
    except profile_skills.ProfileNotBuiltError as exc:
        raise ApiException(400, "SETUP_INCOMPLETE", str(exc)) from exc
    except (profile_skills.SkillNotFoundError, profile_groups.UnknownGroupError) as exc:
        raise ApiException(404, "NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc


@router.put("/profile/skills/{key}", status_code=204)
def update_skill(key: str, body: UpdateProfileSkillIn, request: Request):
    with _errors():
        profile_skills.update_skill(
            get_profile_dir(request),
            key,
            body.name,
            body.aliases,
            body.category,
            group=body.group,
        )


@router.post("/profile/skills/merge", status_code=204)
def merge_skills(body: MergeProfileSkillsIn, request: Request):
    with _errors():
        profile_skills.merge_skills(get_profile_dir(request), body.keys, body.into)


@router.get("/profile/skills/cleanup", response_model=SkillCleanupOut)
def preview_cleanup(request: Request):
    with _errors():
        return SkillCleanupOut.model_validate(
            profile_skills.cleanup_skills(get_profile_dir(request))
        )


@router.post("/profile/skills/cleanup", response_model=SkillCleanupOut)
def cleanup_skills(request: Request):
    with _errors():
        return SkillCleanupOut.model_validate(
            profile_skills.cleanup_skills(get_profile_dir(request), apply=True)
        )


@router.patch("/profile/skills/cleanup", status_code=204)
def cleanup_policy(body: SkillCleanupPolicyIn, request: Request):
    with _errors():
        profile_skills.set_cleanup_policy(get_profile_dir(request), body.enabled)


@router.post("/profile/skills/rebuild", response_model=RunOut, status_code=202)
def rebuild_skills(
    body: RebuildProfileSkillsIn,
    request: Request,
    mgr: RunManager = Depends(get_run_manager),
):
    directory = get_profile_dir(request)
    with _errors():
        profile_skills._load_facts_or_raise(directory)
    settings = get_settings_dep(request)
    models = (
        [settings.cheap_model]
        if body.reclassify_only
        else [settings.cheap_model, settings.mid_model]
    )
    if not all(model_access_available(model, settings=settings) for model in models):
        raise ApiException(
            400,
            "SETUP_INCOMPLETE",
            "Add a funded model key in Settings > API Keys before rebuilding skills.",
        )
    return launch(
        mgr,
        "profile-skills-rebuild",
        lambda reporter: rebuild_profile_skills(
            directory, reporter, reclassify_only=body.reclassify_only
        ),
        singleton_key="profile-build",
        singleton_conflict="raise",
    )


@router.post("/profile/skill-groups", status_code=201)
def create_group(body: SkillOrganizationIn, request: Request):
    with _errors():
        profile_groups.edit_organization(
            get_profile_dir(request), "group", label=body.label, category=body.category
        )
    return {"ok": True}


@router.put("/profile/skill-groups/{key}", status_code=204)
def update_group(key: str, body: SkillOrganizationIn, request: Request):
    with _errors():
        profile_groups.edit_organization(
            get_profile_dir(request),
            "group",
            key=key,
            label=body.label,
            category=body.category,
        )


@router.delete("/profile/skill-groups/{key}", status_code=204)
def delete_group(key: str, request: Request):
    with _errors():
        profile_groups.edit_organization(
            get_profile_dir(request), "group", key=key, delete=True
        )


@router.post("/profile/skill-categories", status_code=201)
def create_category(body: SkillOrganizationIn, request: Request):
    with _errors():
        profile_groups.edit_organization(
            get_profile_dir(request), "category", label=body.label
        )
    return {"ok": True}


@router.put("/profile/skill-categories/{key}", status_code=204)
def update_category(key: str, body: SkillOrganizationIn, request: Request):
    with _errors():
        profile_groups.edit_organization(
            get_profile_dir(request), "category", key=key, label=body.label
        )


@router.delete("/profile/skill-categories/{key}", status_code=204)
def delete_category(key: str, request: Request):
    with _errors():
        profile_groups.edit_organization(
            get_profile_dir(request), "category", key=key, delete=True
        )
