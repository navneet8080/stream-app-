#!/usr/bin/env python3
"""
Entrypoint for Stream Engine Container
======================================
Initializes the database and starts the StreamEngine.
Dashboard container uses a different entrypoint (gunicorn).
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
    logger.info("24×7 BROADCAST CONTROL ENGINE STARTING")
    logger.info("=" * 60)

    # Initialize database
    import database as db
    db.init_db()
    logger.info("Database initialized")

    # Import and start the stream engine
    from stream_engine import stream_engine

    # Start the streaming engine
    logger.info("Starting stream engine (database-driven mode)...")
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
