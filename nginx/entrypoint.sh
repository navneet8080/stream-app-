#!/bin/sh
# Nginx-RTMP entrypoint script
# Starts nginx directly (no env substitution needed since push is removed)

set -e

# Start nginx in foreground
exec nginx -g 'daemon off;'
