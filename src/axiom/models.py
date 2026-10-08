"""Domain models shared by the store, the MCP tools, and the exporter."""

from datetime import datetime
from typing import Literal

import asyncpg
from pydantic import BaseModel, Field

MemoryType = Literal["preference", "fact", "project", "state", "reference", "procedural"]
Category = Literal["you", "people", "areas", "topics"]

NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{1,63}$"


class Memory(BaseModel):
    name: str = Field(pattern=NAME_PATTERN)
    description: str
    content: str
    type: MemoryType
    category: Category = "areas"
    source_app: str
    created_at: datetime
    updated_at: datetime
    # Usage signal, bumped on every recall (see MemoryStore.recall). last_used_at
    # is None until the memory is recalled for the first time.
    use_count: int = 0
    last_used_at: datetime | None = None
    # Names of related memories, so recall results can point onward to
    # neighbours the caller may also want to pull.
    related: list[str] = []
    score: float | None = None
    # Computed at recall time, never stored: a `state` memory whose updated_at
    # is older than the stale threshold. The caller should verify the content
    # before relying on it, and re-remember it to refresh.
    possibly_stale: bool = False

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "Memory":
        return cls(
            name=row["name"],
            description=row["description"],
            content=row["content"],
            type=row["type"],
            category=row.get("category", "areas"),
            source_app=row["source_app"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            use_count=row.get("use_count", 0),
            last_used_at=row.get("last_used_at"),
            related=list(row.get("related") or []),
            score=row.get("score"),
            possibly_stale=row.get("possibly_stale") or False,
        )


class MemorySummary(BaseModel):
    """Index entry: everything needed to decide relevance without the body."""

    name: str
    description: str
    type: MemoryType
    category: Category
    updated_at: datetime


class RememberResult(BaseModel):
    status: Literal["created", "updated", "duplicate_suspected"]
    memory: Memory | None = None
    # Populated when status is duplicate_suspected: the existing memories the
    # new one collided with. The caller should update one of these by name, or
    # retry with allow_duplicate=True if it is genuinely new.
    similar: list[Memory] = []


class DuplicatePair(BaseModel):
    """Two memories similar enough to be worth merging."""

    name_a: str
    name_b: str
    similarity: float


class StaleMemory(BaseModel):
    """A memory flagged for review, with the timestamp that triggered it
    (last use / update for stale state, last surfacing — or creation, if
    never surfaced — for zombies)."""

    name: str
    type: MemoryType
    category: Category = "areas"
    since: datetime


class Event(BaseModel):
    """One episodic event: a weak ambient signal, not a curated fact.
    Events never enter recall; recurring patterns among them are surfaced by
    `axiom review` as candidates for promotion to a real memory."""

    id: int
    content: str
    source_app: str
    created_at: datetime


class EventCluster(BaseModel):
    """A group of similar recent events — evidence of a recurring pattern
    worth promoting to a memory (e.g. many cooking questions → a preference)."""

    count: int
    first_at: datetime
    last_at: datetime
    # Up to a few sample contents, most recent first, to show what the
    # pattern is about without dumping every event.
    samples: list[str]


class ReviewReport(BaseModel):
    """Consolidation candidates surfaced by `axiom review` — never acted on
    automatically; a human decides what to merge, refresh, or forget."""

    duplicates: list[DuplicatePair] = []
    stale_state: list[StaleMemory] = []
    zombies: list[StaleMemory] = []
    # Recurring episodic patterns; promotion candidates, not yet memories.
    recurring: list[EventCluster] = []
