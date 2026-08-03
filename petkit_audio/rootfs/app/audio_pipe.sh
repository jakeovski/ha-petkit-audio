#!/usr/bin/env bash
# Join the feeder's Agora channel and publish its audio into go2rtc.
#
# $1 is go2rtc's {output} RTSP URL. Only stdout carries audio, so both stages
# send their diagnostics to the shared log file - without that, a crash in
# either one surfaces to go2rtc as nothing more than "EOF".
set -uo pipefail

OUTPUT="$1"
LOGFILE=/config/petkit_audio.log

echo "[audio_pipe] starting, output=${OUTPUT}" >> "$LOGFILE"

python3 -u /app/agora_audio.py 2>> "$LOGFILE" \
    | ffmpeg -hide_banner -loglevel warning \
        -f s16le -ar 16000 -ac 1 -i pipe:0 \
        -c:a libopus -b:a 32k -application lowdelay \
        -f rtsp -rtsp_transport tcp "$OUTPUT" 2>> "$LOGFILE"

echo "[audio_pipe] exited rc=$?" >> "$LOGFILE"
