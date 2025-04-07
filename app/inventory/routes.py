from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.models import StockRequest, Product, db, Stock, Notification
from app.utils import requires_roles
from app.inventory import bp
import os
from werkzeug.utils import secure_filename
from datetime import datetime

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/stock_requests')
@login_required
def stock_requests():
    if current_user.role == 'agrodealer':
        requests = StockRequest.query.filter_by(requested_by=current_user.id).all()
    elif current_user.role == 'sao':
        requests = StockRequest.query.filter_by(status='pending').all()
    elif current_user.role == 'md':
        requests = StockRequest.query.filter_by(status='approved_by_sao').all()
    else:
        flash('Unauthorized access', 'error')
        return redirect(url_for('main.index'))
    
    products = Product.query.all()
    return render_template('inventory/stock_requests.html', requests=requests, products=products)

@bp.route('/request_stock', methods=['POST'])
@login_required
@requires_roles('agrodealer')
def request_stock():
    product_id = request.form.get('product_id')
    quantity = request.form.get('quantity')

    if not all([product_id, quantity]):
        flash('All fields are required', 'error')
        return redirect(url_for('inventory.stock_requests'))

    try:
        new_request = StockRequest(
            product_id=product_id,
            quantity=float(quantity),
            requested_by=current_user.id
        )
        db.session.add(new_request)
        db.session.commit()
        flash('Stock request submitted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while submitting the request', 'error')

    return redirect(url_for('inventory.stock_requests'))

@bp.route('/approve_request/<int:request_id>', methods=['POST'])
@login_required
@requires_roles('sao', 'md')
def approve_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if current_user.role == 'sao' and stock_request.status == 'pending':
        stock_request.status = 'approved_by_sao'
        stock_request.approved_by_sao = current_user.id
        flash('Request approved and forwarded to MD', 'success')
    elif current_user.role == 'md' and stock_request.status == 'approved_by_sao':
        stock_request.status = 'approved_by_md'
        stock_request.approved_by_md = current_user.id
        flash('Request approved', 'success')
    else:
        flash('Invalid request status or unauthorized action', 'error')
        return redirect(url_for('inventory.stock_requests'))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the request', 'error')

    return redirect(url_for('inventory.stock_requests'))

@bp.route('/reject_request/<int:request_id>', methods=['POST'])
@login_required
@requires_roles('sao', 'md')
def reject_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if current_user.role == 'sao' and stock_request.status == 'pending':
        stock_request.status = 'rejected_by_sao'
        flash('Request rejected by SAO', 'success')
    elif current_user.role == 'md' and stock_request.status == 'approved_by_sao':
        stock_request.status = 'rejected_by_md'
        flash('Request rejected by MD', 'success')
    else:
        flash('Invalid request status or unauthorized action', 'error')
        return redirect(url_for('inventory.stock_requests'))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while rejecting the request', 'error')

    return redirect(url_for('inventory.stock_requests'))

@bp.route('/upload_invoice/<int:request_id>', methods=['POST'])
@login_required
@requires_roles('agrodealer')
def upload_invoice(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if stock_request.requested_by != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('inventory.stock_requests'))

    if 'invoice' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('inventory.stock_requests'))

    file = request.files['invoice']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('inventory.stock_requests'))

    if not allowed_file(file.filename):
        flash('Invalid file type', 'error')
        return redirect(url_for('inventory.stock_requests'))

    try:
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        stock_request.invoice_path = filename
        db.session.commit()
        flash('Invoice uploaded successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while uploading the invoice', 'error')

    return redirect(url_for('inventory.stock_requests'))

@bp.route('/update_stock', methods=['POST'])
@login_required
@requires_roles('md')
def update_stock():
    product_id = request.form.get('product_id')
    quantity = request.form.get('quantity')

    if not all([product_id, quantity]):
        flash('All fields are required', 'error')
        return redirect(url_for('inventory.stock_requests'))

    try:
        product = Product.query.get_or_404(product_id)
        product.quantity = float(quantity)
        db.session.commit()
        flash('Stock updated successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while updating the stock', 'error')

    return redirect(url_for('inventory.stock_requests'))

