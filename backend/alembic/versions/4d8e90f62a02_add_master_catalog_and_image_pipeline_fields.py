"""add master catalog and image pipeline fields

Revision ID: 4d8e90f62a02
Revises: 3c7d89e51f01
Create Date: 2026-10-26 19:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4d8e90f62a02'
down_revision: Union[str, Sequence[str], None] = '3c7d89e51f01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create master_catalog_items table
    op.create_table(
        'master_catalog_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('normalized_name', sa.String(length=255), nullable=False),
        sa.Column('brand', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('barcode', sa.String(length=100), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('thumb_url', sa.Text(), nullable=True),
        sa.Column('image_source', sa.String(length=50), nullable=True),
        sa.Column('image_license', sa.Text(), nullable=True),
        sa.Column('image_attribution', sa.Text(), nullable=True),
        sa.Column('image_source_url', sa.Text(), nullable=True),
        sa.Column('image_match_confidence', sa.Float(), nullable=True),
        sa.Column('image_reviewed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    op.create_index('ix_master_catalog_items_name', 'master_catalog_items', ['name'])
    op.create_index('ix_master_catalog_items_normalized_name', 'master_catalog_items', ['normalized_name'])
    op.create_index('ix_master_catalog_items_category', 'master_catalog_items', ['category'])
    op.create_index('ix_master_catalog_items_barcode', 'master_catalog_items', ['barcode'])

    # 2. Add columns to products table
    op.add_column('products', sa.Column('barcode', sa.String(length=100), nullable=True))
    op.add_column('products', sa.Column('master_item_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('products', sa.Column('thumb_url', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('image_source', sa.String(length=50), nullable=True))
    op.add_column('products', sa.Column('image_license', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('image_attribution', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('image_source_url', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('image_match_confidence', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('image_reviewed', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('products', sa.Column('custom_image_url', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('custom_thumb_url', sa.Text(), nullable=True))

    op.create_index('ix_products_barcode', 'products', ['barcode'])
    op.create_index('ix_products_master_item_id', 'products', ['master_item_id'])
    op.create_foreign_key(
        'fk_products_master_item_id',
        'products',
        'master_catalog_items',
        ['master_item_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_products_master_item_id', 'products', type_='foreignkey')
    op.drop_index('ix_products_master_item_id', table_name='products')
    op.drop_index('ix_products_barcode', table_name='products')

    op.drop_column('products', 'custom_thumb_url')
    op.drop_column('products', 'custom_image_url')
    op.drop_column('products', 'image_reviewed')
    op.drop_column('products', 'image_match_confidence')
    op.drop_column('products', 'image_source_url')
    op.drop_column('products', 'image_attribution')
    op.drop_column('products', 'image_license')
    op.drop_column('products', 'image_source')
    op.drop_column('products', 'thumb_url')
    op.drop_column('products', 'master_item_id')
    op.drop_column('products', 'barcode')

    op.drop_index('ix_master_catalog_items_barcode', table_name='master_catalog_items')
    op.drop_index('ix_master_catalog_items_category', table_name='master_catalog_items')
    op.drop_index('ix_master_catalog_items_normalized_name', table_name='master_catalog_items')
    op.drop_index('ix_master_catalog_items_name', table_name='master_catalog_items')
    op.drop_table('master_catalog_items')
