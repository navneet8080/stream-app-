#!/usr/bin/env python3
"""
Entrypoint for Stream Engine Container
======================================
This is the main entrypoint for the stream-engine container.
It starts the StreamEngine and keeps the container alive.

CRITICAL: The dashboard container uses a different entrypoint (gunicorn).
"""

import sys
import time
import logging
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Entrypoint")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("24×7 SIMULCAST ENGINE STARTING")
    logger.info("=" * 60)
    
    # Import and start the stream engine
    from stream_engine import stream_engine
    from playlist_manager import playlist_manager
    
    # Wait for video files
    logger.info("Checking for video files...")
    if not playlist_manager.wait_for_files(timeout=60):
        logger.error("No video files found after 60s. Engine will retry...")
    
    # Start the streaming engine
    logger.info("Starting stream engine...")
    stream_engine.start()
    
    # Keep container alive
    logger.info("Stream engine running. Container will stay alive.")
    
    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received")
        stream_engine.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        stream_engine.stop()


if __name__ == "__main__":
    main()
