import pytest

from resume_tailor_harness.profile.corpus import (
    SourceDoc,
    SourceManifest,
    add_source,
    default_mode,
    doc_path,
    load_manifest,
    migrate_legacy,
    remove_source,
    save_manifest,
    update_source,
    frontmatter_repo_url,
    replace_source,
    refresh_source_hashes,
)
from resume_tailor_harness.security.paths import PathEscapeError


def _make_doc(tmp_path, name="resume.txt", content="Ada Lovelace"):
    file = tmp_path / name
    file.write_text(content, encoding="utf-8")
    return file


def test_add_source_registers_and_copies(tmp_path):
    profile_dir = tmp_path / "profile"
    doc = add_source(profile_dir, _make_doc(tmp_path), primary=True)

    manifest = load_manifest(profile_dir)
    assert [item.id for item in manifest.docs] == [doc.id]
    assert manifest.docs[0].primary is True
    assert doc.id.startswith("resume-")
    assert doc_path(profile_dir, doc).read_text(encoding="utf-8") == "Ada Lovelace"


def test_doc_path_confines_manifest_filenames(tmp_path):
    profile_dir = tmp_path / "profile"
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    untrusted = SourceDoc(
        id="resume-unsafe",
        filename="../outside.txt",
        sha256="0" * 64,
        added_at="2026-01-01T00:00:00+00:00",
    )

    with pytest.raises(PathEscapeError):
        doc_path(profile_dir, untrusted)
    assert outside.read_text(encoding="utf-8") == "keep"


def test_add_source_same_content_is_noop(tmp_path):
    profile_dir = tmp_path / "profile"
    first = add_source(profile_dir, _make_doc(tmp_path))
    second = add_source(profile_dir, _make_doc(tmp_path))
    assert first.id == second.id
    assert len(load_manifest(profile_dir).docs) == 1


def test_reupload_repairs_missing_registered_file(tmp_path):
    profile_dir = tmp_path / "profile"
    upload = _make_doc(tmp_path)
    first = add_source(profile_dir, upload)
    doc_path(profile_dir, first).unlink()
    repaired = add_source(profile_dir, upload)
    assert repaired.id == first.id
    assert doc_path(profile_dir, repaired).read_bytes() == upload.read_bytes()


def test_replace_rolls_back_manifest_bytes_and_cache_on_failure(tmp_path, monkeypatch):
    import resume_tailor_harness.profile.corpus as corpus

    profile_dir = tmp_path / "profile"
    doc = add_source(profile_dir, _make_doc(tmp_path))
    cache = profile_dir / "fragments" / f"{doc.id}.json"
    cache.parent.mkdir()
    cache.write_text("cached", encoding="utf-8")
    before = (profile_dir / "sources.json").read_bytes()
    replacement = _make_doc(tmp_path, "new.txt", "updated")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(corpus, "save_manifest", fail)
    with pytest.raises(OSError, match="disk full"):
        replace_source(profile_dir, doc.id, replacement)
    assert (profile_dir / "sources.json").read_bytes() == before
    assert doc_path(profile_dir, doc).read_text(encoding="utf-8") == "Ada Lovelace"
    assert cache.read_text(encoding="utf-8") == "cached"
    assert not (profile_dir / "sources" / "new.txt").exists()


def test_hash_refresh_does_not_resurrect_removed_sources_or_drop_new_ones(tmp_path):
    profile_dir = tmp_path / "profile"
    first = add_source(profile_dir, _make_doc(tmp_path))
    second = add_source(profile_dir, _make_doc(tmp_path, "other.txt", "other"))
    remove_source(profile_dir, first.id)
    third = add_source(profile_dir, _make_doc(tmp_path, "new.txt", "new"))
    refresh_source_hashes(profile_dir, {first.id: (first.sha256, "old extraction")})
    assert {d.id for d in load_manifest(profile_dir).docs} == {second.id, third.id}


def test_replace_rejects_foreign_dossier_and_preserves_project_mode(tmp_path):
    profile_dir = tmp_path / "profile"
    add_source(profile_dir, _make_doc(tmp_path))
    dossier = _make_doc(
        tmp_path, "dossier.md", "---\nrepo_url: https://github.com/me/one\n---\n# One"
    )
    doc = add_source(profile_dir, dossier)
    foreign = _make_doc(
        tmp_path, "other.md", "---\nrepo_url: https://github.com/me/two\n---\n# Two"
    )
    with pytest.raises(ValueError, match="same repository"):
        replace_source(profile_dir, doc.id, foreign)
    with pytest.raises(ValueError, match="project mode"):
        update_source(profile_dir, doc.id, mode="literal")
    assert doc_path(profile_dir, doc).read_bytes() == dossier.read_bytes()


