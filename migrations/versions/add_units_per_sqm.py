"""Add units_per_sqm to Product

Revision ID: add_units_per_sqm
Revises: d9e2b1db74bf
Create Date: 2024-04-04 12:56:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_units_per_sqm'
down_revision = 'd9e2b1db74bf'
branch_labels = None
depends_on = None


def upgrade():
    # Add units_per_sqm column to product table
    op.add_column('product', sa.Column('units_per_sqm', sa.Float(), nullable=True, server_default='1.0'))


def downgrade():
    # Remove units_per_sqm column from product table
    op.drop_column('product', 'units_per_sqm') 