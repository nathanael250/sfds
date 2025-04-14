from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
    send_from_directory,
    send_file
)
from flask_login import login_required, current_user
from app.agrodealer import bp
from app.models import StockRequest, Product, Citizen, db, Notification, Transaction, Stock, StockMovement
from app.utils import requires_roles
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import pandas as pd
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Configure pdfkit with the path to wkhtmltopdf
def get_wkhtmltopdf_path():
    """Get the path to wkhtmltopdf executable."""
    # Try different possible installation paths
    possible_paths = [
        r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
        r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe',
        r'C:\wkhtmltopdf\bin\wkhtmltopdf.exe'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None

# Get the path to wkhtmltopdf
wkhtmltopdf_path = get_wkhtmltopdf_path()

if wkhtmltopdf_path:
    try:
        config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
        print(f"Successfully configured wkhtmltopdf at: {wkhtmltopdf_path}")
    except Exception as e:
        print(f"Error configuring wkhtmltopdf: {str(e)}")
        config = None
else:
    print("wkhtmltopdf not found. Please install it from https://wkhtmltopdf.org/downloads.html")
    config = None


@bp.route("/dashboard")
@login_required
@requires_roles("agrodealer")
def dashboard():
    """Agrodealer dashboard showing overview of stock requests and citizens."""
    # Get counts for dashboard
    pending_requests = StockRequest.query.filter_by(
        requested_by=current_user.id, status="pending"
    ).count()
    approved_requests = StockRequest.query.filter_by(
        requested_by=current_user.id, status="approved_by_md"
    ).count()
    verified_requests = StockRequest.query.filter_by(
        requested_by=current_user.id, status="purchase_verified"
    ).count()
    total_citizens = Citizen.query.count()

    # Get recent stock requests
    recent_requests = (
        StockRequest.query.filter_by(requested_by=current_user.id)
        .order_by(StockRequest.created_at.desc())
        .limit(5)
        .all()
    )

    # Get available stock
    available_stock = (
        Stock.query.filter_by(agrodealer_id=current_user.id)
        .order_by(Stock.last_updated.desc())
        .all()
    )

    # Get unread notifications
    notifications = (
        Notification.query.filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .all()
    )

    # Get pending actions (requests that need receipt upload)
    pending_actions = []
    approved_requests_list = (
        StockRequest.query
        .options(db.joinedload(StockRequest.product))  # Eagerly load product relationship
        .filter_by(requested_by=current_user.id, status="approved_by_md")
        .all()
    )

    for request in approved_requests_list:
        if not request.receipt_path:
            product_name = request.product.name if request.product else "Unknown Product"
            pending_actions.append(
                {
                    "title": "Upload Purchase Proof",
                    "message": f"Please upload the purchase proof for your {product_name} request.",
                    "url": url_for("agrodealer.upload_receipt", request_id=request.id),
                    "button_text": "Upload Receipt",
                }
            )

    return render_template(
        "agrodealer/dashboard.html",
        pending_requests=pending_requests,
        approved_requests=approved_requests,
        verified_requests=verified_requests,
        total_citizens=total_citizens,
        recent_requests=recent_requests,
        available_stock=available_stock,
        notifications=notifications,
        pending_actions=pending_actions,
    )


@bp.route("/stock_requests")
@login_required
@requires_roles("agrodealer")
def stock_requests():
    """View all stock requests made by the agrodealer."""
    requests = (
        StockRequest.query.filter_by(requested_by=current_user.id)
        .order_by(StockRequest.created_at.desc())
        .all()
    )
    return render_template("agrodealer/stock_requests.html", requests=requests)


@bp.route("/request_stock", methods=["GET", "POST"])
@login_required
@requires_roles("agrodealer")
def request_stock():
    """Submit a new stock request."""
    if request.method == "POST":
        product_id = request.form.get("product_id")
        quantity = request.form.get("quantity")

        if not product_id or not quantity:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("agrodealer.request_stock"))

        try:
            quantity = float(quantity)
        except ValueError:
            flash("Invalid quantity value.", "error")
            return redirect(url_for("agrodealer.request_stock"))

        # Create new stock request
        stock_request = StockRequest(
            product_id=product_id,
            quantity=quantity,
            requested_by=current_user.id,
            status="pending",
        )

        db.session.add(stock_request)
        db.session.commit()

        flash("Stock request submitted successfully.", "success")
        return redirect(url_for("agrodealer.stock_requests"))

    # Get available products for the form
    products = Product.query.all()
    return render_template("agrodealer/request_stock.html", products=products)


