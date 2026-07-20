# =============================================================================
# SteamSelfGifter - Single Container Build
# Combines FastAPI backend + React frontend with nginx reverse proxy
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build Frontend
# -----------------------------------------------------------------------------
FROM node:24-alpine AS frontend-build

WORKDIR /frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm ci

# Copy source and build
COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Build Backend
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS backend-build

WORKDIR /app

# Copy source and pyproject.toml
COPY backend/src/ ./src/
COPY backend/pyproject.toml backend/README.md ./

# Install dependencies into a virtual environment, then remove the project
# itself: the app runs from /app/src in the runtime image, and a second copy
# in site-packages would shadow-fight with it.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir . && pip uninstall -y steamselfgifter-backend

# -----------------------------------------------------------------------------
# Stage 3: Final Runtime Image
# -----------------------------------------------------------------------------
FROM python:3.14-slim

# Install nginx and supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python virtual environment from build stage
COPY --from=backend-build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy backend source code
WORKDIR /app
COPY backend/src/ ./src/

# Create config directory for persistent data (database + logs), and the
# unprivileged user the backend runs as when PUID/PGID are set
RUN mkdir -p /config \
    && useradd --system --no-create-home --shell /usr/sbin/nologin app

# Copy frontend build to nginx html directory
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html

# Configure nginx
RUN rm /etc/nginx/sites-enabled/default
COPY <<'NGINX_CONF' /etc/nginx/sites-available/steamselfgifter
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied expired no-cache no-store private auth;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml application/javascript application/json;

    # Handle SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Proxy WebSocket connections
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
NGINX_CONF

RUN ln -s /etc/nginx/sites-available/steamselfgifter /etc/nginx/sites-enabled/

# Configure supervisor to manage both services
COPY <<'SUPERVISOR_CONF' /etc/supervisor/conf.d/steamselfgifter.conf
[supervisord]
nodaemon=true
user=root

[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:backend]
command=/opt/venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
directory=/app/src
user=%(ENV_BACKEND_USER)s
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
SUPERVISOR_CONF

# Entrypoint: optionally drop the backend to an unprivileged user.
# Set PUID (and optionally PGID) to run the backend as that uid/gid and
# chown /config accordingly — useful for Docker where container-root is
# real root. Leave unset for the default root mode (the right choice for
# rootless podman, where container-root already maps to the host user).
COPY <<'ENTRYPOINT_SH' /usr/local/bin/docker-entrypoint.sh
#!/bin/sh
set -e

if [ -n "$PUID" ]; then
    PGID="${PGID:-$PUID}"
    groupmod -o -g "$PGID" app
    usermod -o -u "$PUID" -g "$PGID" app
    chown -R "$PUID:$PGID" /config
    export BACKEND_USER=app
    echo "entrypoint: backend will run as uid=$PUID gid=$PGID"
else
    export BACKEND_USER=root
fi

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
ENTRYPOINT_SH
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose port 80 (nginx serves both frontend and proxies to backend)
EXPOSE 80

# No HEALTHCHECK here: OCI image format (podman's default) can't store it
# and warns on every build. The healthcheck is defined in docker-compose.yml
# instead; for plain `docker run`, pass --health-cmd if you want one:
#   --health-cmd 'curl -f http://localhost/api/v1/system/health || exit 1'

# Start via the entrypoint (handles optional PUID/PGID, then runs
# supervisord which manages nginx + uvicorn)
CMD ["/usr/local/bin/docker-entrypoint.sh"]
