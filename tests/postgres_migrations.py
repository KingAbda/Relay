"""Destructive PostgreSQL migration rehearsal for an explicitly disposable DB.

This module is intentionally excluded from default discovery. It destroys and
recreates the public schema only when both environment guards are present and
the database name is visibly test-shaped.
"""

import os
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlparse

import sqlalchemy as sa

from tests import legacy_schema
from tests.test_migrations import seed_representative_legacy_data


ROOT = Path(__file__).resolve().parents[1]
POSTGRES_URL = os.environ.get("RELAY_TEST_POSTGRES_URL", "").strip()
DESTRUCTIVE_OK = os.environ.get("RELAY_POSTGRES_TEST_DESTRUCTIVE_OK", "").lower() == "true"


def _authorized_test_database():
    if not POSTGRES_URL or not DESTRUCTIVE_OK:
        return False
    parsed = urlparse(POSTGRES_URL)
    database_name = parsed.path.rsplit("/", 1)[-1].lower()
    return parsed.scheme.startswith("postgresql") and any(
        marker in database_name for marker in ("test", "rehearsal", "ci")
    )


@unittest.skipUnless(
    _authorized_test_database(),
    "requires a disposable test-shaped RELAY_TEST_POSTGRES_URL and "
    "RELAY_POSTGRES_TEST_DESTRUCTIVE_OK=true",
)
class PostgreSQLMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = sa.create_engine(POSTGRES_URL)
        with self.engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
        self.engine.dispose()

    def run_db(self, *arguments):
        environment = os.environ.copy()
        environment.update({
            "DATABASE_URL": POSTGRES_URL,
            "RELAY_ENV": "test",
            "RELAY_SECRET_KEY": "postgres-migration-test-only-secret",
            "RATE_LIMIT_STORAGE": "memory://",
        })
        result = subprocess.run(
            [sys.executable, "-m", "flask", "--app", "app.main", "db", *arguments],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            self.fail(f"migration command failed:\n{result.stdout}\n{result.stderr}")
        return result

    def test_representative_legacy_upgrade_and_rollback(self):
        legacy_schema.create_legacy_schema(self.engine)
        seed_representative_legacy_data(self.engine)
        self.run_db("stamp", "20260713_00")
        self.run_db("upgrade", "head")
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one(),
                "20260806_01",
            )
            self.assertEqual(
                connection.execute(sa.text("SELECT balance FROM credit_accounts WHERE user_id='learner'")).scalar_one(),
                2,
            )
            self.assertEqual(
                connection.execute(sa.text("SELECT COUNT(*) FROM credit_transactions")).scalar_one(),
                3,
            )
            self.assertEqual(
                connection.execute(sa.text("SELECT amount_charged FROM sessions WHERE id='session-1'")).scalar_one(),
                1,
            )

        self.run_db("downgrade", "20260713_00")
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one(), 2)
            self.assertEqual(connection.execute(sa.text("SELECT COUNT(*) FROM sessions")).scalar_one(), 1)
            self.assertEqual(
                connection.execute(sa.text("SELECT type::text FROM credit_transactions WHERE id='tx-learner-hold'")).scalar_one(),
                "SPEND",
            )

    def test_fresh_upgrade_has_no_model_drift(self):
        self.run_db("upgrade", "head")
        result = self.run_db("check")
        self.assertIn("No new upgrade operations detected", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
