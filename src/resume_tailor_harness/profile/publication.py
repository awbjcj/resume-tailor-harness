"""Successful source incorporation, independent from edits to saved profile facts.

Only the corpus publisher writes this receipt. Reads compare source content and
interpretation settings with the inputs the successful build actually consumed;
editing facts or caching a fragment cannot certify source incorporation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field

from resume_tailor_harness.models.base import ExtensibleModel
from resume_tailor_harness.profile.corpus import (
    SourceManifest,
    doc_path,
    load_manifest,
    source_lock,
)
from resume_tailor_harness.profile.fragments import fragment_input_metadata
from resume_tailor_harness.rollback import restore_file

PUBLICATION_NAME = "publication.json"
ProfileFreshness = Literal["missing", "unknown", "current", "refresh-needed"]


class SourceInputs(ExtensibleModel):
    documents: dict[str, str] = Field(default_factory=dict)
    registry: str


class ProfilePublication(ExtensibleModel):
    published_at: str
    inputs: SourceInputs


class PublicationStatus(ExtensibleModel):
    freshness: ProfileFreshness
    published_at: str | None = None
    pending_source_count: int = 0


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def source_inputs(
    root: Path | str,
    manifest: SourceManifest | None = None,
    *,
    consumed_hashes: bool = False,
) -> SourceInputs:
    """Capture sources, or describe a build's privately held extraction manifest.

    Extraction updates its private manifest hashes to the bytes it read. Using
    those hashes after extraction avoids claiming concurrently uploaded files
    that were never part of the build. Ordinary reads always hash actual bytes.
    """
    root = Path(root)
    with source_lock(root):
        manifest = manifest if manifest is not None else load_manifest(root)
        documents: dict[str, str] = {}
        for doc in manifest.docs:
            if consumed_hashes:
                content = doc.sha256
            else:
                try:
                    content = hashlib.sha256(
                        doc_path(root, doc).read_bytes()
                    ).hexdigest()
                except OSError:
                    content = None
            # added_at and the manifest's cached hash are bookkeeping. Every
            # field that changes source interpretation belongs in this digest.
            metadata = doc.model_dump(exclude={"added_at", "sha256"})
            documents[doc.id] = _fingerprint(
                {
                    "source": metadata,
                    "content": content,
                    "interpretation": fragment_input_metadata(
                        doc, content or "missing"
                    ),
                }
            )
        return SourceInputs(
            documents=documents,
            registry=_fingerprint(
                {
                    "excludedSources": sorted(manifest.excluded_github_sources),
                    "excludedRepositories": sorted(manifest.excluded_github_repos),
                }
            ),
        )


def load_publication(root: Path | str) -> ProfilePublication | None:
    try:
        return ProfilePublication.model_validate_json(
            (Path(root) / PUBLICATION_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None


def save_publication(root: Path | str, inputs: SourceInputs) -> ProfilePublication:
    publication = ProfilePublication(
        published_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        inputs=inputs,
    )
    restore_file(
        Path(root) / PUBLICATION_NAME,
        (publication.model_dump_json(indent=2) + "\n").encode(),
    )
    return publication


def publication_status(root: Path | str) -> PublicationStatus:
    root = Path(root)
    if not (root / "facts.json").is_file():
        return PublicationStatus(freshness="missing")
    publication = load_publication(root)
    if publication is None:
        return PublicationStatus(freshness="unknown")
    try:
        current = source_inputs(root)
    except (OSError, ValueError):
        return PublicationStatus(
            freshness="unknown", published_at=publication.published_at
        )
    previous = publication.inputs
    pending = sum(
        previous.documents.get(key) != current.documents.get(key)
        for key in previous.documents.keys() | current.documents.keys()
    )
    return PublicationStatus(
        freshness=(
            "refresh-needed"
            if pending or previous.registry != current.registry
            else "current"
        ),
        published_at=publication.published_at,
        pending_source_count=pending,
    )


def pending_sources(root: Path | str, source_ids: set[str]) -> set[str]:
    """Return session evidence not covered by the last successful publication."""
    publication = load_publication(root)
    if publication is None or not (Path(root) / "facts.json").is_file():
        return source_ids.copy()
    try:
        current = source_inputs(root)
    except (OSError, ValueError):
        return source_ids.copy()
    return {
        key
        for key in source_ids
        if key not in current.documents
        or current.documents[key] != publication.inputs.documents.get(key)
    }
