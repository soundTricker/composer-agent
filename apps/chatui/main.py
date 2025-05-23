import re
import sys
import uuid
import logging
import chainlit as cl
from google.adk.events import Event
from google.genai import types
from pydantic.v1 import ValidationError

from chatui.schema.state import State
from chatui.services.chat_api import get_chat_api
from chatui.settings import get_settings

from engineio.payload import Payload
import dotenv

dotenv.load_dotenv()

Payload.max_decode_packets = 512

SETTINGS = get_settings()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

chat = get_chat_api(SETTINGS)

tool_name_map = {
    "ComposerAgent": "作曲エージェント"
}

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="何ができますか？",
            message="何ができますか？",
            ),

        cl.Starter(
            label="Generate Progressive House",
            message="軽快で爽快感のあるアップテンポなプログレッシブハウス",
            ),
        ]

@cl.on_chat_start
def setup():
    """Initialize the chat session."""
    state_dict = cl.user_session.get('state', {})
    state = State.model_validate(state_dict)
    if state.user_id is None:
        state.user_id = uuid.uuid4().hex

    session = chat.create_session(state.user_id)
    state.session_id = session.id
    cl.user_session.set('state', state.model_dump())

async def handle_error(event_dict):
    """Handle error events from the chat API."""
    if "error" in event_dict:
        await cl.Message(content=event_dict["error"]["message"]).send()
        return True
    if "error_message" in event_dict:
        await cl.Message(content=event_dict["error_message"]).send()
        return True
    if "error_code" in event_dict:
        await cl.Message(content=event_dict["error_code"]).send()
        return True
    return False

async def process_artifacts(event, state, partial_msg=None):
    """Process artifacts in event content."""
    elements = []
    for part in event.content.parts:
        if part.text and SETTINGS.BACKEND_TYPE == "agentengine" and "<artifact>" in part.text:
            logger.info("found the artifact")
            artifacts = re.findall(r"<artifact>(.+?)</artifact>", part.text)
            for artifact in artifacts:
                mp3file_dict = chat.load_artifact(user_id=state.user_id, session_id=state.session_id, artifact_id=artifact)
                artifact = types.Part.model_validate(mp3file_dict)
                elements.append(cl.Audio(name="audio.mp3", display="inline", content=artifact.inline_data.data))

    if elements:
        if partial_msg is None:
            partial_msg = cl.Message(content="", elements=elements)
            await partial_msg.send()
        else:
            partial_msg.elements = elements
            await partial_msg.update()

    return partial_msg, elements

async def handle_partial_event(event, state, partial_msg):
    """Handle partial events from the chat API."""
    # Process artifacts in partial event
    partial_msg, _ = await process_artifacts(event, state, partial_msg)

    # Handle text content in partial event
    if event.content.parts[-1].text:
        if partial_msg is None:
            partial_msg = cl.Message(content=event.content.parts[-1].text)
            await partial_msg.send()
        else:
            await partial_msg.stream_token(event.content.parts[-1].text)

    # Handle inline data in partial event
    if event.content.parts[-1].inline_data:
        elements = [cl.Audio(name="audio.mp3", display="inline", content=event.content.parts[-1].inline_data.data)]
        if partial_msg is None:
            partial_msg = cl.Message(content="", elements=elements)
            await partial_msg.send()
        else:
            partial_msg.elements = elements
            await partial_msg.update()

    return partial_msg

async def handle_function_call(event, current_tool):
    """Handle function call events from the chat API."""
    fc = event.content.parts[-1].function_call
    current_tool = cl.Step(
        name=f"🛠{tool_name_map[fc.name]}に問い合わせ中...", 
        type="tool", 
        metadata={"name": fc.name, "args": fc.args}, 
        id=fc.id
    )
    current_tool.input = fc.args
    await current_tool.__aenter__()
    return current_tool

async def handle_function_response(event, current_tool):
    """Handle function response events from the chat API."""
    fr = event.content.parts[-1].function_response
    current_tool.name = f"✔️ {tool_name_map[fr.name]}への問い合わせ完了"
    current_tool.output = fr.response
    await current_tool.__aexit__(None, None, None)
    return None

async def handle_inline_data(event, partial_msg):
    """Handle inline data events from the chat API."""
    part = event.content.parts[-1]
    elements = [cl.Audio(name="audio.mp3", display="inline", content=part.inline_data.data)]

    if partial_msg:
        partial_msg.elements = elements
        await partial_msg.update()
    else:
        await cl.Message(content="", elements=elements).send()

    return partial_msg

async def handle_text_content(event, partial_msg):
    """Handle text content events from the chat API."""
    logger.info(f"update content {event.content.parts[-1].text}")
    if partial_msg:
        logger.info("update partial msg")
        partial_msg.content = event.content.parts[-1].text
        await partial_msg.update()
        return None
    else:
        logger.info("send new message")
        await cl.Message(content=event.content.parts[-1].text).send()
        return None

@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages from the user."""
    state_dict = cl.user_session.get("state", {})
    state = State.model_validate(state_dict)

    current_tool = None
    partial_msg = None

    async for event_dict in chat.async_stream_query(message=message.content, user_id=state.user_id, session_id=state.session_id):
        logging.info(f"fetch event: {event_dict}")

        # Handle errors
        if await handle_error(event_dict):
            return

        try:
            event = Event.model_validate(event_dict)
        except ValidationError as e:
            await cl.context.emitter.send_toast(message=f"Got Error: {e}, {event_dict}", type="error")
            return

        # Handle partial events
        if event.partial:
            partial_msg = await handle_partial_event(event, state, partial_msg)
            continue

        # Handle function calls
        if event.content.parts[-1].function_call:
            current_tool = await handle_function_call(event, current_tool)
            continue

        # Handle function responses
        if event.content.parts[-1].function_response:
            current_tool = await handle_function_response(event, current_tool)
            continue

        # Handle inline data
        if event.content.parts[-1].inline_data:
            partial_msg = await handle_inline_data(event, partial_msg)
            continue

        # Process artifacts
        partial_msg, _ = await process_artifacts(event, state, partial_msg)

        # Handle text content
        if event.content.parts[-1].text:
            partial_msg = await handle_text_content(event, partial_msg)
