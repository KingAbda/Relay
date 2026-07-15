"""Relay — Data models. Users, skills, sessions, credits, reviews."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    String, Integer, DateTime, ForeignKey, Text, Boolean, Enum as SAEnum,
    CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from .database import db


def _uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Enums ──────────────────────────────────────────────

class SkillCategory(str, enum.Enum):
    CREATIVE = "creative"
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    SOCIAL = "social"
    LIFESTYLE = "lifestyle"
    FINANCE = "finance"
    LANGUAGES = "languages"
    TRADES = "trades"
    OTHER = "other"
    def __str__(self):
        return self.value


class SessionStatus(str, enum.Enum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    DISPUTED = "disputed"


class TransactionType(str, enum.Enum):
    STARTER = "starter"
    HOLD = "hold"
    PAYOUT = "payout"
    REVERSAL = "reversal"
    ADJUSTMENT = "adjustment"
    EXPIRE = "expire"
    REFUND = "refund"
    def __str__(self):
        return self.value


# ── Session series ──

class SessionSeries(db.Model):
    __tablename__ = "session_series"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    teacher_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    learner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    skill_name: Mapped[str] = mapped_column(String, nullable=False)
    total_sessions: Mapped[int] = mapped_column(Integer, default=1)
    completed_sessions: Mapped[int] = mapped_column(Integer, default=0)
    credit_cost_per_session: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="active")  # active, completed, cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


# ── Skill request (demand aggregation) ──

class SkillRequest(db.Model):
    __tablename__ = "skill_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[SkillCategory] = mapped_column(SAEnum(SkillCategory), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    max_credits: Mapped[int] = mapped_column(Integer, default=1)
    claimed_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")  # open, claimed, filled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    user = relationship("User", foreign_keys=[user_id])
    claimer = relationship("User", foreign_keys=[claimed_by])


# ── User ───────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="")
    avatar_url: Mapped[str] = mapped_column(String, default="")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=True)
    verification_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    verification_sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    account_locked_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    session_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    account_status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Referral system
    referred_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    
    # Profile expansion
    school: Mapped[str] = mapped_column(String, default="")
    major: Mapped[str] = mapped_column(String, default="")
    graduation_year: Mapped[str] = mapped_column(String, default="")
    profile_photo: Mapped[str] = mapped_column(String, default="")  # path or URL
    
    # Legacy student-verification fields retained only for migration compatibility.
    edu_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Good/bad student tracking
    completed_sessions_count: Mapped[int] = mapped_column(Integer, default=0)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0)
    reported_count: Mapped[int] = mapped_column(Integer, default=0)
    is_ambassador: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Video proof / content credits
    has_proof_video: Mapped[bool] = mapped_column(Boolean, default=False)
    proof_video_url: Mapped[str] = mapped_column(String, default="")
    content_credit_balance: Mapped[int] = mapped_column(Integer, default=0)
    
    # Membership & monetization
    is_member: Mapped[bool] = mapped_column(Boolean, default=False)
    member_since: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'moderator', 'admin')", name="ck_users_role"),
        CheckConstraint("account_status IN ('active', 'suspended', 'deleted')", name="ck_users_account_status"),
    )

    skills_taught = relationship("UserSkill", back_populates="user",
                                  foreign_keys="UserSkill.user_id")
    credit_balance = relationship("CreditAccount", back_populates="user",
                                   uselist=False)


class UserSkill(db.Model):
    __tablename__ = "user_skills"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[SkillCategory] = mapped_column(SAEnum(SkillCategory), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    proficiency: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    # Variable credit pricing: 1 = flat rate (default), up to RELAY_MAX_CREDIT_COST
    credit_cost: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        CheckConstraint("credit_cost = 1", name="ck_user_skills_trial_credit_cost"),
        CheckConstraint("proficiency BETWEEN 1 AND 5", name="ck_user_skills_proficiency"),
    )

    user = relationship("User", back_populates="skills_taught",
                         foreign_keys=[user_id])


class UserWant(db.Model):
    __tablename__ = "user_wants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[SkillCategory] = mapped_column(SAEnum(SkillCategory), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")


# ── Credits ────────────────────────────────────────────

class CreditAccount(db.Model):
    __tablename__ = "credit_accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_credit_accounts_nonnegative"),
    )

    user = relationship("User", back_populates="credit_balance")


class CreditTransaction(db.Model):
    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    actor_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    related_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_credit_transactions_nonzero"),
        UniqueConstraint(
            "user_id", "type", "source_type", "source_id",
            name="uq_credit_transactions_user_event_source",
        ),
    )


# ── Sessions ───────────────────────────────────────────

class Session(db.Model):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    teacher_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    learner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    skill_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(SAEnum(SessionStatus), default=SessionStatus.REQUESTED)
    notes: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    meet_link: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    # Amount charged at debit time — single source of truth for all credit/refund ops.
    # Never re-read the listing price or FLAT_RATE after this is set.
    amount_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Two-party completion: both must confirm before credits release
    teacher_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    learner_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    cancellation_reason: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        CheckConstraint("teacher_id <> learner_id", name="ck_sessions_distinct_participants"),
        CheckConstraint("amount_charged IN (0, 1)", name="ck_sessions_trial_charge"),
    )


# ── Reviews ────────────────────────────────────────────

class SessionReview(db.Model):
    __tablename__ = "session_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    reviewee_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_session_reviews_rating"),
        CheckConstraint("reviewer_id <> reviewee_id", name="ck_session_reviews_distinct_users"),
        UniqueConstraint("session_id", "reviewer_id", name="uq_session_reviews_session_reviewer"),
    )


# ── Waitlist ───────────────────────────────────────────

class WaitlistEntry(db.Model):
    __tablename__ = "waitlist_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    signed_up: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


# ── Password Reset ─────────────────────────────────────

class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EmailDelivery(db.Model):
    __tablename__ = "email_deliveries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recipient_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_code: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'delivered', 'failed')", name="ck_email_deliveries_status"),
        CheckConstraint("attempts >= 0", name="ck_email_deliveries_attempts"),
    )


class ConsentAcceptance(db.Model):
    __tablename__ = "consent_acceptances"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    document: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "document", "version",
            name="uq_consent_acceptances_user_document_version",
        ),
    )


class UserBlock(db.Model):
    __tablename__ = "user_blocks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    blocker_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    blocked_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("blocker_id <> blocked_id", name="ck_user_blocks_distinct_users"),
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_pair"),
    )


class SafetyReport(db.Model):
    __tablename__ = "safety_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    reporter_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    reported_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("reporter_id <> reported_user_id", name="ck_safety_reports_distinct_users"),
        CheckConstraint("status IN ('open', 'reviewing', 'resolved', 'dismissed')", name="ck_safety_reports_status"),
    )


class SessionDispute(db.Model):
    __tablename__ = "session_disputes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), unique=True, nullable=False)
    opened_by_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    resolution: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_session_disputes_status"),
    )


class ModerationAction(db.Model):
    __tablename__ = "moderation_actions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    moderator_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    target_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    report_id: Mapped[str] = mapped_column(String, ForeignKey("safety_reports.id"), nullable=True)
    dispute_id: Mapped[str] = mapped_column(String, ForeignKey("session_disputes.id"), nullable=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
