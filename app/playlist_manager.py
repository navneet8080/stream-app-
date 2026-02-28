"""
Playlist Manager (Legacy Wrapper)
==================================
Thin wrapper around database.py for backward compatibility.
The stream engine now reads directly from the database.
"""

import os
import time
import logging
from pathlib import Path
from typing import List, Optional

import database as db

logger = logging.getLogger("PlaylistManager")

VIDEO_FOLDER = os.environ.get("VIDEO_FOLDER", "/app/output")


class PlaylistManager:
    """Legacy wrapper. Use database.py directly for new code."""

    def get_playlist_items(self) -> List[dict]:
        """Get playlist queue from database."""
        return db.get_playlist_queue()

    def get_file_names(self) -> List[str]:
        """Get filenames from the queue."""
        queue = db.get_playlist_queue()
        return [item["filename"] for item in queue]

    def wait_for_files(self, timeout: int = 60) -> bool:
        """Wait for at least one video file in output folder."""
        logger.info(f"Waiting for video files (timeout: {timeout}s)...")
        start = time.time()
        folder = Path(VIDEO_FOLDER)

        while time.time() - start < timeout:
            if folder.exists():
                files = list(folder.glob("*.mp4"))
                if files:
                    logger.info(f"Found {len(files)} video file(s)")
                    return True
            time.sleep(2)

        logger.warning("Timeout waiting for video files")
        return False


# Global singleton instance
playlist_manager = PlaylistManager()
