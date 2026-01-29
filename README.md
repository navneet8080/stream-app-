# 24×7 Simulcast Engine

Industrial-grade 24×7 live streaming engine for YouTube and other RTMP platforms.

## Architecture

```
┌─────────────────┐
│   output/*.mp4  │  Video files
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Stream Engine  │  FFmpeg (24×7 loop)
│  - loop mode    │
│  - newest mode  │
└────────┬────────┘
         │ RTMP
         ▼
┌─────────────────┐
│   Nginx-RTMP    │  Relay server
│  - HLS output   │
│  - /stat        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  YouTube Live   │  Final destination
│  (rtmp push)    │
└─────────────────┘
```

## Quick Start

### 1. Prerequisites

- Docker Desktop installed and running
- Python 3.8+ (for OAuth CLI tool)
- YouTube channel with live streaming enabled

### 2. YouTube OAuth Setup (ONE TIME)

**⚠️ IMPORTANT: Run this BEFORE starting Docker containers!**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create/select a project
3. Enable **YouTube Data API v3**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Select **Desktop application**
6. Download the JSON file
7. Save as `secrets/client_secrets.json`

Then run:

```bash
pip install google-auth-oauthlib google-api-python-client
python tools/youtube_auth_cli.py
```

This will:
- Open a browser for Google login
- Save token to `secrets/token.json`
- Verify the token works

### 3. Add Videos

Place your MP4 files in the `output/` folder:

```
output/
├── video1.mp4
├── video2.mp4
└── video3.mp4
```

### 4. Configure YouTube Push (Optional)

To push directly to YouTube, add your stream key to `.env`:

```env
YOUTUBE_STREAM_KEY=xxxx-xxxx-xxxx-xxxx-xxxx
```

Then uncomment the push line in `nginx/nginx.conf`:

```nginx
push rtmp://x.rtmp.youtube.com/live2/${YOUTUBE_STREAM_KEY};
```

### 5. Start the Engine

```bash
docker compose up -d
```

That's it! The stream will start automatically and run 24×7.

### 6. Monitor

- **Dashboard**: http://localhost:8000
- **HLS Preview**: http://localhost/hls/stream.m3u8
- **Nginx Stats**: http://localhost/stat

## Services

| Service | Port | Purpose |
|---------|------|---------|
| `stream-engine` | - | FFmpeg 24×7 loop |
| `nginx-rtmp` | 1935, 80 | RTMP relay + HLS |
| `web-dashboard` | 8000 | Read-only monitoring |

## Configuration

### Stream Mode

Edit `config/config.json`:

```json
{
    "stream_mode": "loop",     // "loop" or "newest"
    "resolution": "1080p"      // "1080p" or "720p"
}
```

- **loop**: Play all videos in sequence, repeat forever
- **newest**: Always play the most recently modified file

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STREAM_MODE` | loop | loop or newest |
| `RESOLUTION` | 1080p | 1080p or 720p |
| `RTMP_SERVER_URL` | rtmp://nginx-rtmp:1935/live/stream | Internal RTMP |
| `YOUTUBE_STREAM_KEY` | - | YouTube stream key |

## Commands

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f stream-engine

# Stop all services
docker compose down

# Rebuild after code changes
docker compose up -d --build

# Check health
docker compose ps
```

## Dashboard Features

The read-only dashboard shows:

- ✅ Stream status (LIVE/IDLE)
- ✅ Current video filename
- ✅ FPS
- ✅ Bitrate (Mbps)
- ✅ Uptime
- ✅ HLS preview
- ✅ Video queue

**Note**: Dashboard is observer-only. Stream control is automatic.

## Troubleshooting

### No video files found

Make sure videos are in `output/` folder with `.mp4` extension.

### OAuth error

1. Delete `secrets/token.json`
2. Run `python tools/youtube_auth_cli.py` again
3. Make sure `client_secrets.json` is **Desktop application** type

### FFmpeg keeps restarting

Check logs: `docker compose logs -f stream-engine`

Common causes:
- Invalid video file
- Nginx not ready (wait a few seconds)
- Wrong RTMP URL

### HLS preview not working

1. Check Nginx is running: `docker compose ps`
2. Wait 10-15 seconds for first HLS segment
3. Check CORS: Browser console for errors

## Project Structure

```
stream_nns/
├── app/
│   ├── main.py              # Flask app factory
│   ├── stream_engine.py     # FFmpeg 24×7 loop
│   ├── playlist_manager.py  # Video queue
│   ├── config_loader.py     # Configuration
│   ├── metrics.py           # Monitoring
│   ├── api/                  # Read-only API
│   └── web/                  # Dashboard
├── nginx/
│   └── nginx.conf           # RTMP + HLS
├── tools/
│   └── youtube_auth_cli.py  # OAuth CLI
├── output/                   # Video files
├── secrets/                  # OAuth tokens
├── config/                   # Runtime config
└── docker-compose.yml
```

## License

Proprietary - All rights reserved.
