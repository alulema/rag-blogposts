"""Cliente de Ollama con streaming token a token (``/api/chat``).

Relay asíncrono con httpx: cada delta de ``message.content`` se emite en cuanto llega, para el SSE.
$0 API: apunta a un Ollama local (sidecar en el mismo Container App). Sin secretos.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx


class OllamaClient:
    def __init__(self, host: str, model: str, max_tokens: int) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": self._max_tokens},
        }
        timeout = httpx.Timeout(300.0, connect=10.0)
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", f"{self._host}/api/chat", json=payload) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                delta = data.get("message", {}).get("content")
                if delta:
                    yield delta
                if data.get("done"):
                    break
