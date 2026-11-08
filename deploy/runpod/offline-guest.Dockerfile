# syntax=docker/dockerfile:1
ARG EDITORGPT_RUNPOD_BASE
FROM ${EDITORGPT_RUNPOD_BASE} AS guest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends busybox-static \
    && rm -rf /var/lib/apt/lists/* && mkdir -p /job
COPY --chmod=755 deploy/runpod/offline-guest-init /opt/editorgpt-guest-init

FROM ${EDITORGPT_RUNPOD_BASE} AS pack
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    linux-image-amd64 busybox-static cpio squashfs-tools kmod xz-utils zstd
COPY deploy/runpod/offline-initrd /tmp/guest-init
RUN --mount=type=bind,from=guest,source=/,target=/guest,readonly \
    set -eu; \
    install -d /out /tmp/initrd/bin /tmp/initrd/dev /tmp/initrd/modules /tmp/initrd/rootfs; \
    cp /boot/vmlinuz-* /out/vmlinuz; \
    cp /bin/busybox /tmp/initrd/bin/busybox; \
    ln -s busybox /tmp/initrd/bin/sh; \
    install -m 755 /tmp/guest-init /tmp/initrd/init; \
    kernel=$(basename /boot/vmlinuz-* | sed 's/^vmlinuz-//'); \
    for mod in virtio_pci virtio_blk squashfs 9p 9pnet_virtio; do \
      modprobe --set-version "$kernel" --show-depends "$mod" >> /tmp/modules; \
    done; \
    awk '$1=="insmod" && !seen[$2]++ {print $2}' /tmp/modules > /tmp/module-files; \
    while IFS= read -r src; do \
      name=$(basename "$src"); name=${name%%.ko*}.ko; dst="/tmp/initrd/modules/$name"; \
      case "$src" in \
        *.xz) xz -dc "$src" > "$dst";; \
        *.zst) zstd -dc "$src" > "$dst";; \
        *.gz) gzip -dc "$src" > "$dst";; \
        *) cp "$src" "$dst";; \
      esac; \
      printf '%s\n' "$name" >> /tmp/initrd/modules/order; \
    done < /tmp/module-files; \
    (cd /tmp/initrd && find . -print | cpio --quiet -o -H newc | gzip -1 > /out/initrd.gz); \
    mksquashfs /guest /out/root.squashfs -noappend -comp zstd -Xcompression-level 1 -processors 2

FROM ${EDITORGPT_RUNPOD_BASE} AS runtime
USER root
RUN apt-get update && apt-get install -y --no-install-recommends qemu-system-x86 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=pack /out/ /opt/editorgpt-offline/
COPY app/render_cloud /app/app/render_cloud
USER 10001:10001

FROM runtime AS smoke
USER root
COPY deploy/runpod/offline-guest-smoke.py /opt/editorgpt-offline/smoke.py
RUN python -c 'from pathlib import Path; from engine.hyperframes.assets import ensure_gsap; import shutil; root=Path("/opt/editorgpt-offline"); shutil.copyfile(ensure_gsap(root), root/"gsap.min.js")'
USER 10001:10001
