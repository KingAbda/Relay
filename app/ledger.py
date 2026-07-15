"""Exact, auditable, source-unique Relay credit ledger."""

from __future__ import annotations

from dataclasses import dataclass

from .database import db
from .models import CreditAccount, CreditTransaction, Session, TransactionType, User


class LedgerError(RuntimeError):
    pass


class InsufficientCredits(LedgerError):
    pass


@dataclass(frozen=True)
class ReconciliationResult:
    user_id: str
    balance: int
    ledger_total: int

    @property
    def reconciles(self) -> bool:
        return self.balance == self.ledger_total


def _event_value(event_type: TransactionType | str) -> str:
    return event_type.value if isinstance(event_type, TransactionType) else str(event_type)


class LedgerService:
    """All balance changes pass through this service inside the caller's transaction."""

    @staticmethod
    def apply(
        *,
        user_id: str,
        amount: int,
        event_type: TransactionType | str,
        source_type: str,
        source_id: str,
        reason: str,
        actor_user_id: str | None = None,
        related_user_id: str | None = None,
    ) -> tuple[CreditTransaction, bool]:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
            raise LedgerError("Ledger amounts must be non-zero integer credits")
        if not source_type.strip() or not source_id.strip() or not reason.strip():
            raise LedgerError("Every ledger event requires a source and reason")

        event_value = _event_value(event_type)
        idempotency_key = f"{event_value}:{source_type}:{source_id}:{user_id}"
        account = CreditAccount.query.filter_by(user_id=user_id).with_for_update().first()
        if not account:
            raise LedgerError("Credit account not found")

        existing = CreditTransaction.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing, False

        new_balance = account.balance + amount
        if new_balance < 0:
            raise InsufficientCredits("Insufficient credits")

        transaction = CreditTransaction(
            user_id=user_id,
            amount=amount,
            type=event_value,
            description=reason,
            actor_user_id=actor_user_id,
            related_user_id=related_user_id,
            source_type=source_type,
            source_id=source_id,
            idempotency_key=idempotency_key,
        )
        account.balance = new_balance
        db.session.add(transaction)
        db.session.flush()
        return transaction, True

    @classmethod
    def grant_starter(cls, user: User, amount: int) -> tuple[CreditTransaction | None, bool]:
        if amount == 0:
            return None, False
        return cls.apply(
            user_id=user.id,
            amount=amount,
            event_type=TransactionType.STARTER,
            source_type="user",
            source_id=user.id,
            reason="Controlled-trial starter credits",
            actor_user_id=user.id,
        )

    @classmethod
    def hold_for_session(cls, session: Session, actor_user_id: str) -> tuple[CreditTransaction, bool]:
        return cls.apply(
            user_id=session.learner_id,
            amount=-session.amount_charged,
            event_type=TransactionType.HOLD,
            source_type="session",
            source_id=session.id,
            reason=f"Session hold: {session.skill_name}",
            actor_user_id=actor_user_id,
            related_user_id=session.teacher_id,
        )

    @classmethod
    def refund_session(cls, session: Session, actor_user_id: str, reason: str) -> tuple[CreditTransaction, bool]:
        hold = CreditTransaction.query.filter_by(
            user_id=session.learner_id,
            type=TransactionType.HOLD.value,
            source_type="session",
            source_id=session.id,
        ).first()
        if not hold:
            raise LedgerError("Cannot refund a session without its source hold")
        return cls.apply(
            user_id=session.learner_id,
            amount=session.amount_charged,
            event_type=TransactionType.REFUND,
            source_type="session",
            source_id=session.id,
            reason=reason,
            actor_user_id=actor_user_id,
            related_user_id=session.teacher_id,
        )

    @classmethod
    def payout_session(cls, session: Session, actor_user_id: str) -> tuple[CreditTransaction, bool]:
        hold = CreditTransaction.query.filter_by(
            user_id=session.learner_id,
            type=TransactionType.HOLD.value,
            source_type="session",
            source_id=session.id,
        ).first()
        refund = CreditTransaction.query.filter_by(
            user_id=session.learner_id,
            type=TransactionType.REFUND.value,
            source_type="session",
            source_id=session.id,
        ).first()
        if not hold:
            raise LedgerError("Cannot pay a session without its source hold")
        if refund:
            raise LedgerError("Cannot pay a refunded session")
        return cls.apply(
            user_id=session.teacher_id,
            amount=session.amount_charged,
            event_type=TransactionType.PAYOUT,
            source_type="session",
            source_id=session.id,
            reason=f"Session payout: {session.skill_name}",
            actor_user_id=actor_user_id,
            related_user_id=session.learner_id,
        )

    @classmethod
    def reverse(
        cls,
        *,
        user_id: str,
        amount: int,
        source_id: str,
        reason: str,
        actor_user_id: str,
        related_user_id: str | None = None,
    ) -> tuple[CreditTransaction, bool]:
        return cls.apply(
            user_id=user_id,
            amount=amount,
            event_type=TransactionType.REVERSAL,
            source_type="session_reversal",
            source_id=source_id,
            reason=reason,
            actor_user_id=actor_user_id,
            related_user_id=related_user_id,
        )

    @classmethod
    def reverse_completed_session(
        cls,
        session: Session,
        *,
        actor_user_id: str,
        reason: str,
    ) -> tuple[tuple[CreditTransaction, bool], tuple[CreditTransaction, bool]]:
        """Reverse only a complete, internally consistent hold/payout settlement."""
        hold = CreditTransaction.query.filter_by(
            user_id=session.learner_id,
            type=TransactionType.HOLD.value,
            source_type="session",
            source_id=session.id,
        ).first()
        payout = CreditTransaction.query.filter_by(
            user_id=session.teacher_id,
            type=TransactionType.PAYOUT.value,
            source_type="session",
            source_id=session.id,
        ).first()
        refund = CreditTransaction.query.filter_by(
            user_id=session.learner_id,
            type=TransactionType.REFUND.value,
            source_type="session",
            source_id=session.id,
        ).first()
        if (
            not session.completed_at
            or not hold
            or not payout
            or refund
            or hold.amount != -session.amount_charged
            or payout.amount != session.amount_charged
        ):
            raise LedgerError(
                "Cannot reverse a session without a complete, unreimbursed source settlement"
            )
        source_id = f"{session.id}:completed_settlement"
        teacher_reversal = cls.reverse(
            user_id=session.teacher_id,
            amount=-session.amount_charged,
            source_id=source_id,
            reason=reason,
            actor_user_id=actor_user_id,
            related_user_id=session.learner_id,
        )
        learner_reversal = cls.reverse(
            user_id=session.learner_id,
            amount=session.amount_charged,
            source_id=source_id,
            reason=reason,
            actor_user_id=actor_user_id,
            related_user_id=session.teacher_id,
        )
        return teacher_reversal, learner_reversal

    @staticmethod
    def reconcile(user_id: str) -> ReconciliationResult:
        account = CreditAccount.query.filter_by(user_id=user_id).first()
        if not account:
            raise LedgerError("Credit account not found")
        ledger_total = sum(
            transaction.amount
            for transaction in CreditTransaction.query.filter_by(user_id=user_id).all()
        )
        return ReconciliationResult(
            user_id=user_id,
            balance=account.balance,
            ledger_total=ledger_total,
        )
