"""Flask application factory"""

import os
from flask import Flask


def create_app():
    """Create and configure Flask app"""
    # Get the app directory path
    app_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(app_dir, 'templates')
    static_dir = os.path.join(app_dir, 'templates')

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir, static_url_path='')

    # Load config
    app.config['DEBUG'] = True

    # Serve Flutter web app as static files
    @app.route('/')
    def serve_index():
        """Serve index.html for Flutter web app"""
        with open(os.path.join(static_dir, 'index.html'), 'r') as f:
            return f.read()
    
    @app.route('/<path:path>')
    def serve_static(path):
        """Serve static files and fall back to index.html for client-side routing"""
        file_path = os.path.join(static_dir, path)
        if os.path.isfile(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        # Fall back to index.html for client-side routing
        with open(os.path.join(static_dir, 'index.html'), 'r') as f:
            return f.read()

    # Register blueprints
    from app.routes import simulation_routes, agent_routes
    app.register_blueprint(simulation_routes.bp, url_prefix='/api/simulation')
    app.register_blueprint(agent_routes.bp, url_prefix='/api/agents')

    return app
