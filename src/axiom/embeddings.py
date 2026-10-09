"""Gemini embeddings for semantic recall.

Embeddings are an enhancement, never a dependency: every caller treats a None
return as "no vector available" and falls back to lexical search. Recall is
the hot path shared by every client, so an embedding-API outage must degrade
ranking quality, not break retrieval.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"


class GeminiEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dims: int,
        timeout_seconds: float = 8.0,
        query_timeout_seconds: float = 3.0,
    ):
        self._api_key = api_key
        self._model = model
        self._dims = dims
        # Query embeddings sit on recall's hot path, where waiting out a slow
        # API costs every client more than falling back to lexical ranking.
        # Document embeddings can wait longer: a miss leaves the memory
        # without a vector until `axiom embed` backfills it.
        self._timeout = timeout_seconds
        self._query_timeout = query_timeout_seconds

    @property
    def dims(self) -> int:
        return self._dims

    async def embed(self, text: str, *, kind: str) -> list[float] | None:
        """Return a unit-length embedding, or None on any failure.

        kind is "query" or "document" — Gemini tunes the vector differently
        for each side of retrieval. Vectors come back normalized at the
        requested dimensionality, so cosine similarity is a plain dot product.
        """
        task = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
        timeout = self._query_timeout if kind == "query" else self._timeout
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    _API_URL.format(model=self._model),
                    headers={"x-goog-api-key": self._api_key},
                    json={
                        "content": {"parts": [{"text": text}]},
                        "taskType": task,
                        "outputDimensionality": self._dims,
                    },
                )
                response.raise_for_status()
                values = response.json()["embedding"]["values"]
                if len(values) != self._dims:
                    logger.warning(
                        "Embedding has %d dims, expected %d — ignoring", len(values), self._dims
                    )
                    return None
                return values
        except Exception as e:
            logger.warning("Embedding failed (%s); falling back to lexical: %s", kind, e)
            return None


def to_pgvector(values: list[float]) -> str:
    """Format for a `$n::vector` cast — asyncpg has no native vector codec,
    and the explicit text cast sidesteps parameter type inference entirely."""
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"
