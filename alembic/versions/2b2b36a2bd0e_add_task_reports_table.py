"""add task reports table"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b2b36a2bd0e"
down_revision: str | None = "1f3ea2cb1d31"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "task_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("total_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_progress_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancelled_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_task_reports_owner_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_task_reports"),
        sa.UniqueConstraint("owner_id", name="uq_task_reports_owner_id"),
    )


def downgrade() -> None:
    op.drop_table("task_reports")
