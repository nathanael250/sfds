from flask import (
    render_template, redirect, url_for, flash, request, 
    current_app, send_from_directory, send_file,jsonify,  # Add send_file here
)
from flask_login import login_required, current_user
from app.md import bp
from app.models import StockRequest, Product, db, Notification, Citizen, Stock, User, Transaction
from app.utils import requires_roles
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import base64
from sqlalchemy import func
from io import BytesIO
import pandas as pd  # Make sure pandas is imported if you're using it

# ReportLab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime, timedelta


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
    total_value = db.session.query(func.sum(Product.price_per_unit * Stock.quantity)).join(Stock, Stock.product_id == Product.id).scalar() or 0
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
    print(f"Viewing receipt for request ID: {request_id}")  # Debug log
    
    stock_request = StockRequest.query.get_or_404(request_id)
    print(f"Found stock request: {stock_request.id}")  # Debug log
    
    if not stock_request.receipt_path:
        print("No receipt path found")  # Debug log
        return jsonify({'error': 'No receipt found'}), 404
    
    print(f"Receipt path: {stock_request.receipt_path}")  # Debug log
    
    try:
        # Get the upload folder from config
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        print(f"Upload folder from config: {upload_folder}")  # Debug log
        
        # Ensure we have a valid upload folder
        if not upload_folder:
            print("No upload folder configured")  # Debug log
            return jsonify({'error': 'Server configuration error: No upload folder defined'}), 500
        
        # Construct the full file path
        file_path = os.path.join(upload_folder, stock_request.receipt_path)
        print(f"Full file path: {file_path}")  # Debug log
        
        # Check if file exists
        if not os.path.exists(file_path):
            print(f"File not found at path: {file_path}")  # Debug log
            return jsonify({'error': 'Receipt file not found'}), 404
        
        # Read the file
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Get file type
        file_ext = os.path.splitext(stock_request.receipt_path)[1].lower()
        print(f"File extension: {file_ext}")  # Debug log
        
        if file_ext in ['.jpg', '.jpeg', '.png']:
            file_type = f'image/{file_ext[1:]}'
        elif file_ext == '.pdf':
            file_type = 'application/pdf'
        else:
            print(f"Unsupported file type: {file_ext}")  # Debug log
            return jsonify({'error': 'Unsupported file type'}), 400
        
        print(f"Returning file of type: {file_type}")  # Debug log
        return jsonify({
            'type': file_type,
            'data': base64.b64encode(file_data).decode('utf-8')
        })
    except Exception as e:
        print(f"Error viewing receipt: {str(e)}")  # Debug log
        import traceback
        traceback.print_exc()  # Print full traceback
        return jsonify({'error': str(e)}), 500


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


