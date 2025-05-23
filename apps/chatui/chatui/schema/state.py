from .base import Base

class State(Base):
    session_id: str | None = None
    user_id: str | None = None