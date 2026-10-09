"""Offline recall evaluation against a labelled case file.

Each case is a query plus the memory names a good recall should surface. The
case file describes one person's memories, so real case files stay out of the
repo (see evals/recall_cases.example.toml for the format). Evaluation never
bumps use_count: measuring recall must not distort the signal it measures.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from axiom.models import Category
from axiom.store import MemoryStore


@dataclass
class Case:
    query: str
    expect: list[str]
    category: Category | None = None
    tag: str = ""


@dataclass
class CaseResult:
    case: Case
    got: list[str] = field(default_factory=list)

    @property
    def rank(self) -> int | None:
        """1-based position of the first expected memory, None on a miss."""
        for position, name in enumerate(self.got, start=1):
            if name in self.case.expect:
                return position
        return None


@dataclass
class EvalReport:
    k: int
    results: list[CaseResult]
    # Expected names that no longer exist in the store — the case file has
    # drifted (memory renamed or forgotten) and those cases cannot pass.
    unknown_names: list[str]

    @property
    def hit_rate(self) -> float:
        return sum(r.rank is not None for r in self.results) / len(self.results)

    @property
    def mrr(self) -> float:
        return sum(1 / r.rank for r in self.results if r.rank) / len(self.results)

    def by_tag(self) -> dict[str, tuple[int, int]]:
        """tag -> (hits, total)."""
        out: dict[str, tuple[int, int]] = {}
        for r in self.results:
            hits, total = out.get(r.case.tag, (0, 0))
            out[r.case.tag] = (hits + (r.rank is not None), total + 1)
        return out


def load_cases(path: Path) -> list[Case]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [
        Case(
            query=c["query"],
            expect=list(c["expect"]),
            category=c.get("category"),
            tag=c.get("tag", ""),
        )
        for c in data.get("case", [])
    ]


async def run_eval(store: MemoryStore, cases: list[Case], *, k: int = 5) -> EvalReport:
    if not cases:
        raise ValueError("No cases to evaluate.")
    known = {m.name for m in await store.list_all()}
    unknown = sorted({n for c in cases for n in c.expect if n not in known})
    results = []
    for case in cases:
        memories = await store.recall(
            case.query, category=case.category, limit=k, track_usage=False
        )
        results.append(CaseResult(case=case, got=[m.name for m in memories]))
    return EvalReport(k=k, results=results, unknown_names=unknown)


def format_report(report: EvalReport) -> str:
    lines = [
        f"Cases: {len(report.results)}   hit@{report.k}: {report.hit_rate:.1%}   "
        f"MRR: {report.mrr:.3f}"
    ]
    tags = report.by_tag()
    if len(tags) > 1 or "" not in tags:
        lines.append("")
        for tag, (hits, total) in sorted(tags.items()):
            lines.append(f"  {tag or '(untagged)':<16} {hits}/{total}")
    misses = [r for r in report.results if r.rank is None]
    if misses:
        lines += ["", f"Misses ({len(misses)}):"]
        for r in misses:
            lines.append(f"  {r.case.query!r}  expected {r.case.expect}")
            lines.append(f"      got {r.got or '(nothing)'}")
    if report.unknown_names:
        lines += ["", "Expected names not in the store (case file drifted):"]
        lines += [f"  {n}" for n in report.unknown_names]
    return "\n".join(lines)
