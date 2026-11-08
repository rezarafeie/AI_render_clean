ARG EDITORGPT_RUNPOD_BASE
FROM ${EDITORGPT_RUNPOD_BASE}
USER root
RUN mkdir /opt/editorgpt-headless /tmp/hf-install \
    && HOME=/tmp/hf-install node /opt/hyperframes/node_modules/hyperframes/bin/hyperframes.mjs browser ensure \
    && browser="$(find /tmp/hf-install -type f -name chrome-headless-shell -print -quit)" \
    && test -x "$browser" \
    && cp -a "$(dirname "$browser")/." /opt/editorgpt-headless/ \
    && rm -rf /tmp/hf-install
COPY app/render_cloud /app/app/render_cloud
USER 10001:10001
