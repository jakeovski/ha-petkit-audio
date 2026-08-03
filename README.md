# PetKit Camera Audio — Home Assistant add-on

The PetKit feeders publish their microphone into an Agora channel under a custom
payload type (69). Agora's WebRTC gateway, which the Home Assistant integration
speaks, never forwards that track — the vendor app only hears it because it is a
native Agora SDK client.

Agora ships that SDK as a glibc binary (`aarch64-linux-gnu`). Home Assistant's own
container is Alpine/musl and cannot load it, so this runs as a separate add-on:
it joins the same channel with the native SDK and republishes the audio as RTSP at
`rtsp://<addon>:8554/petkit_audio`, ready to be merged with the existing video.

Credentials come from `petkit_agora_session.json`, written to `/config` by the
PetKit integration (1.27.33+).
