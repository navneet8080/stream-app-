import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Settings
    SECRET_KEY: str = "dev_secret_key"
    
    # Paths
    VIDEO_FOLDER: str = "/app/videos"
    
    # RTMP
    RTMP_SERVER_URL: str = "rtmp://nginx-rtmp:1935/live"
    RTMP_STREAM_KEY: str = "stream"
    
    # YouTube
    GOOGLE_CLIENT_SECRETS_FILE: str = "/app/client_secrets.json"
    YOUTUBE_REDIRECT_URI: str = "http://localhost:8080/youtube/callback"
    
    # Flags
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()

# Ensure video folder exists
if not os.path.exists(settings.VIDEO_FOLDER):
    try:
        os.makedirs(settings.VIDEO_FOLDER)
    except OSError:
        print(f"Warning: Could not create {settings.VIDEO_FOLDER}")
