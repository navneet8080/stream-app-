"""
Stream Engine
=============
The heart of the 24×7 Simulcast Engine.

This module owns the FFmpeg subprocess and is responsible for:
- Running FFmpeg in an infinite loop
- Auto-restarting on crash
- Never blocking Flask
- Logging every restart and error

CRITICAL: This is NOT controlled by the UI.
The stream starts when the container starts and runs forever.
"""

import subprocess
import threading
import time
import logging
import signal
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from config_loader import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("StreamEngine")


class StreamEngine:
    """
    FFmpeg subprocess owner for 24×7 streaming.
    
    This class:
    - Owns exactly ONE FFmpeg subprocess
    - Runs in an infinite loop
    - Auto-restarts on crash
    - Never depends on Flask lifecycle
    - Logs every restart
    """
    
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()
        
        # Metrics
        self._start_time: Optional[datetime] = None
        self._current_file: Optional[str] = None
        self._restart_count: int = 0
        self._last_error: Optional[str] = None
        
        # Graceful shutdown handler
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown on SIGTERM/SIGINT."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.stop()
        sys.exit(0)
    
    def _get_video_files(self) -> List[Path]:
        """Get list of video files from the output folder."""
        video_folder = Path(config.stream_config.video_folder)
        if not video_folder.exists():
            logger.warning(f"Video folder does not exist: {video_folder}")
            return []
        
        # Get all MP4 files, sorted by modification time
        files = list(video_folder.glob("*.mp4"))
        files.sort(key=lambda f: f.stat().st_mtime)
        return files
    
    def _get_current_file(self) -> Optional[Path]:
        """Get the current file to stream based on mode."""
        files = self._get_video_files()
        if not files:
            return None
        
        mode = config.stream_config.stream_mode
        
        if mode == "newest":
            # Stream the most recently modified file
            return files[-1]
        elif mode == "loop":
            # Return first file, looping handled by FFmpeg
            return files[0]
        
        return files[0]
    
    def _build_ffmpeg_command(self, input_file: Path) -> List[str]:
        """Build the FFmpeg command with mandatory flags."""
        bitrate = config.get_bitrate()
        rtmp_url = config.get_rtmp_url()
        preset = config.stream_config.ffmpeg_preset
        
        # Resolution-based scaling
        resolution = config.stream_config.resolution
        scale = "1920:1080" if resolution == "1080p" else "1280:720"
        
        cmd = [
            "ffmpeg",
            # Real-time processing (MANDATORY)
            "-re",
            # Infinite loop (MANDATORY for 24×7)
            "-stream_loop", "-1",
            # Input file
            "-i", str(input_file),
            # Video codec settings (MANDATORY)
            "-c:v", "libx264",
            "-preset", preset,  # veryfast (MANDATORY)
            "-pix_fmt", "yuv420p",  # MANDATORY for compatibility
            # Scaling
            "-vf", f"scale={scale}",
            # Bitrate control
            "-b:v", bitrate.video,
            "-maxrate", bitrate.maxrate,
            "-bufsize", bitrate.bufsize,
            # Keyframe interval (2 seconds at 30fps)
            "-g", "60",
            # Audio codec settings
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            # Output format
            "-f", "flv",
            # RTMP destination (Nginx relay ONLY)
            rtmp_url
        ]
        
        return cmd
    
    def _stream_loop(self):
        """
        Main streaming loop.
        
        This runs in a separate thread and:
        - Starts FFmpeg
        - Monitors for crashes
        - Auto-restarts on failure
        - Never exits unless explicitly stopped
        """
        logger.info("=" * 60)
        logger.info("STREAM ENGINE STARTING - 24×7 MODE")
        logger.info("=" * 60)
        
        self._start_time = datetime.now()
        
        while self._running:
            # Get current file to stream
            input_file = self._get_current_file()
            
            if not input_file:
                logger.error("No video files found! Waiting 10s before retry...")
                time.sleep(10)
                continue
            
            self._current_file = input_file.name
            logger.info(f"Starting stream: {input_file.name}")
            logger.info(f"Mode: {config.stream_config.stream_mode}")
            logger.info(f"Resolution: {config.stream_config.resolution}")
            logger.info(f"RTMP Target: {config.get_rtmp_url()}")
            
            # Build and run FFmpeg command
            cmd = self._build_ffmpeg_command(input_file)
            logger.info(f"FFmpeg command: {' '.join(cmd)}")
            
            try:
                # Start FFmpeg subprocess
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                logger.info(f"FFmpeg started with PID: {self._process.pid}")
                
                # Monitor the process
                while self._running and self._process.poll() is None:
                    # Process is still running
                    time.sleep(1)
                
                # Check exit status
                if self._process.returncode is not None:
                    if self._running:
                        # Unexpected exit - log and restart
                        stderr = self._process.stderr.read() if self._process.stderr else ""
                        self._last_error = stderr[-500:] if len(stderr) > 500 else stderr
                        self._restart_count += 1
                        logger.error(f"FFmpeg exited with code {self._process.returncode}")
                        logger.error(f"Last error: {self._last_error}")
                        logger.info(f"Auto-restarting... (restart #{self._restart_count})")
                        time.sleep(2)  # Brief pause before restart
                    else:
                        # Graceful stop
                        logger.info("FFmpeg stopped gracefully")
                        
            except Exception as e:
                self._last_error = str(e)
                self._restart_count += 1
                logger.error(f"Stream error: {e}")
                logger.info(f"Restarting after error... (restart #{self._restart_count})")
                time.sleep(5)  # Longer pause after error
        
        logger.info("Stream engine stopped")
    
    def start(self):
        """Start the streaming engine in background thread."""
        with self._lock:
            if self._running:
                logger.warning("Stream engine already running")
                return
            
            self._running = True
            self._thread = threading.Thread(target=self._stream_loop, daemon=True)
            self._thread.start()
            logger.info("Stream engine thread started")
    
    def stop(self):
        """Stop the streaming engine gracefully."""
        with self._lock:
            self._running = False
            
            if self._process:
                logger.info("Stopping FFmpeg process...")
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg did not terminate, killing...")
                    self._process.kill()
                self._process = None
            
            if self._thread:
                self._thread.join(timeout=10)
                self._thread = None
    
    @property
    def is_running(self) -> bool:
        """Check if the engine is running."""
        return self._running and self._process is not None and self._process.poll() is None
    
    @property
    def status(self) -> dict:
        """Get current engine status for metrics."""
        uptime = None
        if self._start_time and self._running:
            uptime = (datetime.now() - self._start_time).total_seconds()
        
        return {
            "running": self.is_running,
            "current_file": self._current_file,
            "mode": config.stream_config.stream_mode,
            "resolution": config.stream_config.resolution,
            "restart_count": self._restart_count,
            "uptime_seconds": uptime,
            "last_error": self._last_error,
            "pid": self._process.pid if self._process else None
        }


# Global singleton instance
stream_engine = StreamEngine()


def start_engine():
    """Auto-start function called when module loads in production."""
    stream_engine.start()


# Auto-start if running as main module (for testing)
if __name__ == "__main__":
    print("Starting Stream Engine (standalone mode)...")
    stream_engine.start()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        stream_engine.stop()
