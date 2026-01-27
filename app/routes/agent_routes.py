"""Agent API routes"""

from flask import Blueprint, jsonify, request

bp = Blueprint('agents', __name__)

@bp.route('/plan', methods=['POST'])
def plan():
    """Get agent's plan"""
    return jsonify({'plan': []})

@bp.route('/execute', methods=['POST'])
def execute():
    """Execute agent action"""
    data = request.get_json() or {}
    return jsonify({'message': 'Action executed', 'action': data})

