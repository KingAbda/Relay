"""Relay — Data models. Users, skills, sessions, credits."""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from .database import Base


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


class SessionStatus(str, enum.Enum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class TransactionType(str, enum.Enum):
    EARN = "earn"        # teaching a session
    SPEND = "spend"      # learning a session
    BONUS = "bonus"      # signup bonus, referral
    EXPIRE = "expire"    # credits expired


# ── User ───────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)

    # Profile
    bio = Column(Text, default="")
    avatar_url = Column(String, default="")

    # Onboarding
    onboarded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    skills_taught = relationship("UserSkill", back_populates="user",
                                  foreign_keys="UserSkill.user_id")
    credit_balance = relationship("CreditAccount", back_populates="user",
                                   uselist=False)


class UserSkill(Base):
    """A skill a user can teach."""
    __tablename__ = "user_skills"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)           # e.g. "Guitar"
    category = Column(SAEnum(SkillCategory), nullable=False)
    description = Column(Text, default="")
    proficiency = Column(Integer, default=3)         # 1-5 scale

    user = relationship("User", back_populates="skills_taught",
                         foreign_keys=[user_id])


class UserWant(Base):
    """A skill a user wants to learn."""
    __tablename__ = "user_wants"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    category = Column(SAEnum(SkillCategory), nullable=False)
    description = Column(Text, default="")


# ── Credits ────────────────────────────────────────────

class CreditAccount(Base):
    __tablename__ = "credit_accounts"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Float, default=0.0)

    user = relationship("User", back_populates="credit_balance")


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)            # positive = earn, negative = spend
    type = Column(SAEnum(TransactionType), nullable=False)
    description = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Sessions ───────────────────────────────────────────

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=_uuid)
    teacher_id = Column(String, ForeignKey("users.id"), nullable=False)
    learner_id = Column(String, ForeignKey("users.id"), nullable=False)
    skill_name = Column(String, nullable=False)
    status = Column(SAEnum(SessionStatus), default=SessionStatus.REQUESTED)
    notes = Column(Text, default="")
    scheduled_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
