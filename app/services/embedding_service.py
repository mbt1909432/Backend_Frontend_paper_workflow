from __future__ import annotations

import logging
from typing import List, Sequence

import requests
import numpy as np

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Thin wrapper around the Jina embeddings API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "jina-embeddings-v3",
        task: str = "text-matching",
        base_url: str = "https://api.jina.ai/v1/embeddings",
        request_timeout: int = 30,
    ) -> None:
        self.api_key = api_key or getattr(settings, "jina_api_key", None)
        self.model = model
        self.task = task
        self.base_url = base_url
        self.request_timeout = request_timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            raise ValueError("texts must not be empty")
        if not self.api_key:
            raise RuntimeError("Jina API key is not configured")

        payload = {
            "model": self.model,
            "task": self.task,
            "input": list(texts),
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        logger.info(
            "Requesting %d embeddings from Jina model=%s task=%s",
            len(texts),
            self.model,
            self.task,
        )

        response = requests.post(
            self.base_url,
            json=payload,
            headers=headers,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = [
            item["embedding"]
            for item in data.get("data", [])
            if item.get("embedding") is not None
        ]

        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Expected {len(texts)} embeddings, got {len(embeddings)}"
            )

        return embeddings

    @staticmethod
    def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        if len(vec_a) != len(vec_b):
            raise ValueError("Vectors must have the same length for cosine similarity")

        a = np.asarray(vec_a, dtype=float)
        b = np.asarray(vec_b, dtype=float)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(a @ b / denom) if denom else 0.0