@bp.route("/upload_receipt/<int:request_id>", methods=["GET", "POST"])
@login_required
@requires_roles("agrodealer")
def upload_receipt(request_id):
    """Upload a receipt for a stock request that has been approved by MD."""
    stock_request = StockRequest.query.get_or_404(request_id)

    # Check if the request belongs to the current user
    if stock_request.requested_by != current_user.id:
        flash(
            "You do not have permission to upload a receipt for this request.", "error"
        )
        return redirect(url_for("agrodealer.stock_requests"))

    # Check if the request has been approved by MD
    if stock_request.status != "approved_by_md":
        flash("This request is not ready for receipt upload.", "error")
        return redirect(url_for("agrodealer.stock_requests"))

    if request.method == "POST":
        # Check if a file was uploaded
        if "receipt" not in request.files:
            flash("No file uploaded.", "error")
            return redirect(request.url)

        file = request.files["receipt"]

        # Check if a file was selected
        if file.filename == "":
            flash("No file selected.", "error")
            return redirect(request.url)

        # Check if the file is allowed
        allowed_extensions = {"pdf", "png", "jpg", "jpeg"}
        if not file.filename.lower().endswith(
            tuple("." + ext for ext in allowed_extensions)
        ):
            flash("Invalid file type. Allowed types: PDF, PNG, JPG, JPEG", "error")
            return redirect(request.url)

        try:
            # Ensure upload directory exists
            os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
            
            # Save the file
            filename = secure_filename(
                f"receipt_{stock_request.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{os.path.splitext(file.filename)[1]}"
            )
            file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))

            # Update the stock request
            stock_request.receipt_path = filename
            db.session.commit()
            
            flash("Receipt uploaded successfully. MD will verify it soon.", "success")
            return redirect(url_for("agrodealer.stock_requests"))
            
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while uploading the receipt: {str(e)}", "error")
            return redirect(request.url)

    return render_template(
        "agrodealer/upload_receipt.html", stock_request=stock_request
    )


@bp.route("/view_receipt/<int:request_id>")
@login_required
@requires_roles("agrodealer")
def view_receipt(request_id):
    """View a receipt uploaded for a stock request."""
    stock_request = StockRequest.query.get_or_404(request_id)

    # Check if the request belongs to the current user
    if stock_request.requested_by != current_user.id:
        flash("You do not have permission to view this receipt.", "error")
        return redirect(url_for("agrodealer.stock_requests"))

    if not stock_request.receipt_path:
        flash("No receipt available for this request.", "error")
        return redirect(url_for("agrodealer.stock_requests"))

    # Get the file extension
    file_ext = os.path.splitext(stock_request.receipt_path)[1].lower()
    
    # Set content type based on file extension
    content_type = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png'
    }.get(file_ext, 'application/octet-stream')

    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        stock_request.receipt_path,
        as_attachment=False,
        mimetype=content_type
    )


@bp.route("/available_stock")
@login_required
@requires_roles("agrodealer")
def available_stock():
    """View all stock that has been verified by MD."""
    stock = (
        StockRequest.query.filter_by(
            requested_by=current_user.id, status="purchase_verified"
        )
        .order_by(StockRequest.created_at.desc())
        .all()
    )
    return render_template("agrodealer/available_stock.html", stock=stock)


@bp.route("/citizens")
@login_required
@requires_roles("agrodealer")
def view_citizens():
    """View all citizens."""
    citizens = Citizen.query.all()
    return render_template("agrodealer/citizens.html", citizens=citizens)


@bp.route("/register_citizen", methods=["GET", "POST"])
@login_required
@requires_roles("agrodealer")
def register_citizen():
    """Register a new citizen."""
    print(f"\nRegister Citizen Route:")  # Debug log
    print(f"User authenticated: {current_user.is_authenticated}")  # Debug log
    print(f"User ID: {current_user.id}")  # Debug log
    print(f"User role: {current_user.role}")  # Debug log

    if request.method == "POST":
        try:
            # Get form data
            name = request.form.get("name")
            national_id = request.form.get("national_id")
            upi_number = request.form.get("upi_number")
            phone_number = request.form.get("phone_number")
            plot_size = float(request.form.get("plot_size"))
            allowed_seeds = float(request.form.get("allowed_seeds", 0))
            allowed_fertilizer = float(request.form.get("allowed_fertilizer", 0))
            
            print(f"\nRegistering citizen with data:")  # Debug log
            print(f"Name: {name}")  # Debug log
            print(f"National ID: {national_id}")  # Debug log
            print(f"UPI Number: {upi_number}")  # Debug log
            print(f"Phone Number: {phone_number}")  # Debug log
            print(f"Plot Size: {plot_size}")  # Debug log
            print(f"Allowed Seeds: {allowed_seeds}")  # Debug log
            print(f"Allowed Fertilizer: {allowed_fertilizer}")  # Debug log
            print(f"Registered By: {current_user.id}")  # Debug log
            
            # Validate required fields
            if not all([name, national_id, upi_number, phone_number, plot_size]):
                flash("All fields are required", "error")
                return redirect(url_for("agrodealer.register_citizen"))
            
            # Check if citizen already exists
            existing_citizen = Citizen.query.filter_by(national_id=national_id).first()
            if existing_citizen:
                flash("A citizen with this National ID already exists", "error")
                return redirect(url_for("agrodealer.register_citizen"))
            
            # Create new citizen
            citizen = Citizen(
                name=name,
                national_id=national_id,
                upi_number=upi_number,
                phone_number=phone_number,
                plot_size=plot_size
            )
            
            db.session.add(citizen)
            db.session.commit()
            
            print(f"\nSuccessfully registered citizen with ID: {citizen.id}")  # Debug log
            
            flash("Citizen registered successfully.", "success")
            return redirect(url_for("agrodealer.view_citizens"))
            
        except Exception as e:
            db.session.rollback()
            print(f"\nError registering citizen: {str(e)}")  # Debug log
            flash(f"Error registering citizen: {str(e)}", "error")
    
    return render_template("agrodealer/register_citizen.html")


