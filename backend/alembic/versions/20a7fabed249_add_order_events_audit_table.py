"""add_order_events_audit_table

Revision ID: 20a7fabed249
Revises: 6179f4c20f23
Create Date: 2026-10-27 13:32:38.907402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20a7fabed249'
down_revision: Union[str, Sequence[str], None] = '6179f4c20f23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create order_events audit trail table."""
    op.create_table(
        'order_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('from_state', sa.String(length=32), nullable=False),
        sa.Column('to_state', sa.String(length=32), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('actor_role', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_events_order_id'), 'order_events', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_events_actor_id'), 'order_events', ['actor_id'], unique=False)
    op.create_index(op.f('ix_order_events_created_at'), 'order_events', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema: Drop order_events table."""
    op.drop_index(op.f('ix_order_events_created_at'), table_name='order_events')
    op.drop_index(op.f('ix_order_events_actor_id'), table_name='order_events')
    op.drop_index(op.f('ix_order_events_order_id'), table_name='order_events')
    op.drop_table('order_events')
