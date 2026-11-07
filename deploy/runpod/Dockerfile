# Build the existing runtime at the same source revision first; no second engine.
# Use an immutable image digest for release; a verified local runtime may be used
# for a disconnected image smoke test. Live deployment requires the
# signed transport, host namespace and resource-limit canaries documented in rollout.
ARG EDITORGPT_RUNTIME
FROM ${EDITORGPT_RUNTIME}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends util-linux libseccomp2 \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /work /home/render && chown -R 10001:10001 /work /home/render
COPY app/render_cloud /app/app/render_cloud
COPY assets /app/assets
COPY vendor /app/vendor
ENV HOME=/home/render TMPDIR=/work
WORKDIR /work
USER 10001:10001
HEALTHCHECK NONE
ENTRYPOINT ["python", "-m", "app.render_cloud.runner"]