@bp.route('/dashboard')
@login_required
@requires_roles('md')
def md_dashboard():
    # Get all statistics for MD dashboard
    total_requests = StockRequest.query.count()
    approved_requests = StockRequest.query.filter_by(status='approved_by_sao').count()
    confirmed_requests = StockRequest.query.filter_by(status='approved_by_md').count()
    pending_requests = StockRequest.query.filter_by(status='pending').count()
    total_transactions = StockRequest.query.filter_by(status='approved_by_md').count()  # Or another transaction metric

    stats = {
        'total_requests': total_requests,
        'approved_requests': approved_requests,
        'confirmed_requests': confirmed_requests,
        'pending_requests': pending_requests,
        'total_transactions': total_transactions
    }
    
    return render_template('inventory/md_dashboard.html', stats=stats)

@bp.route('/confirmed_requests')
@login_required
@requires_roles('md')
def confirmed_requests():
    requests = StockRequest.query.filter_by(status='approved_by_md').all()
    return render_template('inventory/confirmed_requests.html', requests=requests)

@bp.route('/sao_requests')
@login_required
@requires_roles('md')
def sao_requests():
    requests = StockRequest.query.filter_by(status='approved_by_sao').all()
    return render_template('inventory/sao_requests.html', requests=requests)

@bp.route('/register_product', methods=['GET', 'POST'])
@login_required
@requires_roles('sao')
def register_product():
    if request.method == 'POST':
        name = request.form.get('name')
        product_type = request.form.get('type')
        unit = request.form.get('unit')
        price_per_unit = request.form.get('price_per_unit')
        units_per_sqm = request.form.get('units_per_sqm')

        print(f"Form data: name={name}, type={product_type}, unit={unit}, price={price_per_unit}, units={units_per_sqm}")

        # Validate required fields
        if not all([name, product_type, unit, price_per_unit]):
            flash('All fields except units per square meter are required', 'error')
            return redirect(url_for('inventory.register_product'))

        try:
            # Convert and validate numeric fields
            price_per_unit = float(price_per_unit)
            units_per_sqm = float(units_per_sqm) if units_per_sqm else 1.0  # Default to 1.0 if not provided

            if price_per_unit <= 0:
                flash('Price per unit must be greater than 0', 'error')
                return redirect(url_for('inventory.register_product'))
            
            if units_per_sqm <= 0:
                flash('Units per square meter must be greater than 0', 'error')
                return redirect(url_for('inventory.register_product'))

            print("Creating new product...")
            new_product = Product(
                name=name,
                type=product_type,
                unit=unit,
                price_per_unit=price_per_unit,
                units_per_sqm=units_per_sqm
            )
            print("Adding product to session...")
            db.session.add(new_product)
            print("Committing to database...")
            db.session.commit()
            print("Product registered successfully")
            flash('Product registered successfully', 'success')
            return redirect(url_for('inventory.stock_requests'))
        except ValueError as e:
            print(f"ValueError: {str(e)}")
            flash('Invalid numeric value for price or units per square meter', 'error')
            return redirect(url_for('inventory.register_product'))
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            db.session.rollback()
            flash('An error occurred while registering the product', 'error')
            return redirect(url_for('inventory.register_product'))

    return render_template('inventory/register_product.html')

@bp.route('/verify_receipt/<int:request_id>', methods=['POST'])
@login_required
@requires_roles('md')
def verify_receipt(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if stock_request.status != 'approved_by_md':
        flash('Invalid request status', 'error')
        return redirect(url_for('inventory.stock_requests'))
    
    try:
        # Update stock request status
        stock_request.status = 'purchase_verified'
        stock_request.receipt_verified_by = current_user.id
        stock_request.receipt_verified_at = datetime.utcnow()
        
        # Update or create stock entry
        stock = Stock.query.filter_by(
            product_id=stock_request.product_id,
            agrodealer_id=stock_request.requested_by
        ).first()
        
        if stock:
            # Update existing stock
            stock.quantity += stock_request.quantity
            stock.last_updated = datetime.utcnow()
        else:
            # Create new stock entry
            stock = Stock(
                product_id=stock_request.product_id,
                agrodealer_id=stock_request.requested_by,
                quantity=stock_request.quantity
            )
            db.session.add(stock)
        
        # Create notification for agrodealer
        notification = Notification(
            user_id=stock_request.requested_by,
            title='Stock Request Verified',
            message=f'Your purchase of {stock_request.quantity} {stock_request.product.unit} of {stock_request.product.name} has been verified.'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash('Receipt verified and stock updated successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while verifying the receipt: {str(e)}', 'error')
    
    return redirect(url_for('inventory.stock_requests')) 