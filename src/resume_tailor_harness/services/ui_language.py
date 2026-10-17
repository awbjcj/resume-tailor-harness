"""Persist the dashboard language for mail sent without an active browser."""

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from typing import Literal

from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.tenancy.system_db import User


def current_language() -> Literal["en", "zh-CN"]:
    context = current_context()
    if context is None or context.system_engine is None:
        return "en"
    with Session(context.system_engine) as session:
        user = session.get(User, context.user_id)
        return "zh-CN" if user and user.dashboard_language == "zh-CN" else "en"


def save_language(engine: Engine, user_id: str, language: str) -> None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user is not None:
            user.dashboard_language = language
            session.commit()
