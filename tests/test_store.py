from pathlib import Path

from axiom.export import export_all
from axiom.store import MemoryStore


async def test_remember_creates_memory(store: MemoryStore):
    result = await store.remember(
        name="prefers-uv-over-pip",
        description="Tim prefers uv over pip for Python projects",
        content="Use `uv` for dependency management in all Python projects.",
        type="preference",
        source_app="test",
    )
    assert result.status == "created"
    assert result.memory is not None
    assert result.memory.name == "prefers-uv-over-pip"


async def test_remember_same_name_updates(store: MemoryStore):
    await store.remember(
        name="current-editor",
        description="Editor Tim uses",
        content="Uses VS Code.",
        type="state",
        source_app="test",
    )
    result = await store.remember(
        name="current-editor",
        description="Editor Tim uses",
        content="Uses Zed.",
        type="state",
        source_app="other-app",
    )
    assert result.status == "updated"
    assert result.memory is not None
    assert result.memory.content == "Uses Zed."
    assert result.memory.source_app == "other-app"


async def test_remember_flags_near_duplicate(store: MemoryStore):
    await store.remember(
        name="prefers-uv-over-pip",
        description="Tim prefers uv over pip for Python dependency management",
        content="Use `uv` for dependency management in all Python projects.",
        type="preference",
        source_app="test",
    )
    result = await store.remember(
        name="uv-for-python-deps",
        description="Tim prefers uv over pip for Python dependency management",
        content="Prefers `uv` for Python dependency management in projects.",
        type="preference",
        source_app="test",
    )
    assert result.status == "duplicate_suspected"
    assert [m.name for m in result.similar] == ["prefers-uv-over-pip"]

    forced = await store.remember(
        name="uv-for-python-deps",
        description="Tim prefers uv over pip for Python dependency management",
        content="Prefers `uv` for Python dependency management in projects.",
        type="preference",
        source_app="test",
        allow_duplicate=True,
    )
    assert forced.status == "created"


async def test_recall_matches_keywords(store: MemoryStore):
    await store.remember(
        name="axiom-project",
        description="Axiom is Tim's personal cross-app memory MCP server",
        content="Side project: MCP memory server, Python + FastMCP + Postgres, Cloud Run.",
        type="project",
        source_app="test",
    )
    await store.remember(
        name="favorite-coffee",
        description="Coffee preference",
        content="Drinks oat milk lattes.",
        type="fact",
        source_app="test",
    )
    results = await store.recall("mcp memory server")
    assert results and results[0].name == "axiom-project"


async def test_recall_tracks_usage(store: MemoryStore):
    await store.remember(
        name="axiom-project",
        description="Axiom is Tim's personal cross-app memory MCP server",
        content="Side project: MCP memory server, Python + FastMCP + Postgres.",
        type="project",
        source_app="test",
    )
    before = await store.get("axiom-project")
    assert before is not None
    assert before.use_count == 0
    assert before.last_used_at is None

    await store.recall("mcp memory server")

    after = await store.get("axiom-project")
    assert after is not None
    assert after.use_count == 1
    assert after.last_used_at is not None

    await store.recall("mcp memory server")
    again = await store.get("axiom-project")
    assert again is not None
    assert again.use_count == 2


async def test_recall_does_not_touch_updated_at(store: MemoryStore):
    # Usage tracking must not masquerade as a content change: `state` staleness
    # decisions rely on updated_at, so recall must leave it alone.
    await store.remember(
        name="current-editor",
        description="Editor Tim uses",
        content="Uses Zed.",
        type="state",
        source_app="test",
    )
    before = await store.get("current-editor")
    assert before is not None

    await store.recall("editor Zed")

    after = await store.get("current-editor")
    assert after is not None
    assert after.updated_at == before.updated_at


async def test_recall_matches_chinese_content(store: MemoryStore):
    await store.remember(
        name="gateway-positioning",
        description="Gateway product positioning",
        content="這個產品是賣給金融業 CISO 的 AI 治理閘道,重點是稽核與存取控制。",
        type="project",
        source_app="test",
    )
    results = await store.recall("金融業 治理")
    assert [m.name for m in results] == ["gateway-positioning"]


async def test_recall_decays_stale_memories(store: MemoryStore, pool):
    # Two memories with identical relevance to the query; the only difference is
    # age. Retrieval-based decay must rank the fresh one above the stale one.
    for name in ("kube-fresh", "kube-stale"):
        await store.remember(
            name=name,
            description="kubernetes deployment and cluster config notes",
            content="Kubernetes deployment notes and cluster configuration.",
            type="fact",
            source_app="test",
            allow_duplicate=True,
        )
    await pool.execute(
        "UPDATE memories SET created_at = now() - interval '2000 days', "
        "last_used_at = now() - interval '2000 days' WHERE name = 'kube-stale'"
    )
    results = await store.recall("kubernetes deployment cluster")
    names = [m.name for m in results]
    assert names.index("kube-fresh") < names.index("kube-stale")


async def test_recall_strengthens_frequently_used(store: MemoryStore, pool):
    # Same relevance, same age; the memory recalled many times before must
    # outrank the never-used one (ACT-R base-level activation).
    for name in ("stack-used", "stack-fresh"):
        await store.remember(
            name=name,
            description="preferred python stack and tooling choices",
            content="Preferred Python stack and tooling choices.",
            type="preference",
            source_app="test",
            allow_duplicate=True,
        )
    await pool.execute("UPDATE memories SET use_count = 30 WHERE name = 'stack-used'")
    results = await store.recall("preferred python stack tooling")
    names = [m.name for m in results]
    assert names.index("stack-used") < names.index("stack-fresh")


