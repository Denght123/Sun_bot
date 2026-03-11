from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
JSON_PAYLOAD = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

# revision identifiers, used by Alembic.
revision = "001_init_rule_engine"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_items",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("source_platform", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("fallback_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", JSON_PAYLOAD, nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("is_finance_related", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("finance_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("process_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_platform", "external_id", name="uk_raw_items_source_platform_external_id"),
    )
    op.create_index("idx_raw_items_source_platform_collected_at", "raw_items", ["source_platform", "collected_at"])
    op.create_index("idx_raw_items_content_hash", "raw_items", ["content_hash"])
    op.create_index("idx_raw_items_is_finance_related", "raw_items", ["is_finance_related"])
    op.create_index("idx_raw_items_published_at", "raw_items", ["published_at"])

    op.create_table(
        "event_clusters",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("sub_category", sa.String(length=50), nullable=True),
        sa.Column("importance_score", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("heat_score", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cluster_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_key", name="uk_event_clusters_event_key"),
    )
    op.create_index("idx_event_clusters_cluster_date_category", "event_clusters", ["cluster_date", "category"])
    op.create_index("idx_event_clusters_importance_score", "event_clusters", ["importance_score"])
    op.create_index("idx_event_clusters_last_seen_at", "event_clusters", ["last_seen_at"])

    op.create_table(
        "event_sources",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("cluster_id", BIGINT_PK, sa.ForeignKey("event_clusters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_item_id", BIGINT_PK, sa.ForeignKey("raw_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_weight", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cluster_id", "raw_item_id", name="uk_event_sources_cluster_id_raw_item_id"),
    )
    op.create_index("idx_event_sources_cluster_id", "event_sources", ["cluster_id"])
    op.create_index("idx_event_sources_raw_item_id", "event_sources", ["raw_item_id"])


def downgrade() -> None:
    op.drop_index("idx_event_sources_raw_item_id", table_name="event_sources")
    op.drop_index("idx_event_sources_cluster_id", table_name="event_sources")
    op.drop_table("event_sources")

    op.drop_index("idx_event_clusters_last_seen_at", table_name="event_clusters")
    op.drop_index("idx_event_clusters_importance_score", table_name="event_clusters")
    op.drop_index("idx_event_clusters_cluster_date_category", table_name="event_clusters")
    op.drop_table("event_clusters")

    op.drop_index("idx_raw_items_published_at", table_name="raw_items")
    op.drop_index("idx_raw_items_is_finance_related", table_name="raw_items")
    op.drop_index("idx_raw_items_content_hash", table_name="raw_items")
    op.drop_index("idx_raw_items_source_platform_collected_at", table_name="raw_items")
    op.drop_table("raw_items")
