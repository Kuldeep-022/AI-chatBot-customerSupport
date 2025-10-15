from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class UserMessage:
    text: str


class LlmChat:
    """
    Minimal async-compatible fallback that mimics the interface used in server.py.
    It doesn't call any external LLM. It simply echoes the input and notes that
    a fallback is active. This keeps the backend running without the optional
    emergentintegrations package.
    """

    def __init__(self, api_key: Optional[str], session_id: str, system_message: str | None = None):
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message or ""
        self._model_provider = None
        self._model_name = None

    def with_model(self, provider: str, model: str) -> "LlmChat":
        self._model_provider = provider
        self._model_name = model
        return self

    async def send_message(self, user_message: UserMessage) -> str:
        # Very simple placeholder behavior
        prefix = "(fallback response) "
        return prefix + user_message.text
