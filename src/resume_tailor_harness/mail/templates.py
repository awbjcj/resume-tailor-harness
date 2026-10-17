from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from resume_tailor_harness.mail.localization import (
    detail_value,
    normalize_language,
    translate,
)


_environment = Environment(
    loader=PackageLoader("resume_tailor_harness.mail", "templates"),
    autoescape=select_autoescape(("html",)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_email(
    template: str, *, language: str = "en", **context: object
) -> tuple[str, str]:
    """Return plain text and escaped HTML from deployment-owned templates."""
    context.update(
        language=normalize_language(language),
        tr=lambda text: translate(text, language),
        detail_value=lambda label, value: detail_value(label, value, language),
    )
    return (
        _environment.get_template(f"{template}.txt").render(**context),
        _environment.get_template(f"{template}.html").render(**context),
    )
