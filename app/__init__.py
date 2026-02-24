"""Flask application factory"""

import os
from flask import Flask, send_from_directory
from flask_cors import CORS


def create_app():
    """Create and configure Flask app"""
    # Get the app directory path
    app_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(app_dir, 'templates')

    app = Flask(__name__, static_folder=static_dir, static_url_path='')

    # CORS configuration - restrict origins in production
    cors_origins = os.getenv('CORS_ORIGINS', '*').split(',')
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})


    # Load config from environment
    app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'False') == 'True'
    app.config['ENV'] = os.getenv('FLASK_ENV', 'development')
    
    # Security: Set SECRET_KEY for production
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')

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
    from app.routes import simulation_routes, agent_routes, auth_routes, gemini_routes, plant_routes, mqtt_routes
    app.register_blueprint(simulation_routes.bp, url_prefix='/api/simulation')
    app.register_blueprint(agent_routes.bp, url_prefix='/api/agents')
    app.register_blueprint(auth_routes.bp, url_prefix='/api/auth')
    app.register_blueprint(gemini_routes.bp, url_prefix='/api/gemini')
    app.register_blueprint(plant_routes.bp, url_prefix='/api/plants')
    app.register_blueprint(mqtt_routes.bp, url_prefix='/api/mqtt')

    # Health check endpoint (required for Cloud Run)
    @app.route('/health')
    def health_check():
        from flask import jsonify
        return jsonify(status='healthy'), 200

    return app
