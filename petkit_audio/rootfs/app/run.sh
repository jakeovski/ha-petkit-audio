#!/usr/bin/env bash
# Serve the feeder's audio as RTSP on :8554/petkit_audio, always live.
#
# go2rtc runs in the background as the RTSP server; the publisher pushes into it
# continuously. Keeping the Agora session warm matters: Home Assistant's camera
# now points at a stream that merges this audio with the video, and go2rtc dials
# every source before serving, so a slow audio source delays the video too.
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

/usr/local/bin/go2rtc -config /app/go2rtc.yaml &
GO2RTC_PID=$!
trap 'kill ${GO2RTC_PID} 2>/dev/null' EXIT

# Give the RTSP server a moment before the first publish attempt.
sleep 3
echo "[petkit_audio] publishing to rtsp://127.0.0.1:8554/petkit_audio"

while true; do
    python3 -u /app/agora_audio.py \
        | ffmpeg -hide_banner -loglevel warning \
            -f s16le -ar 16000 -ac 1 -i pipe:0 \
            -c:a libopus -b:a 32k -application lowdelay \
            -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/petkit_audio

    echo "[petkit_audio] publisher exited; retrying in 5s"
    sleep 5
done
