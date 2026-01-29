#!/bin/sh
# Nginx-RTMP entrypoint script
# Substitutes environment variables in nginx.conf and starts nginx

set -e

# Define which env vars to substitute
# Using explicit list to avoid substituting nginx's own $vars
envsubst '$YOUTUBE_STREAM_KEY' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

# Start nginx in foreground
exec nginx -g 'daemon off;'
