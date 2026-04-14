# CAPA Test Automation - Multi-stage build
# Stage 1: Build React frontend
# Stage 2: Python backend + Ansible + CLIs + built frontend

# ----------------------------------------------------------------------
# Stage 1: Build frontend
# ----------------------------------------------------------------------
FROM node:24-slim AS frontend-build

WORKDIR /app/frontend
COPY ui/frontend/package.json ui/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/frontend/ ./
RUN npm run build

# ----------------------------------------------------------------------
# Stage 2: Final image
# ----------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    jq \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Install oc CLI
RUN curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
    | tar xz -C /usr/local/bin oc kubectl \
    && chmod +x /usr/local/bin/oc /usr/local/bin/kubectl

# Install rosa CLI
RUN curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/rosa/latest/rosa-linux.tar.gz \
    | tar xz -C /usr/local/bin rosa \
    && chmod +x /usr/local/bin/rosa

# Install AWS CLI v2
RUN curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip \
    && apt-get update && apt-get install -y --no-install-recommends unzip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/awscliv2.zip /tmp/aws \
    && apt-get remove -y unzip && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (backend + ansible)
COPY ui/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt ansible requests anthropic pyyaml && rm /tmp/requirements.txt

# Copy application code
COPY playbooks/ /app/playbooks/
COPY tasks/ /app/tasks/
COPY roles/ /app/roles/
COPY templates/ /app/templates/
COPY schemas/ /app/schemas/
COPY scripts/ /app/scripts/
COPY agents/ /app/agents/
COPY config/ /app/config/
COPY common/ /app/common/
COPY vars/ /app/vars/
COPY versions/ /app/versions/
COPY test-suites/ /app/test-suites/
COPY ui/backend/ /app/ui/backend/

# Copy built frontend
COPY --from=frontend-build /app/frontend/build /app/ui/frontend/build

# Nginx config: serve frontend, proxy /api to backend
RUN cat > /etc/nginx/sites-available/default <<'NGINX'
server {
    listen 3000;

    root /app/ui/frontend/build;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

# Create persistent dirs
RUN mkdir -p /app/vars /data

# Entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/api/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
