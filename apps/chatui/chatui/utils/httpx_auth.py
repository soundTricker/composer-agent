import typing

import google.auth
import google.oauth2.credentials
import google.oauth2.id_token
import httpx
from google.auth.transport.requests import Request as AuthRequest
from httpx import Request, Response

from chatui.settings import Settings


class GoogleJWTAuth(httpx.Auth):
    def __init__(self, settings: Settings):
        self.settings = settings

    def auth_flow(self, request: Request) -> typing.Generator[Request, Response, None]:
        creds, _ = google.auth.default()

        creds.refresh(AuthRequest())
        if isinstance(creds, google.oauth2.credentials.Credentials):
            creds.apply(
                request.headers,
                creds.id_token
                if self.settings.BACKEND_TYPE == "remote"
                else creds.token,
            )
        else:
            # maybe run on cloud run
            auth_req = (
                google.auth.transport.requests.Request()
            )  # ty: ignore[unresolved-attribute]
            aud = self.settings.BACKEND_URL
            id_token = google.oauth2.id_token.fetch_id_token(auth_req, aud)
            request.headers["Authorization"] = (
                f"Bearer {id_token if self.settings.BACKEND_TYPE == 'remote' else creds.token}"
            )
        yield request