@bp.route("/cancel_request/<int:request_id>", methods=["POST"])
@login_required
@requires_roles("agrodealer")
def cancel_request(request_id):
    """Cancel a pending stock request."""
    stock_request = StockRequest.query.get_or_404(request_id)

    # Check if the request belongs to the current user
    if stock_request.requested_by != current_user.id:
        flash("You do not have permission to cancel this request.", "error")
        return redirect(url_for("agrodealer.stock_requests"))

    # Check if the request can be cancelled (only pending requests)
    if stock_request.status != "pending":
        flash("Only pending requests can be cancelled.", "error")
        return redirect(url_for("agrodealer.stock_requests"))

    # Delete the request
    db.session.delete(stock_request)
    db.session.commit()

    flash("Stock request cancelled successfully.", "success")
    return redirect(url_for("agrodealer.stock_requests"))


@bp.route("/mark_notification_read/<int:notification_id>", methods=["POST"])
@login_required
@requires_roles("agrodealer")
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    notification = Notification.query.get_or_404(notification_id)

    # Check if the notification belongs to the current user
    if notification.user_id != current_user.id:
        flash("You do not have permission to mark this notification as read.", "error")
        return redirect(url_for("agrodealer.dashboard"))

    notification.is_read = True
    db.session.commit()

    return redirect(url_for("agrodealer.dashboard"))


@bp.route("/sell_product", methods=["GET", "POST"])
@login_required
@requires_roles("agrodealer")
def sell_product():
    """Sell products to citizens with land size validation."""
    print(f"\nDebug - Sell Product Route:")  # Debug log
    print(f"Current User ID: {current_user.id}")  # Debug log
    
    if request.method == "POST":
        try:
            citizen_id = request.form.get("citizen_id")
            product_id = request.form.get("product_id")
            quantity = float(request.form.get("quantity", 0))

            # Get citizen and product
            citizen = Citizen.query.get_or_404(citizen_id)
            product = Product.query.get_or_404(product_id)

            # Convert plot size from acres to square meters
            plot_size_sqm = citizen.plot_size * 4046.86  # 1 acre = 4046.86 square meters
            
            # Calculate maximum allowed quantity based on plot size and units per square meter
            max_allowed = plot_size_sqm * (product.units_per_sqm or 1.0)
            
            # Apply additional limits based on product type
            if product.type == 'seed':
                max_allowed = min(max_allowed, citizen.allowed_seeds)
            elif product.type == 'fertilizer':
                max_allowed = min(max_allowed, citizen.allowed_fertilizer)

            if quantity > max_allowed:
                flash(f"Quantity exceeds maximum allowed. Maximum allowed: {max_allowed:.2f} {product.unit}", "error")
                return redirect(url_for("agrodealer.sell_product"))

            # Get or create stock entry for this agrodealer
            stock = Stock.query.filter_by(
                product_id=product_id,
                agrodealer_id=current_user.id
            ).first()

            if not stock:
                # Create new stock entry if none exists
                stock = Stock(
                    product_id=product_id,
                    agrodealer_id=current_user.id,
                    quantity=product.quantity  # Initialize with product's quantity
                )
                db.session.add(stock)
                db.session.commit()

            # Check if there's enough stock
            if stock.quantity < quantity:
                flash(f"Insufficient stock available. Current stock: {stock.quantity} {product.unit}", "error")
                return redirect(url_for("agrodealer.sell_product"))

            # Calculate total amount
            total_amount = quantity * product.price_per_unit

            # Create transaction
            transaction = Transaction(
                product_id=product_id,
                citizen_id=citizen_id,
                quantity=quantity,
                total_amount=total_amount,
                sold_by=current_user.id
            )

            # Update stock
            stock.quantity -= quantity
            stock.last_updated = datetime.utcnow()

            db.session.add(transaction)
            db.session.commit()

            flash(f"Successfully sold {quantity} {product.unit} of {product.name} to {citizen.name}", "success")
            return redirect(url_for("agrodealer.dashboard"))

        except ValueError:
            flash("Invalid quantity value", "error")
            return redirect(url_for("agrodealer.sell_product"))
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred: {str(e)}", "error")
            return redirect(url_for("agrodealer.sell_product"))

    # GET request - show form
    citizens = Citizen.query.all()
    products = Product.query.all()

    # Get current stock levels for display
    stocks = Stock.query.filter_by(agrodealer_id=current_user.id).all()
    print(f"Found {len(stocks)} stock entries")  # Debug log
    for stock in stocks:
        print(f"Stock entry - Product ID: {stock.product_id}, Quantity: {stock.quantity}")  # Debug log

    stock_levels = {
        stock.product_id: stock.quantity 
        for stock in stocks
    }
    print(f"Final stock_levels dictionary: {stock_levels}")  # Debug log

    return render_template("agrodealer/sell_product.html",
                         citizens=citizens,
                         products=products,
                         stock_levels=stock_levels)


