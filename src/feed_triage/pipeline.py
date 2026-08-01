"""実行フローの組み立て（SPEC-005 フロー #3・#4）。

取得 → 突合 → 評価 → 判定 → 投入 → 記録 の順に adapters を呼び、
`RunSummary` と終了コードを返す。

**本モジュール自身は I/O を行わない。** 副作用はすべて `Adapters` として
外から注入されたものを呼ぶ形で発生する。これにより、組み立ての順序・
分岐・終了コードの決定を偽物のアダプタだけで検証できる。

**投入可否の判定をここで行う理由:** `domain.scoring` は決定論的な判定を持ち、
`adapters.ingest` は HTTP のみを担う。両者を繋ぐのは `adapters → domain` の
import を許されている本モジュールだけである（ADR-004 設計原則: 決定論的
部分と確率的部分の分離）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from feed_triage.contract import exit_codes
from feed_triage.contract.model import (
    Entry,
    EntryVerdict,
    RunRecord,
    RunSummary,
    Source,
    SourceOutcome,
    StateRecord,
)
from feed_triage.implementation.adapters.evaluate import EvaluationOutcome, OutcomeKind
from feed_triage.implementation.adapters.ingest import Candidate, IngestResult
from feed_triage.implementation.domain.scoring import (
    DEFAULT_HOT_THRESHOLD,
    DEFAULT_THRESHOLD,
    adjust,
    is_hot,
    should_ingest,
)
from feed_triage.implementation.domain.state import (
    DEFAULT_EVALUATION_LIMIT,
    DEFAULT_MAX_FAILURES,
    fold_records,
    is_processed,
    select_evaluation_targets,
)

SECONDS_PER_WEEK = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class RunOptions:
    """1回の実行に与えるオプション（SPEC-005 §4 入力(a)）。"""

    dry_run: bool = False
    verbose: bool = False


class _Evaluator(Protocol):
    def evaluate(self, entry: Entry) -> EvaluationOutcome: ...


class _Ingestor(Protocol):
    def ingest_all(self, candidates: list[Candidate]) -> IngestResult: ...


class _Store(Protocol):
    """状態の読み書き。`cli` が `store` / `persist` アダプタを束ねて渡す。"""

    def load_state(self) -> list[StateRecord]: ...

    def load_runs(self) -> list[RunRecord]: ...

    def append(self, records: list[StateRecord], run_record: RunRecord | None) -> None: ...

    def persist(self) -> None: ...


@dataclass(frozen=True)
class RunOutcome:
    """1回の実行の結果。

    `messages` は**標準エラーへ出す**文言（SPEC-004 §3）。サマリ（標準出力）
    とは出力先が異なるため分けて返す（REQ-NF-007）。
    """

    summary: RunSummary
    exit_code: int
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Evaluated:
    """評価段階の成果物。"""

    candidates: list[Candidate]
    records: list[StateRecord]
    verdicts: list[EntryVerdict]
    aborted: bool


@dataclass
class Adapters:
    """処理本体が用いる副作用の集合（SPEC-005 §4 出力「検証済みの設定」）。

    起動時検証を通過した設定と、構築済みのアダプタをまとめて受け取る。
    `cli` が組み立て、`pipeline` は呼ぶだけに徹する。
    """

    sources: list[Source]
    profile: str
    fetch: Callable[[list[Source]], tuple[list[Entry], list[SourceOutcome]]]
    evaluator: _Evaluator
    ingestor: _Ingestor
    store: _Store
    now: Callable[[], datetime]


def run(
    options: RunOptions,
    adapters: Adapters,
    *,
    evaluation_limit: int = DEFAULT_EVALUATION_LIMIT,
    max_failures: int = DEFAULT_MAX_FAILURES,
    threshold: int = DEFAULT_THRESHOLD,
    hot_threshold: int = DEFAULT_HOT_THRESHOLD,
) -> RunOutcome:
    """1回の実行を行い、サマリ・終了コード・標準エラーへの文言を返す。

    **例外を送出しない**（REQ-F-010）。個別の失敗は各アダプタが結果へ畳み、
    段階の全件失敗のみが終了コードに現れる（SPEC-005 §5）。
    """
    run_at = adapters.now()
    summary = RunSummary(dry_run=options.dry_run)

    entries, outcomes = adapters.fetch(adapters.sources)
    summary.sources = outcomes

    state = fold_records(adapters.store.load_state())
    _fill_previous_run(summary, adapters.store.load_runs(), run_at)

    targets = _select_targets(entries, state, max_failures, evaluation_limit)
    summary.new_entries = len(targets)

    evaluated = _evaluate_all(
        targets, adapters, state, summary, run_at, max_failures, threshold, hot_threshold
    )

    ingest = _ingest(evaluated.candidates, adapters, summary, options)
    _apply_ingest_results(evaluated.records, ingest)
    if options.dry_run:
        summary.entries = evaluated.verdicts

    persist_error = _persist(evaluated.records, adapters, summary, options, run_at)
    summary.completed = not evaluated.aborted

    return RunOutcome(
        summary=summary,
        exit_code=_exit_code(ingest, evaluated.aborted, persist_error, outcomes, adapters),
        messages=ingest.messages,
    )


def _select_targets(
    entries: list[Entry],
    state: dict[str, StateRecord],
    max_failures: int,
    limit: int,
) -> list[Entry]:
    """状態と突合して評価対象を選ぶ（SPEC-002 フロー #3）。

    **url をキーに重複を排除する。** 同一 url が複数フィードに現れても
    1度しか評価しない（REQ-F-002）。順序は取得順を保つ — どの記事が
    上限で持ち越されるかを決めるため（SPEC-001 §4）。
    """
    by_url: dict[str, Entry] = {}
    for item in entries:
        by_url.setdefault(item.url, item)

    selected = select_evaluation_targets(by_url.keys(), state, max_failures, limit)
    return [by_url[url] for url in selected]


def _evaluate_all(
    targets: list[Entry],
    adapters: Adapters,
    state: dict[str, StateRecord],
    summary: RunSummary,
    run_at: datetime,
    max_failures: int,
    threshold: int,
    hot_threshold: int,
) -> _Evaluated:
    """全対象を評価し、投入候補・記録すべき行・明細を作る。

    `aborted` は**中止したか**（HTTP 400 → SPEC-003 フロー #15）。中止しても
    それまでの記録は返し、呼び出し元が永続化する。
    """
    candidates: list[Candidate] = []
    records: list[StateRecord] = []
    verdicts: list[EntryVerdict] = []

    for target in targets:
        outcome = adapters.evaluator.evaluate(target)

        if outcome.kind is OutcomeKind.SPEC_ERROR:
            # 実装が是正すべき要求不正。続けても同じ結果になるため中止する
            return _Evaluated(candidates, records, verdicts, aborted=True)

        if not outcome.should_record:
            # API 障害・材料なし。**記録しない**（記録すると処理済み扱いとなり
            # 次回の再評価から漏れる → F-001 AC-015a）
            if outcome.kind is OutcomeKind.API_ERROR:
                summary.evaluation_failures += 1
            continue

        summary.evaluated += 1
        record = _build_record(target, outcome, state, adapters, run_at)
        records.append(record)

        if outcome.verdict is None:
            summary.evaluation_failures += 1
            if is_processed(record, max_failures):
                # 失敗回数が上限に達し以降再評価されない（F-004 AC-011a）
                summary.abandoned += 1
            continue

        summary.score_distribution[outcome.verdict.score] = (
            summary.score_distribution.get(outcome.verdict.score, 0) + 1
        )
        final_score = record.final_score
        assert final_score is not None
        will_ingest = should_ingest(final_score, threshold)

        # **投入対象でないものも含めて明細を作る**（F-005 AC-002）。
        # 投入アダプタは判定を通ったものしか受け取らないため（SPEC-004 §2）、
        # 明細をあちらに任せると閾値未満の行が dry-run 出力から消える
        verdicts.append(
            EntryVerdict(
                url=target.url,
                title=target.title,
                final_score=final_score,
                will_ingest=will_ingest,
            )
        )

        if will_ingest:
            candidates.append(
                Candidate(
                    entry=target,
                    verdict=outcome.verdict,
                    final_score=final_score,
                    will_ingest=True,
                    is_hot=is_hot(final_score, hot_threshold),
                    source_tags=_source_of(adapters, target).tags,
                )
            )

    return _Evaluated(candidates, records, verdicts, aborted=False)


def _build_record(
    target: Entry,
    outcome: EvaluationOutcome,
    state: dict[str, StateRecord],
    adapters: Adapters,
    run_at: datetime,
) -> StateRecord:
    """状態へ追記する1行を作る。

    **閾値以下のエントリも score 付きで記録する** — 後から閾値を検証する
    ための実測データであり、省略すると R-006 が満たせない。
    """
    weight = _source_of(adapters, target).weight
    previous = state.get(target.url)
    carried = previous.failure_count if previous is not None else 0

    if outcome.verdict is None:
        # 意味的不正。試行回数分だけ失敗回数を進める（F-001 AC-015）
        return StateRecord(
            url=target.url,
            title=target.title,
            source_name=target.source_name,
            evaluated_at=run_at,
            score=None,
            weight=weight,
            failure_count=carried + max(outcome.attempts, 1),
        )

    final_score = adjust(outcome.verdict.score, weight)
    return StateRecord(
        url=target.url,
        title=target.title,
        source_name=target.source_name,
        evaluated_at=run_at,
        score=outcome.verdict.score,
        weight=weight,
        final_score=final_score,
        ingested=False,
        reason=outcome.verdict.reason,
        suggested_tags=outcome.verdict.suggested_tags,
        failure_count=carried,
    )


def _ingest(
    candidates: list[Candidate],
    adapters: Adapters,
    summary: RunSummary,
    options: RunOptions,
) -> IngestResult:
    """投入を実行し、結果をサマリへ写す（SPEC-004 §4 の詰め方に従う）。"""
    result = adapters.ingestor.ingest_all(candidates)

    summary.ingested = result.ingested
    summary.ingest_attempted = result.attempted
    summary.ingest_failures = result.failures
    summary.ingest_failure_reasons = dict(result.failure_reasons)
    summary.ingest_unattempted = result.unattempted
    if not options.dry_run:
        summary.deferred = result.unattempted
    return result


def _apply_ingest_results(records: list[StateRecord], ingest: IngestResult) -> None:
    """投入に成功した url の行へ `ingested: true` を立てる（F-001 AC-006）。

    **打ち切りで未試行となった分は記録から外す** — 記録すると処理済み扱いに
    なり、認証失効1回でその週の投入対象が恒久的に失われる（フロー #11 / R-001）。
    """
    unattempted = {c.entry.url for c in ingest.unattempted_candidates}
    ingested = set(ingest.ingested_urls)

    kept: list[StateRecord] = []
    for record in records:
        if record.url in unattempted:
            continue
        if record.url in ingested:
            record = _with_ingested(record)
        kept.append(record)
    records[:] = kept


def _with_ingested(record: StateRecord) -> StateRecord:
    return StateRecord(
        url=record.url,
        title=record.title,
        source_name=record.source_name,
        evaluated_at=record.evaluated_at,
        score=record.score,
        weight=record.weight,
        final_score=record.final_score,
        ingested=True,
        reason=record.reason,
        suggested_tags=record.suggested_tags,
        failure_count=record.failure_count,
    )


def _persist(
    records: list[StateRecord],
    adapters: Adapters,
    summary: RunSummary,
    options: RunOptions,
    run_at: datetime,
) -> str | None:
    """状態と実行記録を追記して永続化する。失敗ならその旨を返す。

    **dry-run では何も書かない**（F-005 AC-004）。
    """
    if options.dry_run:
        return None

    run_record = RunRecord(
        run_at=run_at,
        sources={outcome.source_name: outcome.fetched for outcome in summary.sources},
        source_errors={
            outcome.source_name: outcome.error
            for outcome in summary.sources
            if outcome.error is not None
        },
        new_entries=summary.new_entries,
        evaluated=summary.evaluated,
        ingested=summary.ingested,
        deferred=summary.deferred,
    )

    try:
        adapters.store.append(records, run_record)
        adapters.store.persist()
    except Exception as exc:  # noqa: BLE001 - 例外種別はアダプタごとに異なる
        # **静かに成功扱いにしない。** 記録できないまま投入を続けると
        # 次回実行で重複投入（R-002 違反）が確定する
        message = str(exc) or type(exc).__name__
        summary.state_persist_error = message
        return message
    return None


def _fill_previous_run(
    summary: RunSummary, runs: list[RunRecord], run_at: datetime
) -> None:
    """前回実行の情報をサマリへ入れる（F-004 AC-003a / AC-009）。

    現在の状態は `run_at` が最大の行として再構成する（行順に依存しない）。
    """
    if not runs:
        return
    previous = max(runs, key=lambda record: record.run_at)
    summary.previous_sources = dict(previous.sources)
    elapsed = (run_at - previous.run_at).total_seconds()
    summary.weeks_since_previous_run = elapsed / SECONDS_PER_WEEK


def _source_of(adapters: Adapters, target: Entry) -> Source:
    """エントリの情報源定義を引き当てる。未定義なら重み0・タグなしとして扱う。"""
    for source in adapters.sources:
        if source.name == target.source_name:
            return source
    return Source(name=target.source_name, url="", weight=0, tags=())


def _exit_code(
    ingest: IngestResult,
    aborted: bool,
    persist_error: str | None,
    outcomes: list[SourceOutcome],
    adapters: Adapters,
) -> int:
    """終了コードを決定する（SPEC-005 §5 の優先順位表）。

    **次回の実行へ伝播する障害を、当該実行内で閉じる障害より優先して報せる。**
    """
    if persist_error is not None:
        # 記録の失敗は次回実行の入力を壊す唯一の経路であり最優先（§5）
        return exit_codes.STATE_PERSIST_FAILED
    if aborted:
        return exit_codes.SPEC_ERROR
    if adapters.sources and outcomes and all(o.error is not None for o in outcomes):
        # 定義0件の実行は含まない（§5 の OK 行）
        return exit_codes.FETCH_ALL_FAILED
    if ingest.all_failed:
        return exit_codes.INGEST_ALL_FAILED
    return exit_codes.OK
