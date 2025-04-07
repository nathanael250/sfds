from flask import Blueprint

bp = Blueprint('finance', __name__)

from app.finance import routes 