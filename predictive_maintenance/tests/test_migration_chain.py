import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CWD = REPO_ROOT / "predictive_maintenance"


def _run_alembic(args, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        ["alembic", *args],
        cwd=str(ALEMBIC_CWD),
        env=merged_env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"alembic {' '.join(args)} failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    return proc.stdout


@pytest.mark.integration
def test_alembic_heads_and_upgrade_sql(tmp_path):
    sqlite_path = tmp_path / "chain.sqlite3"
    env = {"PDM_DB_URL": f"sqlite:///{sqlite_path}"}
    _run_alembic(["heads"], env=env)
    sql_output = _run_alembic(["upgrade", "head", "--sql"], env=env)
    assert "CREATE TABLE" in sql_output or "ALTER TABLE" in sql_output


@pytest.mark.integration
def test_alembic_upgrade_downgrade_sqlite_smoke(tmp_path):
    sqlite_path = tmp_path / "smoke.sqlite3"
    env = {"PDM_DB_URL": f"sqlite:///{sqlite_path}"}
    _run_alembic(["upgrade", "head"], env=env)
    _run_alembic(["downgrade", "base"], env=env)


@pytest.mark.integration
def test_alembic_upgrade_downgrade_postgres_smoke():
    pg_url = os.getenv("PDM_TEST_POSTGRES_URL")
    if not pg_url:
        pytest.skip("PDM_TEST_POSTGRES_URL not set; skipping postgres migration smoke test")
    env = {"PDM_DB_URL": pg_url}
    _run_alembic(["upgrade", "head"], env=env)
    _run_alembic(["downgrade", "base"], env=env)
