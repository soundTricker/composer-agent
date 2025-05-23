import base64
import io
import logging
import uuid

import google.auth
from google.adk.tools import ToolContext
from google.cloud import aiplatform
from google.genai import types
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value
from pydub import AudioSegment

loggger = logging.getLogger(__name__)

async def generate_music_tool(prompt: str, negative_prompt: str, seed: int, sample_count: int, tool_context: ToolContext):
    """
    Generates music based on the provided prompts by utilizing Google's AI
    Platform services and the lyria-002 model. The function is responsible for setting
    up the client, creating request instances and parameters, and executing the request
    to retrieve generated samples. The responses consist of generated musical data
    predictions.

    The generated music will be saved to artifact, The filename will be like 'generated_audio_{sample_number}.mp3'.

    :param prompt: The prompt to use for generating music in English, it sends to Lyria model.
    :param negative_prompt: The negative prompt for avoiding specific features in the
        generated music. When you don't need passing, you can set the empty string.
    :param seed: The random seed for initialization to control the variability in
        output. When you don't need passing, you can set -1.
    :param sample_count: The number of samples to generate. it must be 1-4.
    :param tool_context: An object representing the contextual or environmental
        information required for the tool's execution.
    :return: list of the generated music_id, when it returns None, the process is failed. please retry again with changing the prompt.
    """

    try:
        client_options = {"api_endpoint": "aiplatform.googleapis.com"}
        client = aiplatform.gapic.PredictionServiceClient(client_options=client_options)

        params: dict[str, str|int] = {"prompt": prompt}

        if negative_prompt:
            params["negative_prompt"] = negative_prompt

        if seed > 0:
            params["seed"] = seed

        if sample_count:
            params["sample_count"] = sample_count

        instance = json_format.ParseDict(params, Value())
        instances = [instance]

        parameters_dict = {}
        parameters = json_format.ParseDict(parameters_dict, Value())

        _, project_id = google.auth.default()

        endpoint_path = f"projects/{project_id}/locations/us-central1/publishers/google/models/lyria-002"
        loggger.info(f"endpoint path {endpoint_path}")

        response = client.predict(endpoint=endpoint_path, instances=instances, parameters=parameters)
        predictions = response.predictions
        loggger.info(f"Returned {len(predictions)} samples")

        mp3_list = []
        for index, pred in enumerate(predictions):
            bytes_b64 = dict(pred)["bytesBase64Encoded"]
            decoded_audio_data = base64.b64decode(bytes_b64)
            audio_segment = AudioSegment.from_wav(io.BytesIO(decoded_audio_data))

            out = io.BytesIO()
            try:
                audio_segment.export(out, format="mp3", bitrate="192k")
            except Exception as e:
                loggger.exception(f"failed to export mp3 audio {e}, retrying with local ffmpeg")
                audio_segment.converter = "composer/ffmpeg-7.0.2-amd64-static/ffmpeg"
                audio_segment.export(out, format="mp3", bitrate="192k")

            part = types.Part.from_bytes(data=out.getvalue(), mime_type="audio/mp3")
            artifact_id = uuid.uuid4().hex
            await tool_context.save_artifact(artifact_id, part)
            mp3_list.append(artifact_id)

        tool_context.state.update({"music_artifact_list": mp3_list})

        return mp3_list
    except Exception as e:
        loggger.exception(f"failed to create the music. {e}")
        return None
