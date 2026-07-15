"""Strict server-side lifecycle rules for controlled-trial sessions."""

from __future__ import annotations

from .models import Session, SessionStatus


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
