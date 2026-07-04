"""Episodic layer: log_event appends and prunes, recurring_events clusters
similar signals, and the review report carries them as promotion candidates."""

from axiom.store import MemoryStore


async def test_log_event_appends(store: MemoryStore):
    event = await store.log_event(content="asked for a miso soup recipe", source_app="chatgpt")
    assert event.id > 0
    assert event.source_app == "chatgpt"


async def test_log_event_prunes_beyond_retention(store: MemoryStore):
    await store.log_event(content="asked about sourdough starters", source_app="test")
    # Age the first event past the retention window, then trigger the prune
    # that piggybacks on the next write.
    await store._pool.execute(
        "UPDATE events SET created_at = now() - interval '181 days'"
    )
    await store.log_event(content="asked about rye bread", source_app="test")
    count = await store._pool.fetchval("SELECT count(*) FROM events")
    assert count == 1


async def test_recurring_events_clusters_similar_signals(store: MemoryStore):
    for content in [
        "asked for a miso soup recipe",
        "asked for a miso ramen recipe",
        "asked for a quick soup recipe for dinner",
        "discussed Gemini Enterprise architecture",
    ]:
        await store.log_event(content=content, source_app="test")

    clusters = await store.recurring_events(window_days=30, min_count=3)
    assert len(clusters) == 1
    assert clusters[0].count == 3
    assert len(clusters[0].samples) == 3
    assert "recipe" in clusters[0].samples[0]


async def test_recurring_events_ignores_singletons_and_old_events(store: MemoryStore):
    for content in [
        "asked for a miso soup recipe",
        "asked for a miso ramen recipe",
        "asked for a quick soup recipe for dinner",
    ]:
        await store.log_event(content=content, source_app="test")
    # Push one cluster member outside the window: the remaining two fall
    # below min_count and the cluster disappears.
    await store._pool.execute(
        "UPDATE events SET created_at = now() - interval '31 days' "
        "WHERE content LIKE '%ramen%'"
    )
    assert await store.recurring_events(window_days=30, min_count=3) == []


async def test_review_report_includes_recurring(store: MemoryStore):
    for content in [
        "asked for a miso soup recipe",
        "asked for a miso ramen recipe",
        "asked for a quick soup recipe for dinner",
    ]:
        await store.log_event(content=content, source_app="test")

    report = await store.consolidation_candidates(
        stale_state_days=90, zombie_days=60, event_window_days=30, event_min_count=3
    )
    assert len(report.recurring) == 1
    assert report.recurring[0].count == 3
    assert report.recurring[0].first_at <= report.recurring[0].last_at
