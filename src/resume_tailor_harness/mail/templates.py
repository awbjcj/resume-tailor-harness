from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape


_environment = Environment(
    loader=PackageLoader("resume_tailor_harness.mail", "templates"),
    autoescape=select_autoescape(("html",)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_email(template: str, **context: object) -> tuple[str, str]:
    """Return plain text and escaped HTML from deployment-owned templates."""
    return (
        _environment.get_template(f"{template}.txt").render(**context),
        _environment.get_template(f"{template}.html").render(**context),
    )
