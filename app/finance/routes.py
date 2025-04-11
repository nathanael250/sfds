from flask import render_template, jsonify, request, send_file
from flask_login import login_required, current_user
from app.finance import bp
from app.models import Transaction, Product, Stock, StockRequest
from app import db
from datetime import datetime, timedelta
import pandas as pd
import io
from sqlalchemy import func

@bp.route('/financial_report')
@login_required
def financial_report():
    if current_user.role != 'md':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get filters from request parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    product_type = request.args.get('product_type')
    status = request.args.get('status')
    region = request.args.get('region')
    
    # Set default date range to last 30 days if not specified
    if not end_date:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    
    # Base query for transactions
    query = Transaction.query.filter(
        Transaction.created_at.between(start_date, end_date)
    )
    
    # Apply additional filters
    if product_type:
        query = query.join(Product).filter(Product.type == product_type)
    if status:
        query = query.filter(Transaction.status == status)
    if region:
        query = query.filter(Transaction.region == region)
    
    transactions = query.all()
    
    # Calculate financial metrics
    total_revenue = sum(t.total_amount for t in transactions)
    total_transactions = len(transactions)
    
    # Get product-wise sales
    product_sales = {}
    for t in transactions:
        product = Product.query.get(t.product_id)
        if product.name not in product_sales:
            product_sales[product.name] = {
                'quantity': 0,
                'revenue': 0,
                'type': product.type
            }
        product_sales[product.name]['quantity'] += t.quantity
        product_sales[product.name]['revenue'] += t.total_amount
    
    # Get stock report data
    stock_query = Stock.query
    if product_type:
        stock_query = stock_query.join(Product).filter(Product.type == product_type)
    
    current_stock = stock_query.all()
    
    # Calculate stock metrics
    stock_metrics = {
        'total_value': sum(s.quantity * s.unit_price for s in current_stock),
        'total_quantity': sum(s.quantity for s in current_stock),
        'by_type': {}
    }
    
    for stock in current_stock:
        product = Product.query.get(stock.product_id)
        if product.type not in stock_metrics['by_type']:
            stock_metrics['by_type'][product.type] = {
                'quantity': 0,
                'value': 0
            }
        stock_metrics['by_type'][product.type]['quantity'] += stock.quantity
        stock_metrics['by_type'][product.type]['value'] += stock.quantity * stock.unit_price
    
    # Get stock movements
    stock_movements = StockRequest.query.filter(
        StockRequest.created_at.between(start_date, end_date)
    ).all()
    
    return render_template('finance/report.html',
                         transactions=transactions,
                         total_revenue=total_revenue,
                         total_transactions=total_transactions,
                         product_sales=product_sales,
                         current_stock=current_stock,
                         stock_metrics=stock_metrics,
                         stock_movements=stock_movements,
                         start_date=start_date,
                         end_date=end_date,
                         filters={
                             'product_type': product_type,
                             'status': status,
                             'region': region
                         })

@bp.route('/export_report')
@login_required
def export_report():
    if current_user.role != 'md':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get filters from request parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    product_type = request.args.get('product_type')
    status = request.args.get('status')
    region = request.args.get('region')
    report_type = request.args.get('type', 'financial')  # financial or stock
    
    # Set default date range to last 30 days if not specified
    if not end_date:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if report_type == 'financial':
            # Financial report
            query = Transaction.query.filter(
                Transaction.created_at.between(start_date, end_date)
            )
            
            if product_type:
                query = query.join(Product).filter(Product.type == product_type)
            if status:
                query = query.filter(Transaction.status == status)
            if region:
                query = query.filter(Transaction.region == region)
            
            transactions = query.all()
            
            # Create financial data
            financial_data = []
            for t in transactions:
                product = Product.query.get(t.product_id)
                financial_data.append({
                    'Date': t.created_at.strftime('%Y-%m-%d'),
                    'Product': product.name,
                    'Type': product.type,
                    'Quantity': t.quantity,
                    'Unit Price': t.unit_price,
                    'Total Amount': t.total_amount,
                    'Status': t.status,
                    'Region': t.region
                })
            
            df_financial = pd.DataFrame(financial_data)
            df_financial.to_excel(writer, sheet_name='Financial Report', index=False)
            
            # Add summary sheet
            summary_data = {
                'Metric': ['Total Revenue', 'Total Transactions', 'Average Transaction Value'],
                'Value': [
                    df_financial['Total Amount'].sum(),
                    len(df_financial),
                    df_financial['Total Amount'].mean()
                ]
            }
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
            
        else:
            # Stock report
            stock_query = Stock.query
            if product_type:
                stock_query = stock_query.join(Product).filter(Product.type == product_type)
            
            current_stock = stock_query.all()
            
            # Create stock data
            stock_data = []
            for stock in current_stock:
                product = Product.query.get(stock.product_id)
                stock_data.append({
                    'Product': product.name,
                    'Type': product.type,
                    'Current Quantity': stock.quantity,
                    'Unit Price': stock.unit_price,
                    'Total Value': stock.quantity * stock.unit_price,
                    'Last Updated': stock.last_updated.strftime('%Y-%m-%d')
                })
            
            df_stock = pd.DataFrame(stock_data)
            df_stock.to_excel(writer, sheet_name='Stock Report', index=False)
            
            # Add stock movements
            movements = StockRequest.query.filter(
                StockRequest.created_at.between(start_date, end_date)
            ).all()
            
            movement_data = []
            for m in movements:
                product = Product.query.get(m.product_id)
                movement_data.append({
                    'Date': m.created_at.strftime('%Y-%m-%d'),
                    'Product': product.name,
                    'Type': product.type,
                    'Quantity': m.quantity,
                    'Status': m.status,
                    'Requested By': m.requested_by
                })
            
            df_movements = pd.DataFrame(movement_data)
            df_movements.to_excel(writer, sheet_name='Stock Movements', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'{report_type}_report_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.xlsx'
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