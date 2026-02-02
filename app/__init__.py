"""Flask application factory"""

import os
from flask import Flask


def create_app():
    """Create and configure Flask app"""
    # Get the app directory path
    app_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(app_dir, 'templates')

    app = Flask(__name__, template_folder=template_dir)

    # Load config
    app.config['DEBUG'] = True

    # Register blueprints
    from app.routes import health, simulation_routes, agent_routes
    app.register_blueprint(health.bp)
    app.register_blueprint(simulation_routes.bp, url_prefix='/api/simulation')
    app.register_blueprint(agent_routes.bp, url_prefix='/api/agents')

    return app
