#!/usr/bin/env bash
# Serve the feeder's audio as RTSP on :8554/petkit_audio.
#
# go2rtc owns the RTSP server and starts the pipeline on demand. The publisher
# emits silence from the moment it starts, so the stream is servable almost
# immediately instead of after the ~15s Agora handshake.
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

# Mirror the log into /config as well as the Supervisor log: the Supervisor log
# is not always reachable, and diagnosing an audio pipeline blind is hopeless.
LOGFILE=/config/petkit_audio.log
: > "$LOGFILE"
exec /usr/local/bin/go2rtc -config /app/go2rtc.yaml 2>&1 | tee -a "$LOGFILE"
