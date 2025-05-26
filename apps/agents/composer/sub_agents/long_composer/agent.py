import io
import logging
import os
import uuid
from typing import AsyncGenerator

from google.adk import Agent
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai.live_music import AsyncMusicSession
from pydub import AudioSegment

from .prompts import instructions
from composer.schema.music_plan import MusicPlan
from composer.utils.audio import convert_mp3
from google.genai import types
from google import genai
import asyncio


API_KEY = os.environ.get('GEMINI_API_KEY')

BUFFER_SECONDS=1
MODEL='models/lyria-realtime-exp'

logger = logging.getLogger(__name__)

class LongComposerAgent(Agent):

    def __init__(self):
        super().__init__(
            name="LongComposerAgent",
            model='gemini-2.0-flash',
            description='An AI music Composer Agent.',
            instruction=instructions(),
            output_schema=MusicPlan,
            output_key='music_plan',
        )

class LongComposerFlowAgent(BaseAgent):

    audio_byte_array: bytearray = bytearray()

    async def _run_async_impl(
      self, ctx: InvocationContext
  ) -> AsyncGenerator[Event, None]:
        agent = LongComposerAgent()
        async for event in agent.run_async(ctx):
            yield event

        yield Event(content=await self.generate_music(ctx), author=self.name)


    async def generate_music(self, ctx: InvocationContext) -> types.Content | None:

        client = genai.Client(vertexai=False, api_key=API_KEY, http_options={'api_version': 'v1alpha'})

        music_plan_dict: dict = ctx.session.state.get('music_plan')
        music_plan = MusicPlan.model_validate(music_plan_dict)

        initial = True

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
                        self.audio_byte_array.extend(audio_data)
                    elif message.filtered_prompt:
                        logger.info(f"Prompt was filtered out: {message.filtered_prompt}")
                    else:
                        logger.info(f"Unknown error occured with message: {message}")

                    await asyncio.sleep(10**-12)
            except Exception as e:
                logger.exception(f"got error {e}")

        prev_config = None
        async with (
            asyncio.TaskGroup() as tg,
            client.aio.live.music.connect(model='models/lyria-realtime-exp') as session,
        ):
            # Set up task to receive server messages.
            tg.create_task(receive_audio(session))
            for stanza in music_plan.stanzas:
                logger.info(f"next stanza {stanza}")
                # Send initial prompts and config
                await session.set_weighted_prompts(
                    prompts=stanza.to_gemini_prompts()
                )
                if prev_config != stanza.config:
                    logger.info(f"set music config {stanza.config}")
                    await session.set_music_generation_config(
                        config=stanza.to_gemini_config()
                    )
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
        return await self.save_audio(ctx)


    async def save_audio(self, ctx: InvocationContext) -> types.Content:
        audio_segment = AudioSegment.from_raw(io.BytesIO(self.audio_byte_array), sample_width=2, frame_rate=48000, channels=2)

        part = types.Part.from_bytes(data=convert_mp3(audio_segment), mime_type="audio/mp3")

        artifact_id = uuid.uuid4().hex
        await ctx.artifact_service.save_artifact(app_name=ctx.app_name, user_id=ctx.user_id, session_id=ctx.session.id, filename=artifact_id, artifact=part)

        ctx.session.state.update({"music_artifact_list": [artifact_id]})
        return types.Content(parts=[part])


root_agent = LongComposerFlowAgent(name="LongComposerFlowAgent")
