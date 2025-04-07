"""Remove quantity field from Product model

Revision ID: remove_quantity_field
Revises: add_units_per_sqm
Create Date: 2024-04-04 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'remove_quantity_field'
down_revision = 'add_units_per_sqm'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the quantity column from the product table
    op.drop_column('product', 'quantity')


def downgrade():
    # Add back the quantity column if needed to rollback
    op.add_column('product', sa.Column('quantity', mysql.FLOAT(), nullable=True, default=0)) 