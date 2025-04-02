FROM python:3.13.2-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set version labels
ARG BUILD_DATE
ARG VERSION
ARG RELEASE
LABEL org.opencontainers.image.title="SteamSelfGifter" \
      org.opencontainers.image.description="Bot for SteamGifts" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${RELEASE}" \
      org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy application code and requirements
COPY steamselfgifter/ /app
COPY requirements/common.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create config directory with proper permissions
RUN mkdir -p /config && \
    chown -R appuser:appuser /config && \
    chmod 755 /config

# Copy default config
COPY config.ini.sample /config/config.ini
RUN chown appuser:appuser /config/config.ini && \
    chmod 644 /config/config.ini

# Switch to non-root user
USER appuser

# Create volume for config
VOLUME /config

# Run the application
CMD [ "python3", "/app/steamselfgifter.py", "-c", "/config/config.ini"]
