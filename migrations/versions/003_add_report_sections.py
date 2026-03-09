from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
JSON_PAYLOAD = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

# revision identifiers, used by Alembic.
revision = "003_add_report_sections"
down_revision = "002_add_dispatch_scheduler_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_sections",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("report_id", BIGINT_PK, sa.ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_key", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_chunks", JSON_PAYLOAD, nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("report_id", "section_key", name="uk_report_sections_report_id_section_key"),
    )
    op.create_index("idx_report_sections_report_id", "report_sections", ["report_id"])


def downgrade() -> None:
    op.drop_index("idx_report_sections_report_id", table_name="report_sections")
    op.drop_table("report_sections")
