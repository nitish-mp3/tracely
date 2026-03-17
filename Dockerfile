# ARG must be before the first FROM so Docker can use it in any FROM instruction.
# HA Supervisor passes --build-arg BUILD_FROM=<arch-specific base image>.
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest

# ── Stage 1: build the Svelte frontend ───────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts

COPY frontend/ ./
RUN npm run build

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM ${BUILD_FROM}

WORKDIR /app

# Install Python runtime and dependencies.
# Supervisor may still inject the generic HA base image for local builds,
# so install Python explicitly instead of assuming a python-enabled base.
RUN apk add --no-cache \
	python3 \
	py3-pip \
	iputils \
	iproute2

COPY backend/requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy frontend build output from stage 1
COPY --from=frontend-builder /frontend/dist/ ./frontend/dist/

# Copy logo for addon icon (already inside dist after Vite build copies public/)
# Fallback: copy from source if not already present
COPY frontend/logo.png ./frontend/dist/logo.png

# Copy entrypoint
COPY run.sh /
RUN chmod +x /run.sh

EXPOSE 8765

CMD ["/run.sh"]
