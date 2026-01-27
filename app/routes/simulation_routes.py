"""Simulation API routes"""

from flask import Blueprint, jsonify, request

bp = Blueprint('simulation', __name__)

@bp.route('/start', methods=['POST'])
def start_simulation():
    """Start a new simulation"""
    data = request.get_json() or {}
    return jsonify({'message': 'Simulation started', 'data': data})

@bp.route('/step', methods=['POST'])
def step_simulation():
    """Advance simulation by one step"""
    return jsonify({'message': 'Simulation stepped'})

@bp.route('/state', methods=['GET'])
def get_state():
    """Get current simulation state"""
    return jsonify({'state': {}})

