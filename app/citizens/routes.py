from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import Citizen, db
from app.utils import requires_roles
from app.citizens import bp

@bp.route('/')
@login_required
@requires_roles('md', 'agrodealer')
def index():
    citizens = Citizen.query.all()
    return render_template('citizens/index.html', citizens=citizens)

@bp.route('/register', methods=['GET', 'POST'])
@login_required
@requires_roles('agrodealer')
def register_citizen():
    if request.method == 'POST':
        name = request.form.get('name')
        national_id = request.form.get('national_id')
        upi = request.form.get('upi')
        phone = request.form.get('phone')
        plot_size = request.form.get('plot_size')
        allowed_seeds = request.form.get('allowed_seeds')
        allowed_fertilizer = request.form.get('allowed_fertilizer')

        # Validate inputs
        if not all([name, national_id, upi, phone, plot_size, allowed_seeds, allowed_fertilizer]):
            flash('All fields are required', 'error')
            return redirect(url_for('citizens.register_citizen'))

        # Check if citizen already exists
        existing_citizen = Citizen.query.filter_by(national_id=national_id).first()
        if existing_citizen:
            flash('A citizen with this National ID already exists', 'error')
            return redirect(url_for('citizens.register_citizen'))

        try:
            new_citizen = Citizen(
                name=name,
                national_id=national_id,
                upi_number=upi,
                phone_number=phone,
                plot_size=float(plot_size),
                allowed_seeds=float(allowed_seeds),
                allowed_fertilizer=float(allowed_fertilizer),
                registered_by=current_user.id
            )
            db.session.add(new_citizen)
            db.session.commit()
            flash('Citizen registered successfully', 'success')
            return redirect(url_for('citizens.view_citizens'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while registering the citizen', 'error')
            return redirect(url_for('citizens.register_citizen'))

    return render_template('citizens/register.html')

@bp.route('/citizens')
@login_required
@requires_roles('agrodealer')
def view_citizens():
    citizens = Citizen.query.filter_by(registered_by=current_user.id).all()
    return render_template('citizens/view.html', citizens=citizens) 