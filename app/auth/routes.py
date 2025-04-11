from flask import render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.auth import bp
from app.models import User, db
from app.utils import requires_roles
from app.auth.forms import ResetPasswordRequestForm, ResetPasswordForm
from app.email import send_password_reset_email

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # If user is already logged in, redirect to their dashboard
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'md':
            return redirect(url_for('md.index'))
        elif current_user.role == 'sao':
            return redirect(url_for('sao.dashboard'))
        elif current_user.role == 'agrodealer':
            return redirect(url_for('agrodealer.dashboard'))
        else:
            return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Set session as permanent if remember is checked
            if remember:
                session.permanent = True
            
            login_user(user, remember=remember)
            flash('Logged in successfully.', 'success')
            
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'md':
                return redirect(url_for('md.index'))
            elif user.role == 'sao':
                return redirect(url_for('sao.dashboard'))
            elif user.role == 'agrodealer':
                return redirect(url_for('agrodealer.dashboard'))
            else:
                return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('Check your email for the instructions to reset your password', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password_request.html',
                         title='Reset Password', form=form)

@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('main.index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('auth.register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('auth.register'))
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration', 'error')
            return redirect(url_for('auth.register'))
    
    return render_template('auth/register.html')

# Development-only route to switch users without logging out
@bp.route('/switch_user/<username>')
def switch_user(username):
    # Only allow in development mode
    if not current_app.debug:
        flash('This feature is only available in development mode', 'error')
        return redirect(url_for('main.index'))
    
    user = User.query.filter_by(username=username).first()
    if user:
        login_user(user)
        flash(f'Switched to user: {user.username} ({user.role})', 'success')
        
        # Redirect based on role
        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'md':
            return redirect(url_for('md.index'))
        elif user.role == 'sao':
            return redirect(url_for('sao.dashboard'))
        elif user.role == 'agrodealer':
            return redirect(url_for('agrodealer.dashboard'))
        else:
            return redirect(url_for('main.index'))
    else:
        flash(f'User {username} not found', 'error')
        return redirect(url_for('main.index')) 