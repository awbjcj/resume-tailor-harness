import json
from pathlib import Path

from resume_tailor_harness.prompts.registry import PROMPT_SPECS


def test_chinese_labels_cover_built_in_agent_metadata() -> None:
    translations_path = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "src"
        / "i18n"
        / "agent-prompt-zh-CN.json"
    )
    translations = json.loads(translations_path.read_text(encoding="utf-8"))
    missing = [
        f"{spec.key}: {text}"
        for spec in PROMPT_SPECS
        for text in (spec.title, spec.description)
        if not translations.get(text)
    ]

    assert not missing, f"Missing Chinese agent labels: {missing}"
