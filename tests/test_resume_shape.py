from resume_tailor_harness.services.resume_shape import for_rendering
from resume_tailor_harness.tailor.review_config import ReviewConfig


def test_default_rendering_reconciles_legacy_two_page_roster(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = ReviewConfig()
    effective = for_rendering(config)
    assert config.length_budget.page_target == 2
    assert effective.length_budget.page_target == 1
    assert effective.length_budget.target_total_bullets == 16


def test_detailed_rendering_preserves_larger_saved_budget(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "config" / "render.yaml"
    path.parent.mkdir()
    path.write_text("template: academic\nfit_one_page: false\n", encoding="utf-8")
    config = ReviewConfig()
    assert for_rendering(config).length_budget == config.length_budget
