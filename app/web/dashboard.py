"""
Web Dashboard Routes
====================
Read-only dashboard for stream monitoring.

CRITICAL: No control buttons.
CRITICAL: No mutation endpoints.
This is an observer, not a controller.
"""

from flask import Blueprint, render_template

web_bp = Blueprint('web', __name__)


@web_bp.route('/')
def dashboard():
    """
    Main dashboard page.
    
    Displays:
    - Stream status (LIVE/IDLE)
    - Current video
    - FPS, bitrate
    - HLS preview
    - Uptime
    
    NO control buttons.
    """
    from stream_engine import stream_engine
    from playlist_manager import playlist_manager
    from metrics import metrics
    from config_loader import config
    
    # Get engine status
    engine_status = stream_engine.status
    
    # Get metrics
    stream_metrics = metrics.get_stream_metrics(engine_status)
    
    # Get playlist
    playlist = playlist_manager.get_file_names()
    
    return render_template(
        'dashboard.html',
        status=stream_metrics.get('status', 'UNKNOWN'),
        is_live=stream_metrics.get('is_live', False),
        current_file=stream_metrics.get('current_file', 'None'),
        mode=stream_metrics.get('mode', 'unknown'),
        resolution=stream_metrics.get('resolution', 'unknown'),
        fps=stream_metrics.get('fps', 0),
        bitrate_mbps=stream_metrics.get('bitrate_mbps', 0),
        uptime=stream_metrics.get('uptime', 'N/A'),
        restart_count=stream_metrics.get('restart_count', 0),
        nginx_up=stream_metrics.get('nginx_up', False),
        playlist=playlist,
        hls_url='/hls/stream.m3u8'
    )
