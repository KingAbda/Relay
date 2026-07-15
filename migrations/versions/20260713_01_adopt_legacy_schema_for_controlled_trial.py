"""Adopt the legacy Relay schema for the controlled trial.

Revision ID: 20260713_01
Revises: 20260713_00

Existing pre-Alembic Relay databases must be stamped at ``20260713_00`` only
after the documented schema inventory passes. This revision then performs a
fail-closed data preflight before changing any business tables.
"""

import hashlib
import math

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260713_01"
down_revision = "20260713_00"
branch_labels = None
depends_on = None

LEGACY_TABLES = {
    "users", "waitlist_entries", "credit_accounts", "credit_transactions",
    "password_reset_tokens", "session_series", "sessions", "skill_requests",
    "user_skills", "user_wants", "session_reviews",
}
ADDITIVE_TABLES = (
    "moderation_actions", "session_disputes", "safety_reports", "user_blocks",
    "email_deliveries", "consent_acceptances",
)
LEGACY_TRANSACTION_TYPES = {
    "earn", "spend", "bonus", "expire", "referral", "refund", "topup", "purchase",
}
LEGACY_TRANSACTION_ENUM = (
    "EARN", "SPEND", "BONUS", "EXPIRE", "REFERRAL", "REFUND", "TOPUP", "PURCHASE",
)


def _fail(message):
    raise RuntimeError(f"Relay migration preflight failed: {message}")


def _scalar(sql, **params):
    return op.get_bind().execute(sa.text(sql), params).scalar_one()


def _require_integral(table, column, *, nonnegative=False, nonzero=False):
    rows = op.get_bind().execute(sa.text(f"SELECT id, {column} FROM {table}")).all()
    for row_id, value in rows:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            _fail(f"{table}.{column} is not numeric for row {row_id}")
        if not math.isfinite(numeric) or not numeric.is_integer():
            _fail(f"{table}.{column} must be a finite integer for row {row_id}")
        if nonnegative and numeric < 0:
            _fail(f"{table}.{column} must be nonnegative for row {row_id}")
        if nonzero and numeric == 0:
            _fail(f"{table}.{column} must be nonzero for row {row_id}")


def _preflight_upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    missing = sorted(LEGACY_TABLES - existing)
    if missing:
        _fail(f"legacy schema is missing tables: {', '.join(missing)}")

    _require_integral("credit_accounts", "balance", nonnegative=True)
    _require_integral("credit_transactions", "amount", nonzero=True)
    _require_integral("sessions", "amount_charged", nonnegative=True)

    if _scalar("SELECT COUNT(*) FROM sessions WHERE amount_charged NOT IN (0, 1)"):
        _fail("legacy sessions contain a non-trial charge; no value was rewritten")
    if _scalar("SELECT COUNT(*) FROM user_skills WHERE credit_cost <> 1"):
        _fail("legacy listings contain a non-trial price; no value was rewritten")
    if _scalar("SELECT COUNT(*) FROM user_skills WHERE proficiency NOT BETWEEN 1 AND 5"):
        _fail("legacy listings contain invalid proficiency values")
    if _scalar("SELECT COUNT(*) FROM sessions WHERE teacher_id = learner_id"):
        _fail("legacy sessions contain identical teacher and learner IDs")
    if _scalar("SELECT COUNT(*) FROM session_reviews WHERE rating NOT BETWEEN 1 AND 5"):
        _fail("legacy reviews contain invalid ratings")
    if _scalar("SELECT COUNT(*) FROM session_reviews WHERE reviewer_id = reviewee_id"):
        _fail("legacy reviews contain self-reviews")
    if _scalar(
        "SELECT COUNT(*) FROM (SELECT session_id, reviewer_id FROM session_reviews "
        "GROUP BY session_id, reviewer_id HAVING COUNT(*) > 1) AS duplicates"
    ):
        _fail("legacy reviews contain duplicate session/reviewer pairs")
    if _scalar(
        "SELECT COUNT(*) FROM credit_transactions t LEFT JOIN users u "
        "ON t.related_user_id = u.id WHERE t.related_user_id IS NOT NULL AND u.id IS NULL"
    ):
        _fail("legacy ledger contains a related_user_id that is not a user")

    allowed = ", ".join(f"'{value}'" for value in sorted(LEGACY_TRANSACTION_TYPES))
    if _scalar(
        f"SELECT COUNT(*) FROM credit_transactions "
        f"WHERE lower(CAST(type AS VARCHAR)) NOT IN ({allowed})"
    ):
        _fail("legacy ledger contains an unknown transaction type")

    balances = {
        user_id: int(float(balance))
        for user_id, balance in op.get_bind().execute(
            sa.text("SELECT user_id, balance FROM credit_accounts")
        )
    }
    totals = {}
    for user_id, amount in op.get_bind().execute(
        sa.text("SELECT user_id, amount FROM credit_transactions")
    ):
        totals[user_id] = totals.get(user_id, 0) + int(float(amount))
    mismatches = sorted(
        user_id for user_id, balance in balances.items()
        if totals.get(user_id, 0) != balance
    )
    if mismatches:
        _fail(
            f"account/ledger mismatch for {len(mismatches)} user(s); balances were not repaired"
        )


