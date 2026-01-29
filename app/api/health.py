"""
API Routes - Health and Status
==============================
Read-only JSON API endpoints.

CRITICAL: No mutation endpoints allowed.
This API only exposes status and metrics.
"""

from flask import Blueprint, jsonify

# Import will be done at runtime to avoid circular imports
api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/health')
def health():
    """
    Health check endpoint for Docker healthcheck.
    
    Returns:
        JSON with health status
    """
    from metrics import metrics
    return jsonify(metrics.get_health())


@api_bp.route('/status')
def status():
    """
    Get current stream status.
    
    Returns:
        JSON with stream engine status
    """
    from stream_engine import stream_engine
    return jsonify(stream_engine.status)


@api_bp.route('/metrics')
def get_metrics():
    """
    Get detailed metrics for dashboard.
    
    Returns:
        JSON with combined engine and Nginx metrics
    """
    from stream_engine import stream_engine
    from metrics import metrics
    
    engine_status = stream_engine.status
    return jsonify(metrics.get_stream_metrics(engine_status))


@api_bp.route('/playlist')
def get_playlist():
    """
    Get current playlist of videos.
    
    Returns:
        JSON with list of video files
    """
    from playlist_manager import playlist_manager
    
    files = playlist_manager.get_file_names()
    mode, _ = playlist_manager.get_current_target()
    
    return jsonify({
        "files": files,
        "count": len(files),
        "mode": mode
    })
