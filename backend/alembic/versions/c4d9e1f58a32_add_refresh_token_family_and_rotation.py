"""add refresh token family and rotation

Revision ID: c4d9e1f58a32
Revises: 20a7fabed249
Create Date: 2026-10-27 14:47:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c4d9e1f58a32'
down_revision = '20a7fabed249'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add family_id as nullable initially
    op.add_column(
        'refresh_tokens',
        sa.Column('family_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # 2. Backfill family_id with existing id for all existing records
    op.execute("UPDATE refresh_tokens SET family_id = id WHERE family_id IS NULL")
    
    # 3. Alter family_id to NOT NULL and create index
    op.alter_column('refresh_tokens', 'family_id', nullable=False)
    op.create_index(
        op.f('ix_refresh_tokens_family_id'),
        'refresh_tokens',
        ['family_id'],
        unique=False
    )
    
    # 4. Add replaced_by_id pointing to child token
    op.add_column(
        'refresh_tokens',
        sa.Column('replaced_by_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_refresh_tokens_replaced_by_id',
        'refresh_tokens',
        'refresh_tokens',
        ['replaced_by_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_refresh_tokens_replaced_by_id', 'refresh_tokens', type_='foreignkey')
    op.drop_column('refresh_tokens', 'replaced_by_id')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'family_id')
