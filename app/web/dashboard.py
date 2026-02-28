"""
Web Dashboard Routes
====================
Serves the single-page Broadcast Control Dashboard.
All data is loaded via API fetch calls from the frontend.
Includes HLS proxy to forward /hls/* requests to Nginx.
"""

import os
import urllib.request
import urllib.error
from flask import Blueprint, render_template, Response

web_bp = Blueprint('web', __name__)

# Nginx URL inside Docker network
NGINX_URL = os.environ.get("NGINX_STAT_URL", "http://nginx-rtmp").rsplit("/", 1)[0]
# Fallback: http://nginx-rtmp


@web_bp.route('/')
def dashboard():
    """Serve the broadcast control dashboard."""
    return render_template('dashboard.html')


@web_bp.route('/hls/<path:filename>')
def hls_proxy(filename):
    """
    Proxy HLS requests to Nginx-RTMP server.
    
    The dashboard runs on port 8080 but Nginx serves HLS on port 80.
    This proxy lets the dashboard JS fetch /hls/* from its own origin,
    avoiding cross-origin issues.
    """
    nginx_hls_url = f"{NGINX_URL}/hls/{filename}"
    
    try:
        req = urllib.request.Request(nginx_hls_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
            content_type = resp.headers.get('Content-Type', 'application/octet-stream')
            
            # Set correct MIME types for HLS
            if filename.endswith('.m3u8'):
                content_type = 'application/vnd.apple.mpegurl'
            elif filename.endswith('.ts'):
                content_type = 'video/mp2t'
            
            return Response(
                data,
                status=200,
                content_type=content_type,
                headers={
                    'Cache-Control': 'no-cache, no-store',
                    'Access-Control-Allow-Origin': '*'
                }
            )
    except urllib.error.HTTPError as e:
        return Response(f"HLS not available: {e.code}", status=e.code)
    except urllib.error.URLError:
        return Response("Nginx not reachable", status=502)
    except Exception as e:
        return Response(f"HLS proxy error: {str(e)}", status=500)
