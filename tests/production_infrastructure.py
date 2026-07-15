"""Production-shaped boot against acknowledged disposable PostgreSQL and Redis.

This explicit suite drops the PostgreSQL public schema and flushes Redis database
15. It never runs through default discovery.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlparse

from redis import Redis
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[1]
POSTGRES_URL = os.environ.get("RELAY_TEST_POSTGRES_URL", "").strip()
REDIS_URL = os.environ.get("RELAY_TEST_REDIS_URL", "").strip()
POSTGRES_OK = os.environ.get("RELAY_POSTGRES_TEST_DESTRUCTIVE_OK", "").lower() == "true"
REDIS_OK = os.environ.get("RELAY_REDIS_TEST_DESTRUCTIVE_OK", "").lower() == "true"


def _authorized_infrastructure() -> bool:
    postgres = urlparse(POSTGRES_URL)
    redis = urlparse(REDIS_URL)
    postgres_name = postgres.path.rsplit("/", 1)[-1].lower()
    try:
        redis_database = int((redis.path or "/0").lstrip("/") or "0")
    except ValueError:
        return False
    return (
        POSTGRES_OK
        and REDIS_OK
        and postgres.scheme.startswith("postgresql")
        and postgres.hostname in {"127.0.0.1", "localhost", "::1"}
        and any(marker in postgres_name for marker in ("test", "rehearsal", "ci"))
        and redis.scheme in {"redis", "rediss"}
        and redis.hostname in {"127.0.0.1", "localhost", "::1"}
        and redis_database == 15
    )


@unittest.skipUnless(
    _authorized_infrastructure(),
    "requires acknowledged localhost disposable PostgreSQL and Redis database 15",
)
class ProductionInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = sa.create_engine(POSTGRES_URL)
        cls.cache = Redis.from_url(REDIS_URL)
        cls.cache.ping()
        cls._reset_database()
        cls.cache.flushdb()
        os.environ.update({
            "RELAY_ENV": "production",
            "RELAY_SECRET_KEY": "production-infrastructure-test-only-secret-value",
            "RELAY_TRIAL_CATEGORY": "creative",
            "RELAY_PUBLIC_URL": "https://relay.test",
            "RELAY_TRUSTED_HOSTS": "relay.test",
            "RELAY_PROXY_X_FOR": "1",
            "RELAY_PROXY_X_PROTO": "1",
            "RELAY_PROXY_X_HOST": "0",
            # Render-managed Postgres exposes a plain postgresql:// URL. The
            # application must select the installed Psycopg 3 dialect itself.
            "DATABASE_URL": POSTGRES_URL.replace(
                "postgresql+psycopg://", "postgresql://", 1
            ),
            "RATE_LIMIT_STORAGE": REDIS_URL,
            "RELAY_EMAIL_BACKEND": "smtp",
            "RELAY_SMTP_HOST": "smtp.example.invalid",
            "RELAY_EMAIL_FROM": "relay@example.invalid",
            "RELAY_REQUIRE_INVITE": "true",
            "RELAY_INVITED_EMAILS": ",".join(
                f"student{number:02d}@nyu.edu" for number in range(1, 11)
            ),
        })

    @classmethod
    def _reset_database(cls):
        with cls.engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))

    @classmethod
    def tearDownClass(cls):
        cls.cache.flushdb()
        cls.cache.close()
        cls._reset_database()
        cls.engine.dispose()

    def run_db(self, *arguments):
        result = subprocess.run(
            [sys.executable, "-m", "flask", "--app", "app.main", "db", *arguments],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            self.fail(f"migration command failed:\n{result.stdout}\n{result.stderr}")
        return result

    def test_migrated_production_boot_readiness_and_live_limiter(self):
        self.run_db("upgrade", "head")
        current = self.run_db("current")
        drift = self.run_db("check")
        self.assertIn("20260713_01", current.stdout + current.stderr)
        self.assertIn("No new upgrade operations detected", drift.stdout + drift.stderr)

        from app.main import app, db

        with app.app_context():
            self.assertEqual(db.engine.dialect.name, "postgresql")
            self.assertEqual(db.engine.dialect.driver, "psycopg")
        client = app.test_client()
        readiness = client.get("/health/ready", base_url="https://relay.test")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.get_json(), {"status": "ready"})

        limited = client.get(
            "/login",
            base_url="https://relay.test",
            headers={
                "X-Forwarded-For": "198.51.100.44, 203.0.113.17",
                "X-Forwarded-Proto": "http, https",
            },
        )
        self.assertEqual(limited.status_code, 200)
        keys = [key.decode() for key in self.cache.scan_iter("*")]
        self.assertTrue(any("203.0.113.17" in key for key in keys))
        self.assertFalse(any("198.51.100.44" in key for key in keys))


if __name__ == "__main__":
    unittest.main(verbosity=2)