@bp.route("/pending_requests")
@login_required
@requires_roles("agrodealer")
def pending_requests():
    """View pending stock requests."""
    requests = StockRequest.query.filter_by(
        requested_by=current_user.id,
        status="pending"
    ).order_by(StockRequest.created_at.desc()).all()
    
    return render_template("agrodealer/pending_requests.html", requests=requests)


@bp.route("/seeds_stock")
@login_required
@requires_roles("agrodealer")
def seeds_stock():
    """View available seeds stock."""
    print("\nDebug - Seeds Stock Route:")
    print(f"Current User ID: {current_user.id}")
    
    # First get all seed products
    seed_products = Product.query.filter_by(type="seed").all()
    print(f"Found {len(seed_products)} seed products:")
    for product in seed_products:
        print(f"- Product ID: {product.id}, Name: {product.name}, Type: {product.type}")
    
    # Then get stock information for each product
    products_with_stock = []
    for product in seed_products:
        print(f"\nChecking stock for product {product.name} (ID: {product.id}):")
        stock = Stock.query.filter_by(
            product_id=product.id,
            agrodealer_id=current_user.id
        ).first()
        print(f"- Stock found: {stock is not None}")
        if stock:
            print(f"- Stock quantity: {stock.quantity}")
            print(f"- Stock agrodealer_id: {stock.agrodealer_id}")
            if stock.quantity > 0:
                products_with_stock.append((product, stock))
                print("- Added to products_with_stock")
            else:
                print("- Not added (quantity = 0)")
        else:
            print("- No stock entry found")
    
    print(f"\nFinal products_with_stock count: {len(products_with_stock)}")
    
    return render_template("agrodealer/seeds_stock.html", products=products_with_stock)


@bp.route("/fertilizer_stock")
@login_required
@requires_roles("agrodealer")
def fertilizer_stock():
    """View available fertilizer stock."""
    # Query fertilizer products and their stock levels for the current agrodealer
    fertilizers = (
        db.session.query(Product, Stock)
        .join(Stock, Stock.product_id == Product.id)
        .filter(
            Product.type == "fertilizer",
            Stock.agrodealer_id == current_user.id,
            Stock.quantity > 0
        )
        .all()
    )
    
    return render_template("agrodealer/fertilizer_stock.html", products=fertilizers)


