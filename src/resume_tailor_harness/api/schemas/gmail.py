from __future__ import annotations

from pydantic import StrictBool

from resume_tailor_harness.api.schemas.base import CamelModel


class GmailConnectOut(CamelModel):
    auth_url: str


class GmailSyncIn(CamelModel):
    review_cleared: bool = False


class GmailAutomationIn(CamelModel):
    auto_apply_rejections: StrictBool


class GmailStatusOut(CamelModel):
    connected: bool
    scopes: list[str] = []
    draft_capable: bool = False
    client_source: str = "platform"  # "platform" | "own"
    auto_apply_rejections: bool = False
