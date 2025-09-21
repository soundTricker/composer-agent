from abc import ABC, abstractmethod
from typing import Any, AsyncIterable, Generator

import httpx
import vertexai
from fastapi import Depends
from google.adk.sessions import Session
from google.genai import types
from httpx_sse import aconnect_sse, connect_sse
from pydantic_core import from_json
from vertexai import agent_engines

from chatui.settings import Settings, get_settings
from chatui.utils.httpx_auth import GoogleJWTAuth


class ChatAPI(ABC):
    settings: Settings = get_settings()

    @abstractmethod
    async def get_session(self, user_id: str, session_id: str) -> Session | None:
        raise NotImplementedError("not implemented")

    @abstractmethod
    async def list_sessions(self, user_id: str) -> list[Session]:
        raise NotImplementedError("not implemented")

    @abstractmethod
    async def create_session(
        self, user_id: str, state: dict[str, Any] | None = None
    ) -> Session:
        raise NotImplementedError("not implemented")

    @abstractmethod
    async def delete_session(self, user_id: str, session_id: str) -> None:
        raise NotImplementedError("not implemented")

    @abstractmethod
    def stream_query(
        self,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        **kwargs,
    ) -> Generator[dict[str, Any], None, None]:
        raise NotImplementedError("not implemented")

    @abstractmethod
    async def async_stream_query(
        self,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        **kwargs,
    ) -> AsyncIterable[dict[str, Any]]:
        raise NotImplementedError("not implemented")

    @abstractmethod
    async def load_artifact(
        self, user_id: str, session_id: str, artifact_id: str
    ) -> types.Part:
        raise NotImplementedError("not implemented")


class VertexAIRESTChatAPI(ChatAPI):
    async def __async_query(
        self, *, method: str, user_id: str, session_id: str = None, **kwargs
    ):
        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings), timeout=600
        ) as client:
            param = {
                "user_id": user_id,
                "session_id": session_id,
            }

            if kwargs:
                param.update(kwargs)

            data = {"class_method": method, "input": param}
            res = await client.post(f"{self.settings.backend_url}:query", json=data)
            return res

    async def get_session(self, user_id: str, session_id: str) -> Session | None:
        res = await self.__async_query(
            method="get_session",
            user_id=user_id,
            session_id=session_id,
        )
        if res.status_code != 200:
            return None
        else:
            return Session.model_validate(res.json())

    async def list_sessions(self, user_id: str) -> list[Session]:
        res = await self.__async_query(
            method="get_session",
            user_id=user_id,
        )
        if res.status_code != 200:
            return []
        else:
            return [Session.model_validate(s) for s in res.json()]

    async def load_artifact(
        self, user_id: str, session_id: str, artifact_id: str
    ) -> types.Part | None:
        res = await self.__async_query(
            method="load_artifact",
            user_id=user_id,
            session_id=session_id,
            artifact_id=artifact_id,
        )
        if res.status_code != 200:
            return None
        else:
            return types.Part.model_validate(res.json())

    async def create_session(
        self,
        user_id: str,
        session_id: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> Session:
        res = await self.__async_query(
            method="create_session",
            user_id=user_id,
            session_id=session_id,
            state=state,
        )
        res.raise_for_status()
        return Session.model_validate(res.json()["output"])

    async def delete_session(self, user_id: str, session_id: str) -> None:
        await self.__async_query(
            method="delete_session",
            user_id=user_id,
            session_id=session_id,
        )

    def stream_query(
        self,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        streaming=False,
        **kwargs,
    ) -> Generator[dict[str, Any], None, None]:
        with httpx.Client(
            auth=GoogleJWTAuth(settings=self.settings), timeout=None
        ) as client:
            new_message = types.UserContent(parts=[types.Part(text=message)])

            with connect_sse(
                client,
                "POST",
                url=f"{self.settings.backend_url}:streamQuery?alt=sse",
                params={"alt": "sse"},
                json={
                    "class_method": "stream_query",
                    "input": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "message": new_message.to_json_dict(),
                    },
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ) as event_source:
                for sse in event_source.iter_sse():
                    yield from_json(sse.data)

    async def async_stream_query(
        self,
        message: str | dict[str, Any] | types.Content,
        user_id: str,
        session_id: str | None = None,
        streaming=False,
        **kwargs,
    ) -> AsyncIterable[dict[str, Any]]:
        if not isinstance(message, types.Content) and not isinstance(
            message, types.UserContent
        ):
            new_message = types.UserContent(parts=[types.Part(text=message)])
        else:
            new_message = message

        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings),
            timeout=None,
        ) as client:
            async with aconnect_sse(
                client,
                "POST",
                url=f"{self.settings.backend_url}:streamQuery?alt=sse",
                params={"alt": "sse"},
                json={
                    "class_method": "async_stream_query",
                    "input": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "message": new_message.to_json_dict(),
                    },
                },
                headers={
                    "Content-Type": "application/json",
                },
            ) as event_source:
                content_type = event_source.response.headers.get(
                    "content-type", ""
                ).partition(";")[0]

                print(event_source.response.headers.get("content-type", ""))

                if "text/event-stream" not in content_type:
                    text = await event_source.response.aread()
                    yield from_json(text)
                    return
                    # decoder = SSEDecoder()
                    # async for line in event_source.response.aiter_lines():
                    #     line = line.rstrip("\n")
                    #     sse = decoder.decode(line)
                    #     if sse is not None:
                    #         yield from_json(sse.data)
                    # return

                async for sse in event_source.aiter_sse():
                    yield from_json(sse.data)


