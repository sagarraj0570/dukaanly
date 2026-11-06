"""add_delivery_offers_and_dispatch_fields

Revision ID: 7b301ca0ad41
Revises: 2c3278e09b46
Create Date: 2026-11-04 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7b301ca0ad41'
down_revision: Union[str, Sequence[str], None] = '2c3278e09b46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add dispatch metadata columns to deliveries
    op.add_column('deliveries', sa.Column('dispatch_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('deliveries', sa.Column('awaiting_rider', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('deliveries', sa.Column('dispatch_started_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_deliveries_pending_awaiting', 'deliveries', ['status', 'awaiting_rider'], unique=False)

    # 2. Create delivery_offers table with check constraint and indexes
    op.create_table(
        'delivery_offers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('delivery_id', sa.UUID(), nullable=False),
        sa.Column('rider_id', sa.UUID(), nullable=False),
        sa.Column('attempt_no', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='offered'),
        sa.Column('offered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('offered', 'accepted', 'declined', 'expired', 'cancelled')",
            name='chk_delivery_offer_status'
        ),
        sa.ForeignKeyConstraint(['delivery_id'], ['deliveries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rider_id'], ['rider_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('delivery_id', 'rider_id', 'attempt_no', name='uq_delivery_offers_attempt')
    )
    op.create_index('ix_delivery_offers_rider_open', 'delivery_offers', ['rider_id', 'status', 'expires_at'], unique=False)
    op.create_index('ix_delivery_offers_delivery_status', 'delivery_offers', ['delivery_id', 'status'], unique=False)
    op.create_index(op.f('ix_delivery_offers_expires_at'), 'delivery_offers', ['expires_at'], unique=False)
    op.create_index(op.f('ix_delivery_offers_delivery_id'), 'delivery_offers', ['delivery_id'], unique=False)
    op.create_index(op.f('ix_delivery_offers_rider_id'), 'delivery_offers', ['rider_id'], unique=False)


def downgrade() -> None:
    # 1. Drop delivery_offers and its indexes
    op.drop_index(op.f('ix_delivery_offers_rider_id'), table_name='delivery_offers')
    op.drop_index(op.f('ix_delivery_offers_delivery_id'), table_name='delivery_offers')
    op.drop_index(op.f('ix_delivery_offers_expires_at'), table_name='delivery_offers')
    op.drop_index('ix_delivery_offers_delivery_status', table_name='delivery_offers')
    op.drop_index('ix_delivery_offers_rider_open', table_name='delivery_offers')
    op.drop_table('delivery_offers')

    # 2. Drop dispatch metadata columns and index from deliveries
    op.drop_index('ix_deliveries_pending_awaiting', table_name='deliveries')
    op.drop_column('deliveries', 'dispatch_started_at')
    op.drop_column('deliveries', 'awaiting_rider')
    op.drop_column('deliveries', 'dispatch_attempts')
