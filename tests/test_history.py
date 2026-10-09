from axiom.store import MemoryStore


async def test_payload_truncates_long_content(store: MemoryStore):
    await _editor(store, "x" * 50)
    memory = await store.get("current-editor")
    assert memory is not None

    cut = memory.payload(max_chars=20)
    assert cut["content"] == "x" * 20 + "…"
    assert cut["truncated"] is True
    assert "score" not in cut

    full = memory.payload()
    assert full["content"] == "x" * 50
    assert "truncated" not in full


async def _editor(store: MemoryStore, content: str, *, source_app: str = "test") -> None:
    await store.remember(
        name="current-editor",
        description="Editor Tim uses",
        content=content,
        type="state",
        source_app=source_app,
    )


async def test_update_snapshots_previous_version(store: MemoryStore):
    await _editor(store, "Uses VS Code.", source_app="claude-code")
    await _editor(store, "Uses Zed.", source_app="chatgpt")
    await _editor(store, "Uses Helix.")

    versions = await store.history("current-editor")
    assert [v.content for v in versions] == ["Uses Zed.", "Uses VS Code."]
    assert [v.source_app for v in versions] == ["chatgpt", "claude-code"]
    assert all(v.reason == "updated" for v in versions)


async def test_forget_keeps_final_state(store: MemoryStore):
    await _editor(store, "Uses Zed.")
    await store.forget("current-editor")

    versions = await store.history("current-editor")
    assert len(versions) == 1
    assert versions[0].content == "Uses Zed."
    assert versions[0].reason == "forgotten"


async def test_bookkeeping_writes_are_not_versioned(store: MemoryStore):
    # Recall bumps usage, an identical re-remember changes nothing, and the
    # related-scrub forget runs on other memories is link bookkeeping: none
    # of these change what a memory says, so none may create versions.
    await _editor(store, "Uses Zed.")
    await store.remember(
        name="editor-plugins",
        description="Editor plugins",
        content="Vim mode on.",
        type="state",
        source_app="test",
        related=["current-editor"],
    )
    await store.recall("editor Zed")
    await _editor(store, "Uses Zed.")
    await store.forget("current-editor")

    assert await store.history("editor-plugins") == []
    assert [v.reason for v in await store.history("current-editor")] == ["forgotten"]
