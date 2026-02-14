"""Agent API routes — delegates to AgentOrchestrator"""

from flask import Blueprint, jsonify, request
from app.routes.simulation_routes import get_orchestrator

bp = Blueprint('agents', __name__)


def _require_orchestrator():
    """Return orchestrator or (None, error_response)."""
    orch = get_orchestrator()
    if orch is None:
        return None, (jsonify({
            'success': False,
            'error': 'No agents attached. Start a simulation first.'
        }), 400)
    return orch, None


@bp.route('/status', methods=['GET'])
def agent_status():
    """Get combined agent statistics"""
    orch, err = _require_orchestrator()
    if err:
        return err
    return jsonify({'success': True, 'statistics': orch.get_statistics()})


@bp.route('/diagnostics', methods=['GET'])
def get_diagnostics():
    """Get recent RAG diagnostics from reasoning agent"""
    orch, err = _require_orchestrator()
    if err:
        return err
    limit = request.args.get('limit', default=5, type=int)
    return jsonify({
        'success': True,
        'diagnostics': orch.reasoning_agent.get_recent_diagnostics(limit),
    })


@bp.route('/execute', methods=['POST'])
def execute():
    """Execute a tool action via the executor agent.

    Request body:
    {
        "tool_type": "watering",          # required
        "parameters": {"volume_L": 0.3}   # required
    }
    """
    orch, err = _require_orchestrator()
    if err:
        return err

    data = request.get_json() or {}
    tool_type = data.get('tool_type')
    parameters = data.get('parameters', {})

    if not tool_type:
        return jsonify({
            'success': False,
            'error': 'tool_type is required'
        }), 400

    results = orch.executor_agent.execute_plan([
        {'tool_type': tool_type, 'parameters': parameters}
    ])
    result = results[0]

    return jsonify({
        'success': result.success,
        'message': result.message,
        'changes': result.changes,
        'error': None if result.success else result.message,
    })


@bp.route('/executor/log', methods=['GET'])
def executor_log():
    """Get executor action log"""
    orch, err = _require_orchestrator()
    if err:
        return err
    limit = request.args.get('limit', default=20, type=int)
    log = orch.executor_agent.get_log()
    return jsonify({
        'success': True,
        'total': len(log),
        'log': log[-limit:],
    })


@bp.route('/alerts/clear', methods=['POST'])
def clear_alerts():
    """Clear all alert history in the reasoning agent."""
    orch, err = _require_orchestrator()
    if err:
        return err
    orch.reasoning_agent.reset()
    return jsonify({'success': True, 'message': 'Alert history cleared'})


@bp.route('/monitor/enable', methods=['POST'])
def set_monitor():
    """Enable or disable monitor agent.

    Request body: {"enabled": true|false}
    """
    orch, err = _require_orchestrator()
    if err:
        return err
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    orch.set_monitor_enabled(enabled)
    return jsonify({
        'success': True,
        'monitor_enabled': orch.monitor_enabled,
    })
