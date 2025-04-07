from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.admin import bp
from app.models import User, db, Product
from app.utils import requires_roles
from sqlalchemy import text

@bp.route('/dashboard')
@login_required
@requires_roles('admin')
def dashboard():
    """Admin dashboard showing system overview."""
    # Get statistics for the dashboard
    total_users = User.query.count()
    total_agrodealers = User.query.filter_by(role='agrodealer').count()
    total_sao = User.query.filter_by(role='sao').count()
    total_md = User.query.filter_by(role='md').count()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_agrodealers=total_agrodealers,
                         total_sao=total_sao,
                         total_md=total_md)

@bp.route('/users')
@login_required
@requires_roles('admin')
def users():
    """View and manage all users in the system."""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@requires_roles('admin')
def edit_user(user_id):
    """Edit user details."""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.role = request.form.get('role')
        user.is_active = 'is_active' in request.form
        
        db.session.commit()
        flash('User updated successfully.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', user=user)

@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@requires_roles('admin')
def delete_user(user_id):
    """Delete a user."""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))
    
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@requires_roles('admin')
def settings():
    """Manage system settings."""
    if request.method == 'POST':
        # Update system settings here
        flash('Settings updated successfully.', 'success')
        return redirect(url_for('admin.settings'))
    
    return render_template('admin/settings.html')

@bp.route('/fix_product_table')
@login_required
@requires_roles('md')  # Only MD can access this route
def fix_product_table():
    """Remove the quantity field from the Product table."""
    try:
        # Use raw SQL to alter the table
        db.session.execute(text('ALTER TABLE product DROP COLUMN quantity'))
        db.session.commit()
        flash('Successfully removed quantity field from Product table', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error removing quantity field: {str(e)}', 'error')
    
    return redirect(url_for('md.index')) 