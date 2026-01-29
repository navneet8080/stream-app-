"""
Flask Application Factory
=========================
Main entry point for the 24×7 Simulcast Engine.

CRITICAL: No auto-start logic in this file.
The StreamEngine starts automatically when loaded as a module,
but Flask does NOT control stream start/stop.
"""

import os
import sys
import logging
from flask import Flask

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("App")


def create_app():
    """
    Flask application factory.
    
    Creates and configures the Flask app with:
    - API routes (read-only)
    - Web dashboard routes (read-only)
    - Static file serving
    
    CRITICAL: Does NOT control the StreamEngine.
    """
    app = Flask(__name__)
    
    # Load config
    from config_loader import config
    app.secret_key = config.env.SECRET_KEY
    app.debug = config.env.DEBUG
    
    # Register blueprints
    from api import api_bp
    from web import web_bp
    
    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)
    
    logger.info("Flask app initialized (read-only dashboard mode)")
    
    return app


def start_stream_engine():
    """
    Start the stream engine in background.
    
    This is called by the entrypoint script, NOT by Flask.
    The engine runs independently of Flask's lifecycle.
    """
    from stream_engine import stream_engine
    stream_engine.start()
    logger.info("Stream engine started (24×7 mode)")


# Create app instance for gunicorn
app = create_app()


if __name__ == "__main__":
    # For development only
    # In production, use gunicorn + separate engine start
    logger.warning("Running in development mode")
    
    # Start stream engine in background
    start_stream_engine()
    
    # Run Flask dev server
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