@bp.route("/transactions")
@login_required
@requires_roles("agrodealer")
def transactions():
    """View transaction history with filtering and grouping options."""
    # Get filter parameters
    date_preset = request.args.get("date_preset", "custom")
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    product_type = request.args.get("product_type", "all")
    group_by = request.args.get("group_by", "none")
    active_tab = request.args.get("tab", "transactions")
    
    # Calculate date range based on preset
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_date = None
    end_date = None
    
    if date_preset != "custom":
        if date_preset == "today":
            start_date = today
            end_date = datetime.now()
        elif date_preset == "yesterday":
            start_date = today - timedelta(days=1)
            end_date = today - timedelta(seconds=1)
        elif date_preset == "this_week":
            start_date = today - timedelta(days=today.weekday())
            end_date = datetime.now()
        elif date_preset == "last_week":
            start_date = today - timedelta(days=today.weekday() + 7)
            end_date = start_date + timedelta(days=7) - timedelta(seconds=1)
        elif date_preset == "this_month":
            start_date = today.replace(day=1)
            end_date = datetime.now()
        elif date_preset == "last_month":
            last_month = today.replace(day=1) - timedelta(days=1)
            start_date = last_month.replace(day=1)
            end_date = today.replace(day=1) - timedelta(seconds=1)
    else:
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            if end_date_str:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD format.", "error")
    
    # Build base queries for transactions and stock requests
    transaction_query = Transaction.query.filter_by(sold_by=current_user.id)
    stock_request_query = StockRequest.query.filter_by(requested_by=current_user.id, status="verified")
    
    # Apply date filters
    if start_date:
        transaction_query = transaction_query.filter(Transaction.created_at >= start_date)
        stock_request_query = stock_request_query.filter(StockRequest.receipt_verified_at >= start_date)
    
    if end_date:
        transaction_query = transaction_query.filter(Transaction.created_at <= end_date)
        stock_request_query = stock_request_query.filter(StockRequest.receipt_verified_at <= end_date)
    
    # Apply product type filter
    if product_type != "all":
        transaction_query = transaction_query.join(Product).filter(Product.type == product_type)
        stock_request_query = stock_request_query.join(Product).filter(Product.type == product_type)
    
    # Get data with eager loading of relationships
    transactions = (
        transaction_query.options(
            db.joinedload(Transaction.product),
            db.joinedload(Transaction.citizen)
        )
        .order_by(Transaction.created_at.desc())
        .all()
    )
    
    inbound_stock = (
        stock_request_query.options(
            db.joinedload(StockRequest.product)
        )
        .order_by(StockRequest.receipt_verified_at.desc() if StockRequest.receipt_verified_at else StockRequest.created_at.desc())
        .all()
    )
    
    # Outbound stock is the same as transactions
    outbound_stock = transactions
    
    # Calculate summary statistics
    total_sales = sum(t.total_amount for t in transactions)
    total_transactions = len(transactions)
    average_sale = total_sales / total_transactions if total_transactions > 0 else 0
    
    # Calculate today's sales
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = sum(t.total_amount for t in transactions if t.created_at >= today_start)
    
    # Prepare chart data
    # Get dates for the last 30 days
    date_range = [(datetime.now() - timedelta(days=i)).date() for i in range(30)]
    date_range.reverse()  # Oldest to newest
    
    # Format dates for chart
    stock_dates = [d.strftime("%Y-%m-%d") for d in date_range]
    
    # Calculate inbound quantities by date
    inbound_quantities = []
    for date in date_range:
        date_start = datetime.combine(date, datetime.min.time())
        date_end = datetime.combine(date, datetime.max.time())
    # Calculate inbound quantities by date
    inbound_quantities = []
    for date in date_range:
        date_start = datetime.combine(date, datetime.min.time())
        date_end = datetime.combine(date, datetime.max.time())
        
        # Sum quantities for stock requests verified on this date
        daily_inbound = sum(
            sr.quantity for sr in inbound_stock 
            if sr.receipt_verified_at and date_start <= sr.receipt_verified_at <= date_end
        )
        inbound_quantities.append(daily_inbound)
    
    # Calculate outbound quantities by date
    outbound_quantities = []
    for date in date_range:
        date_start = datetime.combine(date, datetime.min.time())
        date_end = datetime.combine(date, datetime.max.time())
        
        # Sum quantities for transactions on this date
        daily_outbound = sum(
            t.quantity for t in transactions 
            if date_start <= t.created_at <= date_end
        )
        outbound_quantities.append(daily_outbound)
    
    # Apply grouping if requested
    grouped_transactions = None
    if group_by != "none":
        grouped_data = {}
        
        if group_by == "product":
            # Group by product
            for t in transactions:
                product_name = t.product.name
                if product_name not in grouped_data:
                    grouped_data[product_name] = {
                        "name": product_name,
                        "quantity": 0,
                        "total_amount": 0,
                        "count": 0
                    }
                grouped_data[product_name]["quantity"] += t.quantity
                grouped_data[product_name]["total_amount"] += t.total_amount
                grouped_data[product_name]["count"] += 1
        
        elif group_by == "type":
            # Group by product type
            for t in transactions:
                product_type = t.product.type
                if product_type not in grouped_data:
                    grouped_data[product_type] = {
                        "name": product_type.title(),
                        "quantity": 0,
                        "total_amount": 0,
                        "count": 0
                    }
                grouped_data[product_type]["quantity"] += t.quantity
                grouped_data[product_type]["total_amount"] += t.total_amount
                grouped_data[product_type]["count"] += 1
        
        elif group_by == "date":
            # Group by date
            for t in transactions:
                date_str = t.created_at.strftime("%Y-%m-%d")
                if date_str not in grouped_data:
                    grouped_data[date_str] = {
                        "name": date_str,
                        "quantity": 0,
                        "total_amount": 0,
                        "count": 0
                    }
                grouped_data[date_str]["quantity"] += t.quantity
                grouped_data[date_str]["total_amount"] += t.total_amount
                grouped_data[date_str]["count"] += 1
        
        # Convert to list and sort
        grouped_transactions = list(grouped_data.values())
        if group_by == "date":
            grouped_transactions.sort(key=lambda x: x["name"], reverse=True)
        else:
            grouped_transactions.sort(key=lambda x: x["total_amount"], reverse=True)
    
    return render_template(
        "agrodealer/transactions.html",
        transactions=transactions,
        inbound_stock=inbound_stock,
        outbound_stock=outbound_stock,
        total_sales=total_sales,
        total_transactions=total_transactions,
        average_sale=average_sale,
        today_sales=today_sales,
        stock_dates=stock_dates,
        inbound_quantities=inbound_quantities,
        outbound_quantities=outbound_quantities,
        date_preset=date_preset,
        start_date=start_date,
        end_date=end_date,
        product_type=product_type,
        group_by=group_by,
        active_tab=active_tab,
        grouped_transactions=grouped_transactions
    )


