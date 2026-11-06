"""add_inventory_reservation_table

Revision ID: 2c3278e09b46
Revises: d5a8e2b74c10
Create Date: 2026-11-01 18:40:25.599667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2c3278e09b46'
down_revision: Union[str, Sequence[str], None] = 'd5a8e2b74c10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'inventory_reservations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('reservation_reference', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('active', 'consumed', 'released', 'expired', name='reservation_status_enum'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('release_reason', sa.String(length=255), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint('quantity > 0', name='chk_reservation_quantity_positive'),
        sa.ForeignKeyConstraint(['customer_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inventory_reservations_reservation_reference'), 'inventory_reservations', ['reservation_reference'], unique=True)
    op.create_index(op.f('ix_inventory_reservations_order_id'), 'inventory_reservations', ['order_id'], unique=False)
    op.create_index(op.f('ix_inventory_reservations_product_id'), 'inventory_reservations', ['product_id'], unique=False)
    op.create_index(op.f('ix_inventory_reservations_customer_id'), 'inventory_reservations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_inventory_reservations_status'), 'inventory_reservations', ['status'], unique=False)
    op.create_index(op.f('ix_inventory_reservations_expires_at'), 'inventory_reservations', ['expires_at'], unique=False)
    op.create_index('ix_inv_res_status_expires_at', 'inventory_reservations', ['status', 'expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_inv_res_status_expires_at', table_name='inventory_reservations')
    op.drop_index(op.f('ix_inventory_reservations_expires_at'), table_name='inventory_reservations')
    op.drop_index(op.f('ix_inventory_reservations_status'), table_name='inventory_reservations')
    op.drop_index(op.f('ix_inventory_reservations_customer_id'), table_name='inventory_reservations')
    op.drop_index(op.f('ix_inventory_reservations_product_id'), table_name='inventory_reservations')
    op.drop_index(op.f('ix_inventory_reservations_order_id'), table_name='inventory_reservations')
    op.drop_index(op.f('ix_inventory_reservations_reservation_reference'), table_name='inventory_reservations')
    op.drop_table('inventory_reservations')
    sa.Enum(name='reservation_status_enum').drop(op.get_bind(), checkfirst=True)
