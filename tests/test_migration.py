import hashlib
import json
import sqlite3

import pytest

from general_agent_os.migrate import migrate_database
from general_agent_os.profile import ProfileError


@pytest.mark.parametrize("double_encoded", [False, True])
def test_migrate_legacy_copy_preserves_original(tmp_path, double_encoded):
    source, target = tmp_path / "old.db", tmp_path / "new.db"
    # A legacy SQL session table with two runs in its JSON runs column.
    with sqlite3.connect(source) as conn:
        conn.execute(
            "CREATE TABLE agno_sessions (session_id TEXT PRIMARY KEY, session_type TEXT, "
            "agent_id TEXT, team_id TEXT, workflow_id TEXT, user_id TEXT, "
            "session_data JSON, agent_data JSON, team_data JSON, workflow_data JSON, "
            "metadata JSON, runs JSON, summary JSON, created_at INTEGER, updated_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO agno_sessions (session_id, session_type, agent_id, runs, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "s1",
                "agent",
                "a1",
                json.dumps(
                    [
                        {
                            "run_id": "r1",
                            "session_id": "s1",
                            "agent_id": "a1",
                            "content": "First",
                            "created_at": 1,
                        },
                        {
                            "run_id": "r2",
                            "session_id": "s1",
                            "agent_id": "a1",
                            "content": "Second",
                            "created_at": 2,
                        },
                    ]
                ),
                1,
                2,
            ),
        )
        if double_encoded:
            raw = conn.execute("SELECT runs FROM agno_sessions").fetchone()[0]
            conn.execute("UPDATE agno_sessions SET runs = ?", (json.dumps(raw),))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = migrate_database(str(source), str(target))
    assert result["verified_legacy_runs"] == 2
    assert result["normalized_json_cells"] == int(double_encoded)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    with sqlite3.connect(target) as conn:
        assert "runs" in {row[1] for row in conn.execute("PRAGMA table_info(agno_sessions)")}
    from agno.db.sqlite import SqliteDb

    db = SqliteDb(db_file=str(target))
    session = db.get_session(session_id="s1")
    assert [run.content for run in session.runs] == ["First", "Second"]


def test_refuse_overwrite(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source):
        pass
    with pytest.raises(ProfileError, match="new file"):
        migrate_database(str(source), str(source))


def test_failed_migration_does_not_publish_output(tmp_path):
    source, target = tmp_path / "bad.db", tmp_path / "output.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE unrelated (id TEXT)")
    with pytest.raises(ProfileError, match="session table"):
        migrate_database(str(source), str(target))
    assert not target.exists()
