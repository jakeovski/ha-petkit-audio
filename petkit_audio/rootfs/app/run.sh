#!/usr/bin/env bash
# Serve the feeder's audio as RTSP on :8554/petkit_audio.
#
# go2rtc owns the RTSP server and starts the Agora pipeline on demand, so the
# channel is only joined while something is listening. ffmpeg alone cannot do
# this: as an RTSP listener it exits the moment no client is attached, which
# leaves the Agora client writing into a broken pipe.
set -uo pipefail

OPTIONS=/data/options.json

if [ -f "$OPTIONS" ]; then
    SESSION_FILE=$(jq -r '.session_file // "/config/petkit_agora_session.json"' "$OPTIONS")
    LOG_LEVEL=$(jq -r '.log_level // "info"' "$OPTIONS")
else
    SESSION_FILE=/config/petkit_agora_session.json
    LOG_LEVEL=info
fi

export SESSION_FILE
export LOG_LEVEL

echo "[petkit_audio] session file: ${SESSION_FILE}"
echo "[petkit_audio] serving rtsp://<addon>:8554/petkit_audio"

exec /usr/local/bin/go2rtc -config /app/go2rtc.yaml
