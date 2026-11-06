"""add_import_batches_table_and_shop_batch_id

Revision ID: 1a5b47c349aa
Revises: 94e21a87bf02
Create Date: 2026-10-13 20:00:44.233763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1a5b47c349aa'
down_revision: Union[str, Sequence[str], None] = '94e21a87bf02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create import_batches table
    op.create_table(
        'import_batches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('source_dataset', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='running'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('accepted_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duplicate_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rejected_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. Add import_batch_id column to shops
    op.add_column(
        'shops',
        sa.Column('import_batch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('import_batches.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index(
        'ix_shops_import_batch_id',
        'shops',
        ['import_batch_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_shops_import_batch_id', table_name='shops')
    op.drop_column('shops', 'import_batch_id')
    op.drop_table('import_batches')
