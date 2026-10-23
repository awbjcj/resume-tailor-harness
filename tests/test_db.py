import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import select

from resume_tailor_harness.db import get_session, init_db, make_engine
from resume_tailor_harness.tracking.tables import Job


def test_make_engine_creates_sqlite_parent_dir(tmp_path):
    db_path = tmp_path / "nested" / "dir" / "test.db"
    engine = make_engine(f"sqlite:///{db_path}")
    init_db(engine)
    assert db_path.parent.exists()


def test_init_db_creates_tables_and_session_round_trips(tmp_path):
    db_path = tmp_path / "test.db"
    engine = make_engine(f"sqlite:///{db_path}")
    init_db(engine)

    with get_session(engine) as session:
        session.add(Job(source="linkedin", jd_text="hello"))
        session.commit()

    with get_session(engine) as session:
        jobs = session.exec(select(Job)).all()
        assert len(jobs) == 1
        assert jobs[0].source == "linkedin"


def test_file_sqlite_gets_wal_and_busy_timeout(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    init_db(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
        assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1


def test_memory_sqlite_keeps_concurrent_readers_alive(caplog):
    engine = make_engine("sqlite://")
    init_db(engine)
    with get_session(engine) as session:
        session.add(Job(source="manual", title="Shared job"))
        session.commit()

    # More simultaneous readers than SingletonThreadPool's five-thread limit
    # reproduces its eviction of connections that are still checked out.
    ready = threading.Barrier(8)

    def read_job():
        with get_session(engine) as session:
            session.connection()
            ready.wait(timeout=10)
            return session.exec(select(Job.title)).all()

    try:
        with caplog.at_level(logging.ERROR, logger="sqlalchemy.pool"):
            with ThreadPoolExecutor(max_workers=8) as workers:
                results = list(workers.map(lambda _: read_job(), range(8)))
        assert results == [["Shared job"]] * 8
        assert not [
            record
            for record in caplog.records
            if record.name.startswith("sqlalchemy.pool")
            and record.levelno >= logging.ERROR
        ]
        with get_session(engine) as session:
            assert session.exec(select(Job.title)).all() == ["Shared job"]
    finally:
        engine.dispose()


def test_memory_sqlite_rollback_cannot_discard_another_sessions_work():
    engine = make_engine("sqlite://")
    init_db(engine)

    def rollback_reader():
        with get_session(engine) as session:
            session.connection().exec_driver_sql("SELECT 1")
            session.rollback()

    try:
        with get_session(engine) as writer:
            writer.add(Job(source="manual", title="Pending job"))
            writer.flush()
            with ThreadPoolExecutor(max_workers=1) as workers:
                workers.submit(rollback_reader).result(timeout=10)
            writer.commit()
        with get_session(engine) as session:
            assert session.exec(select(Job.title)).all() == ["Pending job"]
    finally:
        engine.dispose()
