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
            f"the target is {target}. Shorten repeated wording or secondary details "
            "during revision, or choose the detailed two-page option."
        )


# A nearly full page uses at least 80% of the printable vertical area.
MIN_PAGE_FILL = 0.80
_VERTICAL_MARGIN_PT = 0.55 * 72


class PageBalanceError(PageFitError):
    """Two pages fit, but there is not enough content for a balanced export."""

    def __init__(self, fill: float):
        super().__init__(2, 2)
        self.args = (
            f"The shorter page fills only {fill:.0%} of the usable height after readable "
            "layout adjustment. Revise into one concise page, or add relevant verified "
            "experience, projects or optional sections for two nearly full pages.",
        )


def _page_fills(pdf: bytes) -> list[float]:
    fills = []
    for page in PdfReader(io.BytesIO(pdf)).pages:
        positions: list[tuple[float, float]] = []

        def collect(text, cm, tm, _font, size):
            if text.strip():
                # Typst glyphs use the current transformation matrix.
                y = float(tm[4] * cm[1] + tm[5] * cm[3] + cm[5])
                positions.append((y, float(size)))

        page.extract_text(visitor_text=collect)
        usable = float(page.mediabox.height) - 2 * _VERTICAL_MARGIN_PT
        fills.append(
            (max(y + size for y, size in positions) - min(y for y, _ in positions))
            / usable
            if positions
            else 0.0
        )
    return fills


def _last_page_fill(pdf: bytes) -> float:
    return _page_fills(pdf)[-1]


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
    """Fit with bounded compact/expanded probes, then atomically publish a PDF.

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
    if (
        not math.isfinite(content.layout_density)
        or not -1 <= content.layout_density <= 1
    ):
        raise ValueError("layout_density must be between -1 and 1")
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

    from resume_tailor_harness.render.templates import BUNDLED

    bundled = any(source == template.path.resolve() for template in BUNDLED.values())
    floor = max(min_zoom, 10 / 10.5)

    def compile_at(density: float, break_before: str = "") -> tuple[bytes, int]:
        zoom = 1 - density * ((1 - floor) if density >= 0 else (12 / 10.5 - 1))
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

    preferred_density = content.layout_density
    pdf, pages = compile_at(preferred_density)
    if fit_pages is not None and pages > fit_pages:
        pdf, pages = compile_at(1)
        if pages > fit_pages:
            raise PageFitError(pages, fit_pages)
        low, high = preferred_density, 1.0
        for _ in range(3):
            if high - low <= zoom_step:
                break
            middle = (low + high) / 2
            candidate, count = compile_at(middle)
            if count <= fit_pages:
                pdf, pages, high = candidate, count, middle
            else:
                low = middle

    if (
        bundled
        and fit_pages == 2
        and pages == 2
        and min(_page_fills(pdf)) < MIN_PAGE_FILL
    ):
        # A short spill belongs on one readable page when it can fit there.
        compact, count = compile_at(1)
        if count == 1:
            pdf, pages = compact, count
            low, high = preferred_density, 1.0
            for _ in range(3):
                middle = (low + high) / 2
                candidate, count = compile_at(middle)
                if count == 1:
                    pdf, high = candidate, middle
                else:
                    low = middle
        else:
            # Grow type and spacing together, stopping at 12pt. No forced break
            # can turn two half-empty pages into an acceptable two-page resume.
            best = pdf
            best_fill = min(_page_fills(pdf))
            low, high = 0.0, 1.0
            for expansion in (1.0, None, None, None, None, None):
                amount = expansion if expansion is not None else (low + high) / 2
                candidate, count = compile_at(-amount)
                fill = min(_page_fills(candidate)) if count == 2 else 0.0
                if count == 2 and fill > best_fill:
                    best, best_fill = candidate, fill
                if count > 2 or fill >= MIN_PAGE_FILL:
                    high = amount
                else:
                    low = amount
            if best_fill < MIN_PAGE_FILL:
                raise PageBalanceError(best_fill)
            pdf = best

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
