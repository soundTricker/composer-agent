import re
import sys
import uuid
import logging
from typing import Any

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
    "ComposerAgent": "作曲エージェント",
    "LongComposerFlowAgent": "作曲エージェント",
    "LongComposerAgent": "作曲エージェント"
}

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="何ができますか？",
            message="何ができますか？",
            ),

        cl.Starter(
            label="プロンプトサンプル1",
            message="30秒以内の軽快で爽快感のあるアップテンポなプログレッシブハウスを作成して。ボーカルは入れて",
            ),

        cl.Starter(
            label="プロンプトサンプル2",
            message="""
            BPM: 120
            ジャンル: Deep Houseと80's Funkをあわせたような曲
            楽器: Jazz Piano、サックス、Electric Drums、ボーカルあり
            雰囲気: 夜のクラブで聴くような少し落ち着いたDanceableな曲
            長さ: 2分前後
            進行:
                開始(8小節): ドラムとベースをミュート、Jazz Pianoとサックスのみで演奏
                序盤: Jazz Pianoとサックス、ドラム、ベース、ボーカルを追加
                中盤1(8小節): 小休止でJazz Pianoとボーカルだけのメロディライン
                中盤2: Jazz Pianoとサックス、ドラム、ベース、ボーカルを追加
                終盤(8小節): ドラムとベースのみ
            """,
        ),
        cl.Starter(
            label="プロンプトサンプル3",
            message="""
        BPM: 100
        ジャンル: Arab Gangsta
        楽器: ボコーダー、男性ボーカル、その他
        雰囲気: slick doggのようなギャングスタスタイル
        長さ: 2分前後
        進行:
            開始(8小節): ドラムとベースのみ
            序盤-中盤: ボコーダーや男性ボーカルサウンド
            終盤(8小節): ドラムとベースをミュート
        """,
        ),
        cl.Starter(
            label="プロンプトサンプル4",
            message="""
    BPM: 130
    ジャンル: Big Beat and Techno
    楽器: お任せ
    雰囲気: Fatboy Slim(Norman Cook)のようなデジタル感あふれるグルーブサウンド
    長さ: 2分前後
    進行:
        お任せ、開始と中盤、終わりがわかるように展開がある進行で
    """,
        ),
        cl.Starter(
            label="プロンプトサンプル5",
            message="""
    BPM: 120
    ジャンル: ブレイクダンスミュージック
    楽器: お任せ
    雰囲気: DJ Def Cutのようなブレイクダンスで利用できるアップテンポで攻撃的なサウンド
    長さ: 2分前後
    進行:
        お任せ
    """,
        ),
    ]

@cl.on_chat_start
async def setup():
    """Initialize the chat session."""
    state_dict = cl.user_session.get('state', {})
    state = State.model_validate(state_dict)
    if state.user_id is None:
        state.user_id = uuid.uuid4().hex

    session = await chat.create_session(state.user_id)
    state.session_id = session.id
    cl.user_session.set('state', state.model_dump())

async def handle_error(event_dict):
    """Handle error events from the chat API."""
    if (
            "error" in event_dict
            and isinstance(event_dict["error"], dict)
            and "message" in event_dict["error"]
    ):
        cl.context.emitter.send_toast(
            message=f"Got error: {event_dict['error']['message']}", type="error"
        )
        return True
    if "error" in event_dict:
        cl.context.emitter.send_toast(
            message=f"Got error: {event_dict['error']}", type="error"
        )
        return True
    if "errorMessage" in event_dict:
        cl.context.emitter.send_toast(
            message=f"Got error: {event_dict['errorMessage']}", type="error"
        )
        return True
    if "error_message" in event_dict:
        cl.context.emitter.send_toast(
            message=f"Got error: {event_dict['error_message']}", type="error"
        )
        return True
    if "error_code" in event_dict:
        cl.context.emitter.send_toast(
            message=f"Got error: {event_dict['error_code']}", type="error"
        )
        return True
    return False

