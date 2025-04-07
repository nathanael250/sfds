from flask import render_template, jsonify, request, send_file
from flask_login import login_required, current_user
from app.finance import bp
from app.models import Transaction, Product
from app import db
from datetime import datetime, timedelta
import pandas as pd
import io

@bp.route('/financial_report')
@login_required
def financial_report():
    if current_user.role != 'md':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get date range from request parameters or default to last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    transactions = Transaction.query.filter(
        Transaction.created_at.between(start_date, end_date)
    ).all()
    
    # Calculate total revenue
    total_revenue = sum(t.total_amount for t in transactions)
    
    # Get product-wise sales
    product_sales = {}
    for t in transactions:
        product = Product.query.get(t.product_id)
        if product.name not in product_sales:
            product_sales[product.name] = {
                'quantity': 0,
                'revenue': 0
            }
        product_sales[product.name]['quantity'] += t.quantity
        product_sales[product.name]['revenue'] += t.total_amount
    
    return render_template('finance/report.html',
                         transactions=transactions,
                         total_revenue=total_revenue,
                         product_sales=product_sales,
                         start_date=start_date,
                         end_date=end_date)

@bp.route('/export_report')
@login_required
def export_report():
    if current_user.role != 'md':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get date range from request parameters or default to last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    transactions = Transaction.query.filter(
        Transaction.created_at.between(start_date, end_date)
    ).all()
    
    # Create DataFrame for export
    data = []
    for t in transactions:
        product = Product.query.get(t.product_id)
        data.append({
            'Date': t.created_at.strftime('%Y-%m-%d'),
            'Product': product.name,
            'Quantity': t.quantity,
            'Total Price': t.total_amount
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Financial Report', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'financial_report_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.xlsx'
    )

@bp.route('/daily_summary')
@login_required
def daily_summary():
    if current_user.role != 'md':
        return jsonify({'error': 'Unauthorized'}), 403
    
    today = datetime.now().date()
    transactions = Transaction.query.filter(
        db.func.date(Transaction.created_at) == today
    ).all()
    
    total_revenue = sum(t.total_amount for t in transactions)
    total_transactions = len(transactions)
    
    return jsonify({
        'date': today.strftime('%Y-%m-%d'),
        'total_revenue': total_revenue,
        'total_transactions': total_transactions
    }) 