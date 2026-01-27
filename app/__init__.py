"""Flask application factory"""

from flask import Flask

def create_app():
    """Create and configure Flask app"""
    app = Flask(__name__)
    
    # Load config
    app.config['DEBUG'] = True
    
    # Register blueprints
    from app.routes import health, simulation_routes, agent_routes
    app.register_blueprint(health.bp)
    app.register_blueprint(simulation_routes.bp, url_prefix='/api/simulation')
    app.register_blueprint(agent_routes.bp, url_prefix='/api/agents')
    
    return app

