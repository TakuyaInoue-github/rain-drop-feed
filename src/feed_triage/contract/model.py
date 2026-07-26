"""層をまたいで受け渡される型定義。副作用も依存も持たない。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Source:
    """購読対象の情報源1件（`feeds.yaml` の1エントリ）。"""

    name: str
    url: str
    weight: int
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Entry:
    """フィードから取得した記事1件。一意性は url で判定する（REQ-F-002）。"""

    url: str
    title: str
    summary: str
    published_at: datetime | None
    source_name: str


@dataclass(frozen=True)
class Verdict:
    """1件の記事に対する評価結果（REQ-F-003）。"""

    score: int
    reason: str
    suggested_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateRecord:
    """状態ファイル（`state.jsonl`）の1行に対応する（ADR-005）。

    同一 url の行が複数存在しうる。現在の状態は url ごとに
    evaluated_at が最大の行として再構成する（ADR-005 OQ-001）。
    """

    url: str
    title: str
    source_name: str
    evaluated_at: datetime
    score: int | None = None
    weight: int = 0
    final_score: int | None = None
    ingested: bool = False
    reason: str = ""
    suggested_tags: tuple[str, ...] = ()
    failure_count: int = 0


@dataclass(frozen=True)
class SourceOutcome:
    """1つの情報源の取得結果（F-004 AC-003 / AC-010）。"""

    source_name: str
    fetched: int = 0
    error: str | None = None


@dataclass
class RunSummary:
    """1回の実行のサマリ（REQ-F-008 / F-004）。"""

    sources: list[SourceOutcome] = field(default_factory=list)
    new_entries: int = 0
    evaluated: int = 0
    evaluation_failures: int = 0
    ingested: int = 0
    ingest_failures: int = 0
    deferred: int = 0
    score_distribution: dict[int, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    dry_run: bool = False
    state_persist_error: str | None = None
    weeks_since_previous_run: float | None = None
