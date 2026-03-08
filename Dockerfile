ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

WORKDIR /app

# Install Python runtime and dependencies.
# Supervisor may still inject the generic HA base image for local builds,
# so install Python explicitly instead of assuming a python-enabled base.
RUN apk add --no-cache \
	python3 \
	py3-pip

COPY backend/requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy pre-built frontend (built in CI, not at container runtime)
COPY frontend/dist/ ./frontend/dist/

# Copy logo for addon icon
COPY frontend/logo.png ./frontend/dist/logo.png

# Copy entrypoint
COPY run.sh /
RUN chmod +x /run.sh

EXPOSE 8099

CMD ["/run.sh"]
