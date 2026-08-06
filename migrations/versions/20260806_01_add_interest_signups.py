"""Add the interest_signups table for landing page email capture.

Revision ID: 20260806_01
Revises: 20260731_01

Purely additive: creates one new table for collecting interest-list emails
before the trial launches. No foreign keys or dependencies on existing data.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_01"
down_revision = "20260731_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interest_signups",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_interest_signups"),
    )
    op.create_index("ix_interest_signups_email", "interest_signups", ["email"], unique=True)


def downgrade():
    op.drop_index("ix_interest_signups_email", table_name="interest_signups")
    op.drop_table("interest_signups")
