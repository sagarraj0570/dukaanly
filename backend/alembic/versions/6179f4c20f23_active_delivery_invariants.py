"""active_delivery_invariants

Revision ID: 6179f4c20f23
Revises: 4d8e90f62a02
Create Date: 2026-10-27 00:20:51.225703

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6179f4c20f23'
down_revision: Union[str, Sequence[str], None] = '4d8e90f62a02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Replace unconditional order_id uniqueness with partial unique index for active deliveries."""
    conn = op.get_bind()

    # Pre-check: Ensure no orders currently have multiple active deliveries before applying constraint
    conflicting_orders = conn.execute(sa.text("""
        SELECT order_id, COUNT(*) 
        FROM deliveries 
        WHERE status IN ('pending', 'assigned', 'picked_up', 'out_for_delivery') 
        GROUP BY order_id 
        HAVING COUNT(*) > 1;
    """)).fetchall()
    if conflicting_orders:
        raise RuntimeError(
            f"Cannot apply migration 6179f4c20f23: conflicting active deliveries found for order(s): {conflicting_orders}"
        )

    # 1. Drop existing unconditional unique index on order_id
    op.drop_index(op.f('ix_deliveries_order_id'), table_name='deliveries')

    # 2. Create standard (non-unique) index on order_id for foreign key and query performance
    op.create_index(op.f('ix_deliveries_order_id'), 'deliveries', ['order_id'], unique=False)

    # 3. Create partial unique index on order_id for active delivery states only
    op.create_index(
        'idx_active_delivery_per_order',
        'deliveries',
        ['order_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'assigned', 'picked_up', 'out_for_delivery')")
    )


def downgrade() -> None:
    """Downgrade schema: Restore unconditional unique index on order_id only if existing data permits."""
    conn = op.get_bind()

    # Pre-check: Ensure no order has multiple deliveries in any status before attempting to restore unconditional uniqueness
    duplicate_orders = conn.execute(sa.text("""
        SELECT order_id, COUNT(*) 
        FROM deliveries 
        GROUP BY order_id 
        HAVING COUNT(*) > 1;
    """)).fetchall()
    if duplicate_orders:
        raise RuntimeError(
            f"Cannot downgrade migration 6179f4c20f23: duplicate deliveries exist for order(s): {duplicate_orders}. "
            "Cannot restore unconditional unique index without manual data resolution."
        )

    # 1. Drop partial unique index on active deliveries
    op.drop_index(
        'idx_active_delivery_per_order',
        table_name='deliveries',
        postgresql_where=sa.text("status IN ('pending', 'assigned', 'picked_up', 'out_for_delivery')")
    )

    # 2. Drop non-unique index on order_id
    op.drop_index(op.f('ix_deliveries_order_id'), table_name='deliveries')

    # 3. Restore unconditional unique index on order_id
    op.create_index(op.f('ix_deliveries_order_id'), 'deliveries', ['order_id'], unique=True)