async def test_procedural_memory_decays_slower(store: MemoryStore, pool):
    # Same relevance, same age; the procedural memory's longer half-life must
    # rank it above the fact once both have sat unused for a while.
    for name, type_ in (("deploy-workflow", "procedural"), ("deploy-note", "fact")):
        await store.remember(
            name=name,
            description="deploying the axiom server with docker compose",
            content="Deploying the axiom server with docker compose.",
            type=type_,
            source_app="test",
            allow_duplicate=True,
        )
    await pool.execute(
        "UPDATE memories SET created_at = now() - interval '400 days', "
        "last_used_at = now() - interval '400 days'"
    )
    results = await store.recall("deploying axiom docker compose")
    names = [m.name for m in results]
    assert names.index("deploy-workflow") < names.index("deploy-note")


async def test_recall_flags_stale_state(store: MemoryStore, pool):
    # A state memory past the stale threshold comes back flagged; a fresh one
    # and non-state types never do.
    for name, type_ in (("editor-setup-old", "state"), ("editor-setup-new", "state")):
        await store.remember(
            name=name,
            description="current editor setup and plugins",
            content="Current editor setup and plugins.",
            type=type_,
            source_app="test",
            allow_duplicate=True,
        )
    await pool.execute(
        "UPDATE memories SET updated_at = now() - interval '100 days' "
        "WHERE name = 'editor-setup-old'"
    )
    results = {m.name: m for m in await store.recall("editor setup plugins")}
    assert results["editor-setup-old"].possibly_stale
    assert not results["editor-setup-new"].possibly_stale


async def test_consolidation_report(store: MemoryStore, pool):
    await store.remember(
        name="uv-pref",
        description="Tim prefers uv over pip",
        content="Use uv for Python dependency management.",
        type="preference",
        source_app="test",
    )
    await store.remember(
        name="uv-pref-2",
        description="Tim prefers uv over pip",
        content="Use uv for Python dependency management.",
        type="preference",
        source_app="test",
        allow_duplicate=True,
    )
    await store.remember(
        name="old-editor",
        description="editor Tim uses",
        content="Uses Zed.",
        type="state",
        source_app="test",
    )
    await pool.execute(
        "UPDATE memories SET updated_at = now() - interval '400 days', last_used_at = NULL "
        "WHERE name = 'old-editor'"
    )
    await store.remember(
        name="lonely-note",
        description="a note nobody looks up",
        content="Something never recalled.",
        type="fact",
        source_app="test",
    )
    await pool.execute(
        "UPDATE memories SET created_at = now() - interval '400 days' WHERE name = 'lonely-note'"
    )

    report = await store.consolidation_candidates(stale_state_days=90, zombie_days=60)

    assert frozenset(("uv-pref", "uv-pref-2")) in {
        frozenset((d.name_a, d.name_b)) for d in report.duplicates
    }
    assert "old-editor" in {s.name for s in report.stale_state}
    assert "lonely-note" in {z.name for z in report.zombies}


async def test_remember_stores_and_updates_related(store: MemoryStore):
    await store.remember(
        name="axiom-goal",
        description="Axiom goal",
        content="Cross-app shared memory.",
        type="project",
        source_app="test",
    )
    created = await store.remember(
        name="axiom-arch",
        description="Axiom architecture",
        content="Postgres is the source of truth.",
        type="project",
        source_app="test",
        related=["axiom-goal"],
    )
    assert created.memory is not None
    assert created.memory.related == ["axiom-goal"]

    fetched = await store.get("axiom-arch")
    assert fetched is not None
    assert fetched.related == ["axiom-goal"]

    updated = await store.remember(
        name="axiom-arch",
        description="Axiom architecture",
        content="Postgres is the source of truth; markdown is a read-only mirror.",
        type="project",
        source_app="test",
        related=["axiom-goal", "axiom-decision-postgresql"],
    )
    assert updated.memory is not None
    assert updated.memory.related == ["axiom-goal", "axiom-decision-postgresql"]


async def test_forget(store: MemoryStore):
    await store.remember(
        name="to-be-deleted",
        description="Temporary",
        content="Delete me.",
        type="state",
        source_app="test",
    )
    assert await store.forget("to-be-deleted") is True
    assert await store.forget("to-be-deleted") is False
    assert await store.get("to-be-deleted") is None


async def test_list_all(store: MemoryStore):
    await store.remember(
        name="a-memory",
        description="First",
        content="One.",
        type="fact",
        source_app="test",
    )
    summaries = await store.list_all()
    assert [s.name for s in summaries] == ["a-memory"]


async def test_export_writes_and_prunes(store: MemoryStore, tmp_path: Path):
    await store.remember(
        name="kept-memory",
        description="Stays",
        content="Content here.",
        type="fact",
        source_app="test",
    )
    (tmp_path / "stale-memory.md").write_text("old")

    count = await export_all(store, tmp_path)

    assert count == 1
    assert (tmp_path / "kept-memory.md").exists()
    assert not (tmp_path / "stale-memory.md").exists()
    index = (tmp_path / "MEMORY.md").read_text()
    assert "[kept-memory](kept-memory.md)" in index
    body = (tmp_path / "kept-memory.md").read_text()
    assert body.startswith("---\nname: kept-memory\n")
    assert "Content here." in body
