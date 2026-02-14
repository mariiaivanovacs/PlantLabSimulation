"""Flask application factory"""

import os
from flask import Flask, send_from_directory


def create_app():
    """Create and configure Flask app"""
    # Get the app directory path
    app_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(app_dir, 'templates')

    app = Flask(__name__, static_folder=static_dir, static_url_path='')

    # Load config
    app.config['DEBUG'] = True

    # Serve Flutter web app as static files
    @app.route('/')
    def serve_index():
        """Serve index.html for Flutter web app"""
        return send_from_directory(static_dir, 'index.html')

    @app.route('/<path:path>')
    def serve_static(path):
        """Serve static files with correct MIME types, fall back to index.html"""
        if os.path.isfile(os.path.join(static_dir, path)):
            return send_from_directory(static_dir, path)
        return send_from_directory(static_dir, 'index.html')

    # Register blueprints
    from app.routes import simulation_routes, agent_routes
    app.register_blueprint(simulation_routes.bp, url_prefix='/api/simulation')
    app.register_blueprint(agent_routes.bp, url_prefix='/api/agents')

    return app
