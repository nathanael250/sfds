from flask import Blueprint

bp = Blueprint('citizens', __name__, url_prefix='/citizens')

from app.citizens import routes 