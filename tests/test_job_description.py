import pytest

from resume_tailor_harness.job_description import (
    clean_job_description_text,
    job_description_preview,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", ""),
        ("  Plain description  ", "Plain description"),
        ("_work_ Python, _unknown_ skill", "Python, _unknown_ skill"),
        (r"\_business\_center\_ Acme", "Acme"),
        ("keep_work_ _work_: _work_;", "keep_work_ _work_: _work_;"),
        ("_work_, _place_.", ",."),
        ("**Bold** and _italic_", "**Bold** and _italic_"),
        (r"\*\*_work_\*\*", "_work_"),
        ("\u2003a\u2028b\u2003\n\n\n c \t ;", "a\nb\n\nc;"),
        ("_not_an_icon_ " * 1000, ("_not_an_icon_ " * 1000).strip()),
    ],
)
def test_normalization_preserves_established_output(source, expected):
    assert clean_job_description_text(source) == expected


def test_preview_resolves_distant_markup_and_leading_removable_content():
    text = ("_work_ " * 1000) + r"\*\*" + ("x" * 1000) + r"\*\*"
    assert job_description_preview(text) == "x" * 400


def test_cleanup_order_remains_non_idempotent_for_escaped_markup():
    first = clean_job_description_text(r"\*\*_work_\*\*")
    assert first == "_work_"
    assert clean_job_description_text(first) == ""
