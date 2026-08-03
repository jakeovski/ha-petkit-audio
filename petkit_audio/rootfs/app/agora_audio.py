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
    AudioScenarioType,
    ChannelProfileType,
    ClientRoleType,
    RTCConnConfig,
    RtcConnectionPublishConfig,
)
from agora.rtc.agora_service import AgoraService
from agora.rtc.audio_frame_observer import IAudioFrameObserver
from agora.rtc.local_user_observer import IRTCLocalUserObserver
from agora.rtc.rtc_connection_observer import IRTCConnectionObserver

# The payload type the devices publish under. The vendor app sets the same value
# on its engine before joining; without it the SDK will not decode the stream.
CUSTOM_AUDIO_PAYLOAD_TYPE = 69

# What we hand ffmpeg. The SDK resamples for us, so this is our choice, not the
# device's - 16 kHz mono is plenty for an 8 kHz G.711 source.
SAMPLE_RATE = 16000
CHANNELS = 1

LOGGER = logging.getLogger("petkit_audio")
_running = True


class _ConnectionLog(IRTCConnectionObserver):
    """Report what the channel is actually doing.

    connect() only returns whether the request was accepted, so without this
    there is no way to tell a joined channel from one still retrying, or to see
    whether the feeder is even present.
    """

    def on_connected(self, agora_rtc_conn, conn_info, reason):
        LOGGER.info("Channel connected (reason=%s)", reason)

    def on_disconnected(self, agora_rtc_conn, conn_info, reason):
        LOGGER.warning("Channel disconnected (reason=%s)", reason)

    def on_connection_failure(self, agora_rtc_conn, info, reason):
        LOGGER.error("Channel connection failure (reason=%s)", reason)

    def on_user_joined(self, agora_rtc_conn, user_id):
        LOGGER.info("Remote user joined: %s", user_id)

    def on_user_left(self, agora_rtc_conn, user_id, reason):
        LOGGER.info("Remote user left: %s (reason=%s)", user_id, reason)

    def on_error(self, agora_rtc_conn, error_code, error_msg):
        LOGGER.error("Agora error %s: %s", error_code, error_msg)

    def on_aiqos_capability_missing(self, agora_rtc_conn, recommend_audio_scenario) -> int:
        # The base class returns None here and the SDK immediately does
        # `None >= 0`, so the scenario fallback dies with a TypeError and the
        # connection is left in a scenario the channel cannot satisfy.
        scenario = int(getattr(recommend_audio_scenario, "value", recommend_audio_scenario))
        LOGGER.info("AI-QoS capability missing; falling back to scenario %s", scenario)
        return scenario


class _TrackLog(IRTCLocalUserObserver):
    """Trace the remote audio track from subscription through to decoding.

    Being in the channel says nothing about whether Agora is offering us an
    audio track, or whether anything is arriving on it. These three callbacks
    separate "no track", "track but no packets" and "packets but no decode",
    which need completely different fixes.
    """

    def on_user_audio_track_subscribed(self, agora_local_user, user_id, agora_remote_audio_track):
        LOGGER.info("Audio track SUBSCRIBED for uid=%s", user_id)

    def on_audio_subscribe_state_changed(
        self, agora_local_user, channel, user_id, old_state, new_state, elapse_since_last_state
    ):
        LOGGER.info("Audio subscribe state uid=%s: %s -> %s", user_id, old_state, new_state)

    def on_user_audio_track_state_changed(
        self, agora_local_user, user_id, agora_remote_audio_track, state, reason, elapsed
    ):
        LOGGER.info("Audio track state uid=%s: state=%s reason=%s", user_id, state, reason)

    def on_first_remote_audio_frame(self, agora_local_user, user_id, elapsed):
        LOGGER.info("FIRST REMOTE AUDIO FRAME from uid=%s after %sms", user_id, elapsed)

    def on_first_remote_audio_decoded(self, agora_local_user, user_id, elapsed):
        LOGGER.info("FIRST REMOTE AUDIO DECODED from uid=%s after %sms", user_id, elapsed)

    def on_remote_audio_track_statistics(self, agora_local_user, agora_remote_audio_track, stats):
        LOGGER.info(
            "Remote audio stats: received=%s frozen=%s",
            getattr(stats, "received_bytes", None),
            getattr(stats, "frozen_rate", None),
        )


class _AudioSink(IAudioFrameObserver):
    """Write every remote audio frame straight to stdout."""

    def __init__(self) -> None:
        self.frames = 0
        self.mixed_frames = 0
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

    def on_playback_audio_frame(self, agora_local_user, channelId, frame):
        # Fallback path: with a single remote publisher some builds deliver
        # the mixed playback frame rather than the per-user one.
        data = getattr(frame, "buffer", None)
        if data and not self.frames:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            self.mixed_frames += 1
            if self.mixed_frames == 1:
                LOGGER.info("First mixed audio frame (%d bytes)", len(data))
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
    # The SDK defaults to the AI_SERVER scenario, which this channel does not
    # advertise support for - it asks to fall back to game streaming, so start
    # there rather than relying on a fallback path that has already failed.
    config.audio_scenario = AudioScenarioType.AUDIO_SCENARIO_GAME_STREAMING
    # Keep delivering callbacks even if Agora considers the publisher muted.
    # Without this a muted remote is silently indistinguishable from one that is
    # simply not sending, which is exactly the ambiguity we are trying to settle.
    config.should_callbck_when_muted = 1

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

    # The vendor app sets this on its engine before joining. Setting it only on
    # the service may not reach the connection that actually decodes the stream.
    conn_parameter = connection.get_agora_parameter()
    if conn_parameter is not None:
        conn_parameter.set_parameters(
            json.dumps({"che.audio.custom_payload_type": CUSTOM_AUDIO_PAYLOAD_TYPE})
        )

    connection.register_observer(_ConnectionLog())
    connection.register_local_user_observer(_TrackLog())
    sink = _AudioSink()
    connection.register_audio_frame_observer(sink, 0, None)
    local_user = connection.get_local_user()
    local_user.set_playback_audio_frame_before_mixing_parameters(CHANNELS, SAMPLE_RATE)
    local_user.set_playback_audio_frame_parameters(CHANNELS, SAMPLE_RATE, 0, SAMPLE_RATE // 100)

    if connection.connect(token, channel_id, uid) != 0:
        LOGGER.error("connect failed for channel=%s uid=%s", channel_id, uid)
        connection.release()
        service.release()
        return 1

    # auto_subscribe_audio should cover this, but ask explicitly as well: the
    # feeder is already publishing when we arrive, so there is no join event to
    # trigger an implicit subscribe.
    subscribed = local_user.subscribe_all_audio()
    LOGGER.info("subscribe_all_audio -> %s", subscribed)

    LOGGER.info("Connected; waiting for audio")
    last_report = time.time()
    while _running:
        time.sleep(1)
        if time.time() - last_report >= 30:
            LOGGER.info("%d audio frames forwarded (%d mixed)", sink.frames, sink.mixed_frames)
            last_report = time.time()

    LOGGER.info("Shutting down after %d frames", sink.frames)
    connection.disconnect()
    connection.release()
    service.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
