import re
import json
import io
import math
import os
import tempfile
from pathlib import Path

import typst
from pypdf import PdfReader

from resume_tailor_harness.models.resume import ResumeContent

_FONT_DIRECTORY = Path(__file__).resolve().parents[3] / "templates" / "fonts"


def _slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text.lower())).strip("_")


def output_filename(
    company: str, title: str, date_str: str, qualifier: str | int | None = None
) -> str:
    """Build a slugged PDF filename.

    ``qualifier`` is optional so callers that need stable unique names can avoid
    overwriting another render for the same company/title/date.
    """
    parts = [_slug(company) or "company", _slug(title) or "role", date_str]
    if qualifier is not None:
        qualifier_slug = _slug(str(qualifier))
        if qualifier_slug:
            parts.append(qualifier_slug)
    return f"{'_'.join(parts)}.pdf"


class PageFitError(ValueError):
    """Content cannot fit the requested length at a readable size."""

    def __init__(self, pages: int, target: int):
        self.pages = pages
        self.target = target
        super().__init__(
            f"Resume needs {pages} pages at the readable layout limit; "
            f"the target is {target}. Shorten the draft (remove the summary first, "
            "then secondary details) or choose the detailed two-page option."
        )


def _last_page_fill(pdf: bytes) -> float:
    page = PdfReader(io.BytesIO(pdf)).pages[-1]
    positions: list[float] = []

    def collect(text, cm, tm, _font, _size):
        if text.strip():
            # Typst places glyphs through the current transformation matrix;
            # its text matrix often has a zero translation for every span.
            positions.append(float(tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

    page.extract_text(visitor_text=collect)
    return (
        (max(positions) - min(positions)) / float(page.mediabox.height)
        if positions
        else 0
    )


def _balanced_break(content: ResumeContent, style: str) -> str | None:
    """Choose an entry/section boundary near half the estimated text height."""
    defaults = [
        "summary",
        "experience",
        "projects",
        "skills",
        "education",
        "publications",
        "certifications",
        "awards",
        "languages",
        "volunteer",
    ]
    preferred = {
        "graduate": ["education", "experience", "projects", "skills"],
        "academic": ["education", "publications", "experience", "projects", "skills"],
        "modern": ["summary", "skills", "experience", "projects", "education"],
    }.get(style, defaults)
    order = list(dict.fromkeys([*(content.section_order or preferred), *defaults]))
    blocks: list[tuple[str, float]] = []
    for section in order:
        value = getattr(content, section, None)
        if not value:
            continue
        if section in {"experience", "projects"}:
            for index, entry in enumerate(value):
                lines = 3 + sum(
                    max(1, math.ceil(len(b.text) / 95)) for b in entry.bullets
                )
                lines += math.ceil(len(getattr(entry, "description", None) or "") / 95)
                blocks.append((section if index == 0 else f"{section}:{index}", lines))
        else:
            lines = 2 + math.ceil(len(json.dumps(value, default=str)) / 100)
            blocks.append((section, lines))
    total = sum(weight for _, weight in blocks)
    used = 0
    candidates: list[tuple[float, str]] = []
    for key, weight in blocks:
        if used:
            candidates.append((abs(used - total / 2), key))
        used += weight
    return min(candidates)[1] if candidates else None


def render_pdf(
    content: ResumeContent,
    output_path: str | Path,
    template_path: str | Path = "templates/resume.typ",
    *,
    fit_pages: int | None = 1,
    min_zoom: float = 10 / 10.5,
    zoom_step: float = 0.03,
    root: str | Path | None = None,
    highlight_terms: list[str] | None = None,
) -> Path:
    """Fit with at most five probes, then atomically publish a validated PDF.

    Bundled templates tighten whitespace and clamp body type to 10pt. Custom
    templates retain the zoom input. No resume text is cut during rendering.
    An impossible fit raises before replacing an existing artifact. ``None``
    remains the Python escape hatch for an unconstrained, full-size document.
    """
    if fit_pages is not None and fit_pages not in (1, 2):
        raise ValueError("fit_pages must be 1, 2, or None")
    if not math.isfinite(min_zoom) or not 0 < min_zoom <= 1:
        raise ValueError("min_zoom must be between 0 and 1")
    if not math.isfinite(zoom_step) or not 0 < zoom_step <= 1:
        raise ValueError("zoom_step must be between 0 and 1")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = content.model_dump_json()
    source = Path(template_path).resolve()
    resolved_root = Path(root).resolve() if root is not None else source.parent
    # A fresh compiler belongs to this render/tenant; its font and source cache
    # is reused across probes without sharing candidate data between requests.
    compiler = typst.Compiler(
        str(source), root=str(resolved_root), font_paths=[str(_FONT_DIRECTORY)]
    )

    floor = max(min_zoom, 10 / 10.5)

    def compile_at(density: float, break_before: str = "") -> tuple[bytes, int]:
        zoom = 1 - density * (1 - floor)
        sys_inputs = {
            "data": data,
            "zoom": f"{zoom:.6f}",
            "density": f"{density:.4f}",
            "break_before": break_before,
        }
        if highlight_terms is not None:
            sys_inputs["highlight_terms"] = json.dumps(highlight_terms)
        result = compiler.compile(
            sys_inputs=sys_inputs,
        )
        assert isinstance(result, bytes)
        return result, len(PdfReader(io.BytesIO(result)).pages)

    pdf, pages = compile_at(0)
    density = 0.0
    if fit_pages is not None and pages > fit_pages:
        pdf, pages = compile_at(1)
        if pages > fit_pages:
            raise PageFitError(pages, fit_pages)
        low, high = 0.0, 1.0
        density = 1.0
        for _ in range(3):
            if high - low <= zoom_step:
                break
            middle = (low + high) / 2
            candidate, count = compile_at(middle)
            if count <= fit_pages:
                pdf, pages, density, high = candidate, count, middle, middle
            else:
                low = middle

    # Move a meaningful entry to page two when a natural break leaves a sliver.
    # A balance probe is accepted only if it still fits and improves the tail.
    if fit_pages == 2 and pages == 2 and _last_page_fill(pdf) < 0.35:
        boundary = _balanced_break(content, source.stem)
        if boundary:
            balanced, count = compile_at(density, boundary)
            if count == 2 and _last_page_fill(balanced) > _last_page_fill(pdf):
                pdf = balanced

    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=out.parent, suffix=".pdf", delete=False
        ) as stream:
            temporary = stream.name
            stream.write(pdf)
        os.replace(temporary, out)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return out
