# Light worker image for the Claude film engines (claude_motion; the Claude talking engine renders through the same worker).
# The full worker image is built FROM the whole application runtime (150 layers, models, MLT, tesseract, hyperframes ...); a fresh RunPod host must pull all of it
# before the Pod can start, and that pull is what made new workers sit silent for minutes. This image holds only what the worker pass needs:
# the worker code (app/render_cloud), the Claude renderer, Node + Remotion, Chromium and ffmpeg. The renderer code itself is the same file as in the full image.
FROM python:3.12-slim AS pyenv
COPY requirements.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -c requirements.lock httpx pydantic

FROM node:22-bookworm-slim AS motion
WORKDIR /motion
COPY remotion/package*.json ./
RUN npm ci
# The worker's native sandbox (app/render_cloud/native_loopback.py) is used only when this headless browser exists at /opt/editorgpt-headless; without it the worker falls back to
# `unshare --user --net`, which many RunPod hosts refuse. Remotion's own pinned headless shell is placed there (and removed from node_modules so there is only one copy).
RUN node -e "import('@remotion/renderer').then(m => m.ensureBrowser()).then(() => console.log('browser ready'))" \
    && mkdir /opt/editorgpt-headless \
    && browser="$(find /motion/node_modules/.remotion -type f -name chrome-headless-shell -print -quit)" \
    && test -x "$browser" \
    && cp -a "$(dirname "$browser")/." /opt/editorgpt-headless/ \
    && rm -rf /motion/node_modules/.remotion

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg chromium fonts-dejavu-core util-linux libseccomp2 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /work /home/render /app/engine /app/app \
    && chown -R 10001:10001 /work /home/render
COPY --from=pyenv /opt/venv /opt/venv
COPY --from=motion /usr/local/bin/node /usr/local/bin/node
COPY --from=motion /motion/node_modules /app/remotion/node_modules
COPY --from=motion /opt/editorgpt-headless /opt/editorgpt-headless
COPY remotion/package*.json /app/remotion/
COPY app/render_cloud /app/app/render_cloud
COPY engine/claude_motion_renderer.py /app/engine/claude_motion_renderer.py
ENV PYTHONPATH=/app PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    REMOTION_BROWSER_EXECUTABLE=/usr/bin/chromium REMOTION_CONCURRENCY=2 \
    HOME=/home/render TMPDIR=/work
WORKDIR /work
USER 10001:10001
HEALTHCHECK NONE
ENTRYPOINT ["python", "-m", "app.render_cloud.runner"]