class VertexAIChatAPI(ChatAPI):
    app: agent_engines.AgentEngine

    def __init__(self):
        vertexai.init(
            project=self.settings.GOOGLE_CLOUD_PROJECT,
            location=self.settings.GOOGLE_CLOUD_LOCATION,
        )
        self.client = vertexai.Client(
            project=self.settings.GOOGLE_CLOUD_PROJECT,
            location=self.settings.GOOGLE_CLOUD_LOCATION,
            http_options=types.HttpOptions(
                api_version="v1beta1", base_url=f"https://{self.settings.GOOGLE_CLOUD_LOCATION}-aiplatform.googleapis.com/"
            ),
        )
        self.app = self.client.agent_engines.get(name=self.settings.agent_engine_name)

    async def get_session(self, user_id: str, session_id: str) -> Session | None:
        session = await self.app.async_get_session(
            user_id=user_id, session_id=session_id
        )
        return Session.model_validate(session)

    async def list_sessions(self, user_id: str) -> list[Session]:
        sessions = await self.app.async_list_sessions(user_id=user_id)
        return [Session.model_validate(**s) for s in sessions]

    async def load_artifact(self, user_id: str, session_id: str, artifact_id: str):
        return await self.app.load_artifact(
            user_id=user_id, session_id=session_id, artifact_id=artifact_id
        )

    async def create_session(
        self,
        user_id: str,
        session_id: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> Session:
        session = await self.app.async_create_session(
            user_id=user_id, session_id=session_id, state=state
        )
        return Session.model_validate(session)

    async def delete_session(self, user_id: str, session_id: str) -> None:
        await self.app.async_delete_session(user_id=user_id, session_id=session_id)

    def stream_query(
        self,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        **kwargs,
    ) -> Generator[dict[str, Any], None, None]:
        for event in self.app.stream_query_sse(
            message=message, user_id=user_id, session_id=session_id, **kwargs
        ):
            yield event

    async def async_stream_query(
        self,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        **kwargs,
    ) -> AsyncIterable[dict[str, Any]]:
        if isinstance(message, types.Content):
            message = message.model_dump()

        return self.app.async_stream_query(
            message=message, user_id=user_id, session_id=session_id
        )


class RemoteChatAPI(ChatAPI):
    app_name: str = "composer"

    def __init__(self, app_name="composer"):
        self.app_name = app_name
        super().__init__()

    async def get_session(self, user_id: str, session_id: str) -> Session | None:
        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings), timeout=600
        ) as client:
            res = await client.get(
                f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions/{session_id}"
            )
            if res.status_code != 200:
                return None
            else:
                return Session.model_validate(res.json())

    async def delete_session(self, user_id: str, session_id: str) -> None:
        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings), timeout=600
        ) as client:
            res = await client.delete(
                f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions/{session_id}"
            )
            res.raise_for_status()

    async def list_sessions(self, user_id: str) -> list[Session]:
        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings), timeout=600
        ) as client:
            res = await client.get(
                f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions"
            )
            return [Session.model_validate(j) for j in res.json()]

    async def create_session(
        self, user_id: str, state: dict[str, Any] | None = None
    ) -> Session:
        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings), timeout=600
        ) as client:
            res = await client.post(
                f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions",
                json={"state": state},
            )
            return Session.model_validate(res.json())

    async def load_artifact(self, user_id: str, session_id: str, artifact_id: str):
        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings), timeout=600
        ) as client:
            res = await client.get(
                f"{self.settings.backend_url}/apps/{self.app_name}/users/{user_id}/sessions/{session_id}/artifacts/{artifact_id}"
            )
            if "detail" in res.json() and res.json()["detail"] == "Artifact not found":
                return None
            return types.Part.model_validate(res.json())

    def stream_query(
        self,
        message: str | dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        streaming=False,
        **kwargs,
    ) -> Generator[dict[str, Any], None, None]:
        with httpx.Client(
            auth=GoogleJWTAuth(settings=self.settings), timeout=None
        ) as client:
            new_message = types.UserContent(parts=[types.Part(text=message)])

            with connect_sse(
                client,
                "POST",
                f"{self.settings.backend_url}/run_sse",
                json={
                    "app_name": self.app_name,
                    "user_id": user_id,
                    "session_id": session_id,
                    "new_message": new_message.to_json_dict(),
                    "streaming": streaming,
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ) as event_source:
                for sse in event_source.iter_sse():
                    yield from_json(sse.data)

    async def async_stream_query(
        self,
        message: str | dict[str, Any] | types.Content,
        user_id: str,
        session_id: str | None = None,
        streaming=False,
        **kwargs,
    ) -> AsyncIterable[dict[str, Any]]:
        if not isinstance(message, types.Content) and not isinstance(
            message, types.UserContent
        ):
            new_message = types.UserContent(parts=[types.Part(text=message)])
        else:
            new_message = message

        async with httpx.AsyncClient(
            auth=GoogleJWTAuth(settings=self.settings), timeout=None
        ) as client:
            async with aconnect_sse(
                client,
                "POST",
                f"{self.settings.backend_url}/run_sse",
                json={
                    "app_name": self.app_name,
                    "user_id": user_id,
                    "session_id": session_id,
                    "new_message": new_message.to_json_dict(),
                    "streaming": streaming,
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ) as event_source:
                async for sse in event_source.aiter_sse():
                    print(sse.data)
                    yield from_json(sse.data)


def get_chat_api(settings: Settings = Depends(get_settings)) -> ChatAPI:
    if settings.BACKEND_TYPE == "remote":
        return RemoteChatAPI()
    elif settings.BACKEND_TYPE == "agentengine":
        return VertexAIChatAPI()
    elif settings.BACKEND_TYPE == "agentenginerest":
        return VertexAIRESTChatAPI()
    else:
        raise ValueError(f"Unknown backend type: {settings.BACKEND_TYPE}")