@bp.route('/transaction_reports')
@login_required
@requires_roles('md')
def transaction_reports():
    """View transaction reports for all agrodealers."""
    # Get all agrodealers
    agrodealers = User.query.filter_by(role='agrodealer').all()
    
    # Get filter parameters
    agrodealer_id = request.args.get('agrodealer_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    product_type = request.args.get('product_type', 'all')
    
    # Convert string dates to datetime objects
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    
    # Build query with filters
    query = Transaction.query
    
    if agrodealer_id:
        query = query.filter_by(sold_by=agrodealer_id)
    
    if start_date:
        query = query.filter(Transaction.created_at >= start_date)
    if end_date:
        query = query.filter(Transaction.created_at <= end_date)
    
    # Apply product type filter
    if product_type != 'all':
        query = query.join(Product).filter(Product.type == product_type)
    
    # Get transactions with eager loading of relationships
    transactions = query.options(
        db.joinedload(Transaction.product),
        db.joinedload(Transaction.citizen),
        db.joinedload(Transaction.seller)
    ).order_by(Transaction.created_at.desc()).all()
    
    # Calculate summary statistics
    total_sales = sum(t.total_amount for t in transactions)
    total_quantity = sum(t.quantity for t in transactions)
    
    # Group transactions by agrodealer if no specific agrodealer is selected
    agrodealer_stats = {}
    if not agrodealer_id:
        for transaction in transactions:
            if transaction.seller.id not in agrodealer_stats:
                agrodealer_stats[transaction.seller.id] = {
                    'name': transaction.seller.username,
                    'total_sales': 0,
                    'total_transactions': 0
                }
            
            agrodealer_stats[transaction.seller.id]['total_sales'] += transaction.total_amount
            agrodealer_stats[transaction.seller.id]['total_transactions'] += 1
    
    return render_template(
        'md/transaction_reports.html',
        agrodealers=agrodealers,
        selected_agrodealer_id=agrodealer_id,
        transactions=transactions,
        total_sales=total_sales,
        total_quantity=total_quantity,
        start_date=start_date,
        end_date=end_date,
        product_type=product_type,
        agrodealer_stats=agrodealer_stats
    )

@bp.route('/transaction_reports/export')
@login_required
@requires_roles('md')
def export_transaction_report():
    """Export transaction report in various formats."""
    # Get filter parameters
    agrodealer_id = request.args.get('agrodealer_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    product_type = request.args.get('product_type', 'all')
    export_format = request.args.get('format', 'pdf')
    
    # Convert string dates to datetime objects
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    
    # Build query with filters
    query = Transaction.query
    
    if agrodealer_id:
        query = query.filter_by(sold_by=agrodealer_id)
        # Get agrodealer name for the report title
        agrodealer = User.query.get(agrodealer_id)
        agrodealer_name = agrodealer.username if agrodealer else "Unknown"
    else:
        agrodealer_name = "All Agrodealers"
    
    if start_date:
        query = query.filter(Transaction.created_at >= start_date)
    if end_date:
        query = query.filter(Transaction.created_at <= end_date)
    
    # Apply product type filter
    if product_type != 'all':
        query = query.join(Product).filter(Product.type == product_type)
    
    # Get transactions
    transactions = query.options(
        db.joinedload(Transaction.product),
        db.joinedload(Transaction.citizen),
        db.joinedload(Transaction.seller)
    ).order_by(Transaction.created_at.desc()).all()
    
    if export_format == 'pdf':
        # Create PDF buffer
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        
        # Create styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30
        )
        
        # Create elements
        elements = []
        
        # Add title
        title = Paragraph(f"Transaction Report for {agrodealer_name}", title_style)
        elements.append(title)
        
        # Add date range
        date_text = f"Date Range: {start_date.strftime('%Y-%m-%d') if start_date else 'Start'} to {end_date.strftime('%Y-%m-%d') if end_date else 'End'}"
        elements.append(Paragraph(date_text, styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Add summary
        summary_text = f"Total Sales: RWF {sum(t.total_amount for t in transactions):,.2f} | Total Transactions: {len(transactions)}"
        elements.append(Paragraph(summary_text, styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Create table data
        table_data = [['Date', 'Agrodealer', 'Product', 'Quantity', 'Total Amount', 'Citizen']]
        
        for transaction in transactions:
            table_data.append([
                transaction.created_at.strftime('%Y-%m-%d %H:%M'),
                str(transaction.seller.username),
                str(transaction.product.name),
                f"{transaction.quantity} {transaction.product.unit}",
                f"RWF {transaction.total_amount:,.2f}",
                str(transaction.citizen.name)
            ])
        
        # Create table
        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(table)
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF data
        pdf = buffer.getvalue()
        buffer.close()
        
        # Create response
        filename = f"transactions_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return send_file(
            BytesIO(pdf),
            download_name=filename,
            as_attachment=True,
            mimetype='application/pdf'
        )
        
    elif export_format == 'excel':
        # Create Excel file
        data = []
        for t in transactions:
            data.append({
                'Date': t.created_at.strftime('%Y-%m-%d %H:%M'),
                'Agrodealer': t.seller.username,
                'Product': t.product.name,
                'Type': t.product.type,
                'Citizen': t.citizen.name,
                'Citizen ID': t.citizen.national_id,
                'Quantity': t.quantity,
                'Unit': t.product.unit,
                'Unit Price': t.product.price_per_unit,
                'Total Amount': t.total_amount
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel writer
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Transactions', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Transactions']
            
            # Add formats
            money_format = workbook.add_format({'num_format': '#,##0 "RWF"'})
            date_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm'})
            
            # Set column formats
            worksheet.set_column('A:A', 18, date_format)  # Date
            worksheet.set_column('B:B', 15)  # Agrodealer
            worksheet.set_column('C:C', 15)  # Product
            worksheet.set_column('D:D', 10)  # Type
            worksheet.set_column('E:E', 20)  # Citizen
            worksheet.set_column('F:F', 15)  # Citizen ID
            worksheet.set_column('G:G', 10)  # Quantity
            worksheet.set_column('H:H', 8)   # Unit
            worksheet.set_column('I:I', 12, money_format)  # Unit Price
            worksheet.set_column('J:J', 15, money_format)  # Total Amount
        
        # Create response
        output.seek(0)
        filename = f"transactions_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    elif export_format == 'csv':
        # Create CSV file
        data = []
        for t in transactions:
            data.append({
                'Date': t.created_at.strftime('%Y-%m-%d %H:%M'),
                'Agrodealer': t.seller.username,
                'Product': t.product.name,
                'Type': t.product.type,
                'Citizen': t.citizen.name,
                'Citizen ID': t.citizen.national_id,
                'Quantity': t.quantity,
                'Unit': t.product.unit,
                'Unit Price': t.product.price_per_unit,
                'Total Amount': t.total_amount
            })
        
        df = pd.DataFrame(data)
        
        # Create response
        output = BytesIO()
        df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)
        
        filename = f"transactions_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='text/csv'
        )


@bp.route('/stock_health')
@login_required
@requires_roles('md')
def stock_health():
    """View stock health of all agrodealers."""
    # Get all agrodealers
    agrodealers = User.query.filter_by(role='agrodealer').all()
    
    # Get stock health data for each agrodealer
    stock_health_data = {}
    low_stock_threshold = 10  # Define what constitutes "low stock"
    
    for agrodealer in agrodealers:
        # Get all stock entries for this agrodealer
        stocks = Stock.query.filter_by(agrodealer_id=agrodealer.id).all()
        
        # Calculate statistics
        total_products = len(stocks)
        low_stock_items = sum(1 for s in stocks if s.quantity <= low_stock_threshold)
        out_of_stock_items = sum(1 for s in stocks if s.quantity <= 0)
        
        # Get total stock value
        total_value = db.session.query(
            func.sum(Product.price_per_unit * Stock.quantity)
        ).join(
            Stock, Stock.product_id == Product.id
        ).filter(
            Stock.agrodealer_id == agrodealer.id
        ).scalar() or 0
        
        # Get recent transactions
        recent_transactions = Transaction.query.filter_by(
            sold_by=agrodealer.id
        ).order_by(
            Transaction.created_at.desc()
        ).limit(5).all()
        
        # Calculate sales velocity (average daily sales over the last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_sales = Transaction.query.filter(
            Transaction.sold_by == agrodealer.id,
            Transaction.created_at >= thirty_days_ago
        ).all()
        
        total_sales_amount = sum(t.total_amount for t in recent_sales)
        sales_velocity = total_sales_amount / 30  # Average daily sales
        
        # Store data
        stock_health_data[agrodealer.id] = {
            'username': agrodealer.username,
            'total_products': total_products,
            'low_stock_items': low_stock_items,
            'out_of_stock_items': out_of_stock_items,
            'total_value': total_value,
            'recent_transactions': recent_transactions,
            'sales_velocity': sales_velocity,
            'stocks': stocks
        }
    
    return render_template(
        'md/stock_health.html',
        agrodealers=agrodealers,
        stock_health_data=stock_health_data,
        low_stock_threshold=low_stock_threshold
    )


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


