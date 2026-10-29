import json
from pathlib import Path

from resume_tailor_harness.render.templates import BUNDLED


def test_chinese_labels_cover_bundled_templates() -> None:
    translations_path = (
        Path(__file__).resolve().parents[1] / "web" / "src" / "i18n" / "template-zh-CN.json"
    )
    translations = json.loads(translations_path.read_text(encoding="utf-8"))
    missing = [
        f"{template.id}: {text}"
        for template in BUNDLED.values()
        for text in (template.title, template.description)
        if not translations.get(text)
    ]

    assert not missing, f"Missing Chinese template labels: {missing}"
