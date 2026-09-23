"""Migrate only a NEW SQLite copy and verify all legacy session/run identities."""

import asyncio
import json
import sqlite3
from pathlib import Path

from .profile import ProfileError


def migrate_database(source: str, output: str, session_table: str = "agno_sessions") -> dict:
    from agno.db.migrations.manager import MigrationManager
    from agno.db.sqlite import SqliteDb

    src, dst = Path(source).resolve(), Path(output).resolve()
    if not src.is_file():
        raise ProfileError("Source database does not exist")
    if dst.exists() or dst == src:
        raise ProfileError("Migration output must be a new file; the source is never modified")
    # Quote the identifier rather than interpolating it as SQL code.
    table = '"' + session_table.replace('"', '""') + '"'
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src.as_uri() + "?mode=ro", uri=True) as original, sqlite3.connect(dst) as copied:
        original.backup(copied)
    expected = []
    with sqlite3.connect(dst) as copied:
        columns = {row[1] for row in copied.execute(f"PRAGMA table_info({table})")}
        if "session_id" not in columns:
            raise ProfileError("The specified session table does not exist or is not an Agno session table")
        if "runs" in columns:
            for sid, value in copied.execute(f"SELECT session_id, runs FROM {table}"):
                for run in json.loads(value or "[]"):
                    if not run.get("run_id"):
                        raise ProfileError("Legacy run has no run_id; inspect the migration copy manually")
                    expected.append((sid, run))
    database = SqliteDb(db_file=str(dst), session_table=session_table)
    asyncio.run(MigrationManager(database).up())
    missing = []
    for sid, original_run in expected:
        row = database.get_run(run_id=original_run["run_id"], deserialize=False)
        if (
            not row
            or row.get("session_id") != sid
            or any(row["run_data"].get(k) != v for k, v in original_run.items())
        ):
            missing.append(original_run["run_id"])
    if missing:
        raise ProfileError(
            f"Migration verification failed for {len(missing)} legacy runs; keep using the source"
        )
    return {
        "source": str(src),
        "output": str(dst),
        "verified_legacy_runs": len(expected),
        "legacy_columns_preserved": True,
    }
