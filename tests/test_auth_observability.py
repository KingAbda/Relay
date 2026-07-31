"""Regression tests for the authentication audit trail and log emission.

Two failure modes are covered:

1. `app.logger.info(...)` being silently discarded. Flask leaves `app.logger` at
   NOTSET, so it inherits the root logger's WARNING default and every structured
   request line is dropped before reaching a handler. That is invisible in normal
   use — the code looks correct and simply produces nothing.
2. Authentication events leaving no durable record, so an operator cannot tell
   whether a participant ever signed in, mistyped a password, or hit the lockout.
"""

import json
import logging
import os
import re
import unittest


os.environ.update({
    "DATABASE_URL": "sqlite://",
    "RELAY_ENV": "test",
    "RELAY_TRIAL_CATEGORY": "creative",
    "RELAY_EMAIL_BACKEND": "memory",
    "RELAY_PUBLIC_URL": "http://localhost",
    "RELAY_REQUIRE_INVITE": "false",
})

from app.main import DATABASE_SCHEMA_REVISION, app, db, hash_secret, limiter
from app.models import AuthEvent, User
from sqlalchemy import text
from werkzeug.security import generate_password_hash


CSRF_PATTERN = re.compile(rb'name="csrf_token" value="([^"]+)"')
PASSWORD = "Str0ng!Passw0rd"


class AuthObservabilityTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        app.extensions["relay_outbox"] = []
        # These tests deliberately exhaust the per-email login limit, and the
        # in-memory limiter store is shared across the whole process.
        limiter.reset()
        self.client = app.test_client()
        with app.app_context():
            db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
            db.drop_all()
            db.create_all()
            db.session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            db.session.execute(
                text(f"INSERT INTO alembic_version VALUES ('{DATABASE_SCHEMA_REVISION}')")
            )
            user = User(
                email="participant@nyu.edu",
                password_hash=generate_password_hash(PASSWORD),
                full_name="Trial Participant",
                email_verified=True,
                edu_verified=True,
                onboarded=True,
            )
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id

    def events(self, **filters):
        with app.app_context():
            query = AuthEvent.query
            for column, value in filters.items():
                query = query.filter(getattr(AuthEvent, column) == value)
            return query.order_by(AuthEvent.created_at).all()

    # ── Log emission ──────────────────────────────────────────

    def test_request_log_line_is_actually_emitted(self):
        """The structured per-request line must reach a handler, not just be built."""
        with self.assertLogs(app.logger, level="INFO") as captured:
            self.client.get("/")
        payloads = [
            json.loads(record.message)
            for record in captured.records
            if record.message.startswith("{")
        ]
        request_lines = [p for p in payloads if p.get("event") == "http_request"]
        self.assertEqual(len(request_lines), 1, "expected exactly one http_request line")
        line = request_lines[0]
        self.assertEqual(line["endpoint"], "home")
        self.assertEqual(line["status"], 200)
        self.assertIn("request_id", line)
        self.assertIn("duration_ms", line)

    def test_app_logger_passes_info_records(self):
        """Guards the specific regression: effective level silently back at WARNING."""
        self.assertTrue(
            app.logger.isEnabledFor(logging.INFO),
            "app.logger must accept INFO or the entire request audit trail is dropped",
        )

    def test_request_logging_does_not_double_emit(self):
        """A root handler added alongside Flask's own would duplicate every line."""
        with self.assertLogs(app.logger, level="INFO") as captured:
            self.client.get("/")
        http_lines = [
            record for record in captured.records
            if record.message.startswith("{") and '"http_request"' in record.message
        ]
        self.assertEqual(len(http_lines), 1)

    # ── Audit trail ───────────────────────────────────────────

    def test_successful_login_is_recorded(self):
        response = self.client.post(
            "/login", data={"email": "participant@nyu.edu", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 302)
        recorded = self.events(event="login_succeeded")
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].user_id, self.user_id)

    def test_failed_login_is_recorded_against_the_account(self):
        self.client.post(
            "/login", data={"email": "participant@nyu.edu", "password": "wrong-password"}
        )
        recorded = self.events(event="login_failed")
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].user_id, self.user_id)

    def test_failed_login_for_unknown_address_is_still_correlatable(self):
        """No user row exists, so email_hash is the only thread between attempts."""
        for _ in range(2):
            self.client.post(
                "/login", data={"email": "stranger@nyu.edu", "password": "whatever"}
            )
        recorded = self.events(event="login_failed")
        self.assertEqual(len(recorded), 2)
        self.assertTrue(all(row.user_id is None for row in recorded))
        expected = hash_secret("stranger@nyu.edu")
        self.assertTrue(all(row.email_hash == expected for row in recorded))

    def test_lockout_is_recorded_once_then_blocks_are_recorded(self):
        for _ in range(5):
            self.client.post(
                "/login", data={"email": "participant@nyu.edu", "password": "wrong-password"}
            )
        self.assertEqual(len(self.events(event="account_locked")), 1)
        self.assertEqual(len(self.events(event="login_failed")), 5)

        blocked = self.client.post(
            "/login", data={"email": "participant@nyu.edu", "password": PASSWORD}
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(len(self.events(event="login_blocked_locked")), 1)

    def test_logout_is_attributed_before_the_session_is_cleared(self):
        self.client.post(
            "/login", data={"email": "participant@nyu.edu", "password": PASSWORD}
        )
        self.client.post("/logout")
        recorded = self.events(event="logout")
        self.assertEqual(len(recorded), 1)
        self.assertEqual(
            recorded[0].user_id, self.user_id,
            "logout must resolve the user before session.clear()",
        )
        self.assertEqual(
            recorded[0].email_hash, hash_secret("participant@nyu.edu"),
            "logout without an email hash is invisible to `auth-log --email`",
        )

    def test_password_reset_request_is_recorded(self):
        self.client.post("/forgot-password", data={"email": "participant@nyu.edu"})
        self.assertEqual(len(self.events(event="password_reset_requested")), 1)

    # ── Privacy ───────────────────────────────────────────────

    def test_no_raw_email_or_ip_is_persisted(self):
        self.client.post(
            "/login", data={"email": "participant@nyu.edu", "password": PASSWORD}
        )
        with app.app_context():
            for row in AuthEvent.query.all():
                stored = f"{row.email_hash or ''}{row.ip_hash or ''}"
                self.assertNotIn("participant@nyu.edu", stored)
                self.assertNotIn("127.0.0.1", stored)
                if row.email_hash:
                    self.assertEqual(len(row.email_hash), 64)
                if row.ip_hash:
                    self.assertEqual(len(row.ip_hash), 64)

    def test_auth_event_log_line_carries_no_identifier(self):
        with self.assertLogs(app.logger, level="INFO") as captured:
            self.client.post(
                "/login", data={"email": "participant@nyu.edu", "password": PASSWORD}
            )
        combined = "\n".join(record.message for record in captured.records)
        self.assertIn("auth_event", combined)
        self.assertNotIn("participant@nyu.edu", combined)

    # ── Resilience ────────────────────────────────────────────

    def test_login_still_succeeds_when_the_audit_write_fails(self):
        """An audit trail that can break sign-in is worse than one with a gap."""
        with app.app_context():
            db.session.execute(text("DROP TABLE auth_events"))
            db.session.commit()
        response = self.client.post(
            "/login", data={"email": "participant@nyu.edu", "password": PASSWORD}
        )
        self.assertEqual(
            response.status_code, 302,
            "a failed audit insert must not block authentication",
        )


if __name__ == "__main__":
    unittest.main()
