"""層をまたいで受け渡される型定義。副作用も依存も持たない。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SCORE_MIN = 0
SCORE_MAX = 10
"""評価スコアの値域（REQ-F-003）。

`domain`（判定）と `adapters`（永続化時の丸め）の**双方が参照する**ため
contract 層に置く。adapters → domain の import は禁じられており（ADR-004）、
domain 側に置くと adapters で値を重複定義することになる。

**多軸化（ADR-006）以降は旧基準の列。** 2026-08 以前に評価した行にのみ存在する。
"""

JUDGMENT_MIN = 0
JUDGMENT_MAX = 5
"""判断の主軸の値域（ADR-006）。→ `SCORE_MIN` と同じ理由で contract 層に置く。"""

MECHANISM_MIN = 0
MECHANISM_MAX = 2
"""機構性（仕組みへの踏み込み）の値域（ADR-006）。"""

SCOPE_VALUES = ("core", "broad", "periphery", "outside")
"""射程の取りうる値（ADR-006）。

**`outside` 以外は収集の候補に残る** — 射程は除外ではなく配架のために判定する。
"""

JUDGMENT_MARKERS = (
    "立場の表明",
    "通説への反論",
    "他案の棄却",
    "失敗の記述",
    "再定義",
    "固有の語彙",
    "一人称の判断",
    "迷いの残存",
    "異分野からの持ち込み",
)
"""judgment の根拠として観測されうるマーカー（ADR-006）。"""


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

    # --- 多軸判定（ADR-006）。すべて任意項目 -------------------------------
    # **必須項目は url / evaluated_at の2つのまま増やさない。** 増やすと過去の
    # 行が読み込み時にスキップされ、全件が新規扱いとなって重複投入する
    # （R-002 違反）。
    judgment: int | None = None
    """著者の判断が本文に残っているか（0-5）。収集可否を決める主軸。"""

    mechanism: int | None = None
    """仕組みの層への踏み込み（0-2）。judgment とは独立した加点材料。"""

    scope: str | None = None
    """技術領域（`core` / `broad` / `periphery` / `outside`）。

    **除外ではなく配架のために判定する。** `outside` 以外は収集の候補に残る。
    """

    unscorable: bool = False
    """判断材料がなく採点できなかった。**低評価とは別の状態**。"""

    judgment_markers: tuple[str, ...] = ()
    """judgment の根拠として観測されたマーカー。"""

    priority: int | None = None
    """`judgment * 2 + mechanism`。並べ替えに用いる。"""

    evaluated: bool = False
    """評価が成立したか。**状態導出の唯一の判定軸**（ADR-006）。

    `score is not None` を「評価成功」の代理に使うと、`unscorable`（評価は
    成立したが採点しなかった）を評価失敗と区別できず毎週再評価される。
    値域から独立したフラグにすることで、以後軸を増やしても状態導出が壊れない。
    """


@dataclass(frozen=True)
class RunRecord:
    """`runs.jsonl` の1行に対応する実行単位の記録（SPEC-002 §4）。

    エントリ単位の状態からは復元できない情報を保持する。現在の状態は
    `run_at` が最大の行として再構成する。dry-run では追記しない。
    """

    run_at: datetime
    sources: dict[str, int] = field(default_factory=dict)
    """情報源名 → 取得件数。**取得0件の情報源も含める**（F-004 AC-003a）。"""
    source_errors: dict[str, str] = field(default_factory=dict)
    new_entries: int = 0
    evaluated: int = 0
    ingested: int = 0
    deferred: int = 0


@dataclass(frozen=True)
class SourceOutcome:
    """1つの情報源の取得結果（F-004 AC-003 / AC-010）。"""

    source_name: str
    fetched: int = 0
    error: str | None = None


@dataclass(frozen=True)
class EntryVerdict:
    """dry-run の明細行1件（F-005 AC-002 / SPEC-006 §4）。"""

    url: str
    title: str = ""
    final_score: int | None = None
    """補正後スコア。**0〜10 に丸めない**（SPEC-004 §4 の値域規定）。None は評価失敗。"""
    will_ingest: bool = False


@dataclass
class RunSummary:
    """1回の実行のサマリ（REQ-F-008 / F-004）。

    実行開始時に構築し、各段階が埋める（SPEC-006 §2）。途中で例外が発生しても
    それまでに埋まった範囲が残るため、部分的なサマリを出力できる（F-004 AC-013）。
    """

    sources: list[SourceOutcome] = field(default_factory=list)
    new_entries: int = 0
    evaluated: int = 0
    evaluation_failures: int = 0
    evaluation_failure_reasons: dict[str, int] = field(default_factory=dict)
    """評価失敗の分類（`OutcomeKind` の値）→ 件数（TASK-100）。

    **件数だけでは無人実行で原因を切り分けられない**（F-002 AC-010）。実地の
    dry-run で40件全滅した際、認証失効なのかスキーマ不正なのかが判別できず、
    ログを別途取り直す必要があった。
    """
    abandoned: int = 0
    """失敗回数が上限に達し、以降再評価されなくなった記事の件数（F-004 AC-011a）。

    一時的な障害（evaluation_failures）と恒久的な取りこぼしを区別するために持つ。
    """
    ingested: int = 0
    """通常実行では投入に成功した件数、dry-run では投入対象と判定された件数。

    両者は排他であり（dry-run では POST を行わない）、サマリ上は文言で区別する
    （`投入` / `投入対象` → SPEC-006 §5）。
    """
    ingest_attempted: int = 0
    """実際に POST を試行した件数（F-004 AC-016 / SPEC-004 フロー #15）。

    `ingest_unattempted` を含まない。全件失敗の判定はこの値を分母とする。
    `ingested + ingest_failures` で導出せず独立して受け取るのは、SPEC-006 が
    集計しない原則に従うため（SPEC-006 §1）。
    """
    ingest_failures: int = 0
    ingest_failure_reasons: dict[str, int] = field(default_factory=dict)
    """SPEC-004 の失敗理由コード → 件数（F-004 AC-012）。

    状態には記録せずサマリでのみ集計する（SPEC-004 §4）。
    """
    ingest_unattempted: int = 0
    """401/403 による打ち切りで POST を試行しなかった件数（SPEC-004 §4）。

    成功にも失敗にも数えない。INGEST_ALL_FAILED の分母にも含めない。
    """
    deferred: int = 0
    score_distribution: dict[int, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    dry_run: bool = False
    state_persist_error: str | None = None
    weeks_since_previous_run: float | None = None
    previous_sources: dict[str, int] = field(default_factory=dict)
    """前回実行の情報源別取得件数（F-004 AC-003a）。空なら初回実行として `-` を表示する。"""
    entries: list[EntryVerdict] = field(default_factory=list)
    """dry-run の明細（F-005 AC-002）。通常実行では空のまま。"""
    completed: bool = True
    """処理本体が最後まで到達したか。False なら未完了の標識を付ける（F-004 AC-013）。"""
