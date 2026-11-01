"""Source-document registry for the fact-lock profile corpus."""

import hashlib
import os
import re
import shutil
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from ipaddress import ip_address
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from resume_tailor_harness.models.base import ExtensibleModel
from resume_tailor_harness.profile.resume_reader import SUPPORTED_SUFFIXES
from resume_tailor_harness.security.paths import confined_path
from resume_tailor_harness.rollback import rollback_scope, restore_file
from resume_tailor_harness.tenancy.paths import resolve_tenant_path

MANIFEST_NAME = "sources.json"
SOURCES_DIRNAME = "sources"
FRAGMENTS_DIRNAME = "fragments"

_SLUG = re.compile(r"[^a-z0-9]+")

SourceMode = Literal["literal", "synthesis", "project"]
SourceOrigin = Literal["upload", "github"]

_UNSET: object = object()
_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


@contextmanager
def source_lock(profile_dir: str | Path) -> Iterator[None]:
    """Serialize corpus mutations within one tenant, including sync writes."""
    key = resolve_tenant_path(profile_dir).resolve()
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        yield


def default_mode(filename: str) -> SourceMode:
    """Decks default to synthesis; everything else stays literal extraction."""
    return "synthesis" if Path(filename).suffix.lower() == ".pptx" else "literal"


class SourceDoc(ExtensibleModel):
    id: str
    filename: str
    sha256: str
    added_at: str
    primary: bool = False
    mode: SourceMode = "literal"
    anchor: str | None = None
    origin: SourceOrigin = "upload"
    repo_url: str | None = None
    github_branch: str | None = None


class SourceManifest(ExtensibleModel):
    docs: list[SourceDoc] = Field(default_factory=list)
    excluded_github_sources: list[str] = Field(default_factory=list)
    excluded_github_repos: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_docs(self) -> "SourceManifest":
        primary_count = sum(doc.primary for doc in self.docs)
        if primary_count > 1 or (
            any(doc.mode == "literal" for doc in self.docs) and primary_count != 1
        ):
            raise ValueError(
                "a source manifest with literal documents must have exactly one primary"
            )
        for doc in self.docs:
            if doc.primary and doc.mode != "literal":
                raise ValueError(f"primary source {doc.id} must use literal mode")
            if doc.anchor is not None and doc.mode != "synthesis":
                raise ValueError(f"anchor on {doc.id} requires synthesis mode")
        return self


def sources_dir(profile_dir: str | Path) -> Path:
    return resolve_tenant_path(profile_dir) / SOURCES_DIRNAME


def doc_path(profile_dir: str | Path, doc: SourceDoc) -> Path:
    return confined_path(sources_dir(profile_dir), doc.filename)


def _manifest_path(profile_dir: str | Path) -> Path:
    return resolve_tenant_path(profile_dir) / MANIFEST_NAME


def load_manifest(profile_dir: str | Path) -> SourceManifest:
    path = _manifest_path(profile_dir)
    if not path.exists():
        return SourceManifest()
    try:
        return SourceManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid source manifest: {path}") from exc


