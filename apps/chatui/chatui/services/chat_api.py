from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, Generator, AsyncIterable

import aiohttp
import requests
import vertexai
from google.adk.sessions import Session
from google.genai import types
from pydantic_core import from_json
from sseclient import SSEClient
from vertexai import agent_engines

from chatui.settings import Settings
from chatui.settings import get_settings
from aiohttp_sse_client import client as sse_client


class ChatAPI(ABC):

    settings: Settings = get_settings()

    @abstractmethod
    def get_session(self, user_id: str, session_id: str) -> Session | None:
        raise NotImplementedError("not implemented")

    @abstractmethod
    def list_sessions(self, user_id: str) -> list[Session]:
        raise NotImplementedError("not implemented")

    @abstractmethod
    def create_session(self, user_id: str, state: dict[str, Any] | None = None) -> Session:
        raise NotImplementedError("not implemented")

    @abstractmethod
    def stream_query(self, message: str | dict[str, Any],
        user_id: str,
        session_id: str|None = None,
        **kwargs) -> Generator[dict[str, Any], None, None]:
        raise NotImplementedError("not implemented")
    
    @abstractmethod
    async def async_stream_query(self, message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        **kwargs) -> AsyncIterable[dict[str, Any]]:
        raise NotImplementedError("not implemented")

    @abstractmethod
    def load_artifact(self, user_id: str,session_id: str, artifact_id: str):
        raise NotImplementedError("not implemented")


class VertexAIChatAPI(ChatAPI):

    app: agent_engines.AgentEngine

    def __init__(self):
        vertexai.init(project=self.settings.GOOGLE_CLOUD_PROJECT, location=self.settings.GOOGLE_CLOUD_LOCATION)
        self.app = agent_engines.get(self.settings.agent_engine_name)

    def get_session(self, user_id: str, session_id: str) -> Session | None:
        session = self.app.get_session(user_id=user_id, session_id=session_id)
        return Session.model_validate(session)
    def list_sessions(self, user_id: str) -> list[Session]:
        sessions = self.app.list_sessions(user_id=user_id)
        return [Session.model_validate(**s) for s in sessions]

    def load_artifact(self, user_id: str,session_id: str, artifact_id: str):
        return self.app.load_artifact(user_id=user_id, session_id=session_id, artifact_id=artifact_id)

    def create_session(self, user_id: str, session_id: str|None = None, state: dict[str, Any] | None = None) -> Session:
        session = self.app.create_session(user_id=user_id, session_id=session_id, state=state)
        return Session.model_validate(session)

    def stream_query(self, message: str | dict[str, Any], user_id: str, session_id: str | None = None, **kwargs) -> Generator[dict[str, Any], None, None]:
        for event in self.app.stream_query_sse(message=message, user_id=user_id, session_id=session_id, **kwargs):
            yield event

    async def async_stream_query(self, message: str | dict[str, Any], user_id: str, session_id: str | None = None, **kwargs) -> AsyncIterable[dict[str, Any]]:
        async for event in self.app.async_stream_query_sse(message=message, user_id=user_id, session_id=session_id):
            yield event


class LocalChatAPI(ChatAPI):
    
    app_name: str = "composer"
    
    def __init__(self, app_name="composer"):
        self.app_name = app_name
        super().__init__()
        
    
    def get_session(self, user_id: str, session_id: str) -> Session | None:
        res = requests.get(f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions/{session_id}")

        if res.status_code != 200:
            return None

        return Session.model_validate(res.json())

    def list_sessions(self, user_id: str) -> list[Session]:
        res = requests.get(f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions")
        return [Session.model_validate(j) for j in res.json()]


    def create_session(self, user_id: str, state: dict[str, Any] | None = None) -> Session:

        res = requests.post(f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions", json=state, timeout=(3.0, 7.5))


        return Session.model_validate(res.json())

    def stream_query(self, message: str | dict[str, Any], user_id: str, session_id: str | None = None, **kwargs) -> Generator[dict[str, Any], None, None]:

        new_message = types.UserContent(parts=[types.Part(text=message)])
        res = requests.post(
            f"{self.settings.backend_url}/run_sse",
            json={
                "app_name": self.app_name,
                "user_id": user_id,
                "session_id": session_id,
                "new_message": new_message.to_json_dict(),
                "streaming": True,
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            stream=True,
        )

        client = SSEClient(res)
        for event in client.events():
            yield from_json(event.data)

    async def async_stream_query(self, message: str | dict[str, Any], user_id: str, session_id: str | None = None,
                                 **kwargs) -> AsyncIterable[dict[str, Any]]:
        new_message = types.UserContent(parts=[types.Part(text=message)])

        def on_error():
            raise StopAsyncIteration
        async with aiohttp.ClientSession(read_bufsize=5000000) as session, sse_client.EventSource(
            f"{self.settings.backend_url}/run_sse",
            session=session,
            reconnection_time=timedelta(seconds=3600),
            max_connect_retry=0,
            option={
                "method": "POST",
                "headers":{
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                }
            },
            json={
                "app_name": self.app_name,
                "user_id": user_id,
                "session_id": session_id,
                "new_message": new_message.to_json_dict(),
                "streaming": True
            },
            on_error=on_error
        ) as event_source:
            async for event in event_source:
                yield from_json(event.data)
        #
        # res = requests.post(
        #     f"{self.settings.backend_url}/run_sse",
        #     json={
        #         "app_name": self.app_name,
        #         "user_id": user_id,
        #         "session_id": session_id,
        #         "new_message": new_message.to_json_dict(),
        #         "streaming": True
        #     },
        #     headers={
        #         "Content-Type": "application/json",
        #         "Accept": "text/event-stream",
        #     },
        #     stream=True,
        # )
        #
        # client = SSEClient(res)
        # for event in client.events():
        #     yield from_json(event.data)

def get_chat_api(settings: Settings) -> ChatAPI:
    if settings.BACKEND_TYPE == 'remote':
        return LocalChatAPI()
    elif settings.BACKEND_TYPE == 'agentengine':
        return VertexAIChatAPI()
    else:
        raise ValueError(f"Unknown backend type: {settings.BACKEND_TYPE}")
