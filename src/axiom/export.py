"""Render the database into a human-readable markdown mirror.

Postgres is the source of truth. The export directory is a generated view —
one file per memory plus a MEMORY.md index — meant for browsing, grepping, and
committing to git as a backup. Edits to these files do not flow back.
"""

import json
from pathlib import Path

from axiom.models import Memory
from axiom.store import MemoryStore


def render_memory(memory: Memory) -> str:
    # json.dumps produces valid single-line YAML scalars, quoting included.
    return (
        "---\n"
        f"name: {memory.name}\n"
        f"description: {json.dumps(memory.description, ensure_ascii=False)}\n"
        f"type: {memory.type}\n"
        f"source_app: {memory.source_app}\n"
        f"created_at: {memory.created_at.isoformat()}\n"
        f"updated_at: {memory.updated_at.isoformat()}\n"
        f"related: {json.dumps(memory.related)}\n"
        "---\n\n"
        f"{memory.content}\n"
    )


def render_index(memories: list[Memory]) -> str:
    lines = ["# Memory Index", ""]
    lines += [f"- [{m.name}]({m.name}.md) — {m.description} ({m.type})" for m in memories]
    return "\n".join(lines) + "\n"


async def export_all(store: MemoryStore, out_dir: Path) -> int:
    """Write every memory to out_dir, prune files for forgotten memories."""
    memories = await store.all_memories()
    out_dir.mkdir(parents=True, exist_ok=True)

    current = {f"{m.name}.md" for m in memories}
    for stale in out_dir.glob("*.md"):
        if stale.name != "MEMORY.md" and stale.name not in current:
            stale.unlink()

    for memory in memories:
        (out_dir / f"{memory.name}.md").write_text(render_memory(memory), encoding="utf-8")
    (out_dir / "MEMORY.md").write_text(render_index(memories), encoding="utf-8")
    return len(memories)
