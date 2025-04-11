"""merge add_logo_path and add_units_per_sqm

Revision ID: 2dba55759252
Revises: add_logo_path, remove_quantity_field
Create Date: 2025-04-11 07:44:47.921566

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2dba55759252'
down_revision = ('add_logo_path', 'remove_quantity_field')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
