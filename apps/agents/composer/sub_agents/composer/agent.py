from google.adk.agents import Agent
from .tools import generate_music_tool
from .prompts import instructions

root_agent = Agent(
    model='gemini-2.0-flash',
    name='ComposerAgent',
    description='An AI music Composer Agent.',
    instruction=instructions(),
    tools=[generate_music_tool]
)
