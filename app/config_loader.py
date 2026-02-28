"""
Config Loader
=============
Unified configuration management for the 24×7 Simulcast Engine.

Loads configuration from:
1. .env file (environment variables)
2. config/config.json (runtime settings)

Uses Pydantic for typed validation.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file from app root
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
# Also try parent for local development
load_dotenv(BASE_DIR.parent / ".env")


class BitrateConfig(BaseModel):
    """Bitrate settings for a resolution."""
    video: str = "4500k"
    maxrate: str = "5000k"
    bufsize: str = "10000k"


class YouTubeConfig(BaseModel):
    """YouTube integration settings."""
    enabled: bool = False
    push_via_nginx: bool = True


class StreamConfig(BaseModel):
    """Full streaming configuration from config.json."""
    stream_mode: str = "loop"  # "loop" or "newest"
    resolution: str = "1080p"  # "1080p" or "720p"
    video_folder: str = "/app/output"
    rtmp_ingest: str = "rtmp://nginx-rtmp:1935/live/stream"
    ffmpeg_preset: str = "veryfast"
    refresh_interval_seconds: int = 10
    bitrates: Dict[str, BitrateConfig] = Field(default_factory=lambda: {
        "1080p": BitrateConfig(video="4500k", maxrate="5000k", bufsize="10000k"),
        "720p": BitrateConfig(video="2500k", maxrate="3000k", bufsize="6000k")
    })
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)


class EnvSettings(BaseSettings):
    """Environment variables from .env file."""
    # App Settings
    SECRET_KEY: str = Field(default="change_this_to_secure_key")
    DEBUG: bool = Field(default=False)
    
    # RTMP Settings (can override config.json)
    RTMP_SERVER_URL: Optional[str] = Field(default=None)

    
    # Paths
    VIDEO_FOLDER: Optional[str] = Field(default=None)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class ConfigLoader:
    """
    Unified configuration loader.
    
    Singleton pattern ensures consistent config across the application.
    Supports runtime reload without restart.
    """
    _instance = None
    _config: Optional[StreamConfig] = None
    _env: Optional[EnvSettings] = None
    _config_path: Path = BASE_DIR / "config" / "config.json"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self.reload()
    
    def reload(self) -> None:
        """Reload configuration from files."""
        # Load environment variables
        self._env = EnvSettings()
        
        # Load JSON config
        if self._config_path.exists():
            try:
                with open(self._config_path, "r") as f:
                    data = json.load(f)
                # Parse bitrates correctly
                if "bitrates" in data:
                    data["bitrates"] = {
                        k: BitrateConfig(**v) for k, v in data["bitrates"].items()
                    }
                if "youtube" in data:
                    data["youtube"] = YouTubeConfig(**data["youtube"])
                self._config = StreamConfig(**data)
            except Exception as e:
                print(f"WARNING: Could not load config.json: {e}")
                self._config = StreamConfig()
        else:
            print(f"WARNING: Config file not found at {self._config_path}")
            self._config = StreamConfig()
        
        # Apply environment overrides
        if self._env.VIDEO_FOLDER:
            self._config.video_folder = self._env.VIDEO_FOLDER
        if self._env.RTMP_SERVER_URL:
            self._config.rtmp_ingest = self._env.RTMP_SERVER_URL
    
    @property
    def stream_config(self) -> StreamConfig:
        """Get the current stream configuration."""
        if self._config is None:
            self.reload()
        return self._config
    
    @property
    def env(self) -> EnvSettings:
        """Get environment settings."""
        if self._env is None:
            self.reload()
        return self._env
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by key (for backward compatibility)."""
        if hasattr(self._config, key):
            return getattr(self._config, key)
        return default
    
    def get_bitrate(self) -> BitrateConfig:
        """Get bitrate config for current resolution."""
        resolution = self._config.resolution
        return self._config.bitrates.get(resolution, self._config.bitrates["1080p"])
    
    def get_rtmp_url(self) -> str:
        """Get the full RTMP URL."""
        return self._config.rtmp_ingest


# Global singleton instance
config = ConfigLoader()
