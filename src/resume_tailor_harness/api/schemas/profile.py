"""Profile document + build wire schemas."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, StringConstraints

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.profile.corpus import SourceMode, SourceOrigin


class DocumentOut(CamelModel):
    id: str
    filename: str
    doc_type: str
    size_bytes: int
    uploaded_at: str


class SourceOut(CamelModel):
    id: str
    filename: str
    mode: SourceMode
    primary: bool
    anchor: str | None = None
    added_at: str
    fragment_status: str
    origin: SourceOrigin = "upload"
    file_exists: bool = True
    repo_url: str | None = None
    github_branch: str | None = None


class GithubRepositoryOut(CamelModel):
    owner: str
    name: str
    full_name: str
    default_branch: str | None = None
    selected_branch: str | None = None
    included: bool = False
    uploaded_override: bool = False


class SourcePatch(CamelModel):
    mode: SourceMode | None = None
    anchor: str | None = None
    primary: bool | None = None


class SkeletonEntryOut(CamelModel):
    id: str
    kind: str
    label: str


class NoteIn(CamelModel):
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=1, max_length=100_000)


class UrlIn(CamelModel):
    url: AnyHttpUrl


class MatrixRowOut(CamelModel):
    key: str
    display: str
    category: str | None = None
    group: str | None = None
    group_source: Literal["correction", "override", "taxonomy"] | None = None
    inferred: bool = False
    strength: float = 0.0
    last_used: str | None = None
    aliases: list[str] = Field(default_factory=list)
    evidence_fact_ids: list[str] = Field(default_factory=list)


class SkillGroupOut(CamelModel):
    slug: str
    label: str
    category: str = "other"
    customized: bool = False


class SkillCategoryOut(CamelModel):
    slug: str
    label: str
    customized: bool = False


class MatrixOut(CamelModel):
    generated_at: str = ""
    groups: list[SkillGroupOut] = Field(default_factory=list)
    rows: list[MatrixRowOut] = Field(default_factory=list)
    categories: list[SkillCategoryOut] = Field(default_factory=list)


class SkillEntryOut(CamelModel):
    id: str
    name: str
    category: Literal["hard", "soft", "domain"] | None = None
    aliases: list[str] = Field(default_factory=list)
    inferred: bool = False
    evidence_fact_ids: list[str] = Field(default_factory=list)


class AddSkillIn(CamelModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    category: Literal["hard", "soft", "domain"] | None = None
    aliases: list[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ]
    ] = Field(default_factory=list, max_length=50)
    group: str | None = None


class AddAliasIn(CamelModel):
    alias: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class UpdateProfileSkillIn(AddSkillIn):
    pass


class MergeProfileSkillsIn(CamelModel):
    keys: list[str] = Field(min_length=1, max_length=100)
    into: str = Field(min_length=1, max_length=200)


class SkillCleanupMergeOut(CamelModel):
    into: str
    names: list[str]


class SkillCleanupPruneOut(CamelModel):
    token: str
    display: str
    reason: str


class SkillCleanupOut(CamelModel):
    enabled: bool
    before_count: int
    after_count: int
    merges: list[SkillCleanupMergeOut]
    pruned: list[SkillCleanupPruneOut]


class SkillCleanupPolicyIn(CamelModel):
    enabled: bool


class RebuildProfileSkillsIn(CamelModel):
    reclassify_only: bool = False


class SkillOrganizationIn(CamelModel):
    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    category: str = "other"


class SetGroupIn(CamelModel):
    group: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ]


class ManualEntryOut(CamelModel):
    id: str
    kind: Literal["new_skill", "alias"]
    added_at: str
    name: str | None = None
    category: Literal["hard", "soft", "domain"] | None = None
    alias_text: str | None = None
    target_skill_display: str | None = None


class SuppressedSkillOut(CamelModel):
    token: str
    display: str
    added_at: str
    reason: str | None = None
