"""Memory persistence and retrieval on Postgres.

Write discipline lives here, not in client prompts: exact-name writes update in
place, and new writes are screened against existing memories (trigram
similarity) before insertion so near-duplicates are surfaced instead of
silently accumulating.
"""

import asyncpg

from axiom.embeddings import GeminiEmbedder, to_pgvector
from axiom.models import (
    DuplicatePair,
    Event,
    EventCluster,
    Memory,
    MemorySummary,
    MemoryType,
    RememberResult,
    ReviewReport,
    StaleMemory,
)

# Text the search indexes are built over; must match the migration definitions.
_SEARCH_TEXT = "m.name || ' ' || m.description || ' ' || m.content"

_COLUMNS = (
    "m.name, m.description, m.content, m.type, m.source_app, "
    "m.created_at, m.updated_at, m.use_count, m.last_used_at, m.related"
)


class MemoryStore:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        dedup_threshold: float,
        recall_threshold: float,
        recall_half_life_days: float = 180.0,
        state_half_life_days: float = 30.0,
        procedural_half_life_days: float = 540.0,
        use_count_dampening: float = 4.0,
        stale_state_days: int = 90,
        event_similarity: float = 0.3,
        event_retention_days: int = 180,
        embedder: GeminiEmbedder | None = None,
        semantic_floor: float = 0.55,
    ):
        self._pool = pool
        self._dedup_threshold = dedup_threshold
        self._recall_threshold = recall_threshold
        self._recall_half_life_days = recall_half_life_days
        self._state_half_life_days = state_half_life_days
        self._procedural_half_life_days = procedural_half_life_days
        self._use_count_dampening = use_count_dampening
        self._stale_state_days = stale_state_days
        self._event_similarity = event_similarity
        self._event_retention_days = event_retention_days
        self._embedder = embedder
        # Cosine similarity below this counts as zero relevance; above it,
        # rescaled to 0..1 so it shares a scale with the lexical scores.
        # Calibrated on real data: related pairs land ~0.65, unrelated ~0.50.
        self._semantic_floor = semantic_floor

    async def remember(
        self,
        *,
        name: str,
        description: str,
        content: str,
        type: MemoryType,
        source_app: str,
        related: list[str] | None = None,
        allow_duplicate: bool = False,
    ) -> RememberResult:
        related = related or []
        embedding = await self._embed_memory(name, description, content)
        async with self._pool.acquire() as conn:
            updated = await conn.fetchrow(
                f"""
                UPDATE memories m
                SET description = $2, content = $3, type = $4, source_app = $5,
                    related = $6, embedding = $7::vector, updated_at = now()
                WHERE m.name = $1
                RETURNING {_COLUMNS}
                """,
                name,
                description,
                content,
                type,
                source_app,
                related,
                embedding,
            )
            if updated is not None:
                return RememberResult(status="updated", memory=Memory.from_row(updated))

            if not allow_duplicate:
                similar = await self._find_similar(conn, f"{name} {description} {content}")
                if similar:
                    return RememberResult(status="duplicate_suspected", similar=similar)

            created = await conn.fetchrow(
                f"""
                INSERT INTO memories AS m
                    (name, description, content, type, source_app, related, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
                RETURNING {_COLUMNS}
                """,
                name,
                description,
                content,
                type,
                source_app,
                related,
                embedding,
            )
            assert created is not None
            return RememberResult(status="created", memory=Memory.from_row(created))

    async def _embed_memory(self, name: str, description: str, content: str) -> str | None:
        """Embed the same text the lexical indexes cover. None (no embedder
        configured, or API failure) leaves the column NULL — the memory still
        matches lexically, and `axiom embed` backfills it later."""
        if self._embedder is None:
            return None
        values = await self._embedder.embed(f"{name} {description} {content}", kind="document")
        return to_pgvector(values) if values is not None else None

    async def recall(self, query: str, *, limit: int = 5) -> list[Memory]:
        """Rank by the strongest of full-text match, trigram word similarity
        (covers CJK and fuzzy matches), and — when an embedder is configured —
        semantic cosine similarity, then decay that relevance by recency: a
        memory unused for a long time sinks in the ranking (but is never
        filtered out). `state` memories decay faster; `procedural` ones decay
        slower — skills stay valid even when unused. Retrieval also
        strengthens (ACT-R): a log-dampened use_count factor lets frequently
        recalled memories win ties without letting any memory ride frequency
        past a clearly better match. Matching uses raw relevance, so decay
        and strengthening only reorder. `state` memories past the stale
        threshold come back flagged possibly_stale so callers verify before
        relying on them. An embedding-API failure silently degrades to
        lexical-only ranking; recall never breaks."""
        query_vec: str | None = None
        if self._embedder is not None:
            values = await self._embedder.embed(query, kind="query")
            if values is not None:
                query_vec = to_pgvector(values)

        # Cosine similarity below the floor scores zero; above it, rescaled to
        # 0..1 so it shares a scale with the lexical scores (ts_rank / trigram).
        semantic_expr = (
            """,
            CASE WHEN m.embedding IS NULL THEN 0::float8
                 ELSE GREATEST(
                     0::float8,
                     (1 - (m.embedding <=> $9::vector))::float8 - $10::float8
                 ) / (1::float8 - $10::float8)
            END"""
            if query_vec is not None
            else ""
        )
        params: list = [
            query,
            self._recall_threshold,
            limit,
            self._state_half_life_days,
            self._recall_half_life_days,
            self._procedural_half_life_days,
            self._use_count_dampening,
            self._stale_state_days,
        ]
        if query_vec is not None:
            params += [query_vec, self._semantic_floor]

        rows = await self._pool.fetch(
            f"""
            SELECT {_COLUMNS.replace("m.", "sub.")},
                   (sub.relevance * sub.recency
                    * (1 + ln(1 + sub.use_count) / $7::float8))::float8 AS score,
                   (sub.type = 'state'
                    AND sub.updated_at < now() - make_interval(days => $8::int)
                   ) AS possibly_stale
            FROM (
                SELECT {_COLUMNS},
                       m.search @@ websearch_to_tsquery('simple', $1) AS fts_hit,
                       GREATEST(
                           ts_rank(m.search, websearch_to_tsquery('simple', $1)),
                           word_similarity($1, {_SEARCH_TEXT}){semantic_expr}
                       )::float8 AS relevance,
                       exp(
                           -ln(2)
                           * (extract(epoch FROM now()
                                      - COALESCE(m.last_used_at, m.created_at)) / 86400.0)
                           / (CASE m.type WHEN 'state' THEN $4::float8
                                          WHEN 'procedural' THEN $6::float8
                                          ELSE $5::float8 END)
                       ) AS recency
                FROM memories m
            ) sub
            WHERE sub.fts_hit OR sub.relevance >= $2
            ORDER BY score DESC, sub.updated_at DESC
            LIMIT $3
            """,
            *params,
        )
        memories = [Memory.from_row(r) for r in rows]
        # Retrieval strengthens memory: bump usage for everything we surfaced.
        # The returned objects keep their pre-bump counts, which reflects the
        # state at recall time.
        if memories:
            await self._pool.execute(
                "UPDATE memories SET use_count = use_count + 1, last_used_at = now() "
                "WHERE name = ANY($1::text[])",
                [m.name for m in memories],
            )
        return memories

    async def get(self, name: str) -> Memory | None:
        row = await self._pool.fetchrow(
            f"SELECT {_COLUMNS} FROM memories m WHERE m.name = $1", name
        )
        return Memory.from_row(row) if row else None

    async def forget(self, name: str) -> bool:
        result = await self._pool.execute("DELETE FROM memories WHERE name = $1", name)
        return result == "DELETE 1"

    async def list_all(self) -> list[MemorySummary]:
        rows = await self._pool.fetch(
            "SELECT name, description, type, updated_at FROM memories ORDER BY updated_at DESC"
        )
        return [MemorySummary(**dict(r)) for r in rows]

    async def all_memories(self) -> list[Memory]:
        rows = await self._pool.fetch(f"SELECT {_COLUMNS} FROM memories m ORDER BY m.name")
        return [Memory.from_row(r) for r in rows]

    async def backfill_embeddings(self) -> tuple[int, int]:
        """Embed every memory whose vector is missing (written before
        embeddings existed, or while the API was down). Returns
        (embedded, still_missing)."""
        if self._embedder is None:
            raise RuntimeError("No embedder configured — set AXIOM_GEMINI_API_KEY.")
        rows = await self._pool.fetch(
            "SELECT name, description, content FROM memories WHERE embedding IS NULL"
        )
        embedded = 0
        for row in rows:
            vec = await self._embed_memory(row["name"], row["description"], row["content"])
            if vec is None:
                continue
            await self._pool.execute(
                "UPDATE memories SET embedding = $2::vector WHERE name = $1",
                row["name"],
                vec,
            )
            embedded += 1
        return embedded, len(rows) - embedded

    async def log_event(self, *, content: str, source_app: str) -> Event:
        """Append one episodic event and prune the layer's tail: events older
        than the retention window are deleted outright — this layer is
        designed to forget, unlike memories which only sink in ranking."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO events (content, source_app)
                VALUES ($1, $2)
                RETURNING id, content, source_app, created_at
                """,
                content,
                source_app,
            )
            assert row is not None
            await conn.execute(
                "DELETE FROM events WHERE created_at < now() - ($1 * interval '1 day')",
                self._event_retention_days,
            )
            return Event(**dict(row))

    async def recurring_events(
        self, *, window_days: int, min_count: int
    ) -> list[EventCluster]:
        """Cluster recent events by trigram similarity (single-link over
        similar pairs) and return clusters big enough to suggest a pattern.
        Volumes are personal-scale, so pairing in SQL and grouping in Python
        is plenty."""
        events = await self._pool.fetch(
            """
            SELECT id, content, created_at FROM events
            WHERE created_at >= now() - ($1 * interval '1 day')
            ORDER BY created_at DESC
            """,
            window_days,
        )
        if len(events) < min_count:
            return []
        pairs = await self._pool.fetch(
            """
            SELECT a.id AS id_a, b.id AS id_b
            FROM events a
            JOIN events b ON a.id < b.id
            WHERE a.created_at >= now() - ($1 * interval '1 day')
              AND b.created_at >= now() - ($1 * interval '1 day')
              AND similarity(a.content, b.content) >= $2
            """,
            window_days,
            self._event_similarity,
        )

        parent: dict[int, int] = {r["id"]: r["id"] for r in events}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for p in pairs:
            parent[find(p["id_a"])] = find(p["id_b"])

        by_root: dict[int, list[asyncpg.Record]] = {}
        for e in events:  # already newest-first
            by_root.setdefault(find(e["id"]), []).append(e)

        clusters = [
            EventCluster(
                count=len(group),
                first_at=group[-1]["created_at"],
                last_at=group[0]["created_at"],
                samples=[e["content"] for e in group[:3]],
            )
            for group in by_root.values()
            if len(group) >= min_count
        ]
        clusters.sort(key=lambda c: c.count, reverse=True)
        return clusters

    async def consolidation_candidates(
        self,
        *,
        stale_state_days: int,
        zombie_days: int,
        event_window_days: int = 30,
        event_min_count: int = 3,
    ) -> ReviewReport:
        """Surface memories worth a human's attention — the minimal, offline
        version of sleep-time consolidation. It only reports; it never edits or
        deletes. Four buckets: near-duplicate pairs (merge?), `state` memories
        left untouched too long (still true?), memories never recalled since
        they were stored (worth keeping?), and recurring episodic events
        (promote to a memory?)."""
        dup_rows = await self._pool.fetch(
            f"""
            SELECT a.name AS name_a, b.name AS name_b,
                   similarity({_SEARCH_TEXT.replace("m.", "a.")},
                              {_SEARCH_TEXT.replace("m.", "b.")})::float8 AS similarity
            FROM memories a
            JOIN memories b ON a.name < b.name
            WHERE similarity({_SEARCH_TEXT.replace("m.", "a.")},
                             {_SEARCH_TEXT.replace("m.", "b.")}) >= $1
            ORDER BY similarity DESC
            """,
            self._dedup_threshold,
        )
        stale_rows = await self._pool.fetch(
            """
            SELECT name, type, COALESCE(last_used_at, updated_at) AS since
            FROM memories
            WHERE type = 'state'
              AND COALESCE(last_used_at, updated_at) < now() - ($1 * interval '1 day')
            ORDER BY since
            """,
            stale_state_days,
        )
        zombie_rows = await self._pool.fetch(
            """
            SELECT name, type, created_at AS since
            FROM memories
            WHERE use_count = 0 AND created_at < now() - ($1 * interval '1 day')
            ORDER BY since
            """,
            zombie_days,
        )
        return ReviewReport(
            duplicates=[DuplicatePair(**dict(r)) for r in dup_rows],
            stale_state=[StaleMemory(**dict(r)) for r in stale_rows],
            zombies=[StaleMemory(**dict(r)) for r in zombie_rows],
            recurring=await self.recurring_events(
                window_days=event_window_days, min_count=event_min_count
            ),
        )

    async def _find_similar(
        self, conn: asyncpg.Connection | asyncpg.pool.PoolConnectionProxy, text: str
    ) -> list[Memory]:
        rows = await conn.fetch(
            f"""
            SELECT {_COLUMNS},
                   similarity({_SEARCH_TEXT}, $1)::float8 AS score
            FROM memories m
            WHERE similarity({_SEARCH_TEXT}, $1) >= $2
            ORDER BY score DESC
            LIMIT 3
            """,
            text,
            self._dedup_threshold,
        )
        return [Memory.from_row(r) for r in rows]
