"""Frozen pre-readiness Relay schema baseline.

Revision ID: 20260713_00
Revises: None
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260713_00"
down_revision = None
branch_labels = None
depends_on = None

SKILL_CATEGORIES = (
    "CREATIVE", "ACADEMIC", "TECHNICAL", "SOCIAL", "LIFESTYLE",
    "FINANCE", "LANGUAGES", "TRADES", "OTHER",
)
SESSION_STATUSES = ("REQUESTED", "CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW")
TRANSACTION_TYPES = (
    "EARN", "SPEND", "BONUS", "EXPIRE", "REFERRAL", "REFUND",
    "TOPUP", "PURCHASE",
)


def _enum(name, values):
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for name, values in (
            ("skillcategory", SKILL_CATEGORIES),
            ("sessionstatus", SESSION_STATUSES),
            ("transactiontype", TRANSACTION_TYPES),
        ):
            postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.String(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("verification_token", sa.String(), nullable=True),
        sa.Column("account_locked_until", sa.DateTime(), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("onboarded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_active", sa.DateTime(), nullable=False),
        sa.Column("referred_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("school", sa.String(), nullable=False),
        sa.Column("major", sa.String(), nullable=False),
        sa.Column("graduation_year", sa.String(), nullable=False),
        sa.Column("profile_photo", sa.String(), nullable=False),
        sa.Column("edu_verified", sa.Boolean(), nullable=False),
        sa.Column("verification_code", sa.String(), nullable=True),
        sa.Column("verification_code_sent_at", sa.DateTime(), nullable=True),
        sa.Column("completed_sessions_count", sa.Integer(), nullable=False),
        sa.Column("no_show_count", sa.Integer(), nullable=False),
        sa.Column("reported_count", sa.Integer(), nullable=False),
        sa.Column("is_ambassador", sa.Boolean(), nullable=False),
        sa.Column("has_proof_video", sa.Boolean(), nullable=False),
        sa.Column("proof_video_url", sa.String(), nullable=False),
        sa.Column("content_credit_balance", sa.Integer(), nullable=False),
        sa.Column("is_member", sa.Boolean(), nullable=False),
        sa.Column("member_since", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("signed_up", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_waitlist_entries_email", "waitlist_entries", ["email"], unique=True)

    op.create_table(
        "credit_accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("balance", sa.Float(), nullable=False),
    )
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("type", _enum("transactiontype", TRANSACTION_TYPES), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("related_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"])
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token", "password_reset_tokens", ["token"], unique=True)

    op.create_table(
        "session_series",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("teacher_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("learner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("skill_name", sa.String(), nullable=False),
        sa.Column("total_sessions", sa.Integer(), nullable=False),
        sa.Column("completed_sessions", sa.Integer(), nullable=False),
        sa.Column("credit_cost_per_session", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("teacher_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("learner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("skill_name", sa.String(), nullable=False),
        sa.Column("status", _enum("sessionstatus", SESSION_STATUSES), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("meet_link", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("amount_charged", sa.Float(), nullable=False),
        sa.Column("teacher_completed", sa.Boolean(), nullable=False),
        sa.Column("learner_completed", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "skill_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", _enum("skillcategory", SKILL_CATEGORIES), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("max_credits", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_skill_requests_user_id", "skill_requests", ["user_id"])
    op.create_table(
        "user_skills",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", _enum("skillcategory", SKILL_CATEGORIES), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("proficiency", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("credit_cost", sa.Integer(), nullable=False),
    )
    op.create_table(
        "user_wants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", _enum("skillcategory", SKILL_CATEGORIES), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "session_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("reviewer_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewee_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    for table in (
        "session_reviews", "user_wants", "user_skills", "skill_requests",
        "sessions", "session_series", "password_reset_tokens",
        "credit_transactions", "credit_accounts", "waitlist_entries", "users",
    ):
        op.drop_table(table)

    if op.get_bind().dialect.name == "postgresql":
        bind = op.get_bind()
        for name, values in (
            ("transactiontype", TRANSACTION_TYPES),
            ("sessionstatus", SESSION_STATUSES),
            ("skillcategory", SKILL_CATEGORIES),
        ):
            postgresql.ENUM(*values, name=name).drop(bind, checkfirst=True)
