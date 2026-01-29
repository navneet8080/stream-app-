"""
Playlist Manager
================
Manages the video playlist for 24×7 streaming.

Supports two modes:
- loop: Play all videos in sequence, repeat forever
- newest: Always play the most recently modified file

Ported from simulcast-engine/app/services/playlist_manager.py
with enhancements for file lock safety and zero-downtime switching.
"""

import os
import time
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

from config_loader import config

logger = logging.getLogger("PlaylistManager")


class PlaylistManager:
    """
    Manages video playlist for the streaming engine.
    
    Responsible for:
    - Listing available videos
    - Determining which file to play based on mode
    - Creating FFmpeg concat playlists
    - Detecting new files
    """
    
    def __init__(self):
        self._last_scan: Optional[datetime] = None
        self._cached_files: List[Path] = []
    
    def _get_video_folder(self) -> Path:
        """Get the video folder path."""
        return Path(config.stream_config.video_folder)
    
    def get_playlist_items(self) -> List[Path]:
        """
        Get list of all video files in the output folder.
        
        Returns:
            List of Path objects for each MP4 file, sorted by modification time.
        """
        video_folder = self._get_video_folder()
        
        if not video_folder.exists():
            logger.warning(f"Video folder does not exist: {video_folder}")
            # Try to create it
            try:
                video_folder.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created video folder: {video_folder}")
            except Exception as e:
                logger.error(f"Could not create video folder: {e}")
            return []
        
        # Find all MP4 files
        files = list(video_folder.glob("*.mp4"))
        
        if not files:
            logger.warning("No MP4 files found in video folder")
            return []
        
        # Sort by modification time (oldest first)
        files.sort(key=lambda f: f.stat().st_mtime)
        
        # Cache for quick access
        self._cached_files = files
        self._last_scan = datetime.now()
        
        return files
    
    def get_newest_file(self) -> Optional[Path]:
        """Get the most recently modified video file."""
        files = self.get_playlist_items()
        return files[-1] if files else None
    
    def get_oldest_file(self) -> Optional[Path]:
        """Get the oldest video file."""
        files = self.get_playlist_items()
        return files[0] if files else None
    
    def get_current_target(self) -> Tuple[Optional[str], Optional[any]]:
        """
        Determine which file(s) to play based on mode.
        
        Returns:
            Tuple of (mode, target) where:
            - For "newest" mode: (mode, single file path)
            - For "loop" mode: (mode, list of file paths)
        """
        mode = config.stream_config.stream_mode
        files = self.get_playlist_items()
        
        if not files:
            return None, None
        
        if mode == "newest":
            # Return the newest (most recently modified) file
            return "newest", files[-1]
        
        elif mode == "loop":
            # Return all files for looping
            return "loop", files
        
        return None, None
    
    def create_concat_playlist(self, output_path: str = "/tmp/playlist.txt") -> Optional[str]:
        """
        Create an FFmpeg concat playlist file.
        
        This is used for loop mode to play all files in sequence.
        
        Args:
            output_path: Where to write the playlist file
            
        Returns:
            Path to the created playlist file, or None if no files
        """
        files = self.get_playlist_items()
        
        if not files:
            return None
        
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                for video_file in files:
                    # FFmpeg concat requires forward slashes and proper escaping
                    safe_path = str(video_file.absolute()).replace("\\", "/")
                    # Escape single quotes in filename
                    safe_path = safe_path.replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
            
            logger.info(f"Created concat playlist: {output_path} ({len(files)} files)")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to create concat playlist: {e}")
            return None
    
    def has_new_files(self) -> bool:
        """
        Check if new files have been added since last scan.
        
        Useful for triggering playlist refresh.
        """
        old_count = len(self._cached_files)
        new_files = self.get_playlist_items()
        return len(new_files) > old_count
    
    def get_file_names(self) -> List[str]:
        """Get just the filenames (not full paths) for display."""
        return [f.name for f in self.get_playlist_items()]
    
    def wait_for_files(self, timeout: int = 60) -> bool:
        """
        Wait for at least one video file to appear.
        
        Args:
            timeout: Maximum seconds to wait
            
        Returns:
            True if files found, False if timeout
        """
        logger.info(f"Waiting for video files (timeout: {timeout}s)...")
        start = time.time()
        
        while time.time() - start < timeout:
            files = self.get_playlist_items()
            if files:
                logger.info(f"Found {len(files)} video file(s)")
                return True
            time.sleep(2)
        
        logger.error("Timeout waiting for video files")
        return False


# Global singleton instance
playlist_manager = PlaylistManager()
