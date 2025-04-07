from app import db
from app.models import StockRequest
from sqlalchemy import text

def upgrade():
    # Add new columns to stock_request table
    db.session.execute(text('ALTER TABLE stock_request ADD COLUMN receipt_path VARCHAR(255)'))
    db.session.execute(text('ALTER TABLE stock_request ADD COLUMN receipt_verified_by INTEGER'))
    db.session.execute(text('ALTER TABLE stock_request ADD COLUMN receipt_verified_at DATETIME'))
    
    # Add foreign key constraint for receipt_verified_by
    db.session.execute(text('ALTER TABLE stock_request ADD FOREIGN KEY (receipt_verified_by) REFERENCES user(id)'))
    
    db.session.commit()

def downgrade():
    # Remove foreign key constraint first
    db.session.execute(text('ALTER TABLE stock_request DROP FOREIGN KEY stock_request_ibfk_4'))
    
    # Remove columns
    db.session.execute(text('ALTER TABLE stock_request DROP COLUMN receipt_path'))
    db.session.execute(text('ALTER TABLE stock_request DROP COLUMN receipt_verified_by'))
    db.session.execute(text('ALTER TABLE stock_request DROP COLUMN receipt_verified_at'))
    
    db.session.commit() 