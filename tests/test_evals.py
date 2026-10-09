from pathlib import Path

from axiom.evals import Case, load_cases, run_eval
from axiom.store import MemoryStore


async def _seed(store: MemoryStore) -> None:
    await store.remember(
        name="favorite-coffee",
        description="Coffee preference",
        content="Drinks oat milk lattes.",
        type="preference",
        source_app="test",
    )
    await store.remember(
        name="kube-notes",
        description="kubernetes cluster notes",
        content="Cluster configuration notes.",
        type="fact",
        source_app="test",
    )


async def test_eval_scores_hits_misses_and_drift(store: MemoryStore):
    await _seed(store)
    cases = [
        Case(query="oat milk latte", expect=["favorite-coffee"], tag="lexical"),
        # The category filter excludes the target, so this is a certain miss.
        Case(query="kubernetes cluster", expect=["kube-notes"], category="you", tag="lexical"),
        Case(query="kubernetes cluster", expect=["renamed-away"], tag="drift"),
    ]
    report = await run_eval(store, cases, k=5)

    assert [r.rank for r in report.results] == [1, None, None]
    assert report.hit_rate == 1 / 3
    assert report.mrr == 1 / 3
    assert report.unknown_names == ["renamed-away"]
    assert report.by_tag() == {"lexical": (1, 2), "drift": (0, 1)}


async def test_eval_does_not_bump_usage(store: MemoryStore):
    await _seed(store)
    await run_eval(store, [Case(query="oat milk latte", expect=["favorite-coffee"])])
    memory = await store.get("favorite-coffee")
    assert memory is not None
    assert memory.use_count == 0
    assert memory.last_used_at is None


def test_example_case_file_parses():
    path = Path(__file__).parent.parent / "evals" / "recall_cases.example.toml"
    cases = load_cases(path)
    assert cases
    assert all(c.query and c.expect for c in cases)
