FROM tiangolo/nginx-rtmp

# Install gettext for envsubst (for env var substitution in nginx.conf)
RUN apt-get update && apt-get install -y gettext-base && rm -rf /var/lib/apt/lists/*

# Copy configuration as template (will be processed at runtime)
COPY nginx.conf /etc/nginx/nginx.conf.template

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
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

EXPOSE 1935 80

ENTRYPOINT ["/entrypoint.sh"]

