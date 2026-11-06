"""Expand shop source_id length to 255

Revision ID: 3c7d89e51f01
Revises: 2b6c58d450bb
Create Date: 2026-10-25 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c7d89e51f01'
down_revision: Union[str, Sequence[str], None] = '2b6c58d450bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'shops',
        'source_id',
        existing_type=sa.String(length=100),
        type_=sa.String(length=255),
        existing_nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        'shops',
        'source_id',
        existing_type=sa.String(length=255),
        type_=sa.String(length=100),
        existing_nullable=True
    )
