from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
JSON_PAYLOAD = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

# revision identifiers, used by Alembic.
revision = "002_dispatch_scheduler"
down_revision = "001_init_rule_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_reports",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("generation_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("data_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_word_count", sa.Integer(), nullable=True),
        sa.Column("total_message_chunks", sa.Integer(), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("link_bundle", JSON_PAYLOAD, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("report_date", name="uk_daily_reports_report_date"),
    )
    op.create_index("idx_daily_reports_generation_status", "daily_reports", ["generation_status"])

    op.create_table(
        "dispatch_tasks",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("report_id", BIGINT_PK, sa.ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.String(length=64), nullable=True),
        sa.Column("target_user", sa.String(length=128), nullable=False),
        sa.Column("task_type", sa.String(length=30), nullable=False),
        sa.Column("payload", JSON_PAYLOAD, nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retry", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", name="uk_dispatch_tasks_task_id"),
    )
    op.create_index("idx_dispatch_tasks_report_id", "dispatch_tasks", ["report_id"])
    op.create_index("idx_dispatch_tasks_sender_id", "dispatch_tasks", ["sender_id"])
    op.create_index("idx_dispatch_tasks_status_scheduled_at", "dispatch_tasks", ["status", "scheduled_at"])

    op.create_table(
        "dispatch_attempts",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("task_id", BIGINT_PK, sa.ForeignKey("dispatch_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "attempt_no", name="uk_dispatch_attempts_task_id_attempt_no"),
    )
    op.create_index("idx_dispatch_attempts_task_id", "dispatch_attempts", ["task_id"])
    op.create_index("idx_dispatch_attempts_sender_id", "dispatch_attempts", ["sender_id"])

    op.create_table(
        "senders",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("sender_id", sa.String(length=64), nullable=False),
        sa.Column("sender_name", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="offline"),
        sa.Column("wechat_login_status", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("host_name", sa.String(length=100), nullable=True),
        sa.Column("current_ip", sa.String(length=64), nullable=True),
        sa.Column("client_version", sa.String(length=50), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("sender_id", name="uk_senders_sender_id"),
    )
    op.create_index("idx_senders_status", "senders", ["status"])
    op.create_index("idx_senders_last_heartbeat_at", "senders", ["last_heartbeat_at"])

    op.create_table(
        "sender_heartbeats",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("sender_id", BIGINT_PK, sa.ForeignKey("senders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("wechat_login_status", sa.String(length=20), nullable=False),
        sa.Column("payload", JSON_PAYLOAD, nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_sender_heartbeats_sender_id_reported_at", "sender_heartbeats", ["sender_id", "reported_at"])


def downgrade() -> None:
    op.drop_index("idx_sender_heartbeats_sender_id_reported_at", table_name="sender_heartbeats")
    op.drop_table("sender_heartbeats")

    op.drop_index("idx_senders_last_heartbeat_at", table_name="senders")
    op.drop_index("idx_senders_status", table_name="senders")
    op.drop_table("senders")

    op.drop_index("idx_dispatch_attempts_sender_id", table_name="dispatch_attempts")
    op.drop_index("idx_dispatch_attempts_task_id", table_name="dispatch_attempts")
    op.drop_table("dispatch_attempts")

    op.drop_index("idx_dispatch_tasks_status_scheduled_at", table_name="dispatch_tasks")
    op.drop_index("idx_dispatch_tasks_sender_id", table_name="dispatch_tasks")
    op.drop_index("idx_dispatch_tasks_report_id", table_name="dispatch_tasks")
    op.drop_table("dispatch_tasks")

    op.drop_index("idx_daily_reports_generation_status", table_name="daily_reports")
    op.drop_table("daily_reports")
