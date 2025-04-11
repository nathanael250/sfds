from flask import render_template, redirect, url_for, flash, request, current_app, send_from_directory
from flask_login import login_required, current_user
from app.md import bp
from app.models import StockRequest, Product, db, Notification, Citizen, Stock
from app.utils import requires_roles
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import base64
from sqlalchemy import func

@bp.route('/')
@login_required
@requires_roles('md')
def index():
    """MD index page with quick access to all features."""
    # Get statistics for the dashboard
    pending_requests = StockRequest.query.filter_by(status='approved_by_sao').count()
    approved_requests = StockRequest.query.filter_by(status='approved_by_md').count()
    rejected_requests = StockRequest.query.filter_by(status='rejected').count()
    pending_verifications = StockRequest.query.filter_by(status='approved_by_md').count()
    total_citizens = Citizen.query.count()
    
    return render_template('md/index.html',
                         pending_requests=pending_requests,
                         approved_requests=approved_requests,
                         rejected_requests=rejected_requests,
                         pending_verifications=pending_verifications,
                         total_citizens=total_citizens)

# Stock Management Routes
@bp.route('/stock')
@login_required
@requires_roles('md')
def stock_dashboard():
    """Stock management dashboard."""
    # Get statistics for the dashboard
    total_products = Product.query.count()
    total_value = db.session.query(func.sum(Product.price_per_unit * Product.quantity)).scalar() or 0
    pending_requests = StockRequest.query.filter_by(status='approved_by_sao').count()
    pending_verifications = StockRequest.query.filter_by(status='approved_by_md').count()
    
    # Get recent requests that need MD approval
    recent_requests = (
        StockRequest.query
        .filter_by(status='approved_by_sao')
        .order_by(StockRequest.created_at.desc())
        .limit(5)
        .all()
    )
    
    # Get recent requests that need receipt verification
    recent_verifications = (
        StockRequest.query
        .filter_by(status='approved_by_md')
        .order_by(StockRequest.created_at.desc())
        .limit(5)
        .all()
    )
    
    return render_template('md/stock/dashboard.html', 
                         total_products=total_products,
                         total_value=total_value,
                          pending_requests=pending_requests,
                          pending_verifications=pending_verifications,
                          recent_requests=recent_requests,
                          recent_verifications=recent_verifications)

@bp.route('/stock/requests')
@login_required
@requires_roles('md')
def stock_requests():
    """View all stock requests that have been approved by SAO and need MD approval."""
    requests = StockRequest.query.filter_by(status='approved_by_sao').order_by(StockRequest.created_at.desc()).all()
    return render_template('md/stock/requests.html', requests=requests)

@bp.route('/stock/requests/<int:request_id>/approve', methods=['POST'])
@login_required
@requires_roles('md')
def approve_stock_request(request_id):
    """Approve a stock request."""
    stock_request = StockRequest.query.get_or_404(request_id)
    comment = request.form.get('comment', '').strip()
    
    if stock_request.status != 'approved_by_sao':
        flash('Request must be approved by SAO first', 'error')
        return redirect(url_for('md.stock_requests'))
    
    stock_request.status = 'approved_by_md'
    stock_request.approved_by_md = current_user.id
    stock_request.md_comment = comment
    stock_request.updated_at = datetime.utcnow()
    
    try:
        notification = Notification(
            user_id=stock_request.requested_by,
            title='Stock Request Approved by MD',
            message=f'Your stock request for {stock_request.product.name} has been approved by MD. Comment: {comment}'
        )
        db.session.add(notification)
        db.session.commit()
        flash('Request approved successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving request: {str(e)}', 'error')
    
    return redirect(url_for('md.stock_requests'))

@bp.route('/stock/requests/<int:request_id>/reject', methods=['POST'])
@login_required
@requires_roles('md')
def reject_stock_request(request_id):
    """Reject a stock request."""
    stock_request = StockRequest.query.get_or_404(request_id)
    comment = request.form.get('comment', '').strip()
    
    if not comment:
        flash('Please provide a reason for rejection', 'error')
        return redirect(url_for('md.stock_requests'))
    
    try:
        stock_request.status = 'rejected'
        stock_request.md_comment = comment
        stock_request.updated_at = datetime.utcnow()
        
        notification = Notification(
            user_id=stock_request.requested_by,
            title='Stock Request Rejected by MD',
            message=f'Your stock request for {stock_request.product.name} has been rejected by MD. Reason: {comment}'
        )
        db.session.add(notification)
        db.session.commit()
        flash('Request rejected successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting request: {str(e)}', 'error')
    
    return redirect(url_for('md.stock_requests'))

