"""Guidance is layered beneath base rules and saved safely."""

from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

from resume_tailor_harness.prompts.guidance import (
    GUIDANCE_HEADER,
    MAX_GUIDANCE_CHARS,
    guidance_for,
    load_guidance,
    save_guidance,
    with_guidance,
)
from resume_tailor_harness.prompts.quality import with_quality


def _write(tmp_path, data) -> None:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "agent_guidance.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def test_missing_file_keeps_application_quality(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_guidance() == {}
    assert guidance_for("fit-score") is None
    assert with_guidance("fit-score", ["a", "b"]) == with_quality(
        "fit-score", ["a", "b"]
    )
    assert with_guidance("unregistered", ["a", "b"]) == ["a", "b"]


def test_guidance_appends_beneath_base(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, {"fit-score": "Prefer startup-scale evidence."})
    assert with_guidance("fit-score", ["a", "b"]) == [
        *with_quality("fit-score", ["a", "b"]),
        GUIDANCE_HEADER,
        "Prefer startup-scale evidence.",
    ]


def test_fact_check_procedure_guidance_is_loaded_saved_and_cleared(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    key = "reviewer-fact-check"
    _write(tmp_path, {key: "Check metrics first."})
    assert guidance_for(key) == "Check metrics first."
    assert with_guidance(key, ["Require supporting evidence."]) == [
        "Require supporting evidence.",
        GUIDANCE_HEADER,
        "Check metrics first.",
    ]
    save_guidance(key, "Explain each evidence mismatch.")
    assert guidance_for(key) == "Explain each evidence mismatch."
    save_guidance(key, "")
    assert with_guidance(key, ["Require supporting evidence."]) == [
        "Require supporting evidence."
    ]


def test_save_round_trip_clear_and_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert save_guidance("coach", " Ask about open source. ") == {
        "coach": "Ask about open source."
    }
    assert guidance_for("coach") == "Ask about open source."
    assert save_guidance("coach", "") == {}
    with pytest.raises(ValueError, match="4,000"):
        save_guidance("coach", "x" * (MAX_GUIDANCE_CHARS + 1))


def test_invalid_yaml_shape_and_entries_are_dropped(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path,
        {
            "blank": " ",
            "number": 3,
            "oversized": "x" * (MAX_GUIDANCE_CHARS + 1),
            "ok": " keep ",
        },
    )
    assert load_guidance() == {"ok": "keep"}
    (tmp_path / "config" / "agent_guidance.yaml").write_text("- nope\n")
    assert load_guidance() == {}


def test_concurrent_saves_preserve_distinct_agents(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    entries = {f"agent-{index}": f"guidance-{index}" for index in range(12)}
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda item: save_guidance(*item), entries.items()))
    assert load_guidance() == entries
    assert list((tmp_path / "config").glob("*.tmp")) == []
