from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user
from app.models import User, db
from sqlalchemy import select

def requires_roles(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('You must be logged in to access this page.', 'error')
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def create_test_users():
    """Create test users for development if they don't exist."""
    test_users = [
        {'username': 'admin', 'email': 'admin@example.com', 'password': 'password', 'role': 'admin'},
        {'username': 'md', 'email': 'md@example.com', 'password': 'password', 'role': 'md'},
        {'username': 'sao', 'email': 'sao@example.com', 'password': 'password', 'role': 'sao'},
        {'username': 'agrodealer', 'email': 'agrodealer@example.com', 'password': 'password', 'role': 'agrodealer'}
    ]
    
    for user_data in test_users:
        # Use a specific query that doesn't include logo_path
        stmt = select(User.id).where(User.username == user_data['username'])
        user_exists = db.session.execute(stmt).first() is not None
        
        if not user_exists:
            user = User(
                username=user_data['username'],
                email=user_data['email'],
                password_hash=User.set_password(user_data['password']),
                role=user_data['role']
            )
            db.session.add(user)
    
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error creating test users: {e}")
        return False

def format_currency(value):
    """Format a number as RWF currency."""
    try:
        return "{:,.0f}".format(float(value))
    except (ValueError, TypeError):
        return "0"

def format_number(value, decimals=2):
    """Format a number with the specified number of decimal places."""
    try:
        return "{:,.{prec}f}".format(float(value), prec=decimals)
    except (ValueError, TypeError):
        return "0"

# Register custom filters
def register_filters(app):
    app.jinja_env.filters['currency'] = format_currency
    app.jinja_env.filters['number'] = format_number 