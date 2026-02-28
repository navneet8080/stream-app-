"""
API Routes – Broadcast Control System
======================================
Full CRUD REST API for the editor-controlled broadcast system.

Endpoints:
- Video management (upload, list, delete)
- Playlist queue (add, reorder, update, remove)
- Stream destinations (CRUD)
- Status & health
"""

import os
import subprocess
import logging
import traceback
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

import database as db
from config_loader import config

logger = logging.getLogger("API")

api_bp = Blueprint('api', __name__, url_prefix='/api')

ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov', 'webm'}
VIDEO_FOLDER = os.environ.get("VIDEO_FOLDER", "/app/output")


def _allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_video_duration(filepath: str) -> float:
    """Extract video duration using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath
            ],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            logger.warning(f"ffprobe failed for {filepath}: {result.stderr}")
            return 0.0
        duration = float(result.stdout.strip())
        return round(duration, 2)
    except ValueError:
        logger.warning(f"Could not parse duration for {filepath}")
        return 0.0
    except FileNotFoundError:
        logger.warning("ffprobe not found — cannot extract duration")
        return 0.0
    except Exception as e:
        logger.warning(f"Could not extract duration for {filepath}: {e}")
        return 0.0


# ─────────────────── Error Handler ───────────────────

@api_bp.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large"}), 413


@api_bp.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error", "detail": str(e)}), 500


@api_bp.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {traceback.format_exc()}")
    return jsonify({"error": str(e)}), 500


# ─────────────────── Health ───────────────────

@api_bp.route('/health')
def health():
    """Docker healthcheck endpoint."""
    from metrics import metrics
    return jsonify(metrics.get_health())


# ─────────────────── Videos ───────────────────

@api_bp.route('/videos', methods=['GET'])
def list_videos():
    """List all uploaded videos with metadata."""
    try:
        videos = db.get_all_videos()
        return jsonify({"videos": videos, "count": len(videos)})
    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        return jsonify({"error": f"Failed to list videos: {str(e)}"}), 500


@api_bp.route('/upload', methods=['POST'])
def upload_video():
    """Upload a video file → save to output/ → extract duration → store in DB."""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided. Use form field name 'file'."}), 400

        file = request.files['file']
        if file.filename == '' or file.filename is None:
            return jsonify({"error": "No filename in upload"}), 400

        if not _allowed_file(file.filename):
            return jsonify({
                "error": f"File type not allowed: {file.filename}",
                "allowed": list(ALLOWED_EXTENSIONS)
            }), 400

        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({"error": "Invalid filename after sanitization"}), 400

        filepath = os.path.join(VIDEO_FOLDER, filename)

        # Handle duplicate filenames
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{ext}"
            filepath = os.path.join(VIDEO_FOLDER, filename)
            counter += 1

        # Save file
        os.makedirs(VIDEO_FOLDER, exist_ok=True)
        logger.info(f"Saving upload: {filename} to {filepath}")
        file.save(filepath)

        # Get file size
        file_size = os.path.getsize(filepath)
        logger.info(f"Saved: {filename} ({file_size} bytes)")

        # Extract duration via ffprobe
        duration = _get_video_duration(filepath)

        # Store in database
        video_id = db.add_video(filename, duration, file_size)

        logger.info(f"Upload complete: {filename} ({duration}s, {file_size} bytes, id={video_id})")

        return jsonify({
            "id": video_id,
            "filename": filename,
            "duration_seconds": duration,
            "file_size_bytes": file_size
        }), 201

    except Exception as e:
        logger.error(f"Upload failed: {traceback.format_exc()}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@api_bp.route('/videos/<int:video_id>', methods=['DELETE'])
def delete_video(video_id):
    """Delete a video file and its DB record."""
    try:
        video = db.get_video_by_id(video_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Delete the file
        filepath = os.path.join(VIDEO_FOLDER, video["filename"])
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Deleted file: {filepath}")
        except Exception as e:
            logger.warning(f"Could not delete file {filepath}: {e}")

        # Delete from DB (cascades to queue)
        db.delete_video(video_id)

        return jsonify({"message": f"Deleted {video['filename']}"})
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        return jsonify({"error": f"Delete failed: {str(e)}"}), 500


# ─────────────────── Playlist Queue ───────────────────

@api_bp.route('/playlist', methods=['GET'])
def get_playlist():
    """Get full playlist queue with video details and calculated durations."""
    try:
        queue = db.get_playlist_queue()
        total_seconds = sum(item.get("total_play_seconds", 0) for item in queue)

        return jsonify({
            "queue": queue,
            "count": len(queue),
            "total_seconds": round(total_seconds, 2),
            "total_display": _format_duration(total_seconds),
            "version": db.get_playlist_version()
        })
    except Exception as e:
        logger.error(f"Error getting playlist: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/playlist/add', methods=['POST'])
def add_to_playlist():
    """Add a video to the playlist queue."""
    try:
        data = request.get_json()
        if not data or "video_id" not in data:
            return jsonify({"error": "video_id required"}), 400

        video = db.get_video_by_id(data["video_id"])
        if not video:
            return jsonify({"error": "Video not found"}), 404

        repeat_count = data.get("repeat_count", 1)
        force_duration = data.get("force_duration_seconds", 0)

        queue_id = db.add_to_queue(data["video_id"], repeat_count, force_duration)
        return jsonify({"id": queue_id, "message": "Added to playlist"}), 201
    except Exception as e:
        logger.error(f"Error adding to playlist: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/playlist/reorder', methods=['PUT'])
def reorder_playlist():
    """Reorder playlist items. Body: {"item_ids": [3,1,2]}."""
    try:
        data = request.get_json()
        if not data or "item_ids" not in data:
            return jsonify({"error": "item_ids array required"}), 400

        db.reorder_queue(data["item_ids"])
        return jsonify({"message": "Playlist reordered"})
    except Exception as e:
        logger.error(f"Error reordering: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/playlist/update/<int:queue_id>', methods=['PUT'])
def update_playlist_item(queue_id):
    """Update repeat_count and/or force_duration_seconds for a queue item."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        success = db.update_queue_item(
            queue_id,
            repeat_count=data.get("repeat_count"),
            force_duration_seconds=data.get("force_duration_seconds")
        )

        if success:
            return jsonify({"message": "Updated"})
        return jsonify({"error": "Item not found or no changes"}), 404
    except Exception as e:
        logger.error(f"Error updating queue item: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/playlist/remove/<int:queue_id>', methods=['DELETE'])
def remove_from_playlist(queue_id):
    """Remove an item from the playlist queue."""
    try:
        if db.remove_from_queue(queue_id):
            return jsonify({"message": "Removed from playlist"})
        return jsonify({"error": "Item not found"}), 404
    except Exception as e:
        logger.error(f"Error removing from queue: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/playlist/clear', methods=['POST'])
def clear_playlist():
    """Clear all items from the playlist queue."""
    try:
        db.clear_queue()
        return jsonify({"message": "Playlist cleared"})
    except Exception as e:
        logger.error(f"Error clearing playlist: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────── Destinations ───────────────────

@api_bp.route('/destinations', methods=['GET'])
def list_destinations():
    """List all streaming destinations."""
    try:
        destinations = db.get_all_destinations()
        return jsonify({"destinations": destinations, "count": len(destinations)})
    except Exception as e:
        logger.error(f"Error listing destinations: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/destinations', methods=['POST'])
def add_destination():
    """Add a new streaming destination (just URL + key, like OBS)."""
    try:
        data = request.get_json()
        if not data or "platform_name" not in data or "rtmp_url" not in data:
            return jsonify({"error": "platform_name and rtmp_url required"}), 400

        dest_id = db.add_destination(
            platform_name=data["platform_name"],
            rtmp_url=data["rtmp_url"],
            stream_key=data.get("stream_key", ""),
            is_enabled=data.get("is_enabled", True)
        )

        return jsonify({"id": dest_id, "message": "Destination added"}), 201
    except Exception as e:
        logger.error(f"Error adding destination: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/destinations/<int:dest_id>', methods=['PUT'])
def update_destination(dest_id):
    """Update a streaming destination."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        success = db.update_destination(dest_id, **data)
        if success:
            return jsonify({"message": "Destination updated"})
        return jsonify({"error": "Destination not found or no changes"}), 404
    except Exception as e:
        logger.error(f"Error updating destination: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/destinations/<int:dest_id>', methods=['DELETE'])
def delete_destination(dest_id):
    """Delete a streaming destination."""
    try:
        if db.delete_destination(dest_id):
            return jsonify({"message": "Destination deleted"})
        return jsonify({"error": "Destination not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting destination: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────── Status ───────────────────

@api_bp.route('/status')
def get_status():
    """Get live broadcast status. Works with or without stream engine."""
    try:
        from metrics import metrics

        # Try to get engine status (only works in engine container)
        engine_status = {}
        try:
            from stream_engine import stream_engine
            engine_status = stream_engine.status
        except Exception:
            pass

        stream_metrics = metrics.get_stream_metrics(engine_status)

        currently_playing = db.get_currently_playing()
        upcoming = db.get_upcoming_items(5)
        total_scheduled = db.get_total_scheduled_seconds()

        return jsonify({
            "stream": stream_metrics,
            "currently_playing": currently_playing,
            "upcoming": upcoming,
            "total_scheduled_seconds": round(total_scheduled, 2),
            "total_scheduled_display": _format_duration(total_scheduled),
            "playlist_version": db.get_playlist_version()
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/metrics')
def get_metrics():
    """Get detailed metrics for dashboard."""
    try:
        from stream_engine import stream_engine
        from metrics import metrics

        engine_status = stream_engine.status
        return jsonify(metrics.get_stream_metrics(engine_status))
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────── Helpers ───────────────────

def _format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS display string."""
    if seconds <= 0:
        return "00:00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
