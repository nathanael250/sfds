from app import create_app
from migrations.add_receipt_columns import upgrade

app = create_app()
with app.app_context():
    print("Running database migration...")
    upgrade()
    print("Migration completed successfully!") 