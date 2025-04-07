from flask import Blueprint

bp = Blueprint('inventory', __name__, url_prefix='/inventory')

from app.inventory import routes 