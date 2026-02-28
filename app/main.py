"""
Flask Application Factory
=========================
Main entry point for the Broadcast Control Dashboard.

The dashboard is now a full control panel (not read-only).
Stream engine runs in a separate container.
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
    - REST API routes (full CRUD)
    - Web dashboard route
    - File upload support
    """
    app = Flask(__name__)

    # Load config
    from config_loader import config
    app.secret_key = config.env.SECRET_KEY
    app.debug = config.env.DEBUG

    # No upload size limit (user uploads 2GB+ video files over LAN)
    app.config['MAX_CONTENT_LENGTH'] = None

    # Initialize database
    import database as db
    db.init_db()

    # Register blueprints
    from api import api_bp
    from web import web_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)

    logger.info("Flask app initialized (Broadcast Control Dashboard)")

    return app


# Create app instance for gunicorn
app = create_app()


if __name__ == "__main__":
    # For development only
    logger.warning("Running in development mode")
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
