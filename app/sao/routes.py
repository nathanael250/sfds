from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.models import StockRequest, Product, db, Notification, Citizen
from app.utils import requires_roles
from app.sao import bp
import os
from werkzeug.utils import secure_filename

@bp.route('/inventory/stock_requests')
@login_required
@requires_roles('sao')
def stock_requests():
    requests = StockRequest.query.filter_by(status='pending').all()
    products = Product.query.all()
    return render_template('inventory/stock_requests.html', requests=requests, products=products)

@bp.route('/inventory/sao_requests')
@login_required
@requires_roles('sao')
def sao_requests():
    requests = StockRequest.query.filter_by(status='approved_by_sao').all()
    return render_template('inventory/sao_requests.html', requests=requests)

@bp.route('/inventory/approve_request/<int:request_id>', methods=['POST'])
@login_required
@requires_roles('sao')
def approve_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    comment = request.form.get('comment', '').strip()
    
    if stock_request.status == 'pending':
        stock_request.status = 'approved_by_sao'
        stock_request.approved_by_sao = current_user.id
        stock_request.sao_comment = comment
        flash('Request approved and forwarded to MD', 'success')
    else:
        flash('Invalid request status', 'error')
        return redirect(url_for('sao.stock_requests'))

    try:
        notification = Notification(
            user_id=stock_request.requested_by,
            title='Stock Request Approved by SAO',
            message=f'Your stock request for {stock_request.product.name} has been approved by SAO. Comment: {comment}'
        )
        db.session.add(notification)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the request', 'error')

    return redirect(url_for('sao.stock_requests'))

@bp.route('/inventory/reject_request/<int:request_id>', methods=['POST'])
@login_required
@requires_roles('sao')
def reject_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    comment = request.form.get('comment', '').strip()
    
    if not comment:
        flash('Please provide a reason for rejection', 'error')
        return redirect(url_for('sao.stock_requests'))
    
    if stock_request.status == 'pending':
        stock_request.status = 'rejected_by_sao'
        stock_request.sao_comment = comment
        flash('Request rejected by SAO', 'success')
    else:
        flash('Invalid request status', 'error')
        return redirect(url_for('sao.stock_requests'))

    try:
        notification = Notification(
            user_id=stock_request.requested_by,
            title='Stock Request Rejected by SAO',
            message=f'Your stock request for {stock_request.product.name} has been rejected by SAO. Reason: {comment}'
        )
        db.session.add(notification)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while rejecting the request', 'error')

    return redirect(url_for('sao.stock_requests'))

@bp.route('/dashboard')
@login_required
@requires_roles('sao')
def dashboard():
    """SAO dashboard showing overview of pending requests and inventory."""
    pending_requests = StockRequest.query.filter_by(status='pending').count()
    approved_requests = StockRequest.query.filter_by(status='approved_by_sao').count()
    total_products = Product.query.count()
    
    return render_template('sao/dashboard.html',
                         pending_requests=pending_requests,
                         approved_requests=approved_requests,
                         total_products=total_products)

@bp.route('/citizens')
@login_required
@requires_roles('sao')
def view_citizens():
    """View all registered citizens."""
    citizens = Citizen.query.all()
    return render_template('sao/citizens.html', citizens=citizens) 