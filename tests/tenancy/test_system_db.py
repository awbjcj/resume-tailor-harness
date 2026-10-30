from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.tenancy.system_db import (
    AccountEmail,
    UsageEvent,
    User,
    init_system_db,
    make_system_engine,
)
from resume_tailor_harness.tenancy.migrate_system import migrate_system_db


def test_account_email_failure_migration_preserves_pending_notices(tmp_path):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    with Session(engine) as session:
        session.add(
            AccountEmail(
                id="pending-notice",
                user_id="legacy",
                event="account_created",
                recipient="legacy@example.com",
                context_json="{}",
                payload_json='{"to":"legacy@example.com"}',
            )
        )
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE account_emails DROP COLUMN failed_at"))
        connection.execute(
            text("ALTER TABLE account_emails DROP COLUMN failure_reason")
        )
    migrate_system_db(engine)
    migrate_system_db(engine)
    with Session(engine) as session:
        row = session.execute(select(AccountEmail)).scalar_one()
        assert row.id == "pending-notice"
        assert row.payload_json == '{"to":"legacy@example.com"}'
        assert row.failed_at is None and row.failure_reason is None
    engine.dispose()


def test_dashboard_language_is_added_to_existing_accounts_without_data_loss(tmp_path):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    with Session(engine) as session:
        session.add(User(id="legacy", username="legacy", password_hash="hash"))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users DROP COLUMN dashboard_language"))
    migrate_system_db(engine)
    migrate_system_db(engine)
    with Session(engine) as session:
        user = session.get(User, "legacy")
        assert user is not None
        assert user.username == "legacy"
        assert user.dashboard_language == "en"
    engine.dispose()


def test_system_metadata_is_isolated_from_workspace_metadata(tmp_path):
    system_engine = make_system_engine(tmp_path / "data")
    workspace_engine = make_engine(
        f"sqlite:///{(tmp_path / 'workspace.db').as_posix()}"
    )
    init_system_db(system_engine)
    init_db(workspace_engine)
    assert "users" in inspect(system_engine).get_table_names()
    assert "job" not in inspect(system_engine).get_table_names()
    assert "users" not in inspect(workspace_engine).get_table_names()
    system_engine.dispose()
    workspace_engine.dispose()


def test_user_roundtrip_includes_limits_and_last_activity(tmp_path):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    with Session(engine) as session:
        session.add(
            User(
                id="abc123def456", username="alice", password_hash="hash", role="admin"
            )
        )
        session.commit()
    with Session(engine) as session:
        user = session.execute(select(User)).scalar_one()
        assert user.weekly_token_budget is None
        assert user.last_active_at is None
    engine.dispose()


def test_legacy_usage_migration_preserves_tokens_without_inventing_cost(tmp_path):
    engine = make_system_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users (id VARCHAR(12) PRIMARY KEY, username VARCHAR(64), password_hash VARCHAR, role VARCHAR(8))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE usage_events (id INTEGER PRIMARY KEY, user_id VARCHAR(12), ts DATETIME, provider VARCHAR(32), model VARCHAR(160), input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cache_read_tokens INTEGER DEFAULT 0, cache_creation_tokens INTEGER DEFAULT 0, weighted_total FLOAT DEFAULT 0, own_key BOOLEAN DEFAULT 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO usage_events (id, user_id, input_tokens, output_tokens, cache_creation_tokens) VALUES (1, 'abc123def456', 100, 20, 5)"
            )
        )

    init_system_db(engine)

    with Session(engine) as session:
        event = session.get(UsageEvent, 1)
        assert event is not None
        assert event.total_tokens == 120
        assert event.cache_write_tokens == 5
        assert event.cost_micros is None
        assert event.pricing_status == "LEGACY_UNPRICED"
    engine.dispose()


def test_legacy_checkouts_keep_standard_mode_after_additive_migration(tmp_path):
    engine = make_system_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE stripe_checkouts (id VARCHAR(32) PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO stripe_checkouts (id) VALUES ('legacy_pending')")
        )
    init_system_db(engine)
    init_system_db(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT id, managed_payments FROM stripe_checkouts")
        ).one() == ("legacy_pending", 0)
    engine.dispose()
