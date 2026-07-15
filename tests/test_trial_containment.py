from __future__ import annotations

from datetime import datetime, timedelta
import os
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo


os.environ.update(
    {
        "DATABASE_URL": "sqlite://",
        "RELAY_ENV": "test",
        "RELAY_TRIAL_CATEGORY": "creative",
        "RELAY_EMAIL_BACKEND": "memory",
        "RELAY_PUBLIC_URL": "http://localhost",
        "RELAY_REQUIRE_INVITE": "false",
    }
)

from app.main import (
    CURRENT_CONSENT_VERSIONS,
    app,
    db,
    hash_secret,
    jinja_trial_time,
    parse_trial_schedule,
    submitted_email_limit_key,
    configure_proxy_boundary,
    limiter,
    utc_now,
)
from app.email_service import EmailDeliveryError, send_transactional_email
from app.database import normalize_database_url
from app.ledger import InsufficientCredits, LedgerError, LedgerService
from app.models import (
    CreditAccount,
    CreditTransaction,
    ConsentAcceptance,
    EmailDelivery,
    PasswordResetToken,
    Session,
    SessionDispute,
    SessionReview,
    SessionStatus,
    SafetyReport,
    ModerationAction,
    TransactionType,
    User,
    UserBlock,
    UserSkill,
    UserWant,
)
from app.trial_config import load_trial_config
from app.session_service import IllegalSessionTransition, SessionStateMachine
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from werkzeug.security import generate_password_hash


CSRF_PATTERN = re.compile(rb'name="csrf_token" value="([^"]+)"')


class TrialContainmentTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
        app.extensions["relay_outbox"] = []
        self.client = app.test_client()
        with app.app_context():
            db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
            db.drop_all()
            db.create_all()
            db.session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            db.session.execute(text("INSERT INTO alembic_version VALUES ('20260713_01')"))
            db.session.commit()

    def csrf(self, path: str = "/signup") -> str:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = CSRF_PATTERN.search(response.data)
        self.assertIsNotNone(match, f"No CSRF token found at {path}")
        return match.group(1).decode()

    def test_provider_postgres_url_selects_psycopg3(self):
        self.assertEqual(
            normalize_database_url("postgresql://relay@db/relay"),
            "postgresql+psycopg://relay@db/relay",
        )
        self.assertEqual(
            normalize_database_url("postgresql+psycopg://relay@db/relay"),
            "postgresql+psycopg://relay@db/relay",
        )
        self.assertEqual(normalize_database_url("sqlite://"), "sqlite://")
        self.assertIsNone(normalize_database_url(None))

    def create_user(
        self,
        email: str,
        name: str,
        *,
        verified: bool = True,
        onboarded: bool = True,
        balance: int = 0,
        consented: bool = True,
        role: str = "user",
    ) -> SimpleNamespace:
        with app.app_context():
            user = User(
                email=email,
                full_name=name,
                password_hash=generate_password_hash("Secure123"),
                email_verified=verified,
                edu_verified=verified,
                onboarded=onboarded,
                role=role,
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(CreditAccount(user_id=user.id, balance=balance))
            if consented:
                for document, version in CURRENT_CONSENT_VERSIONS.items():
                    db.session.add(
                        ConsentAcceptance(user_id=user.id, document=document, version=version)
                    )
            if balance:
                db.session.add(
                    CreditTransaction(
                        user_id=user.id,
                        amount=balance,
                        type=TransactionType.ADJUSTMENT.value,
                        description="Test opening balance",
                        actor_user_id=user.id,
                        source_type="test_fixture",
                        source_id=user.id,
                        idempotency_key=f"test_fixture:{user.id}",
                    )
                )
            user_id = user.id
            db.session.commit()
            return SimpleNamespace(id=user_id, email=email)

    def login_as(self, user_id: str) -> None:
        with self.client.session_transaction() as browser_session:
            browser_session["user_id"] = user_id
            browser_session["session_version"] = 0

    def create_held_session(
        self,
        teacher_id: str,
        learner_id: str,
        *,
        status: SessionStatus = SessionStatus.CONFIRMED,
        scheduled_at: datetime | None = None,
        completed: bool = False,
    ) -> str:
        with app.app_context():
            booked = Session(
                teacher_id=teacher_id,
                learner_id=learner_id,
                skill_name="Drawing",
                status=status,
                amount_charged=1,
                scheduled_at=scheduled_at or (utc_now() + timedelta(days=1)),
                completed_at=utc_now() if completed else None,
                teacher_completed=completed,
                learner_completed=completed,
            )
            db.session.add(booked)
            db.session.flush()
            LedgerService.hold_for_session(booked, actor_user_id=learner_id)
            if completed:
                LedgerService.payout_session(booked, actor_user_id=teacher_id)
            session_id = booked.id
            db.session.commit()
            return session_id

    @staticmethod
    def consent_fields() -> dict[str, str]:
        return {
            "accept_terms": "yes",
            "accept_privacy": "yes",
            "confirm_age": "yes",
            "accept_conduct": "yes",
            "accept_safety": "yes",
        }

    def test_production_category_is_required_and_all_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "RELAY_ENV must be"):
            load_trial_config({"RELAY_ENV": "prodution"})
        with self.assertRaisesRegex(RuntimeError, "RELAY_TRIAL_CATEGORY is required"):
            load_trial_config({"RELAY_ENV": "production"})
        with self.assertRaisesRegex(RuntimeError, "RELAY_TRIAL_CATEGORY is required"):
            load_trial_config({"RELAY_ENV": "staging"})
        with self.assertRaisesRegex(RuntimeError, "exactly one supported category"):
            load_trial_config(
                {
                    "RELAY_ENV": "test",
                    "RELAY_TRIAL_CATEGORY": "all",
                    "RELAY_PUBLIC_URL": "http://localhost",
                }
            )

    def test_trial_configuration_is_one_creative_category_and_one_credit(self):
        config = load_trial_config(
            {
                "RELAY_ENV": "test",
                "RELAY_TRIAL_CATEGORY": "creative",
                "RELAY_PUBLIC_URL": "http://localhost",
            }
        )
        self.assertEqual(config.category, "creative")
        self.assertEqual(config.credit_cost, 1)
        self.assertEqual(config.participant_mode, "invite-only")
        with self.assertRaisesRegex(RuntimeError, "between 1 and 10"):
            load_trial_config(
                {
                    "RELAY_ENV": "test",
                    "RELAY_TRIAL_CATEGORY": "creative",
                    "RELAY_PUBLIC_URL": "http://localhost",
                    "RELAY_STARTER_CREDITS": "0",
                }
            )

    def test_production_configuration_requires_postgres_redis_and_fails_closed_invites(self):
        baseline = {
            "RELAY_ENV": "production",
            "RELAY_TRIAL_CATEGORY": "creative",
            "RELAY_PUBLIC_URL": "https://relay.example",
            "RELAY_EMAIL_BACKEND": "smtp",
            "RELAY_SMTP_HOST": "smtp.example",
            "RELAY_EMAIL_FROM": "relay@example.edu",
            "RELAY_SECRET_KEY": "a" * 64,
            "RELAY_REQUIRE_INVITE": "true",
            "RELAY_INVITED_EMAILS": ",".join(
                f"student{i}@nyu.edu" for i in range(10)
            ),
        }
        with self.assertRaisesRegex(RuntimeError, "non-placeholder secret"):
            load_trial_config({**baseline, "RELAY_SECRET_KEY": "replace-with-a-random-secret"})
        with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
            load_trial_config(baseline)
        with self.assertRaisesRegex(RuntimeError, "Redis"):
            load_trial_config(
                {**baseline, "DATABASE_URL": "postgresql+psycopg://db/relay"}
            )
        production_ready_shape = {
            **baseline,
            "DATABASE_URL": "postgresql+psycopg://db/relay",
            "RATE_LIMIT_STORAGE": "rediss://cache/0",
            "RELAY_REQUIRE_INVITE": "true",
            "RELAY_PROXY_X_FOR": "1",
            "RELAY_PROXY_X_PROTO": "1",
            "RELAY_PROXY_X_HOST": "1",
        }
        with self.assertRaisesRegex(RuntimeError, "10–20 unique"):
            load_trial_config({**production_ready_shape, "RELAY_INVITED_EMAILS": ""})
        with self.assertRaisesRegex(RuntimeError, "exactly nyu.edu"):
            load_trial_config({
                **production_ready_shape,
                "RELAY_ALLOWED_EMAIL_DOMAINS": "example.edu",
            })
        with self.assertRaisesRegex(RuntimeError, "must include"):
            load_trial_config({
                **production_ready_shape,
                "RELAY_TRUSTED_HOSTS": "attacker.example",
            })
        with self.assertRaisesRegex(RuntimeError, "must be true"):
            load_trial_config({
                **production_ready_shape,
                "RELAY_REQUIRE_INVITE": "false",
                "RELAY_INVITED_EMAILS": ",".join(
                    f"student{i}@nyu.edu" for i in range(10)
                ),
            })
        config = load_trial_config({
            **production_ready_shape,
            "RELAY_INVITED_EMAILS": ",".join(
                f"student{i}@nyu.edu" for i in range(10)
            ),
        })
        self.assertFalse(config.email_is_invited("unlisted@nyu.edu"))
        self.assertTrue(config.email_is_invited("student0@nyu.edu"))

        staging_config = load_trial_config({
            **production_ready_shape,
            "RELAY_ENV": "staging",
            "RELAY_INVITED_EMAILS": ",".join(
                f"staging-student{i}@nyu.edu" for i in range(10)
            ),
        })
        self.assertTrue(staging_config.is_deployed)
        self.assertFalse(staging_config.is_production)

        config_without_forwarded_host = load_trial_config({
            **production_ready_shape,
            "RELAY_PROXY_X_HOST": "0",
        })
        self.assertEqual(config_without_forwarded_host.proxy_x_host, 0)

        with self.assertRaisesRegex(RuntimeError, "RELAY_PROXY_X_FOR must trust"):
            load_trial_config({**production_ready_shape, "RELAY_PROXY_X_FOR": "0"})

        with self.assertRaisesRegex(RuntimeError, "RELAY_PROXY_X_FOR is required"):
            load_trial_config({
                key: value
                for key, value in production_ready_shape.items()
                if not key.startswith("RELAY_PROXY_")
            })

    def test_proxy_boundary_trusts_only_the_configured_rightmost_hop(self):
        from flask import Flask, jsonify, request

        proxy_app = Flask("proxy-boundary-test")
        proxy_app.config["TRUSTED_HOSTS"] = ["relay.example"]
        configure_proxy_boundary(
            proxy_app,
            SimpleNamespace(proxy_x_for=1, proxy_x_proto=1, proxy_x_host=1),
        )

        @proxy_app.get("/")
        def proxy_probe():
            return jsonify({
                "address": request.remote_addr,
                "scheme": request.scheme,
                "host": request.host,
            })

        response = proxy_app.test_client().get(
            "/",
            base_url="http://internal.invalid",
            headers={
                "X-Forwarded-For": "198.51.100.44, 203.0.113.17",
                "X-Forwarded-Proto": "http, https",
                "X-Forwarded-Host": "attacker.example, relay.example",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "address": "203.0.113.17",
            "scheme": "https",
            "host": "relay.example",
        })

    def test_csrf_remains_enabled(self):
        response = self.client.post(
            "/signup",
            data={"email": "student@nyu.edu", "full_name": "Test Student", "password": "Secure123"},
        )
        self.assertEqual(response.status_code, 400)

    def test_csp_blocks_inline_script_and_rendered_home_has_no_inline_script(self):
        response = self.client.get("/")
        csp = response.headers["Content-Security-Policy"]
        script_policy = next(part for part in csp.split(";") if "script-src" in part)
        self.assertNotIn("unsafe-inline", script_policy)
        self.assertIsNone(re.search(rb"<script(?![^>]*\bsrc=)", response.data, re.I))
        self.assertNotIn("fonts.googleapis.com", response.text)
        self.assertNotIn("gravatar.com", response.text)
        self.assertNotIn("gravatar.com", csp)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Pragma"], "no-cache")

    def test_home_serves_only_contained_assets_within_trial_budget(self):
        response = self.client.get("/")
        asset_urls = {
            match.decode()
            for match in re.findall(rb'(?:src|href)="(/static/[^"?]+)', response.data)
        }
        self.assertTrue(asset_urls)
        forbidden_fragments = ("campaign/", "leaflet", ".mp4", ".gif", "intro-frames")
        for asset_url in asset_urls:
            self.assertFalse(any(fragment in asset_url for fragment in forbidden_fragments), asset_url)
        asset_payloads = [self.client.get(asset_url).data for asset_url in asset_urls]
        self.assertTrue(all(payload for payload in asset_payloads))
        self.assertLess(
            len(response.data) + sum(len(payload) for payload in asset_payloads),
            650_000,
        )

    def test_public_policy_pages_are_available_and_truthfully_unreviewed(self):
        self.assertEqual(self.client.get("/about").status_code, 200)
        for path in ("/privacy", "/terms", "/safety", "/conduct"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(b"External legal review: not yet evidenced", response.data, path)

    def test_intro_is_skippable_once_per_session_and_respects_reduced_motion(self):
        script = self.client.get("/static/elevate.js").text
        self.assertIn('sessionStorage.getItem("relayIntroSeen")', script)
        self.assertIn('sessionStorage.setItem("relayIntroSeen", "1")', script)
        self.assertIn('prefers-reduced-motion: reduce', script)
        self.assertIn('getElementById("introSkip")', script)
        self.assertIn("function settleReveals()", script)
        self.assertLess(
            script.index("if (reduceMotion) {\n      settleReveals();"),
            script.index("if (!hasGSAP || !window.ScrollTrigger)"),
        )

    def test_public_surface_is_dark_mode_only(self):
        homepage = self.client.get("/").text
        stylesheet = self.client.get("/static/style.css").text
        elevated_stylesheet = self.client.get("/static/elevate.css").text
        script = self.client.get("/static/elevate.js").text

        self.assertIn("linear-gradient(180deg,#6d28d9 0%,#4c1d95 100%)", stylesheet)
        self.assertIn(".btn-primary{background:var(--gel-orange)!important;\n  color:#0f172a!important", stylesheet)
        self.assertIn('<meta name="theme-color" content="#0f0d1a" />', homepage)
        self.assertNotIn("themeToggle", homepage)
        self.assertNotIn("prefers-color-scheme:light", homepage)
        self.assertNotIn("light-mode", stylesheet)
        self.assertNotIn("light-mode", elevated_stylesheet)
        self.assertNotIn("light-mode", script)
        self.assertNotIn("relay-logo-light", script)
        self.assertNotIn('localStorage.getItem("theme")', script)

    def test_verification_link_uses_canonical_origin_not_request_host(self):
        signup_page = self.client.get("/signup", base_url="http://attacker.example")
        token = CSRF_PATTERN.search(signup_page.data).group(1).decode()
        response = self.client.post(
            "/signup",
            base_url="http://attacker.example",
            data={
                "csrf_token": token,
                "email": "canonical@nyu.edu",
                "full_name": "Canonical Person",
                "password": "Secure123",
                **self.consent_fields(),
            },
        )
        self.assertEqual(response.status_code, 302)
        body = app.extensions["relay_outbox"][-1]["body"]
        self.assertIn("http://localhost/verify-email/", body)
        self.assertNotIn("attacker.example", body)

    def test_liveness_and_database_readiness_are_separate(self):
        self.assertEqual(self.client.get("/health/live").get_json(), {"status": "ok"})
        ready = self.client.get("/health/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.get_json(), {"status": "ready"})

        with app.app_context():
            db.session.execute(text("UPDATE alembic_version SET version_num = '20260713_00'"))
            db.session.commit()
        stale = self.client.get("/health/ready")
        self.assertEqual(stale.status_code, 503)
        self.assertEqual(stale.get_json(), {"status": "not_ready"})

        with app.app_context():
            db.session.execute(text("UPDATE alembic_version SET version_num = '20260713_01'"))
            db.session.commit()

        with patch("app.main.db.session.execute", side_effect=RuntimeError("database unavailable")):
            not_ready = self.client.get("/health/ready")
        self.assertEqual(not_ready.status_code, 503)
        self.assertEqual(not_ready.get_json(), {"status": "not_ready"})

        with patch.object(limiter.storage, "check", return_value=False):
            no_limiter_storage = self.client.get("/health/ready")
        self.assertEqual(no_limiter_storage.status_code, 503)
        self.assertEqual(no_limiter_storage.get_json(), {"status": "not_ready"})

    def test_smtp_provider_refusal_is_generic_and_secret_free(self):
        previous_backend = app.config["RELAY_EMAIL_BACKEND"]
        previous_environment = {
            key: os.environ.get(key)
            for key in (
                "RELAY_SMTP_HOST",
                "RELAY_SMTP_PORT",
                "RELAY_SMTP_USERNAME",
                "RELAY_SMTP_PASSWORD",
                "RELAY_EMAIL_FROM",
            )
        }
        app.config["RELAY_EMAIL_BACKEND"] = "smtp"
        os.environ.update({
            "RELAY_SMTP_HOST": "127.0.0.1",
            "RELAY_SMTP_PORT": "1",
            "RELAY_SMTP_USERNAME": "synthetic-user",
            "RELAY_SMTP_PASSWORD": "synthetic-secret-not-for-logs",
            "RELAY_EMAIL_FROM": "relay@example.invalid",
        })
        try:
            with patch(
                "app.email_service.smtplib.SMTP",
                side_effect=OSError("synthetic provider socket failure"),
            ):
                with self.assertRaises(EmailDeliveryError) as raised:
                    send_transactional_email(
                        app,
                        to="recipient@example.invalid",
                        subject="Synthetic delivery",
                        body="synthetic message body not for logs",
                    )
        finally:
            app.config["RELAY_EMAIL_BACKEND"] = previous_backend
            for key, value in previous_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        rendered_error = str(raised.exception)
        self.assertEqual(rendered_error, "The email provider did not accept the message")
        self.assertNotIn("synthetic-secret", rendered_error)
        self.assertNotIn("synthetic message body", rendered_error)

    def test_signup_rejects_malformed_edu_text(self):
        response = self.client.post(
            "/signup",
            data={
                "csrf_token": self.csrf(),
                "email": "not-an-address.edu",
                "full_name": "Test Student",
                "password": "Secure123",
                **self.consent_fields(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"valid institutional email", response.data)
        with app.app_context():
            self.assertEqual(User.query.count(), 0)

    def test_starter_credits_wait_for_verification_and_are_repeat_safe(self):
        response = self.client.post(
            "/signup",
            data={
                "csrf_token": self.csrf(),
                "email": "student@nyu.edu",
                "full_name": "Test Student",
                "password": "Secure123",
                **self.consent_fields(),
            },
        )
        self.assertEqual(response.status_code, 302)
        outbox_body = app.extensions["relay_outbox"][-1]["body"]
        token_match = re.search(r"/verify-email/([^\s]+)", outbox_body)
        self.assertIsNotNone(token_match)
        token = token_match.group(1)
        with app.app_context():
            user = User.query.filter_by(email="student@nyu.edu").one()
            self.assertIsNotNone(user.verification_token_hash)
            self.assertEqual(user.credit_balance.balance, 0)
            self.assertEqual(CreditTransaction.query.filter_by(user_id=user.id).count(), 0)
            self.assertEqual(ConsentAcceptance.query.filter_by(user_id=user.id).count(), 5)

        verified = self.client.get(f"/verify-email/{token}")
        self.assertEqual(verified.status_code, 302)
        with app.app_context():
            user = User.query.filter_by(email="student@nyu.edu").one()
            self.assertTrue(user.email_verified)
            self.assertEqual(user.credit_balance.balance, 2)
            self.assertEqual(CreditTransaction.query.filter_by(user_id=user.id).count(), 1)
            self.assertEqual(
                EmailDelivery.query.filter_by(
                    recipient_user_id=user.id, status="delivered"
                ).count(),
                1,
            )

        repeated = self.client.get(f"/verify-email/{token}")
        self.assertEqual(repeated.status_code, 400)
        with app.app_context():
            user = User.query.filter_by(email="student@nyu.edu").one()
            self.assertEqual(user.credit_balance.balance, 2)
            self.assertEqual(CreditTransaction.query.filter_by(user_id=user.id).count(), 1)

    def test_failed_verification_email_is_reported_without_storing_message_content(self):
        previous_backend = app.config["RELAY_EMAIL_BACKEND"]
        app.config["RELAY_EMAIL_BACKEND"] = "disabled"
        try:
            response = self.client.post(
                "/signup",
                data={
                    "csrf_token": self.csrf(),
                    "email": "delivery-failure@nyu.edu",
                    "full_name": "Delivery Failure",
                    "password": "Secure123",
                    **self.consent_fields(),
                },
            )
        finally:
            app.config["RELAY_EMAIL_BACKEND"] = previous_backend
        self.assertEqual(response.status_code, 503)
        with app.app_context():
            user = User.query.filter_by(email="delivery-failure@nyu.edu").one()
            delivery = EmailDelivery.query.filter_by(recipient_user_id=user.id).one()
            self.assertEqual(delivery.message_type, "verification")
            self.assertEqual(delivery.status, "failed")
            self.assertEqual(delivery.failure_code, "provider_rejected")
            self.assertEqual(delivery.attempts, 1)
            self.assertFalse(hasattr(delivery, "body"))

    def test_expired_verification_secret_cannot_verify_or_grant_credits(self):
        user = self.create_user(
            "expired@nyu.edu", "Expired Person", verified=False, onboarded=False
        )
        secret = "expired-verification-secret"
        with app.app_context():
            stored = db.session.get(User, user.id)
            stored.verification_token_hash = hash_secret(secret)
            stored.verification_expires_at = utc_now() - timedelta(minutes=1)
            db.session.commit()
        response = self.client.get(f"/verify-email/{secret}")
        self.assertEqual(response.status_code, 400)
        with app.app_context():
            stored = db.session.get(User, user.id)
            self.assertFalse(stored.email_verified)
            self.assertEqual(stored.credit_balance.balance, 0)

    def test_current_versioned_consents_are_required_and_recorded(self):
        user = self.create_user(
            "consent@nyu.edu", "Consent Person", consented=False
        )
        self.login_as(user.id)
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 302)
        self.assertEqual(dashboard.location, "/consent")
        token = self.csrf("/consent")
        accepted = self.client.post(
            "/consent", data={"csrf_token": token, **self.consent_fields()}
        )
        self.assertEqual(accepted.status_code, 302)
        with app.app_context():
            rows = ConsentAcceptance.query.filter_by(user_id=user.id).all()
            self.assertEqual(len(rows), len(CURRENT_CONSENT_VERSIONS))
            self.assertEqual(
                {(row.document, row.version) for row in rows},
                set(CURRENT_CONSENT_VERSIONS.items()),
            )

    def test_password_reset_hashes_secret_and_revokes_existing_session(self):
        user = self.create_user("reset@nyu.edu", "Reset Person")
        secret = "reset-secret-value"
        with app.app_context():
            db.session.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_secret(secret),
                    expires_at=utc_now() + timedelta(hours=1),
                )
            )
            db.session.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_secret("second-reset-secret"),
                    expires_at=utc_now() + timedelta(hours=1),
                )
            )
            db.session.commit()
            reset_row = PasswordResetToken.query.filter_by(
                token_hash=hash_secret(secret)
            ).one()
            self.assertNotEqual(reset_row.token_hash, secret)
        self.login_as(user.id)
        token = self.csrf(f"/reset-password/{secret}")
        response = self.client.post(
            f"/reset-password/{secret}",
            data={"csrf_token": token, "password": "Changed123"},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            stored = db.session.get(User, user.id)
            self.assertEqual(stored.session_version, 1)
            self.assertEqual(
                {row.used for row in PasswordResetToken.query.filter_by(user_id=user.id).all()},
                {True},
            )
        self.assertEqual(self.client.get("/dashboard").location, "/login")

    def test_unverified_user_cannot_onboard_or_open_full_marketplace(self):
        user = self.create_user(
            "pending@nyu.edu", "Pending Person", verified=False, onboarded=False
        )
        self.login_as(user.id)
        self.assertEqual(self.client.get("/onboarding").location, "/verify-edu")
        browse = self.client.get("/browse")
        self.assertEqual(browse.status_code, 200)
        self.assertIn(b"Limited trial preview", browse.data)

    def test_verified_incomplete_user_is_sent_to_onboarding_before_booking(self):
        teacher = self.create_user("onboarding-teacher@nyu.edu", "Teacher")
        learner = self.create_user(
            "onboarding-learner@nyu.edu",
            "Learner",
            verified=True,
            onboarded=False,
        )
        with app.app_context():
            listing = UserSkill(
                user_id=teacher.id,
                name="Drawing",
                category="creative",
                credit_cost=1,
            )
            db.session.add(listing)
            db.session.commit()
            listing_id = listing.id
        self.login_as(learner.id)
        response = self.client.get(f"/request-session/{listing_id}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/onboarding")
        token = self.csrf("/onboarding")
        add_response = self.client.post(
            "/add-skill",
            data={
                "csrf_token": token,
                "name": "Photography",
                "category": "creative",
            },
        )
        self.assertEqual(add_response.status_code, 302)
        self.assertEqual(add_response.location, "/onboarding")
        with app.app_context():
            self.assertEqual(UserSkill.query.count(), 1)

    def test_public_preview_hides_student_identity_and_profile_link(self):
        teacher = self.create_user("teacher@nyu.edu", "Private Teacher")
        with app.app_context():
            db.session.add(
                UserSkill(
                    user_id=teacher.id,
                    name="Guitar basics",
                    category="creative",
                    description="Private contact private-teacher@example.com 212-555-0100",
                    credit_cost=1,
                )
            )
            db.session.commit()
        response = self.client.get("/browse")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Private Teacher", response.data)
        self.assertNotIn(b"private-teacher@example.com", response.data)
        self.assertNotIn(b"212-555-0100", response.data)
        self.assertNotIn(f"/profile/{teacher.id}".encode(), response.data)
        self.assertIn(b"Verified trial participant", response.data)

        viewer = self.create_user("viewer@nyu.edu", "Verified Viewer")
        self.login_as(viewer.id)
        verified_response = self.client.get("/browse")
        self.assertIn(b"private-teacher@example.com", verified_response.data)

    def test_unsafe_trial_routes_are_intentionally_unavailable(self):
        user = self.create_user("member@nyu.edu", "Trial Member")
        self.login_as(user.id)
        for path in ("/requests", "/proof-video", "/top-up", "/membership", "/admin/timeout-sessions", "/seed-demo"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        for path in ("/browse", "/dashboard"):
            response = self.client.get(path)
            self.assertNotIn(b"/seed-demo", response.data, path)
            self.assertNotIn(b"Add demo skills", response.data, path)
        token = self.csrf("/dashboard")
        self.assertEqual(
            self.client.post("/become-ambassador", data={"csrf_token": token}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/waitlist", data={"csrf_token": token}).status_code,
            404,
        )

    def test_listing_scope_rejects_other_categories_and_prohibited_topics(self):
        user = self.create_user("listing-owner@nyu.edu", "Listing Owner")
        self.login_as(user.id)

        token = self.csrf("/dashboard")
        safe = self.client.post(
            "/add-skill",
            data={
                "csrf_token": token,
                "name": "Watercolor <script>alert(1)</script>",
                "category": "creative",
                "description": "Beginner color mixing <img src=x onerror=alert(2)>",
            },
        )
        self.assertEqual(safe.status_code, 302)
        with app.app_context():
            listing = UserSkill.query.one()
            self.assertEqual(listing.category, "creative")
            self.assertEqual(listing.credit_cost, 1)
            self.assertNotIn("<", listing.name + listing.description)
            self.assertNotIn(">", listing.name + listing.description)

        token = self.csrf("/dashboard")
        outside = self.client.post(
            "/add-skill",
            data={
                "csrf_token": token,
                "name": "Budgeting",
                "category": "business",
                "description": "Personal budgeting basics",
            },
        )
        self.assertEqual(outside.status_code, 400)

        token = self.csrf("/dashboard")
        prohibited = self.client.post(
            "/add-skill",
            data={
                "csrf_token": token,
                "name": "Clinical therapy",
                "category": "creative",
                "description": "Diagnose and treat anxiety",
            },
        )
        self.assertEqual(prohibited.status_code, 400)
        self.assertIn(b"outside the controlled trial", prohibited.data)
        with app.app_context():
            self.assertEqual(UserSkill.query.count(), 1)

    def test_unverified_authorization_matrix_blocks_identity_and_booking(self):
        pending = self.create_user(
            "matrix-pending@nyu.edu",
            "Matrix Pending",
            verified=False,
            onboarded=False,
        )
        teacher = self.create_user("matrix-teacher@nyu.edu", "Matrix Teacher")
        with app.app_context():
            skill = UserSkill(
                user_id=teacher.id,
                name="Sketching",
                category="creative",
                description="Shape and line",
                credit_cost=1,
            )
            db.session.add(skill)
            db.session.commit()
            skill_id = skill.id
        self.login_as(pending.id)
        self.assertEqual(self.client.get("/dashboard").location, "/verify-edu")
        self.assertEqual(self.client.get("/onboarding").location, "/verify-edu")
        self.assertEqual(
            self.client.get(f"/request-session/{skill_id}").location,
            "/verify-edu",
        )
        self.assertEqual(self.client.get(f"/profile/{teacher.id}").status_code, 404)

    def test_booking_holds_exactly_one_credit_and_reconciles(self):
        teacher = self.create_user("teacher@nyu.edu", "Creative Teacher")
        learner = self.create_user("learner@nyu.edu", "Creative Learner", balance=2)
        with app.app_context():
            skill = UserSkill(
                user_id=teacher.id,
                name="Guitar basics",
                category="creative",
                description="Learn three chords.",
                credit_cost=1,
            )
            db.session.add(skill)
            db.session.commit()
            skill_id = skill.id

        self.login_as(learner.id)
        token = self.csrf(f"/request-session/{skill_id}")
        local_time = (
            datetime.now(ZoneInfo("America/New_York")) + timedelta(days=2)
        ).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            f"/request-session/{skill_id}",
            data={"csrf_token": token, "scheduled_at": local_time, "notes": "Chords"},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            account = CreditAccount.query.filter_by(user_id=learner.id).one()
            ledger_sum = sum(tx.amount for tx in CreditTransaction.query.filter_by(user_id=learner.id))
            booked = Session.query.one()
            self.assertEqual(account.balance, 1)
            self.assertEqual(ledger_sum, 1)
            self.assertEqual(booked.amount_charged, 1)

    def test_ledger_events_are_integer_source_unique_and_repeat_safe(self):
        user = self.create_user("ledger@nyu.edu", "Ledger Person")
        with app.app_context():
            first, first_created = LedgerService.apply(
                user_id=user.id,
                amount=2,
                event_type=TransactionType.ADJUSTMENT,
                source_type="approved_adjustment",
                source_id="adjustment-1",
                reason="Approved test adjustment",
                actor_user_id=user.id,
            )
            repeated, repeated_created = LedgerService.apply(
                user_id=user.id,
                amount=2,
                event_type=TransactionType.ADJUSTMENT,
                source_type="approved_adjustment",
                source_id="adjustment-1",
                reason="Approved test adjustment",
                actor_user_id=user.id,
            )
            db.session.commit()
            result = LedgerService.reconcile(user.id)
            self.assertTrue(first_created)
            self.assertFalse(repeated_created)
            self.assertEqual(first.id, repeated.id)
            self.assertEqual(result.balance, 2)
            self.assertEqual(result.ledger_total, 2)
            self.assertTrue(result.reconciles)
            self.assertIsInstance(first.amount, int)

    def test_ledger_prevents_negative_balance(self):
        user = self.create_user("empty@nyu.edu", "Empty Account")
        with app.app_context():
            with self.assertRaises(InsufficientCredits):
                LedgerService.apply(
                    user_id=user.id,
                    amount=-1,
                    event_type=TransactionType.HOLD,
                    source_type="session",
                    source_id="missing-credit-session",
                    reason="Should fail",
                    actor_user_id=user.id,
                )
            db.session.rollback()
            self.assertEqual(CreditAccount.query.filter_by(user_id=user.id).one().balance, 0)
            self.assertEqual(CreditTransaction.query.filter_by(user_id=user.id).count(), 0)

    def test_refund_and_payout_require_an_existing_session_hold(self):
        teacher = self.create_user("missing-hold-teacher@nyu.edu", "Teacher")
        learner = self.create_user("missing-hold-learner@nyu.edu", "Learner")
        with app.app_context():
            booked = Session(
                teacher_id=teacher.id,
                learner_id=learner.id,
                skill_name="Malformed historical session",
                amount_charged=1,
                status=SessionStatus.CONFIRMED,
            )
            db.session.add(booked)
            db.session.flush()
            with self.assertRaisesRegex(LedgerError, "without its source hold"):
                LedgerService.refund_session(
                    booked,
                    actor_user_id=learner.id,
                    reason="Must not mint a refund",
                )
            with self.assertRaisesRegex(LedgerError, "without its source hold"):
                LedgerService.payout_session(booked, actor_user_id=teacher.id)
            self.assertEqual(CreditTransaction.query.count(), 0)
            self.assertEqual(
                CreditAccount.query.filter_by(user_id=learner.id).one().balance,
                0,
            )

    def test_database_rejects_negative_balance_self_session_bad_price_and_rating(self):
        first = self.create_user("constraints-a@nyu.edu", "Constraints A")
        second = self.create_user("constraints-b@nyu.edu", "Constraints B")
        with app.app_context():
            account = CreditAccount.query.filter_by(user_id=first.id).one()
            account.balance = -1
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            db.session.add(
                UserSkill(
                    user_id=first.id,
                    name="Invalid price",
                    category="creative",
                    credit_cost=2,
                )
            )
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            db.session.add(
                Session(
                    teacher_id=first.id,
                    learner_id=first.id,
                    skill_name="Self session",
                    amount_charged=1,
                )
            )
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            valid_session = Session(
                teacher_id=first.id,
                learner_id=second.id,
                skill_name="Drawing",
                amount_charged=1,
            )
            db.session.add(valid_session)
            db.session.flush()
            db.session.add(
                SessionReview(
                    session_id=valid_session.id,
                    reviewer_id=first.id,
                    reviewee_id=second.id,
                    rating=6,
                )
            )
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_reconciliation_command_is_read_only_and_fails_on_discrepancy(self):
        user = self.create_user("reconcile@nyu.edu", "Reconcile Person", balance=2)
        runner = app.test_cli_runner()
        clean = runner.invoke(args=["reconcile-credits", "--user-id", user.id])
        self.assertEqual(clean.exit_code, 0)
        self.assertIn('"discrepancy_count": 0', clean.output)
        self.assertIn('"mode": "read-only"', clean.output)

        with app.app_context():
            account = CreditAccount.query.filter_by(user_id=user.id).one()
            account.balance = 1
            db.session.commit()
        mismatch = runner.invoke(args=["reconcile-credits", "--user-id", user.id])
        self.assertNotEqual(mismatch.exit_code, 0)
        self.assertIn('"discrepancy_count": 1', mismatch.output)
        self.assertIn("No repair was attempted", mismatch.output)
        with app.app_context():
            self.assertEqual(CreditAccount.query.filter_by(user_id=user.id).one().balance, 1)

    def test_expired_request_settlement_is_dry_run_by_default_and_repeat_safe(self):
        teacher = self.create_user("timeout-teacher@nyu.edu", "Timeout Teacher")
        learner = self.create_user(
            "timeout-learner@nyu.edu", "Timeout Learner", balance=1
        )
        session_id = self.create_held_session(
            teacher.id,
            learner.id,
            status=SessionStatus.REQUESTED,
            scheduled_at=utc_now() - timedelta(hours=2),
        )
        runner = app.test_cli_runner()
        preview = runner.invoke(args=["settle-expired-requests"])
        self.assertEqual(preview.exit_code, 0)
        self.assertIn('"mode": "dry-run"', preview.output)
        self.assertIn('"candidate_count": 1', preview.output)
        with app.app_context():
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.REQUESTED)
            self.assertEqual(CreditAccount.query.filter_by(user_id=learner.id).one().balance, 0)

        previous_context = os.environ.get("RELAY_SCHEDULER_AUTHENTICATED")
        os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = "true"
        try:
            applied = runner.invoke(args=["settle-expired-requests", "--apply"])
            repeated = runner.invoke(args=["settle-expired-requests", "--apply"])
        finally:
            if previous_context is None:
                os.environ.pop("RELAY_SCHEDULER_AUTHENTICATED", None)
            else:
                os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = previous_context
        self.assertEqual(applied.exit_code, 0, applied.output)
        self.assertIn('"settled_count": 1', applied.output)
        self.assertEqual(repeated.exit_code, 0, repeated.output)
        self.assertIn('"settled_count": 0', repeated.output)
        with app.app_context():
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.CANCELLED)
            self.assertEqual(CreditAccount.query.filter_by(user_id=learner.id).one().balance, 1)
            self.assertEqual(
                CreditTransaction.query.filter_by(
                    user_id=learner.id, type=TransactionType.REFUND.value
                ).count(),
                1,
            )
            self.assertTrue(LedgerService.reconcile(learner.id).reconciles)
            expiry_messages = EmailDelivery.query.filter_by(
                message_type="session_expired", source_id=session_id
            ).all()
            self.assertEqual(len(expiry_messages), 2)
            self.assertEqual({row.status for row in expiry_messages}, {"delivered"})
            self.assertEqual({row.attempts for row in expiry_messages}, {1})

    def test_expired_settlement_survives_notification_failure_and_reconciles(self):
        teacher = self.create_user("expired-mail-teacher@nyu.edu", "Teacher")
        learner = self.create_user(
            "expired-mail-learner@nyu.edu", "Learner", balance=1
        )
        session_id = self.create_held_session(
            teacher.id,
            learner.id,
            status=SessionStatus.REQUESTED,
            scheduled_at=utc_now() - timedelta(hours=2),
        )
        runner = app.test_cli_runner()
        previous_context = os.environ.get("RELAY_SCHEDULER_AUTHENTICATED")
        previous_backend = app.config["RELAY_EMAIL_BACKEND"]
        os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = "true"
        app.config["RELAY_EMAIL_BACKEND"] = "disabled"
        try:
            result = runner.invoke(args=["settle-expired-requests", "--apply"])
        finally:
            app.config["RELAY_EMAIL_BACKEND"] = previous_backend
            if previous_context is None:
                os.environ.pop("RELAY_SCHEDULER_AUTHENTICATED", None)
            else:
                os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = previous_context

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Settlement succeeded", result.output)
        with app.app_context():
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.CANCELLED)
            self.assertEqual(
                CreditAccount.query.filter_by(user_id=learner.id).one().balance,
                1,
            )
            self.assertTrue(LedgerService.reconcile(learner.id).reconciles)
            failures = EmailDelivery.query.filter_by(
                message_type="session_expired", status="failed"
            ).all()
            self.assertEqual(len(failures), 2)

    def test_session_reminders_are_dry_run_authenticated_and_idempotent(self):
        teacher = self.create_user("reminder-teacher@nyu.edu", "Reminder Teacher")
        learner = self.create_user(
            "reminder-learner@nyu.edu", "Reminder Learner", balance=2
        )
        session_id = self.create_held_session(
            teacher.id,
            learner.id,
            status=SessionStatus.CONFIRMED,
            scheduled_at=utc_now() + timedelta(hours=12),
        )
        self.create_held_session(
            teacher.id,
            learner.id,
            status=SessionStatus.REQUESTED,
            scheduled_at=utc_now() + timedelta(hours=12),
        )
        runner = app.test_cli_runner()

        preview = runner.invoke(args=["send-session-reminders"])
        self.assertEqual(preview.exit_code, 0, preview.output)
        self.assertIn('"mode": "dry-run"', preview.output)
        self.assertIn('"candidate_count": 1', preview.output)
        with app.app_context():
            self.assertEqual(EmailDelivery.query.count(), 0)

        denied = runner.invoke(args=["send-session-reminders", "--apply"])
        self.assertNotEqual(denied.exit_code, 0)
        self.assertIn("authenticated scheduler", denied.output)
        with app.app_context():
            self.assertEqual(EmailDelivery.query.count(), 0)

        previous_context = os.environ.get("RELAY_SCHEDULER_AUTHENTICATED")
        os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = "true"
        try:
            applied = runner.invoke(args=["send-session-reminders", "--apply"])
            repeated = runner.invoke(args=["send-session-reminders", "--apply"])
        finally:
            if previous_context is None:
                os.environ.pop("RELAY_SCHEDULER_AUTHENTICATED", None)
            else:
                os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = previous_context

        self.assertEqual(applied.exit_code, 0, f"{applied.output}\n{applied.exception!r}")
        self.assertIn('"recipient_count": 2', applied.output)
        self.assertEqual(repeated.exit_code, 0, repeated.output)
        self.assertEqual(len(app.extensions["relay_outbox"]), 2)
        self.assertTrue(
            all(
                f"http://localhost/session/{session_id}" in message["body"]
                for message in app.extensions["relay_outbox"]
            )
        )
        with app.app_context():
            reminders = EmailDelivery.query.filter_by(
                message_type="session_reminder", source_id=session_id
            ).all()
            self.assertEqual(len(reminders), 2)
            self.assertEqual({row.status for row in reminders}, {"delivered"})
            self.assertEqual({row.attempts for row in reminders}, {1})

    def test_session_reminder_failures_exit_nonzero_without_changing_session(self):
        teacher = self.create_user("failed-reminder-teacher@nyu.edu", "Teacher")
        learner = self.create_user(
            "failed-reminder-learner@nyu.edu", "Learner", balance=1
        )
        session_id = self.create_held_session(
            teacher.id,
            learner.id,
            scheduled_at=utc_now() + timedelta(hours=12),
        )
        runner = app.test_cli_runner()
        previous_context = os.environ.get("RELAY_SCHEDULER_AUTHENTICATED")
        previous_backend = app.config["RELAY_EMAIL_BACKEND"]
        os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = "true"
        app.config["RELAY_EMAIL_BACKEND"] = "disabled"
        try:
            failed = runner.invoke(args=["send-session-reminders", "--apply"])
        finally:
            app.config["RELAY_EMAIL_BACKEND"] = previous_backend
            if previous_context is None:
                os.environ.pop("RELAY_SCHEDULER_AUTHENTICATED", None)
            else:
                os.environ["RELAY_SCHEDULER_AUTHENTICATED"] = previous_context

        self.assertNotEqual(failed.exit_code, 0)
        self.assertIn("One or more reminders failed", failed.output)
        with app.app_context():
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.CONFIRMED)
            reminders = EmailDelivery.query.filter_by(
                message_type="session_reminder", source_id=session_id
            ).all()
            self.assertEqual(len(reminders), 2)
            self.assertEqual({row.status for row in reminders}, {"failed"})

    def test_rehearsal_fixture_is_dry_run_non_production_and_repeat_safe(self):
        runner = app.test_cli_runner()
        preview = runner.invoke(args=["prepare-rehearsal-data"])
        self.assertEqual(preview.exit_code, 0, preview.output)
        self.assertIn('"mode": "dry-run"', preview.output)
        self.assertIn('"created_user_count": 0', preview.output)
        self.assertNotIn("example.invalid", preview.output)
        with app.app_context():
            self.assertEqual(User.query.count(), 0)

        denied = runner.invoke(args=["prepare-rehearsal-data", "--apply"])
        self.assertNotEqual(denied.exit_code, 0)
        self.assertIn("explicit rehearsal-data authorization", denied.output)

        previous_authorized = os.environ.get("RELAY_REHEARSAL_DATA_AUTHORIZED")
        previous_password = os.environ.get("RELAY_REHEARSAL_PASSWORD")
        os.environ["RELAY_REHEARSAL_DATA_AUTHORIZED"] = "true"
        os.environ["RELAY_REHEARSAL_PASSWORD"] = "Synthetic123!"
        try:
            applied = runner.invoke(args=["prepare-rehearsal-data", "--apply"])
            repeated = runner.invoke(args=["prepare-rehearsal-data", "--apply"])
        finally:
            if previous_authorized is None:
                os.environ.pop("RELAY_REHEARSAL_DATA_AUTHORIZED", None)
            else:
                os.environ["RELAY_REHEARSAL_DATA_AUTHORIZED"] = previous_authorized
            if previous_password is None:
                os.environ.pop("RELAY_REHEARSAL_PASSWORD", None)
            else:
                os.environ["RELAY_REHEARSAL_PASSWORD"] = previous_password

        self.assertEqual(applied.exit_code, 0, f"{applied.output}\n{applied.exception!r}")
        self.assertIn('"created_user_count": 2', applied.output)
        self.assertIn('"created_listing_count": 1', applied.output)
        self.assertEqual(repeated.exit_code, 0, f"{repeated.output}\n{repeated.exception!r}")
        self.assertIn('"created_user_count": 0', repeated.output)
        self.assertIn('"created_listing_count": 0', repeated.output)
        self.assertNotIn("Synthetic123!", applied.output + repeated.output)
        self.assertNotIn("example.invalid", applied.output + repeated.output)
        with app.app_context():
            users = User.query.order_by(User.email).all()
            self.assertEqual(len(users), 2)
            self.assertEqual(UserSkill.query.count(), 1)
            self.assertEqual(ConsentAcceptance.query.count(), 10)
            self.assertEqual(
                CreditTransaction.query.filter_by(type=TransactionType.STARTER.value).count(),
                2,
            )
            for user in users:
                self.assertTrue(user.email.endswith("@example.invalid"))
                self.assertEqual(user.credit_balance.balance, 2)
                self.assertTrue(LedgerService.reconcile(user.id).reconciles)

    def test_trial_health_report_is_aggregate_read_only_and_pii_free(self):
        user = self.create_user(
            "metrics-person@nyu.edu", "Metrics Person", balance=2
        )
        runner = app.test_cli_runner()
        result = runner.invoke(args=["trial-health-report"])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = result.output
        self.assertIn('"verified": 1', payload)
        self.assertIn('"synthetic_rehearsal": 0', payload)
        self.assertIn('"ledger_discrepancies": 0', payload)
        self.assertIn('"mode": "read-only"', payload)
        self.assertNotIn(user.email, payload)
        self.assertNotIn("Metrics Person", payload)

    def test_repeat_sessions_each_pay_once_and_reconcile(self):
        teacher = self.create_user("teacher@nyu.edu", "Creative Teacher")
        learner = self.create_user("learner@nyu.edu", "Creative Learner", balance=2)
        with app.app_context():
            sessions = []
            for offset in (1, 2):
                booked = Session(
                    teacher_id=teacher.id,
                    learner_id=learner.id,
                    skill_name="Drawing",
                    status=SessionStatus.CONFIRMED,
                    amount_charged=1,
                    scheduled_at=utc_now() + timedelta(days=offset),
                )
                db.session.add(booked)
                db.session.flush()
                LedgerService.hold_for_session(booked, actor_user_id=learner.id)
                LedgerService.payout_session(booked, actor_user_id=teacher.id)
                LedgerService.payout_session(booked, actor_user_id=teacher.id)
                sessions.append(booked)
            db.session.commit()
            teacher_result = LedgerService.reconcile(teacher.id)
            learner_result = LedgerService.reconcile(learner.id)
            payouts = CreditTransaction.query.filter_by(
                user_id=teacher.id, type=TransactionType.PAYOUT.value
            ).all()
            self.assertEqual(len(payouts), 2)
            self.assertEqual({p.source_id for p in payouts}, {s.id for s in sessions})
            self.assertEqual(teacher_result.balance, 2)
            self.assertEqual(learner_result.balance, 0)
            self.assertTrue(teacher_result.reconciles)
            self.assertTrue(learner_result.reconciles)

    def test_acceptance_uses_real_details_and_cancellation_refunds_once(self):
        teacher = self.create_user("teacher@nyu.edu", "Creative Teacher")
        learner = self.create_user("learner@nyu.edu", "Creative Learner", balance=2)
        with app.app_context():
            skill = UserSkill(user_id=teacher.id, name="Drawing", category="creative", credit_cost=1)
            db.session.add(skill)
            db.session.commit()
            skill_id = skill.id

        self.login_as(learner.id)
        request_token = self.csrf(f"/request-session/{skill_id}")
        local_time = (
            datetime.now(ZoneInfo("America/New_York")) + timedelta(days=2)
        ).strftime("%Y-%m-%dT%H:%M")
        self.client.post(
            f"/request-session/{skill_id}",
            data={"csrf_token": request_token, "scheduled_at": local_time},
        )
        with app.app_context():
            booked = Session.query.one()
            session_id = booked.id
            displayed_schedule = jinja_trial_time(booked.scheduled_at).encode()

        self.login_as(teacher.id)
        teacher_dashboard = self.client.get("/dashboard")
        self.assertIn(displayed_schedule, teacher_dashboard.data)
        accept_token = self.csrf("/dashboard")
        accepted = self.client.post(
            f"/accept-session/{session_id}",
            data={
                "csrf_token": accept_token,
                "meeting_type": "location",
                "meeting_details": "Bobst Library lobby",
            },
        )
        self.assertEqual(accepted.status_code, 302)
        with app.app_context():
            booked = db.session.get(Session, session_id)
            self.assertEqual(booked.status, SessionStatus.CONFIRMED)
            self.assertEqual(booked.meet_link, "location:Bobst Library lobby")

        self.login_as(learner.id)
        cancel_token = self.csrf("/dashboard")
        self.assertEqual(
            self.client.post(
                f"/cancel-session/{session_id}", data={"csrf_token": cancel_token}
            ).status_code,
            302,
        )
        second_token = self.csrf("/dashboard")
        self.client.post(f"/cancel-session/{session_id}", data={"csrf_token": second_token})
        with app.app_context():
            account = CreditAccount.query.filter_by(user_id=learner.id).one()
            ledger_sum = sum(tx.amount for tx in CreditTransaction.query.filter_by(user_id=learner.id))
            refunds = CreditTransaction.query.filter_by(
                user_id=learner.id, type=TransactionType.REFUND.value
            ).count()
            self.assertEqual(account.balance, 2)
            self.assertEqual(ledger_sum, 2)
            self.assertEqual(refunds, 1)
            self.assertEqual(
                {
                    row.message_type
                    for row in EmailDelivery.query.filter_by(status="delivered").all()
                },
                {"session_requested", "session_accepted", "session_cancelled"},
            )

    def test_schedule_parser_rejects_dst_gaps_and_ambiguous_times(self):
        with self.assertRaisesRegex(ValueError, "nonexistent or ambiguous"):
            parse_trial_schedule("2026-03-08T02:30")
        with self.assertRaisesRegex(ValueError, "nonexistent or ambiguous"):
            parse_trial_schedule("2026-11-01T01:30")
        self.assertEqual(
            parse_trial_schedule("2026-07-14T15:00"),
            datetime(2026, 7, 14, 19, 0),
        )

    def test_failed_session_notification_preserves_booking_and_records_failure(self):
        teacher = self.create_user("mail-teacher@nyu.edu", "Mail Teacher")
        learner = self.create_user(
            "mail-learner@nyu.edu", "Mail Learner", balance=1
        )
        with app.app_context():
            skill = UserSkill(
                user_id=teacher.id,
                name="Drawing",
                category="creative",
                credit_cost=1,
            )
            db.session.add(skill)
            db.session.commit()
            skill_id = skill.id
        self.login_as(learner.id)
        token = self.csrf(f"/request-session/{skill_id}")
        local_time = (
            datetime.now(ZoneInfo("America/New_York")) + timedelta(days=2)
        ).strftime("%Y-%m-%dT%H:%M")
        previous_backend = app.config["RELAY_EMAIL_BACKEND"]
        app.config["RELAY_EMAIL_BACKEND"] = "disabled"
        try:
            response = self.client.post(
                f"/request-session/{skill_id}",
                data={"csrf_token": token, "scheduled_at": local_time},
            )
        finally:
            app.config["RELAY_EMAIL_BACKEND"] = previous_backend
        self.assertEqual(response.status_code, 202)
        self.assertIn(b"session change was saved", response.data)
        with app.app_context():
            self.assertEqual(Session.query.one().status, SessionStatus.REQUESTED)
            self.assertEqual(
                CreditAccount.query.filter_by(user_id=learner.id).one().balance,
                0,
            )
            delivery = EmailDelivery.query.one()
            self.assertEqual(delivery.message_type, "session_requested")
            self.assertEqual(delivery.status, "failed")
            self.assertTrue(LedgerService.reconcile(learner.id).reconciles)

    def test_block_cancels_and_refunds_active_interaction_once(self):
        teacher = self.create_user("teacher@nyu.edu", "Blocked Teacher")
        learner = self.create_user("learner@nyu.edu", "Blocking Learner", balance=1)
        session_id = self.create_held_session(teacher.id, learner.id)
        self.login_as(learner.id)
        token = self.csrf(f"/session/{session_id}")
        first = self.client.post(
            f"/block-user/{teacher.id}",
            data={"csrf_token": token, "reason": "I do not want further contact."},
        )
        self.assertEqual(first.status_code, 302)
        second_token = self.csrf("/dashboard")
        self.client.post(
            f"/block-user/{teacher.id}",
            data={"csrf_token": second_token, "reason": "Repeat request"},
        )
        with app.app_context():
            self.assertEqual(UserBlock.query.count(), 1)
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.CANCELLED)
            self.assertEqual(CreditAccount.query.filter_by(user_id=learner.id).one().balance, 1)
            self.assertEqual(
                CreditTransaction.query.filter_by(
                    user_id=learner.id, type=TransactionType.REFUND.value
                ).count(),
                1,
            )

        self.login_as(teacher.id)
        teacher_token = self.csrf("/dashboard")
        prohibited = self.client.post(
            f"/complete-session/{session_id}", data={"csrf_token": teacher_token}
        )
        self.assertEqual(prohibited.status_code, 404)

    def test_report_resolution_suspends_target_and_appends_audit_action(self):
        reporter = self.create_user("reporter@nyu.edu", "Reporter Person", balance=1)
        target = self.create_user("target@nyu.edu", "Reported Person")
        moderator = self.create_user(
            "moderator@nyu.edu", "Moderator Person", role="moderator"
        )
        with app.app_context():
            listing = UserSkill(
                user_id=target.id,
                name="Drawing",
                category="creative",
                credit_cost=1,
            )
            db.session.add(listing)
            db.session.add(
                PasswordResetToken(
                    user_id=target.id,
                    token_hash=hash_secret("pre-suspension-reset"),
                    expires_at=utc_now() + timedelta(hours=1),
                )
            )
            db.session.commit()
        active_session_id = self.create_held_session(target.id, reporter.id)
        self.login_as(reporter.id)
        token = self.csrf("/dashboard")
        response = self.client.post(
            f"/report-user/{target.id}",
            data={
                "csrf_token": token,
                "category": "harassment",
                "description": "Repeated unwanted messages.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/moderator").status_code, 404)
        with app.app_context():
            report_id = SafetyReport.query.one().id

        self.login_as(moderator.id)
        moderator_token = self.csrf("/moderator")
        resolved = self.client.post(
            f"/moderator/resolve/report/{report_id}",
            data={
                "csrf_token": moderator_token,
                "action_type": "suspend",
                "reason": "Credible harassment report",
                "evidence_notes": "Reviewed reporter statement and session history.",
            },
        )
        self.assertEqual(resolved.status_code, 302)
        with app.app_context():
            stored_target = db.session.get(User, target.id)
            report = db.session.get(SafetyReport, report_id)
            action = ModerationAction.query.one()
            self.assertEqual(stored_target.account_status, "suspended")
            self.assertEqual(stored_target.session_version, 1)
            self.assertFalse(UserSkill.query.filter_by(user_id=target.id).one().is_active)
            self.assertEqual(
                db.session.get(Session, active_session_id).status,
                SessionStatus.CANCELLED,
            )
            self.assertEqual(
                CreditAccount.query.filter_by(user_id=reporter.id).one().balance,
                1,
            )
            self.assertTrue(LedgerService.reconcile(reporter.id).reconciles)
            self.assertEqual(report.status, "resolved")
            self.assertEqual(action.action_type, "suspend")
            self.assertTrue(action.reason)
            self.assertTrue(action.evidence_notes)
            self.assertTrue(PasswordResetToken.query.filter_by(user_id=target.id).one().used)

        login_token = self.csrf("/login")
        suspended_login = self.client.post(
            "/login",
            data={
                "csrf_token": login_token,
                "email": target.email,
                "password": "Secure123",
            },
        )
        self.assertEqual(suspended_login.status_code, 200)
        self.assertIn(b"Invalid email or password", suspended_login.data)

    def test_no_show_to_moderator_refund_drill_reconciles(self):
        teacher = self.create_user("teacher@nyu.edu", "No Show Teacher")
        learner = self.create_user("learner@nyu.edu", "Waiting Learner", balance=1)
        moderator = self.create_user(
            "moderator@nyu.edu", "Moderator Person", role="moderator"
        )
        session_id = self.create_held_session(
            teacher.id,
            learner.id,
            scheduled_at=utc_now() - timedelta(hours=1),
        )
        self.login_as(learner.id)
        token = self.csrf(f"/session/{session_id}")
        no_show = self.client.post(
            f"/no-show/{session_id}",
            data={"csrf_token": token, "reason": "Teacher did not arrive."},
        )
        self.assertEqual(no_show.status_code, 302)
        with app.app_context():
            dispute_id = SessionDispute.query.one().id
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.NO_SHOW)

        self.login_as(moderator.id)
        moderator_token = self.csrf("/moderator")
        resolved = self.client.post(
            f"/moderator/resolve/dispute/{dispute_id}",
            data={
                "csrf_token": moderator_token,
                "target_user_id": teacher.id,
                "action_type": "refund_hold",
                "reason": "Teacher no-show confirmed",
                "evidence_notes": "Reviewed scheduled time and both statements.",
            },
        )
        self.assertEqual(resolved.status_code, 302)
        with app.app_context():
            self.assertEqual(CreditAccount.query.filter_by(user_id=learner.id).one().balance, 1)
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.CANCELLED)
            self.assertEqual(db.session.get(SessionDispute, dispute_id).status, "resolved")
            self.assertTrue(LedgerService.reconcile(learner.id).reconciles)
            self.assertEqual(ModerationAction.query.one().action_type, "refund_hold")

    def test_dismissed_dispute_restores_prior_session_state(self):
        teacher = self.create_user("dismiss-teacher@nyu.edu", "Dismiss Teacher")
        learner = self.create_user(
            "dismiss-learner@nyu.edu", "Dismiss Learner", balance=1
        )
        moderator = self.create_user(
            "dismiss-moderator@nyu.edu", "Dismiss Moderator", role="moderator"
        )
        session_id = self.create_held_session(teacher.id, learner.id)
        self.login_as(learner.id)
        token = self.csrf(f"/session/{session_id}")
        opened = self.client.post(
            f"/dispute-session/{session_id}",
            data={"csrf_token": token, "reason": "Needs neutral review."},
        )
        self.assertEqual(opened.status_code, 302)
        with app.app_context():
            booked = db.session.get(Session, session_id)
            dispute = SessionDispute.query.one()
            self.assertEqual(booked.status, SessionStatus.DISPUTED)
            self.assertEqual(dispute.resolution, "pending_from:confirmed")
            dispute_id = dispute.id

        self.login_as(moderator.id)
        moderator_token = self.csrf("/moderator")
        invalid = self.client.post(
            f"/moderator/resolve/dispute/{dispute_id}",
            data={
                "csrf_token": moderator_token,
                "target_user_id": teacher.id,
                "action_type": "suspend",
                "reason": "Wrong workflow",
                "evidence_notes": "A dispute cannot combine account and settlement actions.",
            },
        )
        self.assertEqual(invalid.status_code, 400)
        moderator_token = self.csrf("/moderator")
        dismissed = self.client.post(
            f"/moderator/resolve/dispute/{dispute_id}",
            data={
                "csrf_token": moderator_token,
                "target_user_id": teacher.id,
                "action_type": "dismiss",
                "reason": "No settlement change warranted",
                "evidence_notes": "Reviewed both participant statements.",
            },
        )
        self.assertEqual(dismissed.status_code, 302)
        with app.app_context():
            self.assertEqual(
                db.session.get(Session, session_id).status,
                SessionStatus.CONFIRMED,
            )
            self.assertEqual(db.session.get(SessionDispute, dispute_id).status, "dismissed")
            self.assertEqual(ModerationAction.query.count(), 1)
            self.assertTrue(LedgerService.reconcile(learner.id).reconciles)

    def test_completed_reversal_requires_the_source_payout(self):
        teacher = self.create_user(
            "malformed-teacher@nyu.edu", "Malformed Teacher", balance=1
        )
        learner = self.create_user(
            "malformed-learner@nyu.edu", "Malformed Learner", balance=1
        )
        moderator = self.create_user(
            "malformed-moderator@nyu.edu", "Malformed Moderator", role="moderator"
        )
        with app.app_context():
            booked = Session(
                teacher_id=teacher.id,
                learner_id=learner.id,
                skill_name="Malformed completed settlement",
                status=SessionStatus.DISPUTED,
                amount_charged=1,
                completed_at=utc_now(),
                teacher_completed=True,
                learner_completed=True,
            )
            db.session.add(booked)
            db.session.flush()
            LedgerService.hold_for_session(booked, actor_user_id=learner.id)
            dispute = SessionDispute(
                session_id=booked.id,
                opened_by_id=learner.id,
                reason="Settlement appears incomplete.",
                resolution="pending_from:completed",
            )
            db.session.add(dispute)
            db.session.commit()
            session_id = booked.id
            dispute_id = dispute.id

        self.login_as(moderator.id)
        moderator_token = self.csrf("/moderator")
        response = self.client.post(
            f"/moderator/resolve/dispute/{dispute_id}",
            data={
                "csrf_token": moderator_token,
                "target_user_id": teacher.id,
                "action_type": "reverse_completed",
                "reason": "Attempt malformed reversal",
                "evidence_notes": "No source payout exists for this historical row.",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn(b"settlement is inconsistent", response.data)
        with app.app_context():
            self.assertEqual(ModerationAction.query.count(), 0)
            self.assertEqual(
                CreditTransaction.query.filter_by(
                    type=TransactionType.REVERSAL.value
                ).count(),
                0,
            )
            self.assertEqual(
                CreditAccount.query.filter_by(user_id=teacher.id).one().balance,
                1,
            )
            self.assertEqual(
                CreditAccount.query.filter_by(user_id=learner.id).one().balance,
                0,
            )
            self.assertEqual(
                db.session.get(Session, session_id).status,
                SessionStatus.DISPUTED,
            )

    def test_completed_dispute_reversal_drill_reconciles_both_accounts(self):
        teacher = self.create_user("teacher@nyu.edu", "Paid Teacher")
        learner = self.create_user("learner@nyu.edu", "Disputing Learner", balance=1)
        moderator = self.create_user(
            "moderator@nyu.edu", "Moderator Person", role="moderator"
        )
        session_id = self.create_held_session(
            teacher.id, learner.id, status=SessionStatus.COMPLETED, completed=True
        )
        self.login_as(learner.id)
        token = self.csrf(f"/session/{session_id}")
        disputed = self.client.post(
            f"/dispute-session/{session_id}",
            data={"csrf_token": token, "reason": "The session was materially misrepresented."},
        )
        self.assertEqual(disputed.status_code, 302)
        with app.app_context():
            dispute_id = SessionDispute.query.one().id

        self.login_as(moderator.id)
        moderator_token = self.csrf("/moderator")
        resolved = self.client.post(
            f"/moderator/resolve/dispute/{dispute_id}",
            data={
                "csrf_token": moderator_token,
                "target_user_id": teacher.id,
                "action_type": "reverse_completed",
                "reason": "Completed-session reversal approved",
                "evidence_notes": "Reviewed both accounts and supporting material.",
            },
        )
        self.assertEqual(resolved.status_code, 302)
        repeat_token = self.csrf("/moderator")
        repeated = self.client.post(
            f"/moderator/resolve/dispute/{dispute_id}",
            data={
                "csrf_token": repeat_token,
                "target_user_id": teacher.id,
                "action_type": "reverse_completed",
                "reason": "Attempted duplicate reversal",
                "evidence_notes": "This repeat must be rejected before an action is created.",
            },
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertIn(b"already been resolved", repeated.data)
        with app.app_context():
            second_report = SafetyReport(
                reporter_id=learner.id,
                reported_user_id=teacher.id,
                session_id=session_id,
                category="fraud",
                description="Separate report must not create a second reversal source.",
            )
            db.session.add(second_report)
            db.session.commit()
            second_report_id = second_report.id
        second_report_token = self.csrf("/moderator")
        cross_case_repeat = self.client.post(
            f"/moderator/resolve/report/{second_report_id}",
            data={
                "csrf_token": second_report_token,
                "action_type": "reverse_completed",
                "reason": "Attempted cross-case duplicate",
                "evidence_notes": "The original session settlement is already reversed.",
            },
        )
        self.assertEqual(cross_case_repeat.status_code, 409)
        self.assertIn(b"settlement has already been reversed", cross_case_repeat.data)
        with app.app_context():
            self.assertEqual(CreditAccount.query.filter_by(user_id=teacher.id).one().balance, 0)
            self.assertEqual(CreditAccount.query.filter_by(user_id=learner.id).one().balance, 1)
            self.assertTrue(LedgerService.reconcile(teacher.id).reconciles)
            self.assertTrue(LedgerService.reconcile(learner.id).reconciles)
            reversals = CreditTransaction.query.filter_by(
                type=TransactionType.REVERSAL.value
            ).all()
            self.assertEqual(len(reversals), 2)
            self.assertEqual(len({row.source_id for row in reversals}), 1)
            self.assertEqual(
                {row.source_type for row in reversals},
                {"session_reversal"},
            )
            self.assertEqual(ModerationAction.query.count(), 1)
            self.assertEqual(ModerationAction.query.one().action_type, "reverse_completed")
            self.assertEqual(
                db.session.get(Session, session_id).status,
                SessionStatus.CANCELLED,
            )

    def test_meeting_host_substring_attack_is_rejected(self):
        teacher = self.create_user("teacher@nyu.edu", "Creative Teacher")
        learner = self.create_user("learner@nyu.edu", "Creative Learner")
        with app.app_context():
            booked = Session(
                teacher_id=teacher.id,
                learner_id=learner.id,
                skill_name="Drawing",
                amount_charged=1,
                scheduled_at=utc_now() + timedelta(days=1),
            )
            db.session.add(booked)
            db.session.commit()
            session_id = booked.id
        self.login_as(teacher.id)
        token = self.csrf("/dashboard")
        response = self.client.post(
            f"/accept-session/{session_id}",
            data={
                "csrf_token": token,
                "meeting_type": "video",
                "meeting_details": "https://meet.google.com.attacker.example/relay",
            },
        )
        self.assertEqual(response.status_code, 400)
        with app.app_context():
            self.assertEqual(db.session.get(Session, session_id).status, SessionStatus.REQUESTED)

    def test_requested_session_cannot_be_completed(self):
        teacher = self.create_user("teacher@nyu.edu", "Creative Teacher")
        learner = self.create_user("learner@nyu.edu", "Creative Learner", balance=1)
        with app.app_context():
            booked = Session(
                teacher_id=teacher.id,
                learner_id=learner.id,
                skill_name="Drawing",
                amount_charged=1,
                scheduled_at=utc_now() + timedelta(days=1),
            )
            db.session.add(booked)
            db.session.commit()
            session_id = booked.id
        self.login_as(teacher.id)
        token = self.csrf("/dashboard")
        response = self.client.post(
            f"/complete-session/{session_id}", data={"csrf_token": token}
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            booked = db.session.get(Session, session_id)
            self.assertEqual(booked.status, SessionStatus.REQUESTED)
            self.assertFalse(booked.teacher_completed)

    def test_completed_session_review_is_recorded_once_on_repeat_route_calls(self):
        teacher = self.create_user("review-teacher@nyu.edu", "Review Teacher")
        learner = self.create_user(
            "review-learner@nyu.edu", "Review Learner", balance=1
        )
        session_id = self.create_held_session(
            teacher.id,
            learner.id,
            status=SessionStatus.COMPLETED,
            completed=True,
        )
        self.login_as(learner.id)
        token = self.csrf(f"/review-session/{session_id}")
        first = self.client.post(
            f"/review-session/{session_id}",
            data={"csrf_token": token, "rating": "5", "review": "Helpful session"},
        )
        second = self.client.post(
            f"/review-session/{session_id}",
            data={"csrf_token": token, "rating": "4", "review": "Duplicate"},
        )
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        with app.app_context():
            reviews = SessionReview.query.filter_by(
                session_id=session_id, reviewer_id=learner.id
            ).all()
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].rating, 5)

    def test_state_machine_rejects_illegal_transition(self):
        teacher = self.create_user("teacher@nyu.edu", "Creative Teacher")
        learner = self.create_user("learner@nyu.edu", "Creative Learner")
        with app.app_context():
            booked = Session(
                teacher_id=teacher.id,
                learner_id=learner.id,
                skill_name="Drawing",
                amount_charged=1,
            )
            db.session.add(booked)
            db.session.flush()
            with self.assertRaises(IllegalSessionTransition):
                SessionStateMachine.transition(booked, SessionStatus.COMPLETED)
            self.assertEqual(booked.status, SessionStatus.REQUESTED)

    def test_failed_logins_increment_and_lock_known_account(self):
        user = self.create_user("login@nyu.edu", "Login Person")
        for attempt in range(5):
            token = self.csrf("/login")
            response = self.client.post(
                "/login",
                data={"csrf_token": token, "email": user.email, "password": "Wrong123"},
            )
            self.assertEqual(response.status_code, 200)
        with app.app_context():
            stored = db.session.get(User, user.id)
            self.assertEqual(stored.failed_login_attempts, 5)
            self.assertIsNotNone(stored.account_locked_until)

    def test_authenticated_safety_rate_limit_is_account_scoped(self):
        with app.test_request_context(
            "/login",
            method="POST",
            data={"email": "Rate-Identity@NYU.edu"},
        ):
            identity_key = submitted_email_limit_key()
        self.assertRegex(identity_key, r"^email:[0-9a-f]{64}$")
        self.assertNotIn("rate-identity@nyu.edu", identity_key)

        first = self.create_user("rate-first@nyu.edu", "First Reporter")
        second = self.create_user("rate-second@nyu.edu", "Second Reporter")
        target = self.create_user("rate-target@nyu.edu", "Reported Participant")

        self.login_as(first.id)
        for attempt in range(10):
            token = self.csrf("/dashboard")
            response = self.client.post(
                f"/report-user/{target.id}",
                data={
                    "csrf_token": token,
                    "category": "harassment",
                    "description": f"Rate-limit test report {attempt}.",
                },
            )
            self.assertEqual(response.status_code, 302)
        token = self.csrf("/dashboard")
        limited = self.client.post(
            f"/report-user/{target.id}",
            data={
                "csrf_token": token,
                "category": "harassment",
                "description": "This report must be throttled.",
            },
        )
        self.assertEqual(limited.status_code, 429)

        # A second signed-in participant behind the same test-client IP retains
        # their own safety-report allowance.
        self.login_as(second.id)
        token = self.csrf("/dashboard")
        independent = self.client.post(
            f"/report-user/{target.id}",
            data={
                "csrf_token": token,
                "category": "privacy",
                "description": "Independent account-scoped report.",
            },
        )
        self.assertEqual(independent.status_code, 302)
        with app.app_context():
            self.assertEqual(SafetyReport.query.count(), 11)

    def test_account_export_includes_identity_consent_and_ledger_records(self):
        user = self.create_user(
            "export@nyu.edu", "Export Person", balance=2
        )
        other = self.create_user("export-other@nyu.edu", "Export Other")
        with app.app_context():
            db.session.add(
                UserSkill(
                    user_id=user.id,
                    name="Illustration",
                    category="creative",
                    description="Ink basics",
                    credit_cost=1,
                )
            )
            db.session.add(
                UserBlock(
                    blocker_id=user.id,
                    blocked_id=other.id,
                    reason="No further interaction",
                )
            )
            db.session.add(
                SafetyReport(
                    reporter_id=user.id,
                    reported_user_id=other.id,
                    category="privacy",
                    description="Private report narrative",
                )
            )
            db.session.add(
                EmailDelivery(
                    recipient_user_id=user.id,
                    message_type="verification",
                    source_id="synthetic-export-source",
                    idempotency_key=f"verification:synthetic-export-source:{user.id}",
                    status="delivered",
                    attempts=1,
                    delivered_at=utc_now(),
                )
            )
            db.session.commit()
        self.login_as(user.id)
        response = self.client.get("/account/export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="relay-account-export.json"',
        )
        payload = response.get_json()
        self.assertEqual(payload["account"]["email"], "export@nyu.edu")
        self.assertEqual(len(payload["consents"]), len(CURRENT_CONSENT_VERSIONS))
        self.assertEqual(payload["credit_ledger"][0]["amount"], 2)
        self.assertEqual(payload["skills"][0]["name"], "Illustration")
        self.assertEqual(payload["blocks_created"][0]["reason"], "No further interaction")
        self.assertEqual(
            payload["reports_submitted"][0]["description"],
            "Private report narrative",
        )
        self.assertEqual(
            payload["email_delivery_outcomes"][0]["message_type"],
            "verification",
        )
        self.assertIn("disputes_opened", payload)
        self.assertIn("reviews_authored", payload)
        self.assertIn("moderation_outcomes", payload)

    def test_account_closure_replaces_identifiers_and_preserves_audit_ledger(self):
        user = self.create_user(
            "delete@nyu.edu", "Delete Person", balance=2
        )
        other = self.create_user("delete-other@nyu.edu", "Delete Other")
        with app.app_context():
            db.session.add(
                UserSkill(
                    user_id=user.id,
                    name="Watercolor",
                    category="creative",
                    description="Color mixing",
                    credit_cost=1,
                )
            )
            db.session.add(
                UserWant(
                    user_id=user.id,
                    name="Collage",
                    category="creative",
                    description="Paper composition",
                )
            )
            db.session.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_secret("pre-deletion-reset"),
                    expires_at=utc_now() + timedelta(hours=1),
                )
            )
            db.session.commit()
        active_session_id = self.create_held_session(other.id, user.id)
        self.login_as(user.id)
        token = self.csrf("/edit-profile")
        response = self.client.post(
            "/account/delete",
            data={
                "csrf_token": token,
                "password": "Secure123",
                "confirmation": "DELETE",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")
        with app.app_context():
            stored = db.session.get(User, user.id)
            self.assertEqual(stored.account_status, "deleted")
            self.assertTrue(stored.email.endswith("@deleted.invalid"))
            self.assertEqual(stored.full_name, "Deleted participant")
            self.assertFalse(UserSkill.query.filter_by(user_id=user.id).one().is_active)
            self.assertEqual(UserWant.query.filter_by(user_id=user.id).count(), 0)
            self.assertEqual(
                db.session.get(Session, active_session_id).status,
                SessionStatus.CANCELLED,
            )
            self.assertEqual(CreditTransaction.query.filter_by(user_id=user.id).count(), 3)
            self.assertEqual(
                CreditAccount.query.filter_by(user_id=user.id).one().balance,
                2,
            )
            self.assertTrue(LedgerService.reconcile(user.id).reconciles)
            self.assertTrue(PasswordResetToken.query.filter_by(user_id=user.id).one().used)
        self.assertEqual(self.client.get("/dashboard").location, "/login")


if __name__ == "__main__":
    unittest.main()
