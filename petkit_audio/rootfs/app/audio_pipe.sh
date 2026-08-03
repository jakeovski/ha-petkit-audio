#!/usr/bin/env bash
# Join the feeder's Agora channel and publish its audio into go2rtc.
#
# $1 is go2rtc's {output} RTSP URL. The Python side emits silence immediately and
# swaps in real audio once the channel is joined, so go2rtc can serve this stream
# right away rather than waiting on the Agora handshake.
set -uo pipefail

OUTPUT="$1"

exec python3 -u /app/agora_audio.py \
    | ffmpeg -hide_banner -loglevel warning \
        -f s16le -ar 16000 -ac 1 -i pipe:0 \
        -c:a libopus -b:a 32k -application lowdelay \
        -f rtsp -rtsp_transport tcp "$OUTPUT"