def _preflight_downgrade():
    for table in ADDITIVE_TABLES:
        if _scalar(f"SELECT COUNT(*) FROM {table}"):
            _fail(f"cannot roll back while {table} contains new-schema records")
    if _scalar("SELECT COUNT(*) FROM users WHERE role <> 'user' OR account_status <> 'active'"):
        _fail("cannot roll back non-user roles or non-active account states")
    if _scalar(
        "SELECT COUNT(*) FROM sessions WHERE upper(CAST(status AS VARCHAR)) = 'DISPUTED'"
    ):
        _fail("cannot roll back disputed sessions to the legacy enum")
    if _scalar(
        "SELECT COUNT(*) FROM credit_transactions WHERE source_type <> 'legacy' "
        "OR source_id <> id OR idempotency_key <> ('legacy:' || id) "
        "OR actor_user_id IS NOT NULL"
    ):
        _fail("cannot roll back ledger events created by the controlled-trial schema")
    allowed = ", ".join(f"'{value}'" for value in sorted(LEGACY_TRANSACTION_TYPES))
    if _scalar(
        f"SELECT COUNT(*) FROM credit_transactions "
        f"WHERE lower(CAST(type AS VARCHAR)) NOT IN ({allowed})"
    ):
        _fail("cannot map current ledger transaction types to the legacy enum")


