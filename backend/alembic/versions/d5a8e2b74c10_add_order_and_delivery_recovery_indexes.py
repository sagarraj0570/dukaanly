"""add order and delivery recovery indexes

Revision ID: d5a8e2b74c10
Revises: c4d9e1f58a32
Create Date: 2026-10-27 18:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5a8e2b74c10'
down_revision = 'c4d9e1f58a32'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Index for fast bounded scanning of stale pending/confirmed orders
    op.create_index(
        'ix_orders_status_created_at',
        'orders',
        ['status', 'created_at'],
        unique=False
    )
    # Index for fast bounded scanning of stale assigned deliveries
    op.create_index(
        'ix_deliveries_status_assigned_at',
        'deliveries',
        ['status', 'assigned_at'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_deliveries_status_assigned_at', table_name='deliveries')
    op.drop_index('ix_orders_status_created_at', table_name='orders')
