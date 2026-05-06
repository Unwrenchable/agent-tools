from __future__ import annotations

import os
from typing import Any

import requests


class RealAIEmbeddings:
    """Thin client for the RealAI embeddings endpoint.

    Swap this in wherever you need vectors — e.g. as a custom embedding
    function for Chroma instead of its built-in defaults.
    """

    def __init__(self) -> None:
        self._api_url = os.getenv("REALAI_API_URL", "")
        self._api_key = os.getenv("REALAI_API_KEY", "")
        self._model = os.getenv("REALAI_EMBED_MODEL", "realai-embed")
        if not self._api_url or not self._api_key:
            raise RuntimeError("RealAIEmbeddings requires REALAI_API_URL and REALAI_API_KEY")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }
        r = requests.post(f"{self._api_url}/v1/embeddings", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return [item["embedding"] for item in data["data"]]
