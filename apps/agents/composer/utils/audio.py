import io
import os

from pydub import AudioSegment

def convert_mp3(audio_segment: AudioSegment) -> bytes:
    out = io.BytesIO()
    if "GOOGLE_CLOUD_AGENT_ENGINE_ID" in os.environ:
        audio_segment.converter = "composer/ffmpeg-7.0.2-amd64-static/ffmpeg"

    audio_segment.export(out, format="mp3")
    return out.getvalue()

