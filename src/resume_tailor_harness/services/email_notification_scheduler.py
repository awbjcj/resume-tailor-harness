"""Run digest dispatch outside the event loop with isolated tenant contexts."""

import asyncio
import logging
from threading import Event
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_tailor_harness.services.email_notifications import deliver_due
from resume_tailor_harness.tenancy.bootstrap import build_context
from resume_tailor_harness.tenancy.context import use_context
from resume_tailor_harness.tenancy.system_db import User


logger = logging.getLogger(__name__)


def email_notification_tick(state: Any, stop: Event | None = None) -> int:
    if state.system_engine is None:
        return int(deliver_due(state.engine, state.mailer, state.settings, "local"))
    with Session(state.system_engine, expire_on_commit=False) as session:
        query = select(User).where(User.disabled_at.is_(None))
        if state.app_mode == "local":
            query = query.where(User.id == state.default_context.user_id)
        users = list(session.scalars(query))
        session.expunge_all()
    sent = 0
    for user in users:
        if stop is not None and stop.is_set():
            break
        try:
            context = build_context(
                user,
                state.data_dir,
                state.settings,
                state.engine_registry,
                system_engine=state.system_engine,
                template_dir=state.template_config_dir,
            )
            if context.engine is None:
                continue
            with use_context(context):
                # Transport credentials always belong to the platform; content
                # options such as follow-up age use the tenant's effective values.
                settings = state.settings.model_copy(
                    update={"follow_up_days": context.settings.follow_up_days}
                )
                sent += int(
                    deliver_due(context.engine, state.mailer, settings, user.id)
                )
        except Exception:  # one tenant must not stop everyone else's digests
            logger.exception("Email digest failed for workspace %s", user.id)
    return sent


async def email_notification_loop(state: Any) -> None:
    stop = Event()
    while True:
        worker = asyncio.create_task(
            asyncio.to_thread(email_notification_tick, state, stop)
        )
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Do not close workspace engines underneath a running mail worker.
            stop.set()
            await worker
            raise
        except Exception:
            logger.exception("Email notification tick failed")
        await asyncio.sleep(60)
