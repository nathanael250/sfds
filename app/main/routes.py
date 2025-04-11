from flask import render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.main import bp
from app.models import Customer, Product, Transaction, StockRequest
from app import db
import json
import os
from datetime import datetime, timedelta

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    if current_user.role == 'md':
        # Get statistics for MD dashboard
        total_requests = StockRequest.query.count()
        approved_requests = StockRequest.query.filter_by(status='approved_by_sao').count()
        confirmed_requests = StockRequest.query.filter_by(status='approved_by_md').count()
        pending_requests = StockRequest.query.filter_by(status='pending').count()
        
        # Get recent transactions
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        transactions = Transaction.query.filter(
            Transaction.created_at.between(start_date, end_date)
        ).all()
        total_transactions = len(transactions)
        
        stats = {
            'total_requests': total_requests,
            'approved_requests': approved_requests,
            'confirmed_requests': confirmed_requests,
            'pending_requests': pending_requests,
            'total_transactions': total_transactions
        }
        
        return render_template('md_dashboard.html', stats=stats)
        
    elif current_user.role == 'sao':
        # Redirect to the dedicated SAO dashboard
        return redirect(url_for('sao.dashboard'))
        
    elif current_user.role == 'agrodealer':
        # Get agrodealer's requests and recent transactions
        my_requests = StockRequest.query.filter_by(requested_by=current_user.id).all()
        my_transactions = Transaction.query.filter_by(sold_by=current_user.id).order_by(Transaction.created_at.desc()).limit(5).all()
        products = Product.query.all()
        
        return render_template('agrodealer/dashboard.html', 
                             requests=my_requests,
                             transactions=my_transactions,
                             products=products)
    
    # Fallback for unknown roles
    flash('Unknown user role', 'error')
    return redirect(url_for('auth.logout'))

@bp.route('/lookup_customer', methods=['POST'])
@login_required
def lookup_customer():
    id_number = request.form.get('id_number')
    customer = Customer.query.filter_by(id_number=id_number).first()
    
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    return jsonify({
        'upi': customer.upi,
        'land_size': customer.land_size
    })

@bp.route('/calculate_price', methods=['POST'])
@login_required
def calculate_price():
    data = request.get_json()
    customer_id = data.get('customer_id')
    product_id = data.get('product_id')
    quantity = float(data.get('quantity'))
    
    customer = Customer.query.get(customer_id)
    product = Product.query.get(product_id)
    
    if not customer or not product:
        return jsonify({'error': 'Invalid customer or product'}), 404
    
    # Calculate price based on land size
    base_price = product.price_per_unit * quantity
    # You can add additional calculations based on land size here
    
    return jsonify({
        'total_price': base_price
    })

@bp.route('/process_transaction', methods=['POST'])
@login_required
def process_transaction():
    data = request.get_json()
    customer_id = data.get('customer_id')
    product_id = data.get('product_id')
    quantity = float(data.get('quantity'))
    total_price = float(data.get('total_price'))
    
    # Create transaction
    transaction = Transaction(
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
        total_price=total_price,
        created_by=current_user.id
    )
    
    # Update product stock
    product = Product.query.get(product_id)
    if product.quantity < quantity:
        return jsonify({'error': 'Insufficient stock'}), 400
    
    product.quantity -= quantity
    
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({'message': 'Transaction completed successfully'}) 