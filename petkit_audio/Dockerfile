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

# go2rtc owns the RTSP server. ffmpeg cannot: as an RTSP listener it exits when
# no client is attached, which breaks the pipe the Agora client writes into.
ARG GO2RTC_VERSION=v1.9.14
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
        arm64) GO2RTC_ARCH=linux_arm64 ;; \
        amd64) GO2RTC_ARCH=linux_amd64 ;; \
        *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/go2rtc \
        "https://github.com/AlexxIT/go2rtc/releases/download/${GO2RTC_VERSION}/go2rtc_${GO2RTC_ARCH}"; \
    chmod +x /usr/local/bin/go2rtc

COPY rootfs/ /
RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
