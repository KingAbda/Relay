"""Forward, rollback, and fail-closed tests for Relay's legacy adoption path."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

import sqlalchemy as sa

from tests import legacy_schema


ROOT = Path(__file__).resolve().parents[1]
LEGACY_REVISION = "20260713_00"
LEGACY_ADOPTION_REVISION = "20260713_01"
HEAD_REVISION = "20260731_01"


def _user(user_id, email, name):
    now = datetime(2026, 7, 1, 12, 0, 0)
    return {
        "id": user_id,
        "email": email,
        "password_hash": f"hash-{user_id}",
        "full_name": name,
        "bio": f"Bio for {name}",
        "avatar_url": "",
        "email_verified": True,
        "verification_token": f"verify-{user_id}",
        "account_locked_until": None,
        "failed_login_attempts": 0,
        "onboarded": True,
        "created_at": now,
        "last_active": now,
        "referred_by": None,
        "school": "NYU",
        "major": "Art",
        "graduation_year": "2027",
        "profile_photo": "",
        "edu_verified": True,
        "verification_code": "123456",
        "verification_code_sent_at": now,
        "completed_sessions_count": 1,
        "no_show_count": 0,
        "reported_count": 0,
        "is_ambassador": False,
        "has_proof_video": False,
        "proof_video_url": "",
        "content_credit_balance": 0,
        "is_member": False,
        "member_since": None,
    }


def seed_representative_legacy_data(engine):
    now = datetime(2026, 7, 1, 12, 0, 0)
    with engine.begin() as connection:
        connection.execute(
            legacy_schema.users.insert(),
            [_user("teacher", "teacher@example.invalid", "Teacher"),
             _user("learner", "learner@example.invalid", "Learner")],
        )
        connection.execute(
            legacy_schema.credit_accounts.insert(),
            [
                {"id": "acct-teacher", "user_id": "teacher", "balance": 5.0},
                {"id": "acct-learner", "user_id": "learner", "balance": 2.0},
            ],
        )
        connection.execute(
            legacy_schema.credit_transactions.insert(),
            [
                {"id": "tx-teacher", "user_id": "teacher", "amount": 5.0,
                 "type": "BONUS", "description": "Legacy grant",
                 "related_user_id": None, "created_at": now},
                {"id": "tx-learner-grant", "user_id": "learner", "amount": 3.0,
                 "type": "BONUS", "description": "Legacy grant",
                 "related_user_id": None, "created_at": now},
                {"id": "tx-learner-hold", "user_id": "learner", "amount": -1.0,
                 "type": "SPEND", "description": "Legacy hold",
                 "related_user_id": "teacher", "created_at": now},
            ],
        )
        connection.execute(legacy_schema.sessions.insert(), {
            "id": "session-1", "teacher_id": "teacher", "learner_id": "learner",
            "skill_name": "Watercolor", "status": "CONFIRMED", "notes": "Meet in lobby",
            "scheduled_at": now, "completed_at": None, "meet_link": None,
            "created_at": now, "amount_charged": 1.0,
            "teacher_completed": False, "learner_completed": False,
        })
        connection.execute(legacy_schema.session_series.insert(), {
            "id": "series-1", "teacher_id": "teacher", "learner_id": "learner",
            "skill_name": "Watercolor", "total_sessions": 2, "completed_sessions": 1,
            "credit_cost_per_session": 1, "status": "active", "created_at": now,
        })
        connection.execute(legacy_schema.user_skills.insert(), {
            "id": "skill-1", "user_id": "teacher", "name": "Watercolor",
            "category": "CREATIVE", "description": "Basics", "proficiency": 4,
            "is_active": True, "created_at": now, "credit_cost": 1,
        })
        connection.execute(legacy_schema.user_wants.insert(), {
            "id": "want-1", "user_id": "learner", "name": "Watercolor",
            "category": "CREATIVE", "description": "Learn washes",
        })
        connection.execute(legacy_schema.skill_requests.insert(), {
            "id": "request-1", "user_id": "learner", "name": "Watercolor",
            "category": "CREATIVE", "description": "Intro", "max_credits": 1,
            "claimed_by": "teacher", "status": "claimed", "created_at": now,
        })
        connection.execute(legacy_schema.session_reviews.insert(), {
            "id": "review-1", "session_id": "session-1", "reviewer_id": "learner",
            "reviewee_id": "teacher", "rating": 5, "review": "Helpful", "created_at": now,
        })
        connection.execute(legacy_schema.waitlist_entries.insert(), {
            "id": "wait-1", "email": "wait@example.invalid", "signed_up": now,
        })
        connection.execute(legacy_schema.password_reset_tokens.insert(), {
            "id": "reset-1", "user_id": "learner", "token": "raw-reset-token",
            "expires_at": now, "used": False, "created_at": now,
        })


class MigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="relay-migration-")
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "relay.sqlite"
        self.database_url = f"sqlite:///{self.database_path}"

    def run_db(self, *arguments, expect_success=True):
        environment = os.environ.copy()
        environment.update({
            "DATABASE_URL": self.database_url,
            "RELAY_ENV": "test",
            "RELAY_SECRET_KEY": "migration-test-only-secret",
            "RATE_LIMIT_STORAGE": "memory://",
        })
        result = subprocess.run(
            [sys.executable, "-m", "flask", "--app", "app.main", "db", *arguments],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if expect_success and result.returncode:
            self.fail(f"migration command failed:\n{result.stdout}\n{result.stderr}")
        return result

    def create_seeded_legacy_database(self):
        engine = sa.create_engine(self.database_url)
        legacy_schema.create_legacy_schema(engine)
        seed_representative_legacy_data(engine)
        engine.dispose()
        self.run_db("stamp", LEGACY_REVISION)

    def test_representative_legacy_upgrade_and_rollback_preserve_core_data(self):
        self.create_seeded_legacy_database()
        expected_counts = {
            "users": 2,
            "credit_accounts": 2,
            "credit_transactions": 3,
            "sessions": 1,
            "session_series": 1,
            "user_skills": 1,
            "user_wants": 1,
            "skill_requests": 1,
            "session_reviews": 1,
            "waitlist_entries": 1,
            "password_reset_tokens": 1,
        }
        self.run_db("upgrade", "head")

        engine = sa.create_engine(self.database_url)
        inspector = sa.inspect(engine)
        self.assertIn("role", {column["name"] for column in inspector.get_columns("users")})
        self.assertIn("moderation_actions", inspector.get_table_names())
        with engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar(), HEAD_REVISION)
            users = connection.execute(sa.text("SELECT id, role, account_status FROM users ORDER BY id")).all()
            self.assertEqual(users, [("learner", "user", "active"), ("teacher", "user", "active")])
            accounts = connection.execute(sa.text("SELECT user_id, balance FROM credit_accounts ORDER BY user_id")).all()
            self.assertEqual(accounts, [("learner", 2), ("teacher", 5)])
            transactions = connection.execute(sa.text(
                "SELECT id, amount, type, source_type, source_id, idempotency_key "
                "FROM credit_transactions ORDER BY id"
            )).all()
            self.assertEqual([row[0] for row in transactions], ["tx-learner-grant", "tx-learner-hold", "tx-teacher"])
            self.assertEqual([row[1] for row in transactions], [3, -1, 5])
            self.assertTrue(all(row[3] == "legacy" and row[4] == row[0] and row[5] == f"legacy:{row[0]}" for row in transactions))
            session_row = connection.execute(sa.text(
                "SELECT id, teacher_id, learner_id, amount_charged, cancellation_reason FROM sessions"
            )).one()
            self.assertEqual(session_row, ("session-1", "teacher", "learner", 1, ""))
            reset_hash = connection.execute(sa.text(
                "SELECT token_hash FROM password_reset_tokens WHERE id = 'reset-1'"
            )).scalar_one()
            self.assertEqual(reset_hash, hashlib.sha256(b"raw-reset-token").hexdigest())
            for table, expected in expected_counts.items():
                self.assertEqual(
                    connection.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one(),
                    expected,
                )
        engine.dispose()

        self.run_db("downgrade", LEGACY_REVISION)
        engine = sa.create_engine(self.database_url)
        inspector = sa.inspect(engine)
        self.assertNotIn("role", {column["name"] for column in inspector.get_columns("users")})
        self.assertNotIn("moderation_actions", inspector.get_table_names())
        with engine.connect() as connection:
            for table, expected in expected_counts.items():
                self.assertEqual(
                    connection.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one(),
                    expected,
                )
            self.assertEqual(connection.execute(sa.text("SELECT balance FROM credit_accounts WHERE user_id='learner'")).scalar_one(), 2.0)
            self.assertEqual(connection.execute(sa.text("SELECT type FROM credit_transactions WHERE id='tx-learner-hold'")).scalar_one(), "SPEND")
            self.assertEqual(connection.execute(sa.text("SELECT COUNT(*) FROM password_reset_tokens")).scalar_one(), 1)
        engine.dispose()

    def test_preflight_rejects_fractional_balance_without_schema_or_data_change(self):
        engine = sa.create_engine(self.database_url)
        legacy_schema.create_legacy_schema(engine)
        now = datetime(2026, 7, 1, 12, 0, 0)
        with engine.begin() as connection:
            connection.execute(legacy_schema.users.insert(), _user("fractional", "f@example.invalid", "Fractional"))
            connection.execute(legacy_schema.credit_accounts.insert(), {
                "id": "acct-fractional", "user_id": "fractional", "balance": 1.5,
            })
            connection.execute(legacy_schema.credit_transactions.insert(), {
                "id": "tx-fractional", "user_id": "fractional", "amount": 1.5,
                "type": "BONUS", "description": "Unsafe fraction",
                "related_user_id": None, "created_at": now,
            })
        engine.dispose()
        self.run_db("stamp", LEGACY_REVISION)
        result = self.run_db("upgrade", "head", expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a finite integer", result.stderr)

        engine = sa.create_engine(self.database_url)
        inspector = sa.inspect(engine)
        self.assertIn("verification_token", {column["name"] for column in inspector.get_columns("users")})
        self.assertNotIn("role", {column["name"] for column in inspector.get_columns("users")})
        with engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text("SELECT balance FROM credit_accounts")).scalar_one(), 1.5)
            self.assertEqual(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one(), LEGACY_REVISION)
        engine.dispose()

    def test_downgrade_refuses_new_audit_data_without_partial_change(self):
        self.create_seeded_legacy_database()
        self.run_db("upgrade", "head")
        engine = sa.create_engine(self.database_url)
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO consent_acceptances "
                "(id, user_id, document, version, accepted_at) "
                "VALUES ('consent-new', 'learner', 'terms', 'current', '2026-07-13 12:00:00')"
            ))
        engine.dispose()

        result = self.run_db("downgrade", LEGACY_REVISION, expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("consent_acceptances contains new-schema records", result.stderr)

        engine = sa.create_engine(self.database_url)
        inspector = sa.inspect(engine)
        self.assertIn("role", {column["name"] for column in inspector.get_columns("users")})
        with engine.connect() as connection:
            # Alembic unwinds one revision at a time. `auth_events` is empty here,
            # so 20260731_01 rolls back cleanly and the chain halts at the legacy
            # adoption guard. No business data is touched, which is what this test
            # is protecting; the audit table gets its own refusal test below.
            self.assertEqual(
                connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one(),
                LEGACY_ADOPTION_REVISION,
            )
            self.assertEqual(
                connection.execute(sa.text("SELECT COUNT(*) FROM consent_acceptances")).scalar_one(),
                1,
            )
            self.assertEqual(connection.execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one(), 2)
        engine.dispose()

    def test_downgrade_refuses_to_discard_recorded_auth_events(self):
        """Rolling back must never silently destroy the authentication trail."""
        self.create_seeded_legacy_database()
        self.run_db("upgrade", "head")
        engine = sa.create_engine(self.database_url)
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO auth_events "
                "(id, user_id, event, email_hash, ip_hash, request_id, created_at) "
                "VALUES ('auth-1', 'learner', 'login_succeeded', 'hash', 'hash', 'req', "
                "'2026-07-31 12:00:00')"
            ))
        engine.dispose()

        result = self.run_db("downgrade", LEGACY_ADOPTION_REVISION, expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("auth_events contains 1 audit record(s)", result.stderr)

        engine = sa.create_engine(self.database_url)
        with engine.connect() as connection:
            self.assertEqual(
                connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one(),
                HEAD_REVISION,
            )
            self.assertEqual(
                connection.execute(sa.text("SELECT COUNT(*) FROM auth_events")).scalar_one(), 1
            )
        engine.dispose()

    def test_fresh_database_upgrades_to_head_without_schema_drift(self):
        self.run_db("upgrade", "head")
        check = self.run_db("check")
        self.assertIn(
            "No new upgrade operations detected",
            check.stdout + check.stderr,
        )


if __name__ == "__main__":
    unittest.main()