def save_manifest(manifest: SourceManifest, profile_dir: str | Path) -> None:
    validated = SourceManifest.model_validate(manifest.model_dump())
    path = _manifest_path(profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(validated.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _doc_id(filename: str, sha256: str) -> str:
    slug = _SLUG.sub("-", Path(filename).stem.casefold()).strip("-") or "doc"
    return f"{slug}-{sha256[:8]}"


_FRONTMATTER = re.compile(
    rb"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?(?:\n|\Z)", re.DOTALL
)


def _valid_repo_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or not parsed.path.strip("/")
        ):
            return False
        if host.casefold() == "localhost" or host.casefold().endswith(".localhost"):
            return False
        try:
            return ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def frontmatter_repo_url(data: bytes) -> str | None:
    """Return a valid public HTTP(S) repo URL from leading YAML frontmatter."""
    match = _FRONTMATTER.match(data)
    if match is None:
        return None
    try:
        block = match.group(1).decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in block.splitlines():
        key, separator, raw_value = line.partition(":")
        if separator and key.strip() == "repo_url":
            value = raw_value.strip().strip("'\"")
            return value if _valid_repo_url(value) else None
    return None


def add_source(
    profile_dir: str | Path,
    file_path: str | Path,
    primary: bool = False,
    mode: SourceMode | None = None,
    anchor: str | None = None,
    origin: SourceOrigin = "upload",
) -> SourceDoc:
    with source_lock(profile_dir):
        return _add_source(profile_dir, file_path, primary, mode, anchor, origin)


def _add_source(
    profile_dir: str | Path,
    file_path: str | Path,
    primary: bool,
    mode: SourceMode | None,
    anchor: str | None,
    origin: SourceOrigin,
) -> SourceDoc:
    source = Path(file_path)
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(
            f"Unsupported document format: {suffix or '(none)'} (use {supported})"
        )

    # ``file_path`` is a local CLI selection or an API-created temporary upload, not an HTTP path.
    # codeql[py/path-injection] -- Intentional local source-file read; persisted destination is confined.
    data = source.read_bytes()
    dossier_mode = (
        source.suffix.lower() == ".md" and frontmatter_repo_url(data) is not None
    )
    resolved_mode = mode or ("project" if dossier_mode else default_mode(source.name))
    if anchor is not None and resolved_mode != "synthesis":
        raise ValueError("anchor requires synthesis mode")
    sha256 = hashlib.sha256(data).hexdigest()
    manifest = load_manifest(profile_dir)
    # Harvest can update bytes before extraction refreshes the registered hash.
    # An old hash must never cause an upload to silently return different bytes.
    existing = next(
        (
            doc
            for doc in manifest.docs
            if doc.sha256 == sha256
            and (
                not doc_path(profile_dir, doc).exists()
                or hashlib.sha256(doc_path(profile_dir, doc).read_bytes()).hexdigest()
                == sha256
            )
        ),
        None,
    )
    if existing is not None:
        changed = False
        if origin == "upload" and existing.origin == "github":
            existing.origin = "upload"
            changed = True
        if primary and not existing.primary:
            for doc in manifest.docs:
                doc.primary = doc.id == existing.id
            changed = True
        if (mode is not None or dossier_mode) and existing.mode != resolved_mode:
            existing.mode = resolved_mode
            if resolved_mode != "synthesis":
                existing.anchor = None
            changed = True
        if anchor is not None and existing.anchor != anchor:
            existing.anchor = anchor
            changed = True
        if existing.mode == "literal" and not any(doc.primary for doc in manifest.docs):
            existing.primary = True
            changed = True
        if changed:
            save_manifest(manifest, profile_dir)
        # A repeated upload also repairs an absent file. Never return a row
        # pointing at missing bytes just because its hash was registered.
        if not doc_path(profile_dir, existing).is_file():
            restore_file(doc_path(profile_dir, existing), data)
        return existing

    primary = primary or (
        resolved_mode == "literal" and not any(doc.primary for doc in manifest.docs)
    )
    if primary and resolved_mode != "literal":
        raise ValueError("the primary resume must use literal mode")
    doc = SourceDoc(
        id=_doc_id(source.name, sha256),
        filename=source.name,
        sha256=sha256,
        added_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        primary=primary,
        mode=resolved_mode,
        anchor=anchor,
        origin=origin,
        repo_url=frontmatter_repo_url(data) if suffix == ".md" else None,
    )
    # Replacement preserves an ID derived from the original bytes. Re-uploading
    # those bytes must get a new identity, or delete/cache operations target both.
    used_ids = {other.id for other in manifest.docs}
    base_id = doc.id
    sequence = 2
    while doc.id in used_ids:
        doc.id = f"{base_id}-{sequence}"
        sequence += 1
    target_dir = sources_dir(profile_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = doc_path(profile_dir, doc)
    occupied = {doc_path(profile_dir, other) for other in manifest.docs}
    filename_sequence = 1
    while target in occupied or (
        target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != sha256
    ):
        discriminator = "" if filename_sequence == 1 else f"-{filename_sequence}"
        doc.filename = f"{doc.id}{discriminator}{suffix}"
        target = doc_path(profile_dir, doc)
        filename_sequence += 1
    # codeql[py/path-injection] -- Local source capability is compared with a confined destination.
    if source.resolve() != target.resolve():
        # codeql[py/path-injection] -- Source is the intentional local file selected above.
        shutil.copyfile(source, target)

    if primary:
        for other in manifest.docs:
            other.primary = False
    manifest.docs.append(doc)
    save_manifest(manifest, profile_dir)
    return doc


def remove_source(
    profile_dir: str | Path,
    ident: str,
    purge: bool = False,
    *,
    exclude_github: bool = False,
) -> SourceDoc | None:
    with source_lock(profile_dir):
        return _remove_source(profile_dir, ident, purge, exclude_github)


def _remove_source(
    profile_dir: str | Path,
    ident: str,
    purge: bool,
    exclude_github: bool,
) -> SourceDoc | None:
    manifest = load_manifest(profile_dir)
    doc = next(
        (
            candidate
            for candidate in manifest.docs
            if ident in (candidate.id, candidate.filename)
        ),
        None,
    )
    if doc is None:
        return None
    manifest.docs = [candidate for candidate in manifest.docs if candidate.id != doc.id]
    if doc.primary and manifest.docs:
        replacement = next(
            (candidate for candidate in manifest.docs if candidate.mode == "literal"),
            None,
        )
        if replacement is not None:
            replacement.primary = True
    repo_url = source_repo_url(profile_dir, doc)
    if exclude_github and (doc.origin == "github" or repo_url):
        if doc.filename not in manifest.excluded_github_sources:
            manifest.excluded_github_sources.append(doc.filename)
        if repo_url and not any(
            source_repo_url(profile_dir, other) == repo_url for other in manifest.docs
        ):
            if repo_url not in manifest.excluded_github_repos:
                manifest.excluded_github_repos.append(repo_url)
    fragments = resolve_tenant_path(profile_dir) / FRAGMENTS_DIRNAME
    cache_paths = (
        confined_path(fragments, f"{doc.id}.json"),
        confined_path(fragments, f"{doc.id}.meta.json"),
        confined_path(fragments, f"{doc.id}.evidence.json"),
    )
    target = doc_path(profile_dir, doc)
    with rollback_scope(
        [_manifest_path(profile_dir), *cache_paths, *([target] if purge else [])]
    ):
        save_manifest(manifest, profile_dir)
        for stale in cache_paths:
            stale.unlink(missing_ok=True)
        if purge:
            target.unlink(missing_ok=True)
    return doc


def update_source(
    profile_dir: str | Path,
    ident: str,
    *,
    mode: SourceMode | None = None,
    anchor: str | None | object = _UNSET,
    primary: bool | None = None,
) -> SourceDoc | None:
    """Update a registered doc's mode/anchor/primary. anchor=None clears it."""
    with source_lock(profile_dir):
        return _update_source(
            profile_dir, ident, mode=mode, anchor=anchor, primary=primary
        )


def _update_source(
    profile_dir: str | Path,
    ident: str,
    *,
    mode: SourceMode | None,
    anchor: str | None | object,
    primary: bool | None,
) -> SourceDoc | None:
    manifest = load_manifest(profile_dir)
    doc = next(
        (c for c in manifest.docs if ident in (c.id, c.filename)),
        None,
    )
    if doc is None:
        return None
    if doc.mode == "project" and (mode not in (None, "project") or primary):
        raise ValueError("project sources must keep project mode and cannot be primary")
    if mode is not None:
        doc.mode = mode
        if mode != "synthesis":
            doc.anchor = None
    if anchor is not _UNSET:
        doc.anchor = anchor  # type: ignore[assignment]
    if primary:
        for other in manifest.docs:
            other.primary = other.id == doc.id
    if doc.mode == "literal" and not any(other.primary for other in manifest.docs):
        doc.primary = True
    save_manifest(manifest, profile_dir)
    return doc


def replace_source(
    profile_dir: str | Path,
    ident: str,
    file_path: str | Path,
) -> SourceDoc | None:
    """Replace bytes atomically while preserving identity, role and repository."""
    source = Path(file_path)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Unsupported document format")
    data = source.read_bytes()
    if not data:
        raise ValueError("Source file must not be empty")
    with source_lock(profile_dir):
        manifest = load_manifest(profile_dir)
        doc = next((d for d in manifest.docs if ident in (d.id, d.filename)), None)
        if doc is None:
            return None
        old_path = doc_path(profile_dir, doc)
        repo_url = doc.repo_url
        if repo_url is None and old_path.suffix.lower() == ".md" and old_path.is_file():
            repo_url = frontmatter_repo_url(old_path.read_bytes())
        incoming_repo = (
            frontmatter_repo_url(data) if source.suffix.lower() == ".md" else None
        )
        if repo_url and incoming_repo:
            from resume_tailor_harness.profile.github_ingest import normalize_repo_url

            if normalize_repo_url(repo_url) != normalize_repo_url(incoming_repo):
                raise ValueError(
                    "Replacement dossier must belong to the same repository"
                )
        old_origin = doc.origin
        old_sha = doc.sha256
        doc.repo_url = incoming_repo or repo_url
        doc.origin = "upload"
        doc.sha256 = hashlib.sha256(data).hexdigest()
        doc.filename = source.name
        target = doc_path(profile_dir, doc)
        occupied = {
            doc_path(profile_dir, other)
            for other in manifest.docs
            if other.id != doc.id
        }
        if target in occupied or (target.exists() and target != old_path):
            # Keep the original upload and any other registered document intact.
            doc.filename = f"{doc.id}--{source.name}"
            target = doc_path(profile_dir, doc)
        if target in occupied or (target.exists() and target != old_path):
            raise ValueError("Replacement filename conflicts with another source")
        fragments = resolve_tenant_path(profile_dir) / FRAGMENTS_DIRNAME
        cache_paths = [
            confined_path(fragments, f"{doc.id}{suffix}")
            for suffix in (
                ".json",
                ".meta.json",
                ".evidence.json",
            )
        ]
        with rollback_scope(
            [_manifest_path(profile_dir), old_path, target, *cache_paths]
        ):
            restore_file(target, data)
            save_manifest(manifest, profile_dir)
            if old_path != target:
                old_path.unlink(missing_ok=True)
            if old_sha != doc.sha256 or old_origin != doc.origin:
                for cache in cache_paths:
                    cache.unlink(missing_ok=True)
        return doc


def restore_github_sources(profile_dir: str | Path) -> None:
    """Allow explicitly removed GitHub files to be discovered on the next sync."""
    with source_lock(profile_dir):
        manifest = load_manifest(profile_dir)
        manifest.excluded_github_sources = []
        manifest.excluded_github_repos = []
        save_manifest(manifest, profile_dir)


def source_repo_url(profile_dir: str | Path, doc: SourceDoc) -> str | None:
    """Read repository identity for current and pre-metadata manifest entries."""
    from resume_tailor_harness.profile.github_ingest import normalize_repo_url

    value = doc.repo_url
    if value is None and doc.filename.casefold().endswith(".md"):
        try:
            value = frontmatter_repo_url(doc_path(profile_dir, doc).read_bytes())
        except OSError:
            pass
    return normalize_repo_url(value)


def refresh_source_hashes(
    profile_dir: str | Path,
    changes: dict[str, tuple[str, str]],
) -> None:
    """Publish observed hashes without overwriting edits made during extraction."""
    with source_lock(profile_dir):
        current = load_manifest(profile_dir)
        changed = False
        for doc in current.docs:
            hashes = changes.get(doc.id)
            if hashes is not None and doc.sha256 == hashes[0]:
                doc.sha256 = hashes[1]
                changed = True
        if changed:
            save_manifest(current, profile_dir)


def migrate_legacy(
    profile_dir: str | Path, resume_path: str | None
) -> SourceDoc | None:
    """Register the legacy configured resume as the primary source once."""
    if _manifest_path(profile_dir).exists():
        return None
    if not resume_path or not Path(resume_path).exists():
        return None
    return add_source(profile_dir, resume_path, primary=True)
