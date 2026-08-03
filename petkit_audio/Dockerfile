# Deliberately NOT using BUILD_FROM. Supervisor injects an Alpine/musl base, and
# Agora ships its RTC SDK as a glibc binary (aarch64-linux-gnu) that cannot load
# there - which is the entire reason this runs as an add-on instead of inside the
# Home Assistant container.
FROM python:3.11-slim-bookworm

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

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
