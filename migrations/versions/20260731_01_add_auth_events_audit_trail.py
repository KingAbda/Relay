"""Add the auth_events authentication audit trail.

Revision ID: 20260731_01
Revises: 20260713_01

Purely additive: creates one new table and touches no existing business data,
so it is safe to apply to a populated trial database.

The downgrade drops the table, which would destroy audit history. It therefore
refuses to run once any event has been recorded, matching the fail-closed
preflight in ``20260713_01`` — an operator must explicitly export and clear the
table before rolling back. Without this guard a multi-step downgrade would
silently discard the trail before the earlier revision's guard ever fired.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_01"
down_revision = "20260713_01"
branch_labels = None
depends_on = None


AUTH_EVENT_CHECK = (
    "event IN ("
    "'login_succeeded', 'login_failed', 'login_blocked_locked', "
    "'account_locked', 'logout', 'email_verified', "
    "'password_reset_requested', 'password_reset_completed')"
)


def upgrade():
    op.create_table(
        "auth_events",
        sa.Column("id", sa.String(), nullable=False),
        # Nullable: failed logins against an unknown address have no user row.
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("event", sa.String(32), nullable=False),
        # SHA-256 hex digests, never raw identifiers.
        sa.Column("email_hash", sa.String(64), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_auth_events"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_auth_events_user_id_users"
        ),
        sa.CheckConstraint(AUTH_EVENT_CHECK, name="ck_auth_events_event"),
    )
    op.create_index("ix_auth_events_user_id", "auth_events", ["user_id"])
    op.create_index("ix_auth_events_event", "auth_events", ["event"])
    op.create_index("ix_auth_events_email_hash", "auth_events", ["email_hash"])
    op.create_index("ix_auth_events_created_at", "auth_events", ["created_at"])


def _fail(message):
    raise RuntimeError(f"Relay migration preflight failed: {message}")


def downgrade():
    recorded = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM auth_events")
    ).scalar_one()
    if recorded:
        _fail(
            f"cannot roll back while auth_events contains {recorded} audit record(s); "
            "export the authentication trail before downgrading"
        )
    op.drop_index("ix_auth_events_created_at", table_name="auth_events")
    op.drop_index("ix_auth_events_email_hash", table_name="auth_events")
    op.drop_index("ix_auth_events_event", table_name="auth_events")
    op.drop_index("ix_auth_events_user_id", table_name="auth_events")
    op.drop_table("auth_events")
