import copy
import logging
import os

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from .prompts import instructions
from .sub_agents.composer.agent import root_agent as composer_agent

if "GOOGLE_CLOUD_AGENT_ENGINE_ID" in os.environ:
    # run on agent engine
    import google.cloud.logging

    client = google.cloud.logging.Client()
    client.setup_logging()

call_composer_agent = AgentTool(composer_agent)

logger = logging.getLogger(__name__)

async def load_artifact(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse:

    if not callback_context.state.get("music_artifact_list"):
        return llm_response

    parts_new = copy.deepcopy(llm_response.content.parts)
    for filename in callback_context.state.get("music_artifact_list"):
        logger.info(f"Loading artifact: {filename}")

        if "GOOGLE_CLOUD_AGENT_ENGINE_ID" in os.environ:
            parts_new.append(types.Part.from_text(text=f"<artifact>{filename}</artifact>"))
            continue
        else:
            audio_artifact = await callback_context.load_artifact(filename=filename)
            if audio_artifact is None:
                continue

            audio_bytes = audio_artifact.inline_data.data
            mime_string = 'audio/mp3'
            parts_new.append(types.Part.from_bytes(data=audio_bytes, mime_type=mime_string))

    callback_context.state.update({"music_artifact_list": None})

    llm_response_new = copy.deepcopy(llm_response)
    llm_response_new.content.parts = parts_new
    return llm_response_new


root_agent = Agent(
    model='gemini-2.0-flash',
    name='root_agent',
    description='A helpful assistant for user questions.',
    instruction=instructions(),
    tools=[call_composer_agent],
    after_model_callback=load_artifact
)
