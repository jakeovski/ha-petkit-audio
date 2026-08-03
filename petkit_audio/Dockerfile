ARG BUILD_FROM=python:3.11-slim-bookworm
FROM ${BUILD_FROM}

# Agora ships its RTC SDK as glibc aarch64 (aarch64-linux-gnu). Home Assistant's
# own container is Alpine/musl and cannot load it, which is the whole reason this
# runs as a separate add-on rather than inside the integration.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        jq \
    && rm -rf /var/lib/apt/lists/*

# 2.4.8 rather than 2.4.9: the latter points at an aarch64 archive that 404s.
RUN pip install --no-cache-dir agora-python-server-sdk==2.4.8

# The native library needs its directory on the loader path before the process
# starts; setting it from inside Python is too late.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/agora/agora_sdk

COPY rootfs/ /
RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
