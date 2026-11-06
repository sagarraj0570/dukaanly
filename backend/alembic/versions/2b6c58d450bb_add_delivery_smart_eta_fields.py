"""add_delivery_smart_eta_fields

Revision ID: 2b6c58d450bb
Revises: 1a5b47c349aa
Create Date: 2026-10-13 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b6c58d450bb'
down_revision: Union[str, Sequence[str], None] = '1a5b47c349aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deliveries', sa.Column('preparation_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deliveries', sa.Column('preparation_estimated_minutes', sa.Integer(), nullable=True))
    op.add_column('deliveries', sa.Column('eta_earliest_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deliveries', sa.Column('eta_latest_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deliveries', sa.Column('eta_calculated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deliveries', sa.Column('eta_remaining_seconds', sa.Integer(), nullable=True))
    op.add_column('deliveries', sa.Column('eta_source', sa.String(length=50), nullable=True))
    op.add_column('deliveries', sa.Column('eta_version', sa.Integer(), server_default='1', nullable=False))
    op.add_column('deliveries', sa.Column('eta_delay_reason', sa.String(length=255), nullable=True))
    op.add_column('deliveries', sa.Column('eta_update_reason', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('deliveries', 'eta_update_reason')
    op.drop_column('deliveries', 'eta_delay_reason')
    op.drop_column('deliveries', 'eta_version')
    op.drop_column('deliveries', 'eta_source')
    op.drop_column('deliveries', 'eta_remaining_seconds')
    op.drop_column('deliveries', 'eta_calculated_at')
    op.drop_column('deliveries', 'eta_latest_at')
    op.drop_column('deliveries', 'eta_earliest_at')
    op.drop_column('deliveries', 'preparation_estimated_minutes')
    op.drop_column('deliveries', 'preparation_started_at')
