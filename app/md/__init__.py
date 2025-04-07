from flask import Blueprint

bp = Blueprint('md', __name__, url_prefix='/md')

from app.md import routes 