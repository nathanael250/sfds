"""add logo_path column to user table

Revision ID: add_logo_path
Revises: d9e2b1db74bf
Create Date: 2024-04-09 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_logo_path'
down_revision = 'd9e2b1db74bf'
branch_labels = None
depends_on = None


def upgrade():
    # Add logo_path column to user table using raw SQL
    op.execute('ALTER TABLE user ADD COLUMN logo_path VARCHAR(255)')


def downgrade():
    # Remove logo_path column from user table using raw SQL
    op.execute('ALTER TABLE user DROP COLUMN logo_path') 