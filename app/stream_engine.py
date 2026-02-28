"""
Stream Engine – Database-Driven Broadcast Controller
=====================================================
Fault-tolerant 24×7 streaming engine.

Key design:
- LOCAL stream to Nginx is ALWAYS separate (never killed by external failures)
- External destinations run as independent FFmpeg processes
- Dynamic playlist reload via version checking
- Exponential backoff on failures
- Real-time status updates
"""

import subprocess
import threading
import time
import logging
import signal
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from config_loader import config
import database as db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("StreamEngine")

VIDEO_FOLDER = os.environ.get("VIDEO_FOLDER", "/app/output")


class StreamEngine:
    """
    Fault-tolerant FFmpeg streaming engine.
    
    Architecture:
    - One PRIMARY FFmpeg → Nginx (HLS preview) — always runs
    - Separate RELAY FFmpeg processes → external destinations — best-effort
    - If a relay fails, only that relay restarts, not the primary
    """

    def __init__(self):
        self._primary_proc: Optional[subprocess.Popen] = None
        self._relay_procs: Dict[int, subprocess.Popen] = {}  # dest_id → process
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()

        # Status (read by dashboard — must be fast, no locks)
        self._start_time: Optional[datetime] = None
        self._current_file: Optional[str] = None
        self._current_queue_id: Optional[int] = None
        self._restart_count: int = 0
        self._last_error: Optional[str] = None
        self._play_start_time: Optional[datetime] = None
        self._state: str = "idle"  # idle, playing, waiting, error

        # Dynamic reload
        self._known_version: int = 0

        # Backoff
        self._backoff: float = 2.0
        self._max_backoff: float = 60.0
        self._last_success: Optional[datetime] = None

        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info(f"Signal {signum} received, shutting down...")
        self.stop()
        sys.exit(0)

    # ─────────────── FFmpeg Commands ───────────────

    def _build_primary_cmd(self, input_file: str, loop_count: int = -1) -> List[str]:
        """Build FFmpeg command for LOCAL Nginx push only."""
        bitrate = config.get_bitrate()
        preset = config.stream_config.ffmpeg_preset
        resolution = config.stream_config.resolution
        scale = "1920:1080" if resolution == "1080p" else "1280:720"
        local_rtmp = config.stream_config.rtmp_ingest

        return [
            "ffmpeg", "-y",
            "-re",
            "-stream_loop", str(loop_count),
            "-i", input_file,
            "-c:v", "libx264",
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={scale}",
            "-b:v", bitrate.video,
            "-maxrate", bitrate.maxrate,
            "-bufsize", bitrate.bufsize,
            "-g", "60",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-f", "flv",
            local_rtmp
        ]

    def _start_relays(self):
        """Start relay FFmpeg processes for each enabled external destination."""
        self._stop_relays()

        destinations = db.get_enabled_destinations()
        if not destinations:
            return

        local_rtmp = config.stream_config.rtmp_ingest

        for dest in destinations:
            dest_url = dest["rtmp_url"]
            if dest["stream_key"]:
                dest_url = f"{dest_url}/{dest['stream_key']}"

            # Relay: read from local Nginx RTMP → push to external
            cmd = [
                "ffmpeg", "-y",
                "-rw_timeout", "5000000",
                "-i", local_rtmp,
                "-c", "copy",
                "-f", "flv",
                "-flvflags", "no_duration_filesize",
                dest_url
            ]

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                self._relay_procs[dest["id"]] = proc
                logger.info(f"  ⇨ Relay started → {dest['platform_name']} (PID {proc.pid})")
            except Exception as e:
                logger.warning(f"  ✗ Relay failed for {dest['platform_name']}: {e}")

    def _stop_relays(self):
        """Stop all relay processes."""
        for dest_id, proc in list(self._relay_procs.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._relay_procs.clear()

    def _check_relays(self):
        """Check relay health and restart any that died."""
        for dest_id, proc in list(self._relay_procs.items()):
            if proc.poll() is not None:
                logger.warning(f"  Relay {dest_id} died (exit {proc.returncode}), restarting...")
                del self._relay_procs[dest_id]

                # Restart this specific relay
                dest_info = None
                for d in db.get_enabled_destinations():
                    if d["id"] == dest_id:
                        dest_info = d
                        break

                if dest_info:
                    dest_url = dest_info["rtmp_url"]
                    if dest_info["stream_key"]:
                        dest_url = f"{dest_url}/{dest_info['stream_key']}"

                    local_rtmp = config.stream_config.rtmp_ingest
                    cmd = [
                        "ffmpeg", "-y",
                        "-rw_timeout", "5000000",
                        "-i", local_rtmp,
                        "-c", "copy",
                        "-f", "flv",
                        "-flvflags", "no_duration_filesize",
                        dest_url
                    ]

                    try:
                        new_proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            universal_newlines=True
                        )
                        self._relay_procs[dest_id] = new_proc
                        logger.info(f"  ⇨ Relay restarted → {dest_info['platform_name']} (PID {new_proc.pid})")
                    except Exception as e:
                        logger.warning(f"  ✗ Relay restart failed for {dest_info['platform_name']}: {e}")

    # ─────────────── Playback ───────────────

    def _play_video(self, filepath: str, loop_count: int = 0, max_duration: int = 0) -> bool:
        """
        Play a video via PRIMARY FFmpeg → Nginx.
        External relays run separately.

        Returns True if completed successfully.
        """
        cmd = self._build_primary_cmd(filepath, loop_count)
        logger.info(f"  FFmpeg: {len(cmd)} args → {config.stream_config.rtmp_ingest}")

        try:
            self._primary_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            self._play_start_time = datetime.now()
            self._state = "playing"
            logger.info(f"  Primary FFmpeg PID: {self._primary_proc.pid}")

            # Start external relays (best-effort, non-blocking)
            relay_thread = threading.Thread(target=self._start_relays, daemon=True)
            relay_thread.start()

            tick = 0
            while self._running and self._primary_proc.poll() is None:
                time.sleep(1)
                tick += 1

                # Check forced duration
                if max_duration > 0 and self._play_start_time:
                    elapsed = (datetime.now() - self._play_start_time).total_seconds()
                    if elapsed >= max_duration:
                        logger.info(f"  Force duration reached ({max_duration}s)")
                        self._kill_primary()
                        return True

                # Check relays every 15 seconds
                if tick % 15 == 0:
                    self._check_relays()

                # Check playlist version every 10 seconds
                if tick % 10 == 0:
                    new_ver = db.get_playlist_version()
                    if new_ver != self._known_version:
                        logger.info(f"  Playlist changed ({self._known_version}→{new_ver})")
                        self._known_version = new_ver

            # Check exit
            if self._primary_proc and self._primary_proc.returncode is not None:
                if self._primary_proc.returncode == 0 or not self._running:
                    return True
                else:
                    stderr = ""
                    try:
                        stderr = self._primary_proc.stderr.read()[-500:]
                    except Exception:
                        pass
                    self._last_error = stderr
                    logger.error(f"  FFmpeg exit code {self._primary_proc.returncode}: {stderr[:200]}")
                    return False

            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"  FFmpeg error: {e}")
            return False

    def _kill_primary(self):
        """Kill primary FFmpeg gracefully."""
        if self._primary_proc:
            try:
                self._primary_proc.terminate()
                self._primary_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._primary_proc.kill()
            except Exception:
                pass
            self._primary_proc = None

    # ─────────────── Main Loop ───────────────

    def _stream_loop(self):
        logger.info("=" * 60)
        logger.info("STREAM ENGINE STARTING – FAULT-TOLERANT MODE")
        logger.info("=" * 60)

        self._start_time = datetime.now()
        self._known_version = db.get_playlist_version()

        while self._running:
            # Get next queued item
            item = db.get_next_queued_item()

            if not item:
                queue = db.get_playlist_queue()
                done_items = [q for q in queue if q["status"] == "done"]

                if done_items:
                    logger.info("All items played. Resetting for continuous loop...")
                    db.reset_all_to_queued()
                    self._state = "waiting"
                    continue
                else:
                    self._state = "waiting"
                    self._current_file = None
                    time.sleep(5)
                    continue

            # Validate file
            video_file = os.path.join(VIDEO_FOLDER, item["filename"])
            if not os.path.exists(video_file):
                logger.error(f"  File not found: {video_file}")
                db.mark_done(item["id"])
                continue

            self._current_file = item["filename"]
            self._current_queue_id = item["id"]
            db.mark_playing(item["id"])

            logger.info(f"▶ {item['filename']} (repeat={item['repeat_count']}, force={item.get('force_duration_seconds',0)}s)")

            force_dur = item.get("force_duration_seconds", 0) or 0
            repeat = item.get("repeat_count", 1) or 1

            if force_dur > 0:
                success = self._play_video(video_file, loop_count=-1, max_duration=force_dur)
            else:
                success = self._play_video(video_file, loop_count=repeat - 1)

            # Stop relays between videos
            self._stop_relays()

            if success:
                db.mark_done(item["id"])
                self._backoff = 2.0
                self._last_success = datetime.now()
                logger.info(f"✓ Done: {item['filename']}")
            else:
                if self._running:
                    self._restart_count += 1
                    self._state = "error"
                    logger.error(f"✗ Failed: {item['filename']} (retry #{self._restart_count})")
                    time.sleep(self._backoff)
                    self._backoff = min(self._backoff * 2, self._max_backoff)

                    if self._last_success:
                        if (datetime.now() - self._last_success).total_seconds() > 300:
                            self._backoff = 2.0

                    db.mark_done(item["id"])

        self._stop_relays()
        self._state = "idle"
        logger.info("Stream engine stopped")

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._stream_loop, daemon=True)
            self._thread.start()
            logger.info("Stream engine thread started")

    def stop(self):
        with self._lock:
            self._running = False
            self._kill_primary()
            self._stop_relays()
            if self._thread:
                self._thread.join(timeout=10)
                self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running and self._primary_proc is not None and self._primary_proc.poll() is None

    @property
    def status(self) -> dict:
        uptime = None
        if self._start_time and self._running:
            uptime = (datetime.now() - self._start_time).total_seconds()

        elapsed = None
        if self._play_start_time and self.is_running:
            elapsed = (datetime.now() - self._play_start_time).total_seconds()

        active_relays = sum(1 for p in self._relay_procs.values() if p.poll() is None)

        return {
            "running": self.is_running,
            "state": self._state,
            "current_file": self._current_file,
            "current_queue_id": self._current_queue_id,
            "mode": "database",
            "resolution": config.stream_config.resolution,
            "restart_count": self._restart_count,
            "uptime_seconds": uptime,
            "elapsed_current_seconds": elapsed,
            "last_error": self._last_error,
            "pid": self._primary_proc.pid if self._primary_proc else None,
            "playlist_version": self._known_version,
            "active_relays": active_relays,
            "total_destinations": len(self._relay_procs)
        }


# Singleton
stream_engine = StreamEngine()


def start_engine():
    stream_engine.start()


if __name__ == "__main__":
    db.init_db()
    stream_engine.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stream_engine.stop()
