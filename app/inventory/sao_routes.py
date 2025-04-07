from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.models import StockRequest, Product, db
from app.utils import requires_roles
from app.inventory import bp
import os
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/stock_requests')
@login_required
@requires_roles('sao')
def stock_requests():
    requests = StockRequest.query.filter_by(status='pending').all()
    products = Product.query.all()
    return render_template('inventory/stock_requests.html', requests=requests, products=products)

@bp.route('/sao_requests')
@login_required
@requires_roles('sao')
def sao_requests():
    requests = StockRequest.query.filter_by(status='approved_by_sao').all()
    return render_template('inventory/sao_requests.html', requests=requests)

@bp.route('/register_product', methods=['GET', 'POST'])
@login_required
@requires_roles('sao')
def register_product():
    if request.method == 'POST':
        name = request.form.get('name')
        type = request.form.get('type')
        quantity = request.form.get('quantity')
        unit = request.form.get('unit')
        price_per_unit = request.form.get('price_per_unit')

        if not all([name, type, quantity, unit, price_per_unit]):
            flash('All fields are required', 'error')
            return redirect(url_for('inventory.register_product'))

        try:
            new_product = Product(
                name=name,
                type=type,
                quantity=float(quantity),
                unit=unit,
                price_per_unit=float(price_per_unit)
            )
            db.session.add(new_product)
            db.session.commit()
            flash('Product registered successfully', 'success')
            return redirect(url_for('inventory.stock_requests'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while registering the product', 'error')
            return redirect(url_for('inventory.register_product'))

    return render_template('inventory/register_product.html')

@bp.route('/approve_request/<int:request_id>', methods=['POST'])
@login_required
@requires_roles('sao')
def approve_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if stock_request.status == 'pending':
        stock_request.status = 'approved_by_sao'
        stock_request.approved_by_sao = current_user.id
        flash('Request approved and forwarded to MD', 'success')
    else:
        flash('Invalid request status', 'error')
        return redirect(url_for('inventory.stock_requests'))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the request', 'error')

    return redirect(url_for('inventory.stock_requests')) 