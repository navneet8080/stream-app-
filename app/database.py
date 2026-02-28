"""
Database Layer – Optimized for Concurrent Access
=================================================
Connection-per-request pattern with WAL mode for
concurrent reads during streaming + dashboard usage.
"""

import sqlite3
import threading
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Database")

DB_PATH = os.environ.get("DB_PATH", "/app/data/broadcast.db")

_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Get a thread-local database connection (reused within same thread)."""
    conn = getattr(_local, 'conn', None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return conn


def init_db():
    """Create tables on first run."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            duration_seconds REAL DEFAULT 0,
            file_size_bytes INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS playlist_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            repeat_count INTEGER NOT NULL DEFAULT 1,
            force_duration_seconds INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS playlist_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS stream_destinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_name TEXT NOT NULL,
            rtmp_url TEXT NOT NULL,
            stream_key TEXT NOT NULL DEFAULT '',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO playlist_version (id, version) VALUES (1, 1);
    """)
    conn.commit()
    logger.info(f"Database initialized at {DB_PATH}")


def bump_playlist_version():
    conn = get_db()
    conn.execute("UPDATE playlist_version SET version = version + 1, updated_at = datetime('now') WHERE id = 1")
    conn.commit()


def get_playlist_version() -> int:
    row = get_db().execute("SELECT version FROM playlist_version WHERE id = 1").fetchone()
    return row["version"] if row else 0


# ──── Video CRUD ────

def add_video(filename: str, duration_seconds: float = 0, file_size_bytes: int = 0) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO videos (filename, duration_seconds, file_size_bytes) VALUES (?, ?, ?)",
        (filename, duration_seconds, file_size_bytes)
    )
    conn.commit()
    return cur.lastrowid


def get_all_videos() -> List[Dict[str, Any]]:
    rows = get_db().execute(
        "SELECT id, filename, duration_seconds, file_size_bytes, created_at FROM videos ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_video_by_id(video_id: int) -> Optional[Dict[str, Any]]:
    row = get_db().execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    return dict(row) if row else None


def delete_video(video_id: int) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    if cur.rowcount > 0:
        bump_playlist_version()
        return True
    return False


# ──── Playlist Queue CRUD ────

def add_to_queue(video_id: int, repeat_count: int = 1, force_duration_seconds: int = 0) -> int:
    conn = get_db()
    row = conn.execute("SELECT COALESCE(MAX(position), 0) as mp FROM playlist_queue").fetchone()
    cur = conn.execute(
        "INSERT INTO playlist_queue (video_id, position, repeat_count, force_duration_seconds) VALUES (?, ?, ?, ?)",
        (video_id, row["mp"] + 1, repeat_count, force_duration_seconds)
    )
    conn.commit()
    bump_playlist_version()
    return cur.lastrowid


def get_playlist_queue() -> List[Dict[str, Any]]:
    rows = get_db().execute("""
        SELECT pq.id, pq.video_id, pq.position, pq.repeat_count,
               pq.force_duration_seconds, pq.status,
               v.filename, v.duration_seconds, v.file_size_bytes
        FROM playlist_queue pq
        JOIN videos v ON pq.video_id = v.id
        ORDER BY pq.position ASC
    """).fetchall()

    result = []
    for r in rows:
        item = dict(r)
        fd = item["force_duration_seconds"] or 0
        if fd > 0:
            item["total_play_seconds"] = fd
        else:
            item["total_play_seconds"] = item["duration_seconds"] * item["repeat_count"]
        result.append(item)
    return result


def get_next_queued_item() -> Optional[Dict[str, Any]]:
    row = get_db().execute("""
        SELECT pq.id, pq.video_id, pq.position, pq.repeat_count,
               pq.force_duration_seconds, pq.status,
               v.filename, v.duration_seconds
        FROM playlist_queue pq
        JOIN videos v ON pq.video_id = v.id
        WHERE pq.status = 'queued'
        ORDER BY pq.position ASC LIMIT 1
    """).fetchone()
    return dict(row) if row else None


def mark_playing(queue_id: int):
    conn = get_db()
    conn.execute("UPDATE playlist_queue SET status = 'playing' WHERE id = ?", (queue_id,))
    conn.commit()


def mark_done(queue_id: int):
    conn = get_db()
    conn.execute("UPDATE playlist_queue SET status = 'done' WHERE id = ?", (queue_id,))
    conn.commit()


def reset_all_to_queued():
    conn = get_db()
    conn.execute("UPDATE playlist_queue SET status = 'queued' WHERE status = 'done'")
    conn.commit()


def update_queue_item(queue_id: int, repeat_count=None, force_duration_seconds=None) -> bool:
    updates, params = [], []
    if repeat_count is not None:
        updates.append("repeat_count = ?")
        params.append(repeat_count)
    if force_duration_seconds is not None:
        updates.append("force_duration_seconds = ?")
        params.append(force_duration_seconds)
    if not updates:
        return False
    params.append(queue_id)
    conn = get_db()
    cur = conn.execute(f"UPDATE playlist_queue SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    if cur.rowcount > 0:
        bump_playlist_version()
        return True
    return False


def reorder_queue(item_ids: List[int]) -> bool:
    conn = get_db()
    for pos, item_id in enumerate(item_ids, start=1):
        conn.execute("UPDATE playlist_queue SET position = ? WHERE id = ?", (pos, item_id))
    conn.commit()
    bump_playlist_version()
    return True


def remove_from_queue(queue_id: int) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM playlist_queue WHERE id = ?", (queue_id,))
    conn.commit()
    if cur.rowcount > 0:
        bump_playlist_version()
        return True
    return False


def clear_queue():
    conn = get_db()
    conn.execute("DELETE FROM playlist_queue")
    conn.commit()
    bump_playlist_version()


# ──── Destinations CRUD ────

def add_destination(platform_name: str, rtmp_url: str, stream_key: str = "", is_enabled: bool = True) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO stream_destinations (platform_name, rtmp_url, stream_key, is_enabled) VALUES (?, ?, ?, ?)",
        (platform_name, rtmp_url, stream_key, 1 if is_enabled else 0)
    )
    conn.commit()
    return cur.lastrowid


def get_all_destinations() -> List[Dict[str, Any]]:
    rows = get_db().execute(
        "SELECT id, platform_name, rtmp_url, stream_key, is_enabled, created_at FROM stream_destinations ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_enabled_destinations() -> List[Dict[str, Any]]:
    rows = get_db().execute(
        "SELECT id, platform_name, rtmp_url, stream_key FROM stream_destinations WHERE is_enabled = 1"
    ).fetchall()
    return [dict(r) for r in rows]


def update_destination(dest_id: int, **kwargs) -> bool:
    allowed = {"platform_name", "rtmp_url", "stream_key", "is_enabled"}
    updates, params = [], []
    for k, v in kwargs.items():
        if k in allowed:
            updates.append(f"{k} = ?")
            params.append(v)
    if not updates:
        return False
    params.append(dest_id)
    conn = get_db()
    cur = conn.execute(f"UPDATE stream_destinations SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    return cur.rowcount > 0


def delete_destination(dest_id: int) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM stream_destinations WHERE id = ?", (dest_id,))
    conn.commit()
    return cur.rowcount > 0


# ──── Status Helpers ────

def get_currently_playing() -> Optional[Dict[str, Any]]:
    row = get_db().execute("""
        SELECT pq.id, pq.video_id, pq.position, pq.repeat_count,
               pq.force_duration_seconds, pq.status,
               v.filename, v.duration_seconds
        FROM playlist_queue pq
        JOIN videos v ON pq.video_id = v.id
        WHERE pq.status = 'playing' LIMIT 1
    """).fetchone()
    return dict(row) if row else None


def get_upcoming_items(limit: int = 5) -> List[Dict[str, Any]]:
    rows = get_db().execute("""
        SELECT pq.id, pq.video_id, pq.position, pq.repeat_count,
               pq.force_duration_seconds,
               v.filename, v.duration_seconds
        FROM playlist_queue pq
        JOIN videos v ON pq.video_id = v.id
        WHERE pq.status = 'queued'
        ORDER BY pq.position ASC LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_total_scheduled_seconds() -> float:
    rows = get_db().execute("""
        SELECT pq.repeat_count, pq.force_duration_seconds, v.duration_seconds
        FROM playlist_queue pq
        JOIN videos v ON pq.video_id = v.id
        WHERE pq.status IN ('queued', 'playing')
    """).fetchall()
    total = 0.0
    for r in rows:
        fd = r["force_duration_seconds"] or 0
        total += fd if fd > 0 else r["duration_seconds"] * r["repeat_count"]
    return total
