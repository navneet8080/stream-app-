"""
Metrics Module
==============
Collects and exposes streaming metrics for the dashboard.

Metrics include:
- Stream status (live/idle)
- Current video file
- FPS (from Nginx /stat)
- Bitrate
- Dropped frames
- FFmpeg uptime
- Restart count
"""

import time
import logging
import threading
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
from datetime import datetime
import urllib.request
import urllib.error

from config_loader import config

logger = logging.getLogger("Metrics")


class MetricsCollector:
    """
    Collects streaming metrics from multiple sources:
    - StreamEngine status
    - Nginx-RTMP /stat endpoint
    """
    
    def __init__(self):
        self._nginx_stat_url = "http://nginx-rtmp/stat"
        self._last_nginx_check: Optional[datetime] = None
        self._nginx_stats: Dict[str, Any] = {}
        self._lock = threading.Lock()
    
    def set_nginx_url(self, url: str):
        """Set the Nginx stat URL (for different environments)."""
        self._nginx_stat_url = url
    
    def _fetch_nginx_stats(self) -> Dict[str, Any]:
        """
        Fetch statistics from Nginx-RTMP /stat endpoint.
        
        Returns parsed statistics or empty dict on failure.
        """
        try:
            with urllib.request.urlopen(self._nginx_stat_url, timeout=5) as response:
                content = response.read().decode('utf-8')
            
            # Parse XML response
            root = ET.fromstring(content)
            
            stats = {
                "nginx_up": True,
                "uptime": None,
                "streams": [],
                "total_clients": 0
            }
            
            # Get server uptime
            uptime_elem = root.find(".//uptime")
            if uptime_elem is not None:
                stats["uptime"] = int(uptime_elem.text)
            
            # Get stream info
            for stream in root.findall(".//stream"):
                stream_info = {
                    "name": stream.findtext("name", "unknown"),
                    "time": int(stream.findtext("time", 0)),
                    "bw_in": int(stream.findtext("bw_in", 0)),
                    "bw_out": int(stream.findtext("bw_out", 0)),
                    "bytes_in": int(stream.findtext("bytes_in", 0)),
                    "bytes_out": int(stream.findtext("bytes_out", 0)),
                    "clients": int(stream.findtext("nclients", 0)),
                }
                
                # Get video info if available
                video = stream.find("meta/video")
                if video is not None:
                    stream_info["video"] = {
                        "width": int(video.findtext("width", 0)),
                        "height": int(video.findtext("height", 0)),
                        "frame_rate": float(video.findtext("frame_rate", 0)),
                        "codec": video.findtext("codec", "unknown")
                    }
                
                # Get audio info if available
                audio = stream.find("meta/audio")
                if audio is not None:
                    stream_info["audio"] = {
                        "sample_rate": int(audio.findtext("sample_rate", 0)),
                        "channels": int(audio.findtext("channels", 0)),
                        "codec": audio.findtext("codec", "unknown")
                    }
                
                stats["streams"].append(stream_info)
                stats["total_clients"] += stream_info["clients"]
            
            self._last_nginx_check = datetime.now()
            self._nginx_stats = stats
            return stats
            
        except urllib.error.URLError as e:
            logger.debug(f"Could not reach Nginx /stat: {e}")
            return {"nginx_up": False, "error": str(e)}
        except ET.ParseError as e:
            logger.warning(f"Could not parse Nginx /stat XML: {e}")
            return {"nginx_up": True, "parse_error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching Nginx stats: {e}")
            return {"nginx_up": False, "error": str(e)}
    
    def get_stream_metrics(self, engine_status: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get combined metrics from engine and Nginx.
        
        Args:
            engine_status: Status dict from StreamEngine
            
        Returns:
            Combined metrics dict for dashboard
        """
        with self._lock:
            # Fetch fresh Nginx stats
            nginx = self._fetch_nginx_stats()
            
            # Calculate display values
            stream_live = engine_status.get("running", False)
            current_stream = None
            fps = 0
            bitrate_kbps = 0
            
            if nginx.get("streams"):
                current_stream = nginx["streams"][0]
                if current_stream.get("video"):
                    fps = current_stream["video"].get("frame_rate", 0)
                # Convert bw_in from bits to kbps
                bitrate_kbps = current_stream.get("bw_in", 0) / 1000
            
            # Calculate uptime string
            uptime_str = "N/A"
            if engine_status.get("uptime_seconds"):
                seconds = int(engine_status["uptime_seconds"])
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                uptime_str = f"{hours:02d}:{minutes:02d}:{secs:02d}"
            
            return {
                # Stream status
                "status": "LIVE" if stream_live else "IDLE",
                "is_live": stream_live,
                "state": engine_status.get("state", "idle"),
                
                # Current file
                "current_file": engine_status.get("current_file", "None"),
                "mode": engine_status.get("mode", "unknown"),
                "resolution": engine_status.get("resolution", "unknown"),
                
                # Performance metrics
                "fps": round(fps, 1),
                "bitrate_kbps": round(bitrate_kbps, 1),
                "bitrate_mbps": round(bitrate_kbps / 1000, 2),
                
                # Health
                "restart_count": engine_status.get("restart_count", 0),
                "uptime": uptime_str,
                "uptime_seconds": engine_status.get("uptime_seconds", 0),
                "last_error": engine_status.get("last_error"),
                
                # Nginx status
                "nginx_up": nginx.get("nginx_up", False),
                "nginx_uptime": nginx.get("uptime"),
                "total_clients": nginx.get("total_clients", 0),
                
                # Relays
                "active_relays": engine_status.get("active_relays", 0),
                "total_destinations": engine_status.get("total_destinations", 0),
                
                # Process info
                "pid": engine_status.get("pid"),
                
                # Timestamp
                "timestamp": datetime.now().isoformat()
            }
    
    def get_health(self) -> Dict[str, Any]:
        """
        Get health check status for Docker healthcheck.
        
        Returns:
            Health status dict with overall status
        """
        nginx = self._fetch_nginx_stats()
        
        return {
            "status": "healthy" if nginx.get("nginx_up") else "degraded",
            "nginx": nginx.get("nginx_up", False),
            "timestamp": datetime.now().isoformat()
        }


# Global singleton instance
metrics = MetricsCollector()