async def process_artifacts(part, state, partial_msg=None):
    """Process artifacts in event content."""
    elements = []
    if part.text and SETTINGS.BACKEND_TYPE == "agentengine" and "<artifact>" in part.text:
        logger.info("found the artifact")
        artifacts = re.findall(r"<artifact>(.+?)</artifact>", part.text)
        for artifact in artifacts:
            mp3file_dict = await chat.load_artifact(user_id=state.user_id, session_id=state.session_id,
                                                    artifact_id=artifact)
            artifact = types.Part.model_validate(mp3file_dict)
            elements.append(cl.Audio(name="audio.mp3", display="inline", content=artifact.inline_data.data))

    if not elements:
        return partial_msg, elements

    if partial_msg is None:
        partial_msg = cl.Message(content="", elements=elements)
        await partial_msg.send()
    else:
        partial_msg.elements = elements
        await partial_msg.update()

    return partial_msg, elements

async def handle_partial_event(part, state, partial_msg):
    """Handle partial events from the chat API."""
    # Process artifacts in partial event
    partial_msg, _ = await process_artifacts(part, state, partial_msg)

    # Handle text content in partial event
    if part.text:
        if partial_msg is None:
            partial_msg = cl.Message(content=part.text)
            await partial_msg.send()
        else:
            await partial_msg.stream_token(part.text)

    # Handle inline data in partial event
    if part.inline_data:
        elements = [cl.Audio(name="audio.mp3", display="inline", content=part.inline_data.data)]
        if partial_msg is None:
            partial_msg = cl.Message(content="", elements=elements)
            await partial_msg.send()
        else:
            partial_msg.elements = elements
            await partial_msg.update()

    return partial_msg

async def handle_function_call(part, current_tool):
    """Handle function call events from the chat API."""
    fc = part.function_call
    current_tool = cl.Step(
        name=f"🛠{tool_name_map[fc.name]}に問い合わせ中...", 
        type="tool", 
        metadata={"name": fc.name, "args": fc.args}, 
        id=fc.id
    )
    current_tool.input = fc.args
    return await current_tool.__aenter__()

async def handle_function_response(part, current_tool):
    """Handle function response events from the chat API."""
    fr = part.function_response
    current_tool.name = f"✔️ {tool_name_map[fr.name]}への問い合わせ完了"
    current_tool.output = fr.response
    return await current_tool.__aexit__(None, None, None)

async def handle_inline_data(part, partial_msg):
    """Handle inline data events from the chat API."""
    elements = [cl.Audio(name="audio.mp3", display="inline", content=part.inline_data.data)]

    if partial_msg:
        partial_msg.elements = elements
        await partial_msg.update()
    else:
        await cl.Message(content="", elements=elements).send()

    return partial_msg

async def handle_text_content(part, partial_msg):
    """Handle text content events from the chat API."""
    logger.info(f"update content {part.text}")
    if partial_msg:
        logger.info("update partial msg")
        partial_msg.content = part.text
        await partial_msg.update()
        return None
    else:
        logger.info("send new message")
        await cl.Message(content=part.text).send()
        return None

@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages from the user."""
    state_dict = cl.user_session.get("state", {})
    state = State.model_validate(state_dict)
    content = message.content
    partial_msg = cl.Message(
        content="",
    )
    await partial_msg.stream_token(token=" ")
    await process_streaming_query(content, state, partial_msg=partial_msg)

async def process_streaming_query(
        content: str | dict[str, Any] | types.Content,
        state: State,
        partial_msg=None,
):
    current_tool = None

    res = await chat.async_stream_query(message=content, user_id=state.user_id, session_id=state.session_id)
    async for event_dict in res:
        logging.info(f"fetch event: {event_dict}")

        # Handle errors
        if await handle_error(event_dict):
            return

        try:
            event = Event.model_validate(event_dict)
        except ValidationError as e:
            cl.context.emitter.send_toast(message=f"Got Error: {e}, {event_dict}", type="error")
            return

        # Handle partial events
        if event.partial:
            for part in event.content.parts:
                partial_msg = await handle_partial_event(part, state, partial_msg)
            continue

        for part in event.content.parts:
            # Handle function calls
            if part.function_call and not part.function_response:
                current_tool = await handle_function_call(part, current_tool)

            # Handle function responses
            if part.function_response:
                current_tool = await handle_function_response(part, current_tool)

            # Handle inline data
            if part.inline_data:
                partial_msg = await handle_inline_data(part, partial_msg)

            # Process artifacts
            partial_msg, _ = await process_artifacts(part, state, partial_msg)

            # Handle text content
            if part.text:
                partial_msg = await handle_text_content(part, partial_msg)
