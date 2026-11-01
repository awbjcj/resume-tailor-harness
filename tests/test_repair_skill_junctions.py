import os
from pathlib import Path
import subprocess

import pytest

from scripts.repair_skill_junctions import repair_skill_junctions


def _junction(link: Path, target: Path) -> None:
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junctions")
def test_repair_preserves_target_and_all_skill_contents(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    target = tmp_path / "agent-skills" / "example"
    target.mkdir(parents=True)
    raw = b"---\r\nname: example\r\n---\r\nOriginal instructions\r\n"
    (target / "SKILL.md").write_bytes(raw)
    (target / "references").mkdir()
    (target / "references" / "local.txt").write_text("Untracked local notes")
    link = root / "example"
    _junction(link, target)

    assert repair_skill_junctions(root) == ["example"]

    assert not link.is_junction()
    assert (link / "SKILL.md").read_bytes() == raw
    assert (target / "SKILL.md").read_bytes() == raw
    assert (link / "references" / "local.txt").read_text() == "Untracked local notes"
    (link / "SKILL.md").write_text("Independent copy")
    assert (target / "SKILL.md").read_bytes() == raw
    assert repair_skill_junctions(root) == []
    assert sorted(p.name for p in root.iterdir()) == ["example"]


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junctions")
def test_repair_refuses_a_linked_skill_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    root = tmp_path / "skills"
    _junction(root, target)

    with pytest.raises(ValueError, match="real directory"):
        repair_skill_junctions(root)

    assert root.is_junction()
    assert target.is_dir()


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junctions")
def test_copy_failure_keeps_original_junction_and_target(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "SKILL.md").write_text("Original")
    link = root / "example"
    _junction(link, target)

    def fail_copy(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr("scripts.repair_skill_junctions.shutil.copytree", fail_copy)
    with pytest.raises(OSError, match="Disk full"):
        repair_skill_junctions(root)

    assert link.is_junction()
    assert (link / "SKILL.md").read_text() == "Original"
    assert (target / "SKILL.md").read_text() == "Original"


def test_repair_leaves_real_directories_unchanged(tmp_path):
    root = tmp_path / "skills"
    skill = root / "example"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Original")

    assert repair_skill_junctions(root) == []
    assert (skill / "SKILL.md").read_text() == "Original"
