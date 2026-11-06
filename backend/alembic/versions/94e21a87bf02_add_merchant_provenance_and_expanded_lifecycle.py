"""Add merchant provenance and expanded lifecycle

Revision ID: 94e21a87bf02
Revises: 83f19e42bd31
Create Date: 2026-10-13 18:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94e21a87bf02'
down_revision: Union[str, Sequence[str], None] = '83f19e42bd31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Expand shop_verification_status enum values using autocommit block
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE shop_verification_status ADD VALUE IF NOT EXISTS 'pending_review'")
        op.execute("ALTER TYPE shop_verification_status ADD VALUE IF NOT EXISTS 'rejected'")
        op.execute("ALTER TYPE shop_verification_status ADD VALUE IF NOT EXISTS 'archived'")

    # 2. Add provenance tracking columns
    op.add_column('shops', sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shops', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shops', sa.Column('original_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('shops', 'original_url')
    op.drop_column('shops', 'last_seen_at')
    op.drop_column('shops', 'imported_at')
    # Note: PostgreSQL does not support dropping individual enum values cleanly without recreating type
