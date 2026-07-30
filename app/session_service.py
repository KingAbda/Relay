"""Strict server-side lifecycle rules for controlled-trial sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .database import db
from .models import Session, SessionStatus


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class IllegalSessionTransition(RuntimeError):
    pass


ALLOWED_TRANSITIONS = {
    SessionStatus.REQUESTED: {SessionStatus.CONFIRMED, SessionStatus.CANCELLED},
    SessionStatus.CONFIRMED: {
        SessionStatus.COMPLETED,
        SessionStatus.CANCELLED,
        SessionStatus.NO_SHOW,
        SessionStatus.DISPUTED,
    },
    SessionStatus.COMPLETED: {SessionStatus.DISPUTED, SessionStatus.CANCELLED},
    SessionStatus.NO_SHOW: {SessionStatus.DISPUTED, SessionStatus.CANCELLED},
    SessionStatus.DISPUTED: {
        SessionStatus.CONFIRMED,
        SessionStatus.COMPLETED,
        SessionStatus.NO_SHOW,
        SessionStatus.CANCELLED,
    },
    SessionStatus.CANCELLED: set(),
}


class SessionStateMachine:
    @staticmethod
    def transition(booked: Session, target: SessionStatus) -> bool:
        current = booked.status if isinstance(booked.status, SessionStatus) else SessionStatus(booked.status)
        if current == target:
            return False
        if target not in ALLOWED_TRANSITIONS[current]:
            raise IllegalSessionTransition(f"Cannot transition session from {current.value} to {target.value}")
        booked.status = target
        return True

    @classmethod
    def confirm_completion(cls, booked: Session, user_id: str) -> tuple[bool, bool]:
        current = booked.status if isinstance(booked.status, SessionStatus) else SessionStatus(booked.status)
        if current != SessionStatus.CONFIRMED:
            raise IllegalSessionTransition("Only a confirmed session can be completed")
        if user_id == booked.teacher_id:
            if booked.teacher_completed:
                return False, False
            booked.teacher_completed = True
        elif user_id == booked.learner_id:
            if booked.learner_completed:
                return False, False
            booked.learner_completed = True
        else:
            raise IllegalSessionTransition("Only a participant can confirm completion")

        settled = booked.teacher_completed and booked.learner_completed
        if settled:
            cls.transition(booked, SessionStatus.COMPLETED)
        return True, settled

    # ── Stale session cleanup ──────────────────────────────────────

    _REQUESTED_TIMEOUT_HOURS = 24
    _CONFIRMED_TIMEOUT_HOURS = 48

    @staticmethod
    def cleanup_stale(apply: bool = False) -> dict:
        """Find and optionally cancel sessions stuck in an intermediate state.

        Sessions in REQUESTED older than ``_REQUESTED_TIMEOUT_HOURS`` (24 h)
        or CONFIRMED older than ``_CONFIRMED_TIMEOUT_HOURS`` (48 h) are
        candidates.

        Returns a dict with candidate count, settled count, and a dry-run note.
        """
        now = utc_now()
        requested_cutoff = now - timedelta(hours=SessionStateMachine._REQUESTED_TIMEOUT_HOURS)
        confirmed_cutoff = now - timedelta(hours=SessionStateMachine._CONFIRMED_TIMEOUT_HOURS)

        candidates = list(
            Session.query.filter(
                (
                    (Session.status == SessionStatus.REQUESTED)
                    & (Session.created_at <= requested_cutoff)
                )
                | (
                    (Session.status == SessionStatus.CONFIRMED)
                    & (Session.created_at <= confirmed_cutoff)
                ),
            )
            .order_by(Session.created_at)
            .all()
        )

        result = {
            "mode": "apply" if apply else "dry-run",
            "candidate_count": len(candidates),
            "settled_count": 0,
        }

        if not apply:
            return result

        settled = []
        try:
            for candidate in candidates:
                booked = Session.query.filter_by(id=candidate.id).with_for_update().one()
                if booked.status not in (SessionStatus.REQUESTED, SessionStatus.CONFIRMED):
                    continue
                if booked.status == SessionStatus.REQUESTED and booked.created_at > requested_cutoff:
                    continue
                if booked.status == SessionStatus.CONFIRMED and booked.created_at > confirmed_cutoff:
                    continue
                prior_status = booked.status
                SessionStateMachine.transition(booked, SessionStatus.CANCELLED)
                booked.cancellation_reason = (
                    "Auto-cancelled: stale REQUESTED session"
                    if prior_status == SessionStatus.REQUESTED
                    else "Auto-cancelled: stale CONFIRMED session"
                )
                result["settled_count"] += 1
                settled.append(booked)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return result


def cleanup_stale_sessions(apply: bool = False) -> dict:
    """CLI-friendly wrapper around SessionStateMachine.cleanup_stale()."""
    return SessionStateMachine.cleanup_stale(apply=apply)
