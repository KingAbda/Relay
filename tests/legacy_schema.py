"""Frozen Relay schema from the committed pre-readiness models.

This module deliberately does not import ``app.models``. Migration tests use it
as independent evidence that the adoption revision upgrades the actual legacy
shape rather than merely creating today's schema from scratch.
"""

import sqlalchemy as sa


metadata = sa.MetaData()

skill_category = sa.Enum(
    "CREATIVE", "ACADEMIC", "TECHNICAL", "SOCIAL", "LIFESTYLE",
    "FINANCE", "LANGUAGES", "TRADES", "OTHER", name="skillcategory",
)
session_status = sa.Enum(
    "REQUESTED", "CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW",
    name="sessionstatus",
)
transaction_type = sa.Enum(
    "EARN", "SPEND", "BONUS", "EXPIRE", "REFERRAL", "REFUND",
    "TOPUP", "PURCHASE", name="transactiontype",
)

users = sa.Table(
    "users", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("email", sa.String, nullable=False),
    sa.Column("password_hash", sa.String, nullable=False),
    sa.Column("full_name", sa.String, nullable=False),
    sa.Column("bio", sa.Text, nullable=False),
    sa.Column("avatar_url", sa.String, nullable=False),
    sa.Column("email_verified", sa.Boolean, nullable=False),
    sa.Column("verification_token", sa.String),
    sa.Column("account_locked_until", sa.DateTime),
    sa.Column("failed_login_attempts", sa.Integer, nullable=False),
    sa.Column("onboarded", sa.Boolean, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("last_active", sa.DateTime, nullable=False),
    sa.Column("referred_by", sa.String, sa.ForeignKey("users.id")),
    sa.Column("school", sa.String, nullable=False),
    sa.Column("major", sa.String, nullable=False),
    sa.Column("graduation_year", sa.String, nullable=False),
    sa.Column("profile_photo", sa.String, nullable=False),
    sa.Column("edu_verified", sa.Boolean, nullable=False),
    sa.Column("verification_code", sa.String),
    sa.Column("verification_code_sent_at", sa.DateTime),
    sa.Column("completed_sessions_count", sa.Integer, nullable=False),
    sa.Column("no_show_count", sa.Integer, nullable=False),
    sa.Column("reported_count", sa.Integer, nullable=False),
    sa.Column("is_ambassador", sa.Boolean, nullable=False),
    sa.Column("has_proof_video", sa.Boolean, nullable=False),
    sa.Column("proof_video_url", sa.String, nullable=False),
    sa.Column("content_credit_balance", sa.Integer, nullable=False),
    sa.Column("is_member", sa.Boolean, nullable=False),
    sa.Column("member_since", sa.DateTime),
)
sa.Index("ix_users_email", users.c.email, unique=True)

waitlist_entries = sa.Table(
    "waitlist_entries", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("email", sa.String, nullable=False),
    sa.Column("signed_up", sa.DateTime, nullable=False),
)
sa.Index("ix_waitlist_entries_email", waitlist_entries.c.email, unique=True)

credit_accounts = sa.Table(
    "credit_accounts", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False, unique=True),
    sa.Column("balance", sa.Float, nullable=False),
)

credit_transactions = sa.Table(
    "credit_transactions", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("amount", sa.Float, nullable=False),
    sa.Column("type", transaction_type, nullable=False),
    sa.Column("description", sa.String, nullable=False),
    sa.Column("related_user_id", sa.String),
    sa.Column("created_at", sa.DateTime, nullable=False),
)
sa.Index("ix_credit_transactions_user_id", credit_transactions.c.user_id)

password_reset_tokens = sa.Table(
    "password_reset_tokens", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("token", sa.String, nullable=False),
    sa.Column("expires_at", sa.DateTime, nullable=False),
    sa.Column("used", sa.Boolean, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
)
sa.Index("ix_password_reset_tokens_token", password_reset_tokens.c.token, unique=True)
sa.Index("ix_password_reset_tokens_user_id", password_reset_tokens.c.user_id)

session_series = sa.Table(
    "session_series", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("teacher_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("learner_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("skill_name", sa.String, nullable=False),
    sa.Column("total_sessions", sa.Integer, nullable=False),
    sa.Column("completed_sessions", sa.Integer, nullable=False),
    sa.Column("credit_cost_per_session", sa.Integer, nullable=False),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
)

sessions = sa.Table(
    "sessions", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("teacher_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("learner_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("skill_name", sa.String, nullable=False),
    sa.Column("status", session_status, nullable=False),
    sa.Column("notes", sa.Text, nullable=False),
    sa.Column("scheduled_at", sa.DateTime),
    sa.Column("completed_at", sa.DateTime),
    sa.Column("meet_link", sa.String),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("amount_charged", sa.Float, nullable=False),
    sa.Column("teacher_completed", sa.Boolean, nullable=False),
    sa.Column("learner_completed", sa.Boolean, nullable=False),
)

skill_requests = sa.Table(
    "skill_requests", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("category", skill_category, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("max_credits", sa.Integer, nullable=False),
    sa.Column("claimed_by", sa.String, sa.ForeignKey("users.id")),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
)
sa.Index("ix_skill_requests_user_id", skill_requests.c.user_id)

user_skills = sa.Table(
    "user_skills", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("category", skill_category, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("proficiency", sa.Integer, nullable=False),
    sa.Column("is_active", sa.Boolean, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("credit_cost", sa.Integer, nullable=False),
)

user_wants = sa.Table(
    "user_wants", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("category", skill_category, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
)

session_reviews = sa.Table(
    "session_reviews", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("reviewer_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("reviewee_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("rating", sa.Integer, nullable=False),
    sa.Column("review", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
)


def create_legacy_schema(engine):
    """Create only the frozen pre-readiness schema on a disposable engine."""
    metadata.create_all(engine)
