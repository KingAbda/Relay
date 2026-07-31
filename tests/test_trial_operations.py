"""Tests for trial operations: moderator provisioning and verification link lifetime.

Both cover gaps that only show up once real participants are using the product:
a safety queue nobody can reach, and verification links that die overnight.
"""

import os
import re
import unittest
from datetime import timedelta


os.environ.update({
    "DATABASE_URL": "sqlite://",
    "RELAY_ENV": "test",
    "RELAY_TRIAL_CATEGORY": "creative",
    "RELAY_EMAIL_BACKEND": "memory",
    "RELAY_PUBLIC_URL": "http://localhost",
    "RELAY_REQUIRE_INVITE": "false",
})

from app.main import (
    DATABASE_SCHEMA_REVISION,
    VERIFICATION_LINK_TTL,
    app,
    db,
    limiter,
    make_moderator_cli,
)
from app.models import User
from sqlalchemy import text


CONSENT = {
    key: "yes" for key in
    ("accept_terms", "accept_privacy", "confirm_age", "accept_conduct", "accept_safety")
}
PASSWORD = "Str0ng!Passw0rd"


class TrialOperationsTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        app.extensions["relay_outbox"] = []
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
            db.session.commit()

    def signup(self, email="operator@nyu.edu", verify=True):
        self.client.post("/signup", data={
            "email": email, "password": PASSWORD, "full_name": "Trial Operator", **CONSENT,
        })
        if verify:
            body = app.extensions["relay_outbox"][-1]["body"]
            token = re.search(r"/verify-email/(\S+)", body).group(1)
            self.client.get(f"/verify-email/{token}")
        with app.app_context():
            return User.query.filter_by(email=email).one()

    def run_cli(self, *args):
        runner = app.test_cli_runner()
        return runner.invoke(make_moderator_cli, list(args))

    # ── Moderator provisioning ────────────────────────────────

    def test_moderator_dashboard_is_unreachable_without_promotion(self):
        """Baseline: the safety queue 404s for an ordinary signed-in participant."""
        self.signup()
        self.assertEqual(self.client.get("/moderator").status_code, 404)

    def test_promotion_grants_access_to_the_moderator_dashboard(self):
        self.signup()
        result = self.run_cli("--email", "operator@nyu.edu", "--apply")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('"status": "promoted"', result.output)
        # The promoted account must sign in again: --apply bumps session_version.
        self.client.post("/login", data={"email": "operator@nyu.edu", "password": PASSWORD})
        self.assertEqual(self.client.get("/moderator").status_code, 200)

    def test_promotion_is_dry_run_by_default(self):
        self.signup()
        result = self.run_cli("--email", "operator@nyu.edu")
        self.assertIn('"status": "would_change"', result.output)
        self.assertIn("Dry run", result.output)
        with app.app_context():
            self.assertEqual(User.query.filter_by(email="operator@nyu.edu").one().role, "user")

    def test_promotion_invalidates_existing_sessions(self):
        """A live session must not silently gain moderator powers mid-flight."""
        user = self.signup()
        before = user.session_version
        self.run_cli("--email", "operator@nyu.edu", "--apply")
        with app.app_context():
            after = User.query.filter_by(email="operator@nyu.edu").one().session_version
        self.assertGreater(after, before)

    def test_repeat_promotion_is_idempotent(self):
        self.signup()
        self.run_cli("--email", "operator@nyu.edu", "--apply")
        result = self.run_cli("--email", "operator@nyu.edu", "--apply")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('"status": "already_moderator"', result.output)

    def test_unknown_address_fails_loudly(self):
        """Silently succeeding here would leave the operator thinking they have access."""
        result = self.run_cli("--email", "nobody@nyu.edu", "--apply")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('"status": "no_such_account"', result.output)

    def test_demotion_returns_the_account_to_user(self):
        self.signup()
        self.run_cli("--email", "operator@nyu.edu", "--apply")
        result = self.run_cli("--email", "operator@nyu.edu", "--demote", "--apply")
        self.assertIn('"status": "demoted"', result.output)
        self.client.post("/login", data={"email": "operator@nyu.edu", "password": PASSWORD})
        self.assertEqual(self.client.get("/moderator").status_code, 404)

    def test_addresses_fall_back_to_the_environment_variable(self):
        self.signup()
        os.environ["RELAY_MODERATOR_EMAILS"] = "operator@nyu.edu"
        self.addCleanup(os.environ.pop, "RELAY_MODERATOR_EMAILS", None)
        result = self.run_cli("--apply")
        self.assertIn('"status": "promoted"', result.output)

    def test_no_addresses_anywhere_is_an_error_not_a_silent_no_op(self):
        os.environ.pop("RELAY_MODERATOR_EMAILS", None)
        result = self.run_cli("--apply")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("No addresses given", result.output)

    # ── Verification link lifetime ────────────────────────────

    def test_verification_link_lasts_a_full_day(self):
        """One hour stranded anyone who signed up at night."""
        self.assertEqual(VERIFICATION_LINK_TTL, timedelta(hours=24))

    def test_signup_stamps_the_configured_expiry(self):
        user = self.signup(verify=False)
        with app.app_context():
            fresh = User.query.filter_by(email="operator@nyu.edu").one()
            delta = fresh.verification_expires_at - fresh.verification_sent_at
        self.assertAlmostEqual(
            delta.total_seconds(), VERIFICATION_LINK_TTL.total_seconds(), delta=5
        )

    def test_verification_email_states_the_expiry(self):
        self.signup(verify=False)
        body = app.extensions["relay_outbox"][-1]["body"]
        self.assertIn("valid for 24 hours", body)

    def test_resend_reissues_with_the_same_window(self):
        self.signup(verify=False)
        self.client.post("/login", data={"email": "operator@nyu.edu", "password": PASSWORD})
        with app.app_context():
            user = User.query.filter_by(email="operator@nyu.edu").one()
            user.verification_sent_at = user.verification_sent_at - timedelta(minutes=10)
            db.session.commit()
        self.client.post("/resend-verification")
        with app.app_context():
            fresh = User.query.filter_by(email="operator@nyu.edu").one()
            delta = fresh.verification_expires_at - fresh.verification_sent_at
        self.assertAlmostEqual(
            delta.total_seconds(), VERIFICATION_LINK_TTL.total_seconds(), delta=5
        )


if __name__ == "__main__":
    unittest.main()