@bp.route('/stock/requests/<int:request_id>')
@login_required
@requires_roles('agrodealer')
def view_request(request_id):
    """View details of a specific stock request."""
    stock_request = StockRequest.query.get_or_404(request_id)
    
    # Ensure the request belongs to the current agrodealer
    if stock_request.requested_by != current_user.id:
        flash('You do not have permission to view this request.', 'error')
        return redirect(url_for('agrodealer.stock_requests'))
    
    return render_template('agrodealer/request_details.html', request=stock_request)


@bp.route("/reports")
@login_required
@requires_roles("agrodealer")
def reports():
    """View reports dashboard with filters."""
    # Get today's date for filtering
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    
    # Calculate today's statistics
    today_transactions = Transaction.query.filter(
        Transaction.sold_by == current_user.id,
        Transaction.created_at >= today
    ).all()
    
    today_stats = {
        'total_sales': sum(t.total_amount for t in today_transactions),
        'transactions': len(today_transactions)
    }
    
    # Calculate this month's statistics
    month_transactions = Transaction.query.filter(
        Transaction.sold_by == current_user.id,
        Transaction.created_at >= month_start
    ).all()
    
    products_sold = {}
    for t in month_transactions:
        if t.product.name in products_sold:
            products_sold[t.product.name] += t.quantity
        else:
            products_sold[t.product.name] = t.quantity
    
    month_stats = {
        'total_sales': sum(t.total_amount for t in month_transactions),
        'products_sold': len(products_sold)
    }
    
    # Calculate stock statistics
    stocks = Stock.query.filter_by(agrodealer_id=current_user.id).all()
    low_stock_threshold = 10  # Define what constitutes "low stock"
    
    stock_stats = {
        'total_products': len(stocks),
        'low_stock_items': sum(1 for s in stocks if s.quantity <= low_stock_threshold)
    }
    
    return render_template(
        "agrodealer/reports.html",
        today_stats=today_stats,
        month_stats=month_stats,
        stock_stats=stock_stats
    )


