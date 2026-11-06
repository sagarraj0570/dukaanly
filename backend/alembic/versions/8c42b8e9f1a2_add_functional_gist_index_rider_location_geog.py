"""add_functional_gist_index_rider_location_geog

Revision ID: 8c42b8e9f1a2
Revises: 7b301ca0ad41
Create Date: 2026-11-04 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c42b8e9f1a2'
down_revision: Union[str, Sequence[str], None] = '7b301ca0ad41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Functional GiST index on cast(location as geography) to enable index-backed ST_DWithin and ST_Distance scans
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rider_profiles_location_geog "
        "ON rider_profiles USING gist (cast(location as geography))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rider_profiles_location_geog")
