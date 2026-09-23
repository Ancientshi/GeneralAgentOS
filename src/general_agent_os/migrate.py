"""Migrate only a NEW SQLite copy and verify all legacy session/run identities."""

import asyncio
import json
import os
import sqlite3
import tempfile
from contextlib import closing
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
    fd, staging = tempfile.mkstemp(prefix=".gaos-migration-", suffix=".db", dir=dst.parent)
    os.close(fd)
    with (
        closing(sqlite3.connect(src.as_uri() + "?mode=ro", uri=True)) as original,
        closing(sqlite3.connect(staging)) as copied,
    ):
        original.backup(copied)
    expected = []
    normalized_cells = 0
    with closing(sqlite3.connect(staging)) as copied:
        columns = {row[1] for row in copied.execute(f"PRAGMA table_info({table})")}
        if "session_id" not in columns:
            raise ProfileError("The specified session table does not exist or is not an Agno session table")
        # Some legacy deployments stored JSON strings inside JSON columns. Normalize
        # structural fields on the staging copy before Agno reads them through SQLAlchemy.
        for field in sorted(
            columns
            & {"runs", "session_data", "agent_data", "team_data", "workflow_data", "metadata", "summary"}
        ):
            for sid, raw in copied.execute(f'SELECT session_id, "{field}" FROM {table}').fetchall():
                if raw is None:
                    continue
                value = json.loads(raw)
                if isinstance(value, str):
                    try:
                        nested = json.loads(value)
                    except (ValueError, TypeError):
                        raise ProfileError(
                            f"Invalid legacy JSON in {field}; inspect staging copy {staging}"
                        ) from None
                    if not isinstance(nested, (dict, list)) and nested is not None:
                        raise ProfileError(f"Unexpected legacy JSON structure in {field}")
                    copied.execute(
                        f'UPDATE {table} SET "{field}" = ? WHERE session_id = ?', (json.dumps(nested), sid)
                    )
                    normalized_cells += 1
        copied.commit()
        if "runs" in columns:
            for sid, value in copied.execute(f"SELECT session_id, runs FROM {table}"):
                runs = json.loads(value or "[]") or []
                if not isinstance(runs, list):
                    raise ProfileError("Legacy runs must be a list; inspect the migration staging copy")
                for run in runs:
                    if not isinstance(run, dict) or not run.get("run_id"):
                        raise ProfileError("Legacy run has no run_id; inspect the migration copy manually")
                    expected.append((sid, run))
    database = SqliteDb(db_file=staging, session_table=session_table)
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
    database.db_engine.dispose()
    # Publish only a fully verified database; refuse an output created concurrently.
    os.link(staging, dst)
    Path(staging).unlink()
    return {
        "source": str(src),
        "output": str(dst),
        "verified_legacy_runs": len(expected),
        "legacy_columns_preserved": True,
        "normalized_json_cells": normalized_cells,
    }