def test_first_source_is_automatically_primary(tmp_path):
    profile_dir = tmp_path / "profile"
    add_source(profile_dir, _make_doc(tmp_path))
    assert load_manifest(profile_dir).docs[0].primary is True


def test_add_second_primary_demotes_first(tmp_path):
    profile_dir = tmp_path / "profile"
    add_source(profile_dir, _make_doc(tmp_path, "a.txt", "A"), primary=True)
    add_source(profile_dir, _make_doc(tmp_path, "b.txt", "B"), primary=True)
    primaries = [doc for doc in load_manifest(profile_dir).docs if doc.primary]
    assert [doc.filename for doc in primaries] == ["b.txt"]


def test_add_source_rejects_unsupported_suffix(tmp_path):
    bad = tmp_path / "img.png"
    bad.write_bytes(b"\x89PNG")
    with pytest.raises(ValueError):
        add_source(tmp_path / "profile", bad)


def test_remove_source_by_filename(tmp_path):
    profile_dir = tmp_path / "profile"
    doc = add_source(profile_dir, _make_doc(tmp_path))
    removed = remove_source(profile_dir, "resume.txt")
    assert removed is not None and removed.id == doc.id
    assert load_manifest(profile_dir).docs == []
    assert doc_path(profile_dir, doc).exists()


def test_remove_source_purge_deletes_copy(tmp_path):
    profile_dir = tmp_path / "profile"
    doc = add_source(profile_dir, _make_doc(tmp_path))
    remove_source(profile_dir, doc.id, purge=True)
    assert not doc_path(profile_dir, doc).exists()


def test_remove_primary_promotes_oldest_remaining(tmp_path):
    profile_dir = tmp_path / "profile"
    first = add_source(profile_dir, _make_doc(tmp_path, "a.txt", "A"))
    second = add_source(profile_dir, _make_doc(tmp_path, "b.txt", "B"))
    remove_source(profile_dir, first.id)
    assert load_manifest(profile_dir).docs == [
        second.model_copy(update={"primary": True})
    ]


def test_remove_primary_uses_manifest_order_when_timestamps_tie(tmp_path):
    profile_dir = tmp_path / "profile"
    manifest = SourceManifest(
        docs=[
            SourceDoc(
                id="primary",
                filename="primary.txt",
                sha256="0" * 64,
                added_at="2026-07-01T00:00:00+00:00",
                primary=True,
            ),
            SourceDoc(
                id="z-second",
                filename="second.txt",
                sha256="1" * 64,
                added_at="2026-07-01T00:00:00+00:00",
            ),
            SourceDoc(
                id="a-third",
                filename="third.txt",
                sha256="2" * 64,
                added_at="2026-07-01T00:00:00+00:00",
            ),
        ]
    )
    save_manifest(manifest, profile_dir)
    remove_source(profile_dir, "primary")
    assert load_manifest(profile_dir).docs[0].id == "z-second"
    assert load_manifest(profile_dir).docs[0].primary is True


