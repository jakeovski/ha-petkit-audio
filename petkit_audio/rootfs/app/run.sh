#!/usr/bin/env bash
# Serve the feeder's audio as RTSP on :8554/petkit_audio.
#
# ffmpeg acts as the RTSP server (-rtsp_flags listen), so it blocks until a
# client connects and exits when that client goes away - hence the restart loop.
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
echo "[petkit_audio] serving rtsp://0.0.0.0:8554/petkit_audio"

while true; do
    python3 -u /app/agora_audio.py \
        | ffmpeg -hide_banner -loglevel warning \
            -f s16le -ar 16000 -ac 1 -i pipe:0 \
            -c:a libopus -b:a 32k -application lowdelay \
            -f rtsp -rtsp_flags listen \
            rtsp://0.0.0.0:8554/petkit_audio

    echo "[petkit_audio] pipeline exited; restarting in 5s"
    sleep 5
done
