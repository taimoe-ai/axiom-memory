from axiom.models import Provenance
from axiom.store import MemoryStore


async def test_provenance_defaults_to_stated_and_survives_updates(store: MemoryStore):
    created = await store.remember(
        name="likes-spicy-food",
        description="Spicy food preference",
        content="Probably enjoys spicy food; ordered mala hotpot three times.",
        type="preference",
        provenance="inferred",
        source_app="test",
    )
    assert created.memory is not None
    assert created.memory.provenance == "inferred"

    # A routine edit that does not mention provenance must not silently
    # upgrade an inference to a stated fact.
    edited = await store.remember(
        name="likes-spicy-food",
        description="Spicy food preference",
        content="Probably enjoys spicy food; ordered mala hotpot four times.",
        type="preference",
        source_app="test",
    )
    assert edited.memory is not None
    assert edited.memory.provenance == "inferred"

    confirmed = await store.remember(
        name="likes-spicy-food",
        description="Spicy food preference",
        content="Enjoys spicy food.",
        type="preference",
        provenance="stated",
        source_app="test",
    )
    assert confirmed.memory is not None
    assert confirmed.memory.provenance == "stated"
    assert [v.provenance for v in await store.history("likes-spicy-food")] == [
        "inferred",
        "inferred",
    ]

    plain = await store.remember(
        name="birthday",
        description="Date of birth",
        content="Born on 1990-01-01.",
        type="fact",
        source_app="test",
    )
    assert plain.memory is not None
    assert plain.memory.provenance == "stated"


async def test_inferred_memories_rank_below_equally_relevant_stated(store: MemoryStore):
    cases: list[tuple[str, Provenance]] = [
        ("editor-inferred", "inferred"),
        ("editor-stated", "stated"),
    ]
    for name, provenance in cases:
        await store.remember(
            name=name,
            description="preferred code editor and keybindings",
            content="Preferred code editor and keybindings.",
            type="preference",
            provenance=provenance,
            source_app="test",
            allow_duplicate=True,
        )
    results = await store.recall("preferred code editor keybindings")
    names = [m.name for m in results]
    assert names.index("editor-stated") < names.index("editor-inferred")
    assert {m.name: m.provenance for m in results}["editor-inferred"] == "inferred"
