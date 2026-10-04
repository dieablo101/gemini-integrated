"""Google GenAI SDK wrapper."""

import asyncio
from google import genai

from gemini_app.config import DEFAULT_MODEL

_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


async def generate_response(history: list[dict], model: str = DEFAULT_MODEL) -> str:
    """Dispatches generation request to Gemini in an async thread."""
    client = get_genai_client()
    payload = [
        {"role": turn["role"], "parts": [{"text": turn["text"]}]}
        for turn in history
    ]

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=payload,
    )
    return response.text or ""
