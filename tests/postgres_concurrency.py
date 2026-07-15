"""Explicit PostgreSQL concurrency suite; never runs through default discovery.

This module drops and recreates tables in the supplied disposable database. It requires
both a test-shaped PostgreSQL URL and an explicit destructive-test acknowledgement.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
import threading
import unittest
from urllib.parse import urlparse


POSTGRES_URL = os.environ.get("RELAY_TEST_POSTGRES_URL", "").strip()
DESTRUCTIVE_OK = os.environ.get("RELAY_POSTGRES_TEST_DESTRUCTIVE_OK", "").lower() == "true"


def _authorized_test_database() -> bool:
    if not POSTGRES_URL or not DESTRUCTIVE_OK:
        return False
    parsed = urlparse(POSTGRES_URL)
    database_name = parsed.path.rsplit("/", 1)[-1].lower()
    return parsed.scheme.startswith("postgresql") and any(
        marker in database_name for marker in ("test", "rehearsal", "ci")
    )


@unittest.skipUnless(
    _authorized_test_database(),
    "requires RELAY_TEST_POSTGRES_URL pointing to a disposable test database and "
    "RELAY_POSTGRES_TEST_DESTRUCTIVE_OK=true",
)
class PostgreSQLConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.update(
            {
                "DATABASE_URL": POSTGRES_URL,
                "RELAY_ENV": "test",
                "RELAY_TRIAL_CATEGORY": "creative",
                "RELAY_EMAIL_BACKEND": "memory",
                "RELAY_PUBLIC_URL": "http://localhost",
                "RELAY_REQUIRE_INVITE": "false",
            }
        )
        from app.main import app, db, utc_now
        from app.ledger import InsufficientCredits, LedgerService
        from app.models import CreditAccount, CreditTransaction, Session, SessionStatus, User
        from app.session_service import SessionStateMachine

        cls.app = app
        cls.db = db
        cls.utc_now = staticmethod(utc_now)
        cls.InsufficientCredits = InsufficientCredits
        cls.LedgerService = LedgerService
        cls.CreditAccount = CreditAccount
        cls.CreditTransaction = CreditTransaction
        cls.Session = Session
        cls.SessionStatus = SessionStatus
        cls.User = User
        cls.SessionStateMachine = SessionStateMachine

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.session.remove()
            cls.db.drop_all()
            cls.db.engine.dispose()

    def setUp(self):
        with self.app.app_context():
            self.db.drop_all()
            self.db.create_all()

    def create_pair(self, learner_credits=1):
        from werkzeug.security import generate_password_hash

        with self.app.app_context():
            teacher = self.User(
                email="pg-teacher@example.invalid",
                full_name="PostgreSQL Teacher",
                password_hash=generate_password_hash("Synthetic123!"),
                email_verified=True,
                edu_verified=True,
                onboarded=True,
            )
            learner = self.User(
                email="pg-learner@example.invalid",
                full_name="PostgreSQL Learner",
                password_hash=generate_password_hash("Synthetic123!"),
                email_verified=True,
                edu_verified=True,
                onboarded=True,
            )
            self.db.session.add_all([teacher, learner])
            self.db.session.flush()
            self.db.session.add_all(
                [
                    self.CreditAccount(user_id=teacher.id, balance=0),
                    self.CreditAccount(user_id=learner.id, balance=0),
                ]
            )
            self.db.session.flush()
            if learner_credits:
                self.LedgerService.grant_starter(learner, learner_credits)
            teacher_id, learner_id = teacher.id, learner.id
            self.db.session.commit()
            return teacher_id, learner_id

    def create_held_session(self, teacher_id, learner_id):
        with self.app.app_context():
            booked = self.Session(
                teacher_id=teacher_id,
                learner_id=learner_id,
                skill_name="Watercolor",
                status=self.SessionStatus.CONFIRMED,
                amount_charged=1,
                scheduled_at=self.utc_now() + timedelta(days=1),
            )
            self.db.session.add(booked)
            self.db.session.flush()
            self.LedgerService.hold_for_session(booked, actor_user_id=learner_id)
            session_id = booked.id
            self.db.session.commit()
            return session_id

    def test_two_competing_holds_cannot_overdraw_one_credit(self):
        teacher_id, learner_id = self.create_pair(learner_credits=1)
        barrier = threading.Barrier(2)

        def attempt_hold(index):
            with self.app.app_context():
                booked = self.Session(
                    teacher_id=teacher_id,
                    learner_id=learner_id,
                    skill_name=f"Watercolor {index}",
                    amount_charged=1,
                    scheduled_at=self.utc_now() + timedelta(days=1),
                )
                self.db.session.add(booked)
                self.db.session.flush()
                barrier.wait(timeout=10)
                try:
                    self.LedgerService.hold_for_session(booked, actor_user_id=learner_id)
                    self.db.session.commit()
                    return "held"
                except self.InsufficientCredits:
                    self.db.session.rollback()
                    return "insufficient"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt_hold, (1, 2)))
        self.assertCountEqual(results, ["held", "insufficient"])
        with self.app.app_context():
            account = self.CreditAccount.query.filter_by(user_id=learner_id).one()
            self.assertEqual(account.balance, 0)
            self.assertEqual(
                self.CreditTransaction.query.filter_by(user_id=learner_id, type="hold").count(),
                1,
            )
            self.assertTrue(self.LedgerService.reconcile(learner_id).reconciles)

    def test_competing_completion_confirmations_pay_once(self):
        teacher_id, learner_id = self.create_pair(learner_credits=1)
        session_id = self.create_held_session(teacher_id, learner_id)
        barrier = threading.Barrier(2)

        def confirm(participant_id):
            with self.app.app_context():
                barrier.wait(timeout=10)
                booked = self.Session.query.filter_by(id=session_id).with_for_update().one()
                _, settled = self.SessionStateMachine.confirm_completion(booked, participant_id)
                if settled:
                    booked.completed_at = self.utc_now()
                    self.LedgerService.payout_session(booked, actor_user_id=participant_id)
                self.db.session.commit()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(confirm, (teacher_id, learner_id)))
        with self.app.app_context():
            booked = self.db.session.get(self.Session, session_id)
            self.assertEqual(booked.status, self.SessionStatus.COMPLETED)
            self.assertEqual(
                self.CreditTransaction.query.filter_by(user_id=teacher_id, type="payout").count(),
                1,
            )
            self.assertTrue(self.LedgerService.reconcile(teacher_id).reconciles)
            self.assertTrue(self.LedgerService.reconcile(learner_id).reconciles)

    def test_cancellation_racing_one_completion_confirmation_refunds_once(self):
        teacher_id, learner_id = self.create_pair(learner_credits=1)
        session_id = self.create_held_session(teacher_id, learner_id)
        barrier = threading.Barrier(2)

        def cancel():
            with self.app.app_context():
                barrier.wait(timeout=10)
                booked = self.Session.query.filter_by(id=session_id).with_for_update().one()
                if booked.status == self.SessionStatus.CONFIRMED:
                    self.SessionStateMachine.transition(booked, self.SessionStatus.CANCELLED)
                    self.LedgerService.refund_session(
                        booked,
                        actor_user_id=learner_id,
                        reason="PostgreSQL cancellation race test",
                    )
                self.db.session.commit()

        def confirm_teacher():
            with self.app.app_context():
                barrier.wait(timeout=10)
                booked = self.Session.query.filter_by(id=session_id).with_for_update().one()
                if booked.status == self.SessionStatus.CONFIRMED:
                    self.SessionStateMachine.confirm_completion(booked, teacher_id)
                self.db.session.commit()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda function: function(), (cancel, confirm_teacher)))
        with self.app.app_context():
            booked = self.db.session.get(self.Session, session_id)
            self.assertEqual(booked.status, self.SessionStatus.CANCELLED)
            self.assertEqual(
                self.CreditTransaction.query.filter_by(user_id=learner_id, type="refund").count(),
                1,
            )
            self.assertEqual(
                self.CreditTransaction.query.filter_by(user_id=teacher_id, type="payout").count(),
                0,
            )
            self.assertTrue(self.LedgerService.reconcile(learner_id).reconciles)


if __name__ == "__main__":
    unittest.main(verbosity=2)
