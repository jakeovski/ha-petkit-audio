"""Join the PetKit feeder's Agora channel and stream its audio to stdout.

The feeder publishes G.711 mu-law audio under a custom payload type (69). Agora's
WebRTC gateway - which the Home Assistant integration speaks - never delivers it,
but the native SDK does, which is how the vendor app plays it. This joins the same
channel the same way and writes the decoded PCM to stdout as s16le, so ffmpeg can
turn it into something a browser will play.

Reads its session parameters from a JSON file the integration keeps up to date:

    {"app_id": "...", "channel_id": "...", "rtc_token": "...", "uid": 300240168}
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time

from agora.rtc.agora_base import (
    AgoraServiceConfig,
    ChannelProfileType,
    ClientRoleType,
    RTCConnConfig,
    RtcConnectionPublishConfig,
)
from agora.rtc.agora_service import AgoraService
from agora.rtc.audio_frame_observer import IAudioFrameObserver

# The payload type the devices publish under. The vendor app sets the same value
# on its engine before joining; without it the SDK will not decode the stream.
CUSTOM_AUDIO_PAYLOAD_TYPE = 69

# What we hand ffmpeg. The SDK resamples for us, so this is our choice, not the
# device's - 16 kHz mono is plenty for an 8 kHz G.711 source.
SAMPLE_RATE = 16000
CHANNELS = 1

LOGGER = logging.getLogger("petkit_audio")
_running = True


class _AudioSink(IAudioFrameObserver):
    """Write every remote audio frame straight to stdout."""

    def __init__(self) -> None:
        self.frames = 0
        self.first_frame_logged = False

    def on_playback_audio_frame_before_mixing(
        self, agora_local_user, channelId, uid, frame, vad_result_state, vad_result_bytearray
    ):
        # Callbacks must stay cheap - copying bytes out is all we do here.
        data = getattr(frame, "buffer", None)
        if data:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            self.frames += 1
            if not self.first_frame_logged:
                LOGGER.info("First audio frame from uid=%s (%d bytes)", uid, len(data))
                self.first_frame_logged = True
        return 0


def _load_session(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _stop(signum, frame) -> None:
    global _running
    _running = False


def main() -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    session_file = os.environ.get("SESSION_FILE", "/config/petkit_agora_session.json")
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            session = _load_session(session_file)
            break
        except (OSError, ValueError) as err:
            LOGGER.info("Waiting for %s (%s)", session_file, err)
            time.sleep(5)
    else:
        LOGGER.error("No session file at %s; is the PetKit camera streaming?", session_file)
        return 1

    app_id = session["app_id"]
    channel_id = session["channel_id"]
    token = session["rtc_token"]
    # A second client cannot share the integration's uid - Agora evicts the older
    # one, which would take the video stream down with it.
    uid = str(session.get("audio_uid") or (int(session["uid"]) + 1))

    LOGGER.info("Joining channel=%s as uid=%s", channel_id, uid)

    config = AgoraServiceConfig()
    config.appid = app_id
    config.enable_audio_device = 0
    config.enable_audio_processor = 1
    config.enable_video = 0
    config.channel_profile = ChannelProfileType.CHANNEL_PROFILE_LIVE_BROADCASTING

    service = AgoraService()
    if service.initialize(config) != 0:
        LOGGER.error("AgoraService.initialize failed")
        return 1

    parameter = service.get_agora_parameter()
    if parameter is not None:
        parameter.set_parameters(
            json.dumps({"che.audio.custom_payload_type": CUSTOM_AUDIO_PAYLOAD_TYPE})
        )

    conn_config = RTCConnConfig(
        auto_subscribe_audio=1,
        auto_subscribe_video=0,
        client_role_type=ClientRoleType.CLIENT_ROLE_BROADCASTER,
        channel_profile=ChannelProfileType.CHANNEL_PROFILE_LIVE_BROADCASTING,
    )
    connection = service.create_rtc_connection(conn_config, RtcConnectionPublishConfig())
    if connection is None:
        LOGGER.error("create_rtc_connection returned nothing")
        service.release()
        return 1

    sink = _AudioSink()
    connection.register_audio_frame_observer(sink, 0, None)
    local_user = connection.get_local_user()
    local_user.set_playback_audio_frame_before_mixing_parameters(CHANNELS, SAMPLE_RATE)

    if connection.connect(token, channel_id, uid) != 0:
        LOGGER.error("connect failed for channel=%s uid=%s", channel_id, uid)
        connection.release()
        service.release()
        return 1

    LOGGER.info("Connected; waiting for audio")
    last_report = time.time()
    while _running:
        time.sleep(1)
        if time.time() - last_report >= 30:
            LOGGER.info("%d audio frames forwarded", sink.frames)
            last_report = time.time()

    LOGGER.info("Shutting down after %d frames", sink.frames)
    connection.disconnect()
    connection.release()
    service.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
