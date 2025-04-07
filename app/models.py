from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

# Initialize extensions
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False)  # 'md', 'sao', or 'agrodealer'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def set_password(password):
        return generate_password_hash(password)

class Citizen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    national_id = db.Column(db.String(20), unique=True, nullable=False)
    upi_number = db.Column(db.String(20), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    plot_size = db.Column(db.Float, nullable=False)
    allowed_seeds = db.Column(db.Float, nullable=False)
    allowed_fertilizer = db.Column(db.Float, nullable=False)
    registered_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    registrar = db.relationship('User', backref=db.backref('registered_citizens', lazy=True))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # seed or fertilizer
    unit = db.Column(db.String(20), nullable=False)  # kg, g, l, ml
    price_per_unit = db.Column(db.Float, nullable=False)
    units_per_sqm = db.Column(db.Float, nullable=True, default=1.0)  # Making this field optional with default value
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Stock(db.Model):
    """Model for tracking product inventory for agrodealers."""
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    agrodealer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    product = db.relationship('Product', backref=db.backref('stock_entries', lazy=True))
    agrodealer = db.relationship('User', backref=db.backref('stock_entries', lazy=True))

    def __repr__(self):
        return f'<Stock {self.product.name}: {self.quantity} {self.product.unit}>'

    @classmethod
    def get_stock_level(cls, product_id, agrodealer_id):
        """Get current stock level for a product for an agrodealer."""
        stock = cls.query.filter_by(
            product_id=product_id,
            agrodealer_id=agrodealer_id
        ).first()
        return stock.quantity if stock else 0.0

    def update_quantity(self, new_quantity):
        """Update stock quantity and last_updated timestamp."""
        self.quantity = new_quantity
        self.last_updated = datetime.utcnow()

class StockRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved_by_sao, approved_by_md, purchase_verified, rejected
    requested_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    approved_by_sao = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_by_md = db.Column(db.Integer, db.ForeignKey('user.id'))
    receipt_path = db.Column(db.String(255))
    receipt_verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    receipt_verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    product = db.relationship('Product', backref=db.backref('stock_requests', lazy=True))
    requester = db.relationship('User', foreign_keys=[requested_by], backref=db.backref('stock_requests', lazy=True))
    sao_approver = db.relationship('User', foreign_keys=[approved_by_sao], backref=db.backref('sao_approved_requests', lazy=True))
    md_approver = db.relationship('User', foreign_keys=[approved_by_md], backref=db.backref('md_approved_requests', lazy=True))
    receipt_verifier = db.relationship('User', foreign_keys=[receipt_verified_by], backref=db.backref('verified_receipts', lazy=True))

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_number = db.Column(db.String(20), unique=True, nullable=False)
    upi = db.Column(db.String(20), nullable=False)
    land_size = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    citizen_id = db.Column(db.Integer, db.ForeignKey('citizen.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    sold_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    product = db.relationship('Product', backref=db.backref('transactions', lazy=True))
    citizen = db.relationship('Citizen', backref=db.backref('transactions', lazy=True))
    seller = db.relationship('User', backref=db.backref('sales', lazy=True))

class Notification(db.Model):
    """Model for system notifications."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('notifications', lazy=True))
    
    def __repr__(self):
        return f'<Notification {self.title}>' 