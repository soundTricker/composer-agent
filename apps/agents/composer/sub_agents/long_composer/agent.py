import asyncio
import io
import logging
import os
import uuid
from typing import AsyncGenerator

import websockets
from google import genai
from google.adk import Agent
from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.planners import BuiltInPlanner
from google.genai import types
from google.genai.live_music import AsyncMusicSession
from pydub import AudioSegment

from composer.schema.music_plan import MusicPlan
from composer.utils.audio import convert_mp3
from .prompts import instructions
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get('GEMINI_API_KEY')

BUFFER_SECONDS=1
MODEL='models/lyria-realtime-exp'

logger = logging.getLogger(__name__)

class LongComposerAgent(Agent):

    def __init__(self):
        super().__init__(
            name="LongComposerAgent",
            model='gemini-2.5-flash',
            description='An AI music Composer Agent',
            instruction=instructions(),
            planner=BuiltInPlanner(
                thinking_config=types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=-1,
                )
            ),
            output_key="music_plan_raw"
        )

class MusicPlanFormatAgent(Agent):
    def __init__(self):
        super().__init__(
            name="MusicPlanFormatAgent",
            model='gemini-2.5-flash',
            description='An AI music Composer Agent',
            instruction="""
You are an agent that formats the answers from LongComposerAgent agent.
# Your task
Read data from session state with key 'music_plan_raw' and format'
            """,
            output_key="music_plan",
            output_schema=MusicPlan
        )

class LongComposerFlowAgent(BaseAgent):

    async def _run_async_impl(
      self, ctx: InvocationContext
  ) -> AsyncGenerator[Event, None]:
        agent = SequentialAgent(name="ComposerFlowAgent", sub_agents=[LongComposerAgent(), MusicPlanFormatAgent()])
        async for event in agent.run_async(ctx):
            yield event

        results = await self.generate_music(ctx)

        music_artifact_list = ctx.session.state.get('music_artifact_list')

        artifact_delta = {}
        for artifact_id in music_artifact_list:
            artifact_delta[artifact_id] = 0

        event_actions = EventActions(state_delta={"music_artifact_list": ctx.session.state.get('music_artifact_list')}, artifact_delta=artifact_delta)

        yield Event(
            invocation_id=ctx.invocation_id,
            id=Event.new_id(),
            content=results,
            author=self.name,
            actions=event_actions,
            branch=ctx.branch,
        )


    async def generate_music(self, ctx: InvocationContext) -> types.Content | None:

        client = genai.Client(vertexai=False, api_key=API_KEY, http_options={'api_version': 'v1alpha'})

        music_plan_dict: dict = ctx.session.state.get('music_plan')
        music_plan = MusicPlan.model_validate(music_plan_dict)

        initial = True
        audio_byte_array = bytearray()
        async def receive_audio(session: AsyncMusicSession):
            """Example background task to process incoming audio."""

            chunks_count = 0
            logger.info("start receive music")

            try:
                async for message in session.receive():
                    chunks_count += 1
                    if chunks_count == 1:
                        # Introduce a delay before starting playback to have a buffer for network jitter.
                        await asyncio.sleep(BUFFER_SECONDS)

                    if message.server_content:
                        audio_data = message.server_content.audio_chunks[0].data
                        audio_byte_array.extend(audio_data)
                    elif message.filtered_prompt:
                        logger.info(f"Prompt was filtered out: {message.filtered_prompt}")
                    else:
                        logger.info(f"Unknown error occured with message: {message}")

                    await asyncio.sleep(10**-12)
            except websockets.exceptions.ConnectionClosedOK:
                # nothing to do
                pass
            except Exception as e:
                logger.exception(f"got error {e}")

        prev_config = None
        async with (
            asyncio.TaskGroup() as tg,
            client.aio.live.music.connect(model="models/lyria-realtime-exp") as session,
        ):
            # Set up task to receive server messages.
            tg.create_task(receive_audio(session))
            for stanza in music_plan.stanzas:
                logger.info(f"next stanza {stanza}")
                # Send initial prompts and config
                await session.set_weighted_prompts(prompts=stanza.to_gemini_prompts())
                if prev_config != stanza.config:
                    logger.info(f"set music config {stanza.config}")
                    await session.set_music_generation_config(config=stanza.to_gemini_config())
                    if prev_config and (prev_config.scale != stanza.config.scale or prev_config.bpm != stanza.config.bpm):
                        await session.reset_context()

                prev_config = stanza.config
                if initial:
                    # Start streaming music
                    logger.info("start session")
                    await session.play()
                    initial = False
                logger.info(f"sleep {stanza.seconds}")
                await asyncio.sleep(stanza.seconds)

            logger.info("session stop")
            await session.pause()

        logger.info("save audio")
        return await self.save_audio(ctx, audio_byte_array)


    async def save_audio(self, ctx: InvocationContext, audio_byte_array: bytearray) -> types.Content:
        audio_segment = AudioSegment.from_raw(io.BytesIO(audio_byte_array), sample_width=2, frame_rate=48000, channels=2)

        part = types.Part.from_bytes(data=convert_mp3(audio_segment), mime_type="audio/mp3")

        artifact_id = uuid.uuid4().hex
        await ctx.artifact_service.save_artifact(app_name=ctx.app_name, user_id=ctx.user_id, session_id=ctx.session.id, filename=artifact_id, artifact=part)

        ctx.session.state.update({"music_artifact_list": [artifact_id]})

        if "GOOGLE_CLOUD_AGENT_ENGINE_ID" in os.environ:
            return types.Content(parts=[types.Part.from_text(text=f"<artifact>{artifact_id}</artifact>")], role="model")

        return types.Content(parts=[part], role="model")


root_agent = LongComposerFlowAgent(name="LongComposerFlowAgent")
