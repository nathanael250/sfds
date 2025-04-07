from flask import Blueprint

bp = Blueprint('sao', __name__, url_prefix='/sao')

from app.sao import routes 