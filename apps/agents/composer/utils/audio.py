import io
import os

from pydub import AudioSegment

def convert_mp3(audio_segment: AudioSegment) -> bytes:
    out = io.BytesIO()
    audio_segment.export(out, format="mp3")
    return out.getvalue()

