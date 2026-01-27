"""Health check routes"""

from flask import Blueprint, jsonify

bp = Blueprint('health', __name__)

@bp.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@bp.route('/')
def index():
    return jsonify({'message': 'Plant Simulator API', 'version': '1.0.0'})

