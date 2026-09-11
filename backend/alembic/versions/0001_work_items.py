import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("external_id", sa.String(100), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="RECEIVED"),
        sa.Column("analysis", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("ai_provider", sa.String(50), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('RECEIVED','ANALYSING','READY_FOR_REVIEW','COMPLETED','FAILED')",
            name="valid_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="nonnegative_attempts"),
        sa.CheckConstraint(
            "(status IN ('READY_FOR_REVIEW','COMPLETED')) = (analysis IS NOT NULL)",
            name="analysis_state",
        ),
        sa.CheckConstraint(
            "(status = 'FAILED' AND error_code IS NOT NULL AND error_message IS NOT NULL) OR (status <> 'FAILED' AND error_code IS NULL AND error_message IS NULL)",
            name="error_state",
        ),
        sa.CheckConstraint(
            "(status = 'ANALYSING' AND attempt_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status <> 'ANALYSING' AND attempt_token IS NULL AND lease_expires_at IS NULL)",
            name="lease_state",
        ),
    )
    op.create_index("ix_work_items_status_created", "work_items", ["status", "created_at"])
    op.create_index("ix_work_items_created", "work_items", ["created_at"])


def downgrade():
    op.drop_table("work_items")
