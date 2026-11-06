"""Add shop verification and public listings

Revision ID: 83f19e42bd31
Revises: 710e16fe5e57
Create Date: 2026-10-13 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '83f19e42bd31'
down_revision: Union[str, Sequence[str], None] = '710e16fe5e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create Enum type
    shop_verification_status_enum = postgresql.ENUM('discovered', 'claimed', 'verified', name='shop_verification_status')
    shop_verification_status_enum.create(op.get_bind(), checkfirst=True)

    # 2. Alter owner_id to nullable
    op.alter_column('shops', 'owner_id', existing_type=sa.UUID(), nullable=True)

    # 3. Update foreign key to SET NULL
    op.drop_constraint('shops_owner_id_fkey', 'shops', type_='foreignkey')
    op.create_foreign_key('shops_owner_id_fkey', 'shops', 'users', ['owner_id'], ['id'], ondelete='SET NULL')

    # 4. Add new columns
    op.add_column('shops', sa.Column('verification_status', postgresql.ENUM('discovered', 'claimed', 'verified', name='shop_verification_status', create_type=False), nullable=False, server_default='discovered'))
    op.add_column('shops', sa.Column('is_orderable', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('shops', sa.Column('source', sa.String(length=50), nullable=True, server_default='manual'))
    op.add_column('shops', sa.Column('source_id', sa.String(length=100), nullable=True))
    op.add_column('shops', sa.Column('source_attribution', sa.String(length=255), nullable=True))
    op.add_column('shops', sa.Column('phone', sa.String(length=50), nullable=True))
    op.add_column('shops', sa.Column('opening_hours', sa.String(length=100), nullable=True))

    # 5. Create composite unique index on (source, source_id) where source_id is not null
    op.create_index(
        'uq_shops_source_source_id',
        'shops',
        ['source', 'source_id'],
        unique=True,
        postgresql_where=sa.text('source_id IS NOT NULL')
    )

    # 6. Set existing shops (which have owner_id) to verified and orderable
    op.execute("UPDATE shops SET verification_status = 'verified', is_orderable = true WHERE owner_id IS NOT NULL")


def downgrade() -> None:
    op.drop_index('uq_shops_source_source_id', table_name='shops')
    op.drop_column('shops', 'opening_hours')
    op.drop_column('shops', 'phone')
    op.drop_column('shops', 'source_attribution')
    op.drop_column('shops', 'source_id')
    op.drop_column('shops', 'source')
    op.drop_column('shops', 'is_orderable')
    op.drop_column('shops', 'verification_status')

    op.drop_constraint('shops_owner_id_fkey', 'shops', type_='foreignkey')
    op.create_foreign_key('shops_owner_id_fkey', 'shops', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
    op.alter_column('shops', 'owner_id', existing_type=sa.UUID(), nullable=False)

    shop_verification_status_enum = postgresql.ENUM('discovered', 'claimed', 'verified', name='shop_verification_status')
    shop_verification_status_enum.drop(op.get_bind(), checkfirst=True)
