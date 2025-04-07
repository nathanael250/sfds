from flask import Blueprint

bp = Blueprint('agrodealer', __name__, url_prefix='/agrodealer')

from app.agrodealer import routes 