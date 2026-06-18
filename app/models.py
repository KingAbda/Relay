"""Relay — Data models. Users, skills, sessions, credits, reviews."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from .database import db


def _uuid():
    return str(uuid.uuid4())


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


class TransactionType(str, enum.Enum):
    EARN = "earn"
    SPEND = "spend"
    BONUS = "bonus"
    EXPIRE = "expire"
    REFERRAL = "referral"
    REFUND = "refund"
    def __str__(self):
        return self.value


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
    verification_token: Mapped[str] = mapped_column(String, nullable=True)
    account_locked_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Referral system
    referred_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    
    # Profile expansion
    school: Mapped[str] = mapped_column(String, default="")
    major: Mapped[str] = mapped_column(String, default="")
    graduation_year: Mapped[str] = mapped_column(String, default="")
    profile_photo: Mapped[str] = mapped_column(String, default="")  # path or URL
    
    # Student verification
    edu_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_code: Mapped[str] = mapped_column(String, nullable=True)
    verification_code_sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # Good/bad student tracking
    completed_sessions_count: Mapped[int] = mapped_column(Integer, default=0)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0)
    reported_count: Mapped[int] = mapped_column(Integer, default=0)
    is_ambassador: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Video proof / content credits
    has_proof_video: Mapped[bool] = mapped_column(Boolean, default=False)
    proof_video_url: Mapped[str] = mapped_column(String, default="")
    content_credit_balance: Mapped[int] = mapped_column(Integer, default=0)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    balance: Mapped[float] = mapped_column(Float, default=0.0)

    user = relationship("User", back_populates="credit_balance")


class CreditTransaction(db.Model):
    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType), nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    related_user_id: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Reviews ────────────────────────────────────────────

class SessionReview(db.Model):
    __tablename__ = "session_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    reviewee_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Waitlist ───────────────────────────────────────────

class WaitlistEntry(db.Model):
    __tablename__ = "waitlist_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    signed_up: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── Password Reset ─────────────────────────────────────

class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