def test_corrupt_manifest_fails_loudly(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "sources.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        load_manifest(profile_dir)


def test_manifest_rejects_invalid_primary_count():
    with pytest.raises(ValueError, match="exactly one primary"):
        SourceManifest(
            docs=[
                SourceDoc(
                    id="a",
                    filename="a.txt",
                    sha256="0" * 64,
                    added_at="2026-07-01T00:00:00+00:00",
                )
            ]
        )


def test_manifest_round_trip_is_atomic_file(tmp_path):
    profile_dir = tmp_path / "profile"
    add_source(profile_dir, _make_doc(tmp_path))
    save_manifest(load_manifest(profile_dir), profile_dir)
    assert not list(profile_dir.glob("*.tmp"))


def test_migrate_legacy_registers_primary_once(tmp_path):
    profile_dir = tmp_path / "profile"
    legacy = _make_doc(tmp_path, "legacy_resume.txt")
    doc = migrate_legacy(profile_dir, str(legacy))
    assert doc is not None and doc.primary is True
    assert migrate_legacy(profile_dir, str(legacy)) is None
    assert migrate_legacy(tmp_path / "other", None) is None


def _file(tmp_path, name, content="body"):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


def test_default_mode_by_suffix():
    assert default_mode("deck.pptx") == "synthesis"
    assert default_mode("resume.pdf") == "literal"
    assert default_mode("notes.md") == "literal"


def test_add_source_defaults_and_overrides_mode(tmp_path):
    add_source(
        tmp_path / "p", _file(tmp_path, "resume.txt", "resume body"), primary=True
    )
    doc = add_source(
        tmp_path / "p", _file(tmp_path, "notes.md", "notes body"), mode="synthesis"
    )
    assert doc.mode == "synthesis"
    reloaded = load_manifest(tmp_path / "p")
    assert {d.filename: d.mode for d in reloaded.docs} == {
        "resume.txt": "literal",
        "notes.md": "synthesis",
    }


def test_only_a_literal_source_can_be_primary(tmp_path):
    doc = add_source(tmp_path / "p", _file(tmp_path, "deck.md"), mode="synthesis")
    assert doc.primary is False
    with pytest.raises(ValueError, match="literal"):
        update_source(tmp_path / "p", doc.id, primary=True)


def test_anchor_requires_synthesis_mode(tmp_path):
    add_source(tmp_path / "p", _file(tmp_path, "resume.txt"), primary=True)
    with pytest.raises(ValueError, match="synthesis"):
        add_source(tmp_path / "p", _file(tmp_path, "notes.md"), anchor="abc123")


def test_update_source_mode_anchor_primary(tmp_path):
    profile_dir = tmp_path / "p"
    add_source(profile_dir, _file(tmp_path, "resume.txt", "resume body"), primary=True)
    doc = add_source(
        profile_dir, _file(tmp_path, "notes.md", "notes body"), mode="synthesis"
    )

    updated = update_source(profile_dir, doc.id, anchor="fact42")
    assert updated is not None and updated.anchor == "fact42"

    cleared = update_source(profile_dir, doc.id, anchor=None)
    assert cleared is not None and cleared.anchor is None

    literal = update_source(profile_dir, doc.id, mode="literal")
    assert literal is not None and literal.mode == "literal" and literal.anchor is None

    promoted = update_source(profile_dir, doc.id, primary=True)
    assert promoted is not None and promoted.primary
    manifest = load_manifest(profile_dir)
    assert sum(d.primary for d in manifest.docs) == 1

    assert update_source(profile_dir, "nope") is None


def test_remove_primary_promotes_a_literal_doc(tmp_path):
    profile_dir = tmp_path / "p"
    primary = add_source(
        profile_dir, _file(tmp_path, "resume.txt", "resume body"), primary=True
    )
    add_source(profile_dir, _file(tmp_path, "deck.md", "deck body"), mode="synthesis")
    literal = add_source(
        profile_dir, _file(tmp_path, "old-resume.txt", "old resume body")
    )

    remove_source(profile_dir, primary.id)
    manifest = load_manifest(profile_dir)
    new_primary = next(d for d in manifest.docs if d.primary)
    assert new_primary.id == literal.id


def test_remove_primary_keeps_synthesis_sources_until_another_resume_is_added(tmp_path):
    profile_dir = tmp_path / "p"
    primary = add_source(
        profile_dir, _file(tmp_path, "resume.txt", "resume body"), primary=True
    )
    add_source(profile_dir, _file(tmp_path, "deck.md", "deck body"), mode="synthesis")
    remove_source(profile_dir, primary.id)
    assert all(not doc.primary for doc in load_manifest(profile_dir).docs)
    new = add_source(profile_dir, _file(tmp_path, "new.txt", "new resume"))
    assert new.primary


def test_legacy_manifest_without_mode_loads(tmp_path):
    profile_dir = tmp_path / "p"
    profile_dir.mkdir(parents=True)
    sha256 = "0" * 64
    (profile_dir / "sources.json").write_text(
        '{"docs": [{"id": "r-1", "filename": "r.txt", "sha256": "' + sha256 + '",'
        ' "added_at": "2026-01-01T00:00:00+00:00", "primary": true}]}',
        encoding="utf-8",
    )
    manifest = load_manifest(profile_dir)
    assert manifest.docs[0].mode == "literal"
    assert manifest.docs[0].anchor is None


DOSSIER = b"""---
repo_url: https://github.com/me/myrepo
repo_name: myrepo
---
# Project: myrepo
"""


def test_dossier_frontmatter_is_validated_and_defaults_to_project_mode(tmp_path):
    assert frontmatter_repo_url(DOSSIER) == "https://github.com/me/myrepo"
    assert frontmatter_repo_url(b"---\nrepo_url: file:///etc/passwd\n---\n") is None
    assert frontmatter_repo_url(b"---\nrepo_url: http://127.0.0.1/repo\n---\n") is None
    assert frontmatter_repo_url(b"\xff\xfe---") is None

    profile_dir = tmp_path / "profile"
    add_source(profile_dir, _make_doc(tmp_path), primary=True)
    dossier = tmp_path / "myrepo-dossier.md"
    dossier.write_bytes(DOSSIER)
    doc = add_source(profile_dir, dossier)
    assert doc.mode == "project"
    assert doc.origin == "upload"


def test_explicit_mode_overrides_dossier_sniff_and_project_rejects_anchor(tmp_path):
    profile_dir = tmp_path / "profile"
    add_source(profile_dir, _make_doc(tmp_path), primary=True)
    dossier = tmp_path / "myrepo-dossier.md"
    dossier.write_bytes(DOSSIER)
    assert add_source(profile_dir, dossier, mode="literal").mode == "literal"

    other = tmp_path / "other.md"
    other.write_bytes(DOSSIER.replace(b"myrepo", b"other"))
    with pytest.raises(ValueError, match="anchor"):
        add_source(profile_dir, other, mode="project", anchor="exp1")


def test_origin_round_trips_and_dedupe_does_not_retag_upload(tmp_path):
    profile_dir = tmp_path / "profile"
    resume = _make_doc(tmp_path)
    upload = add_source(profile_dir, resume, primary=True)
    same = add_source(profile_dir, resume, origin="github")
    assert same.id == upload.id and same.origin == "upload"

    virtual = tmp_path / "github--repo.md"
    virtual.write_text("# Repository: repo", encoding="utf-8")
    github_doc = add_source(profile_dir, virtual, mode="project", origin="github")
    assert github_doc.origin == "github"
    assert load_manifest(profile_dir).docs[-1].origin == "github"


def test_uploading_original_after_replacement_keeps_distinct_source_ids(tmp_path):
    profile_dir = tmp_path / "profile"
    original = _file(tmp_path, "resume.txt", "original resume")
    first = add_source(profile_dir, original)
    replace_source(profile_dir, first.id, _file(tmp_path, "updated.txt", "new resume"))

    restored = add_source(profile_dir, original)

    assert restored.id != first.id
    assert len({doc.id for doc in load_manifest(profile_dir).docs}) == 2
    remove_source(profile_dir, restored.id, purge=True)
    remaining = load_manifest(profile_dir).docs
    assert len(remaining) == 1 and remaining[0].id == first.id
    assert doc_path(profile_dir, remaining[0]).read_text() == "new resume"


def test_upload_does_not_deduplicate_against_a_stale_stored_hash(tmp_path):
    profile_dir = tmp_path / "profile"
    original = _file(tmp_path, "dossier.md", "original evidence")
    first = add_source(profile_dir, original, mode="project", origin="github")
    doc_path(profile_dir, first).write_text("synced evidence", encoding="utf-8")

    uploaded = add_source(profile_dir, original, mode="project")

    assert uploaded.id != first.id
    assert doc_path(profile_dir, uploaded).read_text() == "original evidence"
    assert doc_path(profile_dir, first).read_text() == "synced evidence"


def test_reupload_does_not_overwrite_a_source_with_the_fallback_filename(tmp_path):
    profile_dir = tmp_path / "profile"
    original = _file(tmp_path, "resume.txt", "original resume")
    first = add_source(profile_dir, original)
    replacement = tmp_path / "replacement" / "resume.txt"
    replacement.parent.mkdir()
    replacement.write_text("updated resume", encoding="utf-8")
    replace_source(profile_dir, first.id, replacement)
    conflict = add_source(profile_dir, _file(tmp_path, f"{first.id}-2.txt", "other evidence"))

    restored = add_source(profile_dir, original)

    assert restored.filename != conflict.filename
    assert doc_path(profile_dir, restored).read_text() == "original resume"
    assert doc_path(profile_dir, conflict).read_text() == "other evidence"
