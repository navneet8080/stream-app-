FROM tiangolo/nginx-rtmp

# Copy configuration directly (no envsubst needed)
COPY nginx.conf /etc/nginx/nginx.conf

# Copy RTMP statistics stylesheet
COPY stat.xsl /etc/nginx/stat.xsl

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create HLS directory with proper permissions
RUN mkdir -p /tmp/hls && chmod -R 777 /tmp/hls

# Create log directory
RUN mkdir -p /var/log/nginx

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=5 \
    CMD curl -f http://localhost/health || exit 1

EXPOSE 1935 80

ENTRYPOINT ["/entrypoint.sh"]
