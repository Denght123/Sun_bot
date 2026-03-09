from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
JSON_PAYLOAD = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

# revision identifiers, used by Alembic.
revision = "004_add_system_events"
down_revision = "003_add_report_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_events",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("object_type", sa.String(length=50), nullable=True),
        sa.Column("object_id", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", JSON_PAYLOAD, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_system_events_event_type", "system_events", ["event_type"])
    op.create_index("idx_system_events_level_occurred_at", "system_events", ["level", "occurred_at"])
    op.create_index("idx_system_events_object_type_object_id", "system_events", ["object_type", "object_id"])


def downgrade() -> None:
    op.drop_index("idx_system_events_object_type_object_id", table_name="system_events")
    op.drop_index("idx_system_events_level_occurred_at", table_name="system_events")
    op.drop_index("idx_system_events_event_type", table_name="system_events")
    op.drop_table("system_events")
