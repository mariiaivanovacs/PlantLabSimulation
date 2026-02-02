"""Health check routes and UI"""

from flask import Blueprint, jsonify, render_template

bp = Blueprint('health', __name__)


@bp.route('/health')
def health():
    return jsonify({'status': 'healthy'})


@bp.route('/')
def index():
    """Serve the simulation control UI"""
    return render_template('index.html')


@bp.route('/api')
def api_info():
    """API information endpoint"""
    return jsonify({
        'message': 'Plant Simulator API',
        'version': '1.0.0',
        'endpoints': {
            'ui': '/',
            'start': 'POST /api/simulation/start',
            'stop': 'POST /api/simulation/stop',
            'state': 'GET /api/simulation/state',
            'plants': 'GET /api/simulation/plants',
            'history': 'GET /api/simulation/history',
            'alerts': 'GET /api/simulation/monitor/alerts'
        }
    })
