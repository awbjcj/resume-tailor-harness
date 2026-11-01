"""Materialize Windows skill junctions without changing their target directories.

Run explicitly after a skill installer has replaced the shipped skills with
junctions. Runtime path confinement and hash verification remain unchanged.
"""

from pathlib import Path
import shutil
import tempfile


def repair_skill_junctions(skill_root: Path) -> list[str]:
    """Copy immediate junction children into real directories, preserving contents.

    Stage each copy beside the junction before removing only the junction itself.
    On failure, retain the staged copy for recovery rather than deleting data.
    """
    if skill_root.is_symlink() or skill_root.is_junction():
        raise ValueError("The skill root must be a real directory")
    skill_root = skill_root.resolve(strict=True)
    repaired = []
    for path in sorted(skill_root.iterdir()):
        if not path.is_junction():
            continue
        target = path.resolve(strict=True)
        stage = Path(tempfile.mkdtemp(prefix=".skill-repair-", dir=skill_root))
        replacement = stage / path.name
        shutil.copytree(path, replacement, symlinks=True)
        if not path.is_junction() or path.resolve(strict=True) != target:
            raise RuntimeError(f"Junction changed during repair; copy retained at {stage}")
        # On Windows rmdir removes the junction, never its target or contents.
        path.rmdir()
        replacement.rename(path)
        stage.rmdir()
        repaired.append(path.name)
    return repaired


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "skills"
    repaired = repair_skill_junctions(root)
    for name in repaired:
        print(f"Materialized skills/{name}")
    print(f"Repaired {len(repaired)} skill junction(s); targets preserved.")


if __name__ == "__main__":
    main()