@bp.route("/generate_report")
@login_required
@requires_roles("agrodealer")
def generate_report():
    """Generate and export transaction reports in various formats."""
    # Get filter parameters
    date_preset = request.args.get("date_preset", "custom")
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    product_type = request.args.get("product_type", "all")
    group_by = request.args.get("group_by", "none")
    export_format = request.args.get("format", "pdf")
    active_tab = request.args.get("tab", "transactions")
    
    # Calculate date range based on preset
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_date = None
    end_date = None
    
    if date_preset != "custom":
        if date_preset == "today":
            start_date = today
            end_date = datetime.now()
        elif date_preset == "yesterday":
            start_date = today - timedelta(days=1)
            end_date = today - timedelta(seconds=1)
        elif date_preset == "this_week":
            start_date = today - timedelta(days=today.weekday())
            end_date = datetime.now()
        elif date_preset == "last_week":
            start_date = today - timedelta(days=today.weekday() + 7)
            end_date = start_date + timedelta(days=7) - timedelta(seconds=1)
        elif date_preset == "this_month":
            start_date = today.replace(day=1)
            end_date = datetime.now()
        elif date_preset == "last_month":
            last_month = today.replace(day=1) - timedelta(days=1)
            start_date = last_month.replace(day=1)
            end_date = today.replace(day=1) - timedelta(seconds=1)
    else:
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            if end_date_str:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD format.", "error")
    
    # Build base queries based on active tab
    if active_tab == "transactions" or active_tab == "outbound":
        # For transactions or outbound tab
        query = Transaction.query.filter_by(sold_by=current_user.id)
        
        # Apply date filters
        if start_date:
            query = query.filter(Transaction.created_at >= start_date)
        if end_date:
            query = query.filter(Transaction.created_at <= end_date)
        
        # Apply product type filter
        if product_type != "all":
            query = query.join(Product).filter(Product.type == product_type)
        
        # Get data with eager loading of relationships
        data = (
            query.options(
                db.joinedload(Transaction.product),
                db.joinedload(Transaction.citizen)
            )
            .order_by(Transaction.created_at.desc())
            .all()
        )
        
        # Set report title based on tab
        if active_tab == "transactions":
            report_title = "Transaction History Report"
        else:
            report_title = "Outbound Stock Report"
            
    elif active_tab == "inbound":
        # For inbound tab
        query = StockRequest.query.filter_by(requested_by=current_user.id, status="verified")
        
        # Apply date filters
        if start_date:
            query = query.filter(StockRequest.receipt_verified_at >= start_date)
        if end_date:
            query = query.filter(StockRequest.receipt_verified_at <= end_date)
        
        # Apply product type filter
        if product_type != "all":
            query = query.join(Product).filter(Product.type == product_type)
        
        # Get data with eager loading of relationships
        data = (
            query.options(
                db.joinedload(StockRequest.product)
            )
            .order_by(StockRequest.receipt_verified_at.desc() if StockRequest.receipt_verified_at else StockRequest.created_at.desc())
            .all()
        )
        
        report_title = "Inbound Stock Report"
    
    # Generate report based on format
    if export_format == "pdf":
        # Create PDF buffer
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        
        # Create styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle", parent=styles["Heading1"], fontSize=16, spaceAfter=30
        )
        
        # Create elements
        elements = []
        
        # Add title
        title = Paragraph(f"{report_title} - {current_user.username}", title_style)
        elements.append(title)
        
        # Add date range
        date_text = f"Date Range: {start_date.strftime('%Y-%m-%d') if start_date else 'Start'} to {end_date.strftime('%Y-%m-%d') if end_date else 'End'}"
        elements.append(Paragraph(date_text, styles["Normal"]))
        elements.append(Spacer(1, 20))
        
        # Create table data based on active tab
        if active_tab == "transactions" or active_tab == "outbound":
            # Add summary
            total_amount = sum(t.total_amount for t in data)
            summary_text = f"Total Sales: RWF {total_amount:,.2f} | Total Transactions: {len(data)}"
            elements.append(Paragraph(summary_text, styles["Normal"]))
            elements.append(Spacer(1, 20))
            
            # Create table header
            table_data = [
                ["Date", "Product", "Type", "Citizen", "Quantity", "Unit Price", "Total Amount"]
            ]
            
            # Add rows
            for item in data:
                table_data.append([
                    item.created_at.strftime("%Y-%m-%d %H:%M"),
                    item.product.name,
                    item.product.type.title(),
                    item.citizen.name,
                    f"{item.quantity} {item.product.unit}",
                    f"RWF {item.product.price_per_unit:,.2f}",
                    f"RWF {item.total_amount:,.2f}"
                ])
        
        elif active_tab == "inbound":
            # Add summary
            total_quantity = sum(item.quantity for item in data)
            total_value = sum(item.quantity * item.product.price_per_unit for item in data)
            summary_text = f"Total Items: {total_quantity} | Total Value: RWF {total_value:,.2f}"
            elements.append(Paragraph(summary_text, styles["Normal"]))
            elements.append(Spacer(1, 20))
            
            # Create table header
            table_data = [
                ["Date", "Product", "Type", "Quantity", "Unit Price", "Total Value", "Status"]
            ]
            
            # Add rows
            for item in data:
                verified_date = item.receipt_verified_at.strftime("%Y-%m-%d") if item.receipt_verified_at else item.created_at.strftime("%Y-%m-%d")
                total_value = item.quantity * item.product.price_per_unit
                
                table_data.append([
                    verified_date,
                    item.product.name,
                    item.product.type.title(),
                    f"{item.quantity} {item.product.unit}",
                    f"RWF {item.product.price_per_unit:,.2f}",
                    f"RWF {total_value:,.2f}",
                    item.status.replace("_", " ").title()
                ])
        
        # Create table
        table = Table(table_data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        
        elements.append(table)
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF data
        pdf = buffer.getvalue()
        buffer.close()
        
        # Create response
        filename = f"{active_tab}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return send_file(
            BytesIO(pdf),
            download_name=filename,
            as_attachment=True,
            mimetype="application/pdf",
        )
    
    elif export_format == "excel":
        # Create Excel data
        output = BytesIO()
        
        if active_tab == "transactions" or active_tab == "outbound":
            # Create data for transactions/outbound
            excel_data = []
            for item in data:
                excel_data.append({
                    "Date": item.created_at.strftime("%Y-%m-%d %H:%M"),
                    "Product": item.product.name,
                    "Type": item.product.type.title(),
                    "Citizen": item.citizen.name,
                    "Citizen ID": item.citizen.national_id,
                    "Quantity": item.quantity,
                    "Unit": item.product.unit,
                    "Unit Price": item.product.price_per_unit,
                    "Total Amount": item.total_amount
                })
        
        elif active_tab == "inbound":
            # Create data for inbound
            excel_data = []
            for item in data:
                verified_date = item.receipt_verified_at if item.receipt_verified_at else item.created_at
                total_value = item.quantity * item.product.price_per_unit
                
                excel_data.append({
                    "Date": verified_date.strftime("%Y-%m-%d"),
                    "Product": item.product.name,
                    "Type": item.product.type.title(),
                    "Quantity": item.quantity,
                    "Unit": item.product.unit,
                    "Unit Price": item.product.price_per_unit,
                    "Total Value": total_value,
                    "Status": item.status.replace("_", " ").title()
                })
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Write to Excel
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name=active_tab.title(), index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets[active_tab.title()]
            
            # Add formats
            money_format = workbook.add_format({"num_format": '#,##0 "RWF"'})
            date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})
            
            # Set column formats
            if active_tab == "transactions" or active_tab == "outbound":
                worksheet.set_column("A:A", 18, date_format)  # Date
                worksheet.set_column("B:B", 15)  # Product
                worksheet.set_column("C:C", 10)  # Type
                worksheet.set_column("D:D", 20)  # Citizen
                worksheet.set_column("E:E", 15)  # Citizen ID
                worksheet.set_column("F:F", 10)  # Quantity
                worksheet.set_column("G:G", 8)   # Unit
                worksheet.set_column("H:H", 12, money_format)  # Unit Price
                worksheet.set_column("I:I", 15, money_format)  # Total Amount
            
            elif active_tab == "inbound":
                worksheet.set_column("A:A", 18, date_format)  # Date
                worksheet.set_column("B:B", 15)  # Product
                worksheet.set_column("C:C", 10)  # Type
                worksheet.set_column("D:D", 10)  # Quantity
                worksheet.set_column("E:E", 8)   # Unit
                worksheet.set_column("F:F", 12, money_format)  # Unit Price
                worksheet.set_column("G:G", 15, money_format)  # Total Value
                worksheet.set_column("H:H", 15)  # Status
            
            # Add title and summary
            title_format = workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'center',
                'valign': 'vcenter'
            })
            
            # Add a title
            title = f"{report_title} - {current_user.username}"
            worksheet.merge_range('A1:I1', title, title_format)
            
            # Add date range
            date_range = f"Date Range: {start_date.strftime('%Y-%m-%d') if start_date else 'Start'} to {end_date.strftime('%Y-%m-%d') if end_date else 'End'}"
            worksheet.merge_range('A2:I2', date_range, workbook.add_format({'align': 'center'}))
            
            # Add summary
            if active_tab == "transactions" or active_tab == "outbound":
                total_amount = sum(item.total_amount for item in data)
                summary = f"Total Sales: RWF {total_amount:,.2f} | Total Transactions: {len(data)}"
            else:
                total_quantity = sum(item.quantity for item in data)
                total_value = sum(item.quantity * item.product.price_per_unit for item in data)
                summary = f"Total Items: {total_quantity} | Total Value: RWF {total_value:,.2f}"
                
            worksheet.merge_range('A3:I3', summary, workbook.add_format({'align': 'center'}))
            
            # Adjust the data range to start after the header rows
            worksheet.set_column('A4:I4', None, workbook.add_format({'bold': True}))
        
        # Create response
        output.seek(0)
        filename = f"{active_tab}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    
    elif export_format == "csv":
        # Create CSV data
        if active_tab == "transactions" or active_tab == "outbound":
            # Create data for transactions/outbound
            csv_data = []
            for item in data:
                csv_data.append({
                    "Date": item.created_at.strftime("%Y-%m-%d %H:%M"),
                    "Product": item.product.name,
                    "Type": item.product.type.title(),
                    "Citizen": item.citizen.name,
                    "Citizen ID": item.citizen.national_id,
                    "Quantity": item.quantity,
                    "Unit": item.product.unit,
                    "Unit Price": item.product.price_per_unit,
                    "Total Amount": item.total_amount
                })
        
        elif active_tab == "inbound":
            # Create data for inbound
            csv_data = []
            for item in data:
                verified_date = item.receipt_verified_at if item.receipt_verified_at else item.created_at
                total_value = item.quantity * item.product.price_per_unit
                
                csv_data.append({
                    "Date": verified_date.strftime("%Y-%m-%d"),
                    "Product": item.product.name,
                    "Type": item.product.type.title(),
                    "Quantity": item.quantity,
                    "Unit": item.product.unit,
                    "Unit Price": item.product.price_per_unit,
                    "Total Value": total_value,
                    "Status": item.status.replace("_", " ").title()
                })
        
        # Create DataFrame
        df = pd.DataFrame(csv_data)
        
        # Create response
        output = BytesIO()
        df.to_csv(output, index=False, encoding="utf-8")
        output.seek(0)
        
        filename = f"{active_tab}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="text/csv",
        )
    
    # If we get here, something went wrong
    flash("Invalid export format specified", "error")
    return redirect(url_for("agrodealer.transactions"))


@bp.route("/upload_logo", methods=["GET", "POST"])
@login_required
@requires_roles("agrodealer")
def upload_logo():
    """Upload or update agrodealer's logo."""
    if request.method == "POST":
        if 'logo' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
            
        file = request.files['logo']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            try:
                # Create uploads directory if it doesn't exist
                upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'logos')
                os.makedirs(upload_dir, exist_ok=True)
                
                # Generate unique filename
                filename = secure_filename(f"logo_{current_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{os.path.splitext(file.filename)[1]}")
                filepath = os.path.join(upload_dir, filename)
                
                # Save the file
                file.save(filepath)
                
                # Update user's logo path
                current_user.logo_path = os.path.join('uploads', 'logos', filename)
                db.session.commit()
                
                flash('Logo uploaded successfully', 'success')
                return redirect(url_for('agrodealer.dashboard'))
                
            except Exception as e:
                flash(f'Error uploading logo: {str(e)}', 'error')
                return redirect(request.url)
        else:
            flash('Invalid file type. Allowed types: PNG, JPG, JPEG', 'error')
            return redirect(request.url)
            
    return render_template('agrodealer/upload_logo.html')

def allowed_file(filename):
    """Check if the file extension is allowed."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