@bp.route('/stock/verifications')
@login_required
@requires_roles('md')
def stock_verifications():
    """View all stock requests that need receipt verification."""
    requests = StockRequest.query.filter_by(status='approved_by_md').order_by(StockRequest.created_at.desc()).all()
    return render_template('md/verifications.html', requests=requests)

@bp.route('/stock/verifications/<int:request_id>/view')
@login_required
@requires_roles('md')
def view_stock_receipt(request_id):
    """View a stock receipt."""
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if not stock_request.receipt_path:
        return {'error': 'No receipt found'}, 404
    
    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stock_request.receipt_path)
        if not os.path.exists(file_path):
            return {'error': 'Receipt file not found'}, 404
        
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Get file type
        file_ext = os.path.splitext(stock_request.receipt_path)[1].lower()
        if file_ext in ['.jpg', '.jpeg', '.png']:
            file_type = f'image/{file_ext[1:]}'
        elif file_ext == '.pdf':
            file_type = 'application/pdf'
        else:
            return {'error': 'Unsupported file type'}, 400
        
        return {
            'type': file_type,
            'data': base64.b64encode(file_data).decode('utf-8')
        }
    except Exception as e:
        return {'error': str(e)}, 500

@bp.route("/stock/verifications/<int:request_id>/verify", methods=["POST"])
@login_required
@requires_roles("md")
def verify_stock_receipt(request_id):
    """Verify a stock receipt and update inventory."""
    stock_request = StockRequest.query.get_or_404(request_id)
    
    try:
        # Update stock request status
        stock_request.status = "verified"
        stock_request.receipt_verified_at = datetime.utcnow()
        stock_request.receipt_verified_by = current_user.id
        
        # Create or update stock entry
        stock = Stock.query.filter_by(
            agrodealer_id=stock_request.requested_by,
            product_id=stock_request.product_id
        ).first()
        
        if stock:
            stock.quantity += stock_request.quantity
        else:
            stock = Stock(
                agrodealer_id=stock_request.requested_by,
                product_id=stock_request.product_id,
                quantity=stock_request.quantity
            )
            db.session.add(stock)
        
        # Add notification
        notification = Notification(
            user_id=stock_request.requested_by,
            title='Stock Request Verified',
            message=f'Your stock request for {stock_request.product.name} has been verified. Your stock has been updated.'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash("Stock request verified successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error verifying stock request: {str(e)}", "error")
    
    return redirect(url_for("md.stock_verifications"))

@bp.route("/stock/verifications/<int:request_id>/reject", methods=["POST"])
@login_required
@requires_roles("md")
def reject_stock_receipt(request_id):
    """Reject a stock receipt verification."""
    stock_request = StockRequest.query.get_or_404(request_id)
    
    try:
        stock_request.status = "rejected"
        stock_request.receipt_verified_at = datetime.utcnow()
        stock_request.receipt_verified_by = current_user.id
        
        # Add notification
        notification = Notification(
            user_id=stock_request.requested_by,
            title='Stock Request Rejected',
            message=f'Your stock request for {stock_request.product.name} has been rejected. Please check the receipt and try again.'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash("Stock request rejected", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error rejecting stock request: {str(e)}", "error")
    
    return redirect(url_for("md.stock_verifications"))

# Citizen Management Routes
@bp.route('/citizens')
@login_required
@requires_roles('md')
def citizens():
    """View all registered citizens."""
    citizens = Citizen.query.order_by(Citizen.created_at.desc()).all()
    return render_template('md/citizens/index.html', citizens=citizens)

@bp.route('/citizens/register', methods=['GET', 'POST'])
@login_required
@requires_roles('md')
def register_citizen():
    """Register a new citizen."""
    if request.method == 'POST':
        try:
            # Combine first and last name
            name = f"{request.form['first_name']} {request.form['last_name']}"
            
            citizen = Citizen(
                name=name,
                national_id=request.form['id_number'],
                upi_number=request.form['upi_number'],
                phone_number=request.form['phone'],
                plot_size=float(request.form['farm_size'])
            )
            db.session.add(citizen)
            db.session.commit()
            flash('Citizen registered successfully', 'success')
            return redirect(url_for('md.citizens'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering citizen: {str(e)}', 'error')
    
    return render_template('md/citizens/register.html')

@bp.route('/export')
@login_required
@requires_roles('md')
def export_data():
    """Export system data."""
    # Get all data for export
    stock_requests = StockRequest.query.order_by(StockRequest.created_at.desc()).all()
    citizens = Citizen.query.order_by(Citizen.created_at.desc()).all()
    products = Product.query.all()
    
    return render_template('md/export.html',
                         stock_requests=stock_requests,
                         citizens=citizens,
                         products=products) 