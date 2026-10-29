"""Resolve public template identifiers to trusted filesystem paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from resume_tailor_harness.security.paths import confined_path
from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.tenancy.paths import resolve_tenant_path


CUSTOM_TEMPLATES_DIR = "config/templates"
_CUSTOM_STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class TemplateInfo:
    id: str
    title: str
    description: str
    kind: str
    path: Path


BUNDLED = {
    "classic": TemplateInfo(
        id="classic",
        title="Classic",
        description="Traditional serif layout for general applications and conservative industries.",
        kind="bundled",
        path=_REPOSITORY_ROOT / "templates" / "resume.typ",
    ),
    "modern": TemplateInfo(
        id="modern",
        title="Modern",
        kind="bundled",
        description="Clean sans-serif type and blue accents for product, business, and technology roles.",
        path=_REPOSITORY_ROOT / "templates" / "modern.typ",
    ),
    "technical": TemplateInfo(
        id="technical",
        title="Technical",
        kind="bundled",
        description="Experience and projects lead a precise engineering-focused layout.",
        path=_REPOSITORY_ROOT / "templates" / "technical.typ",
    ),
    "executive": TemplateInfo(
        id="executive",
        title="Executive",
        kind="bundled",
        description="Restrained navy headings and strong role hierarchy for senior professionals.",
        path=_REPOSITORY_ROOT / "templates" / "executive.typ",
    ),
    "graduate": TemplateInfo(
        id="graduate",
        title="Graduate",
        kind="bundled",
        description="Education-first serif layout for students, internships, and early careers.",
        path=_REPOSITORY_ROOT / "templates" / "graduate.typ",
    ),
    "academic": TemplateInfo(
        id="academic",
        title="Academic",
        kind="bundled",
        description="Research-oriented typography with education and publications placed prominently.",
        path=_REPOSITORY_ROOT / "templates" / "academic.typ",
    ),
    "minimal": TemplateInfo(
        id="minimal",
        title="Minimal",
        kind="bundled",
        description="Quiet monochrome styling with generous whitespace for a simple professional resume.",
        path=_REPOSITORY_ROOT / "templates" / "minimal.typ",
    ),
    "compact": TemplateInfo(
        id="compact",
        title="Compact",
        kind="bundled",
        description="Space-efficient headings and entries for a concise resume with substantial project work.",
        path=_REPOSITORY_ROOT / "templates" / "compact.typ",
    ),
}


class TemplateNotFoundError(ValueError):
    """The public template id does not resolve to an available template."""


def validate_custom_stem(stem: str) -> str:
    if not _CUSTOM_STEM.fullmatch(stem):
        raise TemplateNotFoundError(
            "Custom template names may contain letters, digits, hyphens, and underscores."
        )
    return stem


def custom_template_path(stem: str) -> Path:
    safe_stem = validate_custom_stem(stem)
    directory = resolve_tenant_path(CUSTOM_TEMPLATES_DIR).resolve()
    try:
        return confined_path(directory, f"{safe_stem}.typ")
    except ValueError as exc:
        raise TemplateNotFoundError(
            "Custom template path escapes the workspace."
        ) from exc


def _custom_info(stem: str, path: Path) -> TemplateInfo:
    return TemplateInfo(
        id=f"custom:{stem}",
        title=stem,
        description="Uploaded template",
        kind="custom",
        path=path,
    )


def resolve_template(template_id: str) -> TemplateInfo:
    bundled = BUNDLED.get(template_id)
    if bundled is not None:
        return bundled
    if template_id.startswith("custom:"):
        stem = template_id.removeprefix("custom:")
        path = custom_template_path(stem)
        if path.is_file():
            return _custom_info(stem, path)
    raise TemplateNotFoundError(
        f"Template {template_id!r} does not exist. Pick a bundled template or "
        "re-upload the custom file."
    )


def list_templates() -> list[TemplateInfo]:
    directory = resolve_tenant_path(CUSTOM_TEMPLATES_DIR)
    custom_paths = sorted(directory.glob("*.typ"), key=lambda path: path.stem)
    custom = [
        _custom_info(path.stem, path)
        for path in custom_paths
        if _CUSTOM_STEM.fullmatch(path.stem)
    ]
    return [*BUNDLED.values(), *custom]


def template_path_for(config) -> Path:
    """Resolve new template ids while retaining the legacy CLI path escape hatch."""
    if config.template:
        return resolve_template(config.template).path
    if config.template_path:
        if current_context() is not None:
            if Path(config.template_path).as_posix() == "templates/resume.typ":
                return resolve_template("classic").path
            raise TemplateNotFoundError(
                "Legacy template paths are disabled in multi-user mode; use a template id."
            )
        return Path(config.template_path)
    return resolve_template("classic").path
