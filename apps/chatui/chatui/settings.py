from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


BackendType = Literal['agentengine', 'remote']

class Settings(BaseSettings):
    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_LOCATION: str
    BACKEND_TYPE: BackendType= 'local'
    BACKEND_URL: str|None = 'http://localhost:8000'
    GOOGLE_CLOUD_AGENT_ENGINE_ID: str|None = None
    CHAINLIT_AUTH_SECRET: str|None = None

    model_config = SettingsConfigDict(
        env_file=".env",
    )

    @property
    def backend_url(self):
        if self.BACKEND_TYPE != 'agentengine':
            return self.BACKEND_URL
        return f"https://{self.GOOGLE_CLOUD_LOCATION}-aiplatform.googleapis.com/v1/{self.agent_engine_name}",

    @property
    def agent_engine_name(self):
        return f"projects/{self.GOOGLE_CLOUD_PROJECT}/locations/{self.GOOGLE_CLOUD_LOCATION}/reasoningEngines/{self.GOOGLE_CLOUD_AGENT_ENGINE_ID}"


def get_settings() -> Settings:
    return Settings()
