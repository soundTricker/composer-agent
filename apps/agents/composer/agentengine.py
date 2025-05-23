# -*- coding: utf-8 -*-
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import asyncio
from typing import Any, AsyncIterable

from google.adk.agents.run_config import StreamingMode, RunConfig
from google.adk.artifacts import BaseArtifactService
from vertexai.preview import reasoning_engines

class CustomAdkApp(reasoning_engines.AdkApp):
    def clone(self):
        """Returns a clone of the ADK application."""
        import copy

        return CustomAdkApp(
            agent=copy.deepcopy(self._tmpl_attrs.get("agent")),
            enable_tracing=self._tmpl_attrs.get("enable_tracing"),
            session_service_builder=self._tmpl_attrs.get("session_service_builder"),
            artifact_service_builder=self._tmpl_attrs.get("artifact_service_builder"),
        )
    """An ADK Application."""
    def stream_query_sse(
        self,
        *,
        message: str| dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        **kwargs,
    ):
        return self.stream_query(message=message, user_id=user_id, session_id=session_id, run_config=RunConfig(streaming_mode=StreamingMode.SSE), **kwargs)

    async def async_stream_query_sse(
        self,
        *,
        message: str| dict[str, Any],
        user_id: str,
        session_id: str | None = None,
        **kwargs,
    ) -> AsyncIterable[dict[str, Any]]:
        return self.async_stream_query(message=message, user_id=user_id, session_id=session_id, run_config=RunConfig(streaming_mode=StreamingMode.SSE), **kwargs)

    def load_artifact(self, user_id: str, session_id: str, artifact_id: str, **kwargs):

        import nest_asyncio
        nest_asyncio.apply()

        artifact_service: BaseArtifactService = self._tmpl_attrs["artifact_service"]
        return asyncio.run(artifact_service.load_artifact(
            app_name=self._tmpl_attrs.get("app_name"), user_id=user_id, session_id=session_id, filename=artifact_id)
        )

    def register_operations(self) -> dict[str, list[str]]:
        """Registers the operations of the ADK application."""
        return {
            "": [
                "get_session",
                "list_sessions",
                "create_session",
                "delete_session",
                "load_artifact"
            ],
            "stream": ["stream_query_sse", "stream_query", "streaming_agent_run_with_events"],
            "async_stream": ["async_stream_query_sse", "async_stream_query"],
        }