def _create_additive_tables():
    op.create_table(
        "consent_acceptances",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("document", sa.String(32), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "document", "version",
            name="uq_consent_acceptances_user_document_version",
        ),
    )
    op.create_index("ix_consent_acceptances_user_id", "consent_acceptances", ["user_id"])

    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("recipient_user_id", sa.String(), nullable=False),
        sa.Column("message_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'failed')", name="ck_email_deliveries_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_email_deliveries_attempts"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_email_deliveries_idempotency_key"),
    )
    op.create_index("ix_email_deliveries_recipient_user_id", "email_deliveries", ["recipient_user_id"])

    op.create_table(
        "user_blocks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("blocker_id", sa.String(), nullable=False),
        sa.Column("blocked_id", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("blocker_id <> blocked_id", name="ck_user_blocks_distinct_users"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_pair"),
    )
    op.create_index("ix_user_blocks_blocked_id", "user_blocks", ["blocked_id"])
    op.create_index("ix_user_blocks_blocker_id", "user_blocks", ["blocker_id"])

    op.create_table(
        "safety_reports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("reporter_id", sa.String(), nullable=False),
        sa.Column("reported_user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('open', 'reviewing', 'resolved', 'dismissed')", name="ck_safety_reports_status"),
        sa.CheckConstraint("reporter_id <> reported_user_id", name="ck_safety_reports_distinct_users"),
        sa.ForeignKeyConstraint(["reported_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_safety_reports_reported_user_id", "safety_reports", ["reported_user_id"])
    op.create_index("ix_safety_reports_reporter_id", "safety_reports", ["reporter_id"])
    op.create_index("ix_safety_reports_session_id", "safety_reports", ["session_id"])

    op.create_table(
        "session_disputes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("opened_by_id", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_session_disputes_status"),
        sa.ForeignKeyConstraint(["opened_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_session_disputes_session_id"),
    )

    op.create_table(
        "moderation_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("moderator_id", sa.String(), nullable=False),
        sa.Column("target_user_id", sa.String(), nullable=True),
        sa.Column("report_id", sa.String(), nullable=True),
        sa.Column("dispute_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dispute_id"], ["session_disputes.id"]),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["safety_reports.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_moderation_actions_moderator_id", "moderation_actions", ["moderator_id"])
    op.create_index("ix_moderation_actions_target_user_id", "moderation_actions", ["target_user_id"])


def upgrade():
    _preflight_upgrade()
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'DISPUTED'")

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("verification_token_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("verification_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("verification_sent_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("session_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("role", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("account_status", sa.String(16), nullable=True))
    op.execute("UPDATE users SET session_version = 0, role = 'user', account_status = 'active'")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("session_version", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("role", existing_type=sa.String(16), nullable=False)
        batch_op.alter_column("account_status", existing_type=sa.String(16), nullable=False)
        batch_op.create_unique_constraint("uq_users_verification_token_hash", ["verification_token_hash"])
        batch_op.create_check_constraint("ck_users_role", "role IN ('user', 'moderator', 'admin')")
        batch_op.create_check_constraint(
            "ck_users_account_status", "account_status IN ('active', 'suspended', 'deleted')"
        )
        batch_op.drop_column("verification_token")
        batch_op.drop_column("verification_code_sent_at")
        batch_op.drop_column("verification_code")

    with op.batch_alter_table("credit_accounts") as batch_op:
        batch_op.alter_column(
            "balance", existing_type=sa.Float(), type_=sa.Integer(), nullable=False,
            postgresql_using="balance::integer",
        )
        batch_op.create_check_constraint("ck_credit_accounts_nonnegative", "balance >= 0")

    with op.batch_alter_table("credit_transactions") as batch_op:
        batch_op.add_column(sa.Column("actor_user_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_type", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("source_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(), nullable=True))
    if dialect == "postgresql":
        op.execute(
            "UPDATE credit_transactions SET source_type = 'legacy', "
            "source_id = id, idempotency_key = 'legacy:' || id"
        )
    else:
        op.execute(
            "UPDATE credit_transactions SET type = lower(type), source_type = 'legacy', "
            "source_id = id, idempotency_key = 'legacy:' || id"
        )
    legacy_type = (
        postgresql.ENUM(*LEGACY_TRANSACTION_ENUM, name="transactiontype", create_type=False)
        if dialect == "postgresql" else sa.String(8)
    )
    with op.batch_alter_table("credit_transactions") as batch_op:
        batch_op.alter_column(
            "amount", existing_type=sa.Float(), type_=sa.Integer(), nullable=False,
            postgresql_using="amount::integer",
        )
        batch_op.alter_column(
            "type", existing_type=legacy_type, type_=sa.String(32), nullable=False,
            postgresql_using="lower(type::text)",
        )
        batch_op.alter_column("source_type", existing_type=sa.String(32), nullable=False)
        batch_op.alter_column("source_id", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("idempotency_key", existing_type=sa.String(), nullable=False)
        batch_op.create_check_constraint("ck_credit_transactions_nonzero", "amount <> 0")
        batch_op.create_unique_constraint(
            "uq_credit_transactions_user_event_source",
            ["user_id", "type", "source_type", "source_id"],
        )
        batch_op.create_unique_constraint(
            "uq_credit_transactions_idempotency_key", ["idempotency_key"]
        )
        batch_op.create_foreign_key(
            "fk_credit_transactions_actor_user_id_users", "users", ["actor_user_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_credit_transactions_related_user_id_users", "users", ["related_user_id"], ["id"]
        )
    if dialect == "postgresql":
        postgresql.ENUM(*LEGACY_TRANSACTION_ENUM, name="transactiontype").drop(bind, checkfirst=True)

    with op.batch_alter_table("password_reset_tokens") as batch_op:
        batch_op.add_column(sa.Column("token_hash", sa.String(64), nullable=True))
    for token_id, token in bind.execute(sa.text("SELECT id, token FROM password_reset_tokens")):
        bind.execute(
            sa.text("UPDATE password_reset_tokens SET token_hash = :digest WHERE id = :id"),
            {"digest": hashlib.sha256(token.encode("utf-8")).hexdigest(), "id": token_id},
        )
    with op.batch_alter_table("password_reset_tokens") as batch_op:
        batch_op.alter_column("token_hash", existing_type=sa.String(64), nullable=False)
        batch_op.drop_index("ix_password_reset_tokens_token")
        batch_op.create_index("ix_password_reset_tokens_token_hash", ["token_hash"], unique=True)
        batch_op.drop_column("token")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.execute("UPDATE sessions SET cancellation_reason = ''")
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column(
            "amount_charged", existing_type=sa.Float(), type_=sa.Integer(), nullable=False,
            postgresql_using="amount_charged::integer",
        )
        batch_op.alter_column("cancellation_reason", existing_type=sa.Text(), nullable=False)
        batch_op.create_check_constraint(
            "ck_sessions_distinct_participants", "teacher_id <> learner_id"
        )
        batch_op.create_check_constraint("ck_sessions_trial_charge", "amount_charged IN (0, 1)")

    with op.batch_alter_table("user_skills") as batch_op:
        batch_op.create_check_constraint("ck_user_skills_trial_credit_cost", "credit_cost = 1")
        batch_op.create_check_constraint("ck_user_skills_proficiency", "proficiency BETWEEN 1 AND 5")

    with op.batch_alter_table("session_reviews") as batch_op:
        batch_op.create_check_constraint("ck_session_reviews_rating", "rating BETWEEN 1 AND 5")
        batch_op.create_check_constraint(
            "ck_session_reviews_distinct_users", "reviewer_id <> reviewee_id"
        )
        batch_op.create_unique_constraint(
            "uq_session_reviews_session_reviewer", ["session_id", "reviewer_id"]
        )

    _create_additive_tables()


def downgrade():
    _preflight_downgrade()
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_table("moderation_actions")
    op.drop_table("session_disputes")
    op.drop_table("safety_reports")
    op.drop_table("user_blocks")
    op.drop_table("email_deliveries")
    op.drop_table("consent_acceptances")

    with op.batch_alter_table("session_reviews") as batch_op:
        batch_op.drop_constraint("uq_session_reviews_session_reviewer", type_="unique")
        batch_op.drop_constraint("ck_session_reviews_distinct_users", type_="check")
        batch_op.drop_constraint("ck_session_reviews_rating", type_="check")

    with op.batch_alter_table("user_skills") as batch_op:
        batch_op.drop_constraint("ck_user_skills_proficiency", type_="check")
        batch_op.drop_constraint("ck_user_skills_trial_credit_cost", type_="check")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("ck_sessions_trial_charge", type_="check")
        batch_op.drop_constraint("ck_sessions_distinct_participants", type_="check")
        batch_op.alter_column(
            "amount_charged", existing_type=sa.Integer(), type_=sa.Float(), nullable=False,
            postgresql_using="amount_charged::double precision",
        )
        batch_op.drop_column("cancellation_reason")

    with op.batch_alter_table("password_reset_tokens") as batch_op:
        batch_op.add_column(sa.Column("token", sa.String(), nullable=True))
    op.execute("UPDATE password_reset_tokens SET token = token_hash")
    with op.batch_alter_table("password_reset_tokens") as batch_op:
        batch_op.alter_column("token", existing_type=sa.String(), nullable=False)
        batch_op.drop_index("ix_password_reset_tokens_token_hash")
        batch_op.create_index("ix_password_reset_tokens_token", ["token"], unique=True)
        batch_op.drop_column("token_hash")

    if dialect == "postgresql":
        legacy_enum = postgresql.ENUM(*LEGACY_TRANSACTION_ENUM, name="transactiontype")
        legacy_enum.create(bind, checkfirst=True)
        legacy_type = postgresql.ENUM(
            *LEGACY_TRANSACTION_ENUM, name="transactiontype", create_type=False
        )
    else:
        legacy_type = sa.Enum(*LEGACY_TRANSACTION_ENUM, name="transactiontype")
    op.execute("UPDATE credit_transactions SET type = upper(type)")
    with op.batch_alter_table("credit_transactions") as batch_op:
        batch_op.drop_constraint(
            "fk_credit_transactions_related_user_id_users", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_credit_transactions_actor_user_id_users", type_="foreignkey"
        )
        batch_op.drop_constraint("uq_credit_transactions_idempotency_key", type_="unique")
        batch_op.drop_constraint(
            "uq_credit_transactions_user_event_source", type_="unique"
        )
        batch_op.drop_constraint("ck_credit_transactions_nonzero", type_="check")
        batch_op.alter_column(
            "type", existing_type=sa.String(32), type_=legacy_type, nullable=False,
            postgresql_using="upper(type)::transactiontype",
        )
        batch_op.alter_column(
            "amount", existing_type=sa.Integer(), type_=sa.Float(), nullable=False,
            postgresql_using="amount::double precision",
        )
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_type")
        batch_op.drop_column("actor_user_id")

    with op.batch_alter_table("credit_accounts") as batch_op:
        batch_op.drop_constraint("ck_credit_accounts_nonnegative", type_="check")
        batch_op.alter_column(
            "balance", existing_type=sa.Integer(), type_=sa.Float(), nullable=False,
            postgresql_using="balance::double precision",
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("verification_token", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("verification_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("verification_code_sent_at", sa.DateTime(), nullable=True))
        batch_op.drop_constraint("uq_users_verification_token_hash", type_="unique")
        batch_op.drop_constraint("ck_users_account_status", type_="check")
        batch_op.drop_constraint("ck_users_role", type_="check")
        batch_op.drop_column("account_status")
        batch_op.drop_column("role")
        batch_op.drop_column("session_version")
        batch_op.drop_column("verification_sent_at")
        batch_op.drop_column("verification_expires_at")
        batch_op.drop_column("verification_token_hash")
