"""実行フローの組み立てのテスト（SPEC-005 §3 フロー #3・#4 / §5）。

`pipeline.run()` は adapters を**引数で受け取る**ため、ここでは偽物を渡して
組み立ての順序・条件分岐・終了コードの決定だけを検証する。各アダプタ自身の
振る舞いは `test_fetch` / `test_evaluate` / `test_ingest` などが担う。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from feed_triage.contract import exit_codes
from feed_triage.contract.model import (
    Entry,
    RunRecord,
    Source,
    SourceOutcome,
    StateRecord,
    Verdict,
)
from feed_triage.implementation.adapters.evaluate import EvaluationOutcome, OutcomeKind
from feed_triage.implementation.adapters.ingest import Candidate, IngestResult
from feed_triage.pipeline import Adapters, RunOptions, run

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)


def source(name: str = "example", weight: int = 0, tags: tuple[str, ...] = ()) -> Source:
    return Source(name=name, url=f"https://{name}.test/feed", weight=weight, tags=tags)


def entry(url: str = "https://example.test/a", source_name: str = "example") -> Entry:
    return Entry(
        url=url, title="記事", summary="要約", published_at=None, source_name=source_name
    )


class FakeFetcher:
    def __init__(
        self,
        entries: list[Entry] | None = None,
        outcomes: list[SourceOutcome] | None = None,
    ) -> None:
        self.entries = entries if entries is not None else [entry()]
        self.outcomes = outcomes if outcomes is not None else [SourceOutcome("example", 1)]
        self.calls = 0

    def __call__(self, sources: list[Source]) -> tuple[list[Entry], list[SourceOutcome]]:
        self.calls += 1
        return self.entries, self.outcomes


class FakeEvaluator:
    """既定では全件を score=8 で成功させる。url ごとに結果を差し替えられる。"""

    def __init__(self, outcomes: dict[str, EvaluationOutcome] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.seen: list[str] = []

    def evaluate(self, target: Entry) -> EvaluationOutcome:
        self.seen.append(target.url)
        if target.url in self.outcomes:
            return self.outcomes[target.url]
        return EvaluationOutcome(
            OutcomeKind.OK, verdict=Verdict(score=8, reason="良い", suggested_tags=("llm",))
        )


class FakeIngestor:
    def __init__(self, result: IngestResult | None = None) -> None:
        self.result = result if result is not None else IngestResult()
        self.received: list[Candidate] = []
        self.calls = 0

    def ingest_all(self, candidates: list[Candidate]) -> IngestResult:
        self.calls += 1
        self.received = list(candidates)
        if self.result.attempted == 0 and self.result.ingested == 0:
            # 既定は「渡された分だけ成功」
            self.result.ingested = len(self.received)
            self.result.attempted = len(self.received)
        return self.result


class FakeStore:
    def __init__(
        self,
        records: list[StateRecord] | None = None,
        runs: list[RunRecord] | None = None,
    ) -> None:
        self.records = records or []
        self.runs = runs or []
        self.appended: list[StateRecord] = []
        self.appended_runs: list[RunRecord] = []
        self.persisted = 0
        self.persist_error: str | None = None

    def load_state(self) -> list[StateRecord]:
        return self.records

    def load_runs(self) -> list[RunRecord]:
        return self.runs

    def append(self, records: list[StateRecord], run_record: RunRecord | None) -> None:
        self.appended.extend(records)
        if run_record is not None:
            self.appended_runs.append(run_record)

    def persist(self) -> None:
        self.persisted += 1
        if self.persist_error is not None:
            raise PersistFailed(self.persist_error)


class PersistFailed(Exception):
    pass


def adapters(**kwargs: object) -> Adapters:
    kwargs.setdefault("sources", [source()])
    kwargs.setdefault("profile", "基準")
    kwargs.setdefault("fetch", FakeFetcher())
    kwargs.setdefault("evaluator", FakeEvaluator())
    kwargs.setdefault("ingestor", FakeIngestor())
    kwargs.setdefault("store", FakeStore())
    kwargs.setdefault("now", lambda: NOW)
    return Adapters(**kwargs)  # type: ignore[arg-type]


def options(**kwargs: object) -> RunOptions:
    return RunOptions(**kwargs)  # type: ignore[arg-type]


# --- 組み立ての順序（フロー #3） ---------------------------------------------


def test_取得_評価_投入_記録の順に実行される() -> None:
    """SPEC-005 フロー #3: SPEC-001 → 002 → 003 → 004 の順。"""
    fetcher = FakeFetcher()
    evaluator = FakeEvaluator()
    ingestor = FakeIngestor()
    store = FakeStore()

    outcome = run(
        options(), adapters(fetch=fetcher, evaluator=evaluator, ingestor=ingestor, store=store)
    )

    assert fetcher.calls == 1
    assert evaluator.seen == ["https://example.test/a"]
    assert ingestor.calls == 1
    assert store.persisted == 1
    assert outcome.exit_code == exit_codes.OK
    assert outcome.summary.completed is True


def test_サマリに各段階の件数が集約される() -> None:
    outcome = run(options(), adapters())

    assert outcome.summary.new_entries == 1
    assert outcome.summary.evaluated == 1
    assert outcome.summary.ingested == 1
    assert [outcome.source_name for outcome in outcome.summary.sources] == ["example"]


# --- 状態との突合（SPEC-002） ------------------------------------------------


def test_処理済みのエントリは評価されない() -> None:
    """R-002: 冪等性の要。突合を飛ばせば毎週同じ記事を再評価してレッド。"""
    known = StateRecord(
        url="https://example.test/a",
        title="記事",
        source_name="example",
        evaluated_at=NOW - timedelta(days=7),
        score=8,
    )
    evaluator = FakeEvaluator()

    outcome = run(
        options(), adapters(evaluator=evaluator, store=FakeStore(records=[known]))
    )

    assert evaluator.seen == []
    assert outcome.summary.new_entries == 0
    assert outcome.summary.evaluated == 0


def test_評価に失敗した記事は次回再評価される() -> None:
    """F-001 AC-018: 1回の失敗で恒久的に取りこぼしてはならない。"""
    failed = StateRecord(
        url="https://example.test/a",
        title="記事",
        source_name="example",
        evaluated_at=NOW - timedelta(days=7),
        score=None,
        failure_count=1,
    )
    evaluator = FakeEvaluator()

    run(options(), adapters(evaluator=evaluator, store=FakeStore(records=[failed])))

    assert evaluator.seen == ["https://example.test/a"]


def test_失敗回数が上限に達した記事は再評価されない() -> None:
    """F-001 AC-019: 恒久的に壊れた記事を追いかけ続けない。"""
    abandoned = StateRecord(
        url="https://example.test/a",
        title="記事",
        source_name="example",
        evaluated_at=NOW - timedelta(days=7),
        score=None,
        failure_count=3,
    )
    evaluator = FakeEvaluator()

    run(options(), adapters(evaluator=evaluator, store=FakeStore(records=[abandoned])))

    assert evaluator.seen == []


def test_同一_URL_が複数フィードに現れても1度しか評価しない() -> None:
    """REQ-F-002: 一意性は url で判定する。"""
    duplicated = [entry("https://example.test/a"), entry("https://example.test/a")]
    evaluator = FakeEvaluator()

    run(
        options(),
        adapters(fetch=FakeFetcher(entries=duplicated), evaluator=evaluator),
    )

    assert evaluator.seen == ["https://example.test/a"]


# --- スコアと投入判定（SPEC-004 との接続） ----------------------------------


def test_閾値未満のエントリは投入アダプタへ渡されない() -> None:
    """SPEC-004 §2: 投入は「突合済み・判定済みの集合のみを受け取る」。

    判定は `pipeline` が `domain.scoring` を使って行う（adapters → domain の
    import は禁止のため）。閾値未満まで渡すと、投入側が判定をやり直すか
    黙って捨てるかになり、責務が二重化する。
    """
    entries = [entry("https://example.test/high"), entry("https://example.test/low")]
    evaluator = FakeEvaluator(
        {
            "https://example.test/high": EvaluationOutcome(
                OutcomeKind.OK, verdict=Verdict(score=8, reason="")
            ),
            "https://example.test/low": EvaluationOutcome(
                OutcomeKind.OK, verdict=Verdict(score=2, reason="")
            ),
        }
    )
    ingestor = FakeIngestor()

    run(
        options(),
        adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator, ingestor=ingestor),
    )

    assert [c.entry.url for c in ingestor.received] == ["https://example.test/high"]
    assert all(c.will_ingest for c in ingestor.received)


def test_情報源の重みが補正後スコアに反映される() -> None:
    """REQ-F-004 / F-001 AC-005。"""
    ingestor = FakeIngestor()
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.OK, verdict=Verdict(4, ""))}
    )

    run(
        options(),
        adapters(sources=[source(weight=1)], evaluator=evaluator, ingestor=ingestor),
    )

    assert ingestor.received[0].final_score == 5
    assert ingestor.received[0].will_ingest is True


def test_情報源のタグが投入候補へ引き渡される() -> None:
    """F-001 AC-002b: `feeds.yaml` の tags を引き当てる。"""
    ingestor = FakeIngestor()

    run(options(), adapters(sources=[source(tags=("aws",))], ingestor=ingestor))

    assert ingestor.received[0].source_tags == ("aws",)


def test_閾値以下のエントリも状態に記録される() -> None:
    """R-006: 後から閾値を検証するための実測データ。省略すると成立しない。"""
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.OK, verdict=Verdict(2, ""))}
    )
    store = FakeStore()

    run(options(), adapters(evaluator=evaluator, store=store))

    assert len(store.appended) == 1
    assert store.appended[0].score == 2
    assert store.appended[0].ingested is False


# --- 評価失敗の扱い（SPEC-003 との接続） ------------------------------------


def test_評価に失敗したエントリは投入候補にならない() -> None:
    """F-001 AC-029: 範囲外スコアを投入判定に用いてはならない。"""
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.INVALID_VALUE, attempts=2)}
    )
    ingestor = FakeIngestor()

    outcome = run(options(), adapters(evaluator=evaluator, ingestor=ingestor))

    assert ingestor.received == []
    assert outcome.summary.evaluation_failures == 1


def test_意味的不正は失敗回数を進めて記録される() -> None:
    """F-001 AC-015: 試行回数分を failure_count に加算する。"""
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.INVALID_VALUE, attempts=2)}
    )
    store = FakeStore()

    run(options(), adapters(evaluator=evaluator, store=store))

    assert len(store.appended) == 1
    assert store.appended[0].score is None
    assert store.appended[0].failure_count == 2


def test_API障害は記録せず失敗回数も進めない() -> None:
    """F-001 AC-015a: 記録すると処理済み扱いになり次回の再評価から漏れる。"""
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.API_ERROR)}
    )
    store = FakeStore()

    run(options(), adapters(evaluator=evaluator, store=store))

    assert store.appended == []


def test_失敗回数が上限に達したエントリは放棄として数える() -> None:
    """F-004 AC-011a: 一時的な障害と恒久的な取りこぼしを区別する。"""
    almost = StateRecord(
        url="https://example.test/a",
        title="記事",
        source_name="example",
        evaluated_at=NOW - timedelta(days=7),
        score=None,
        failure_count=2,
    )
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.INVALID_VALUE, attempts=1)}
    )

    outcome = run(
        options(),
        adapters(evaluator=evaluator, store=FakeStore(records=[almost])),
    )

    assert outcome.summary.abandoned == 1


def test_HTTP400_は実行を中止するが評価済みは記録する() -> None:
    """SPEC-003 フロー #15 / SPEC-005 §5: 記録を先に完了させる。"""
    entries = [entry("https://example.test/a"), entry("https://example.test/b")]
    evaluator = FakeEvaluator(
        {"https://example.test/b": EvaluationOutcome(OutcomeKind.SPEC_ERROR)}
    )
    store = FakeStore()

    outcome = run(
        options(), adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator, store=store)
    )

    assert outcome.exit_code == exit_codes.SPEC_ERROR
    assert [r.url for r in store.appended] == ["https://example.test/a"]
    assert store.persisted == 1, "中止しても永続化は行う"
    assert outcome.summary.completed is False


# --- 終了コード（§5） --------------------------------------------------------


def test_投入対象0件は正常終了() -> None:
    """T-017 / F-001 AC-022: 新着のない週を失敗扱いにしない。"""
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.OK, verdict=Verdict(1, ""))}
    )

    outcome = run(options(), adapters(evaluator=evaluator))

    assert outcome.exit_code == exit_codes.OK


def test_投入を試行して全件失敗すれば_INGEST_ALL_FAILED() -> None:
    """T-018 / F-001 AC-014。"""
    result = IngestResult(attempted=2, ingested=0, failures=2)
    outcome = run(options(), adapters(ingestor=FakeIngestor(result)))
    assert outcome.exit_code == exit_codes.INGEST_ALL_FAILED


def test_評価失敗の理由が分類ごとに集計される() -> None:
    """TASK-100: 件数だけでは無人実行で原因を切り分けられない（F-002 AC-010）。

    実地の dry-run で40件全滅した際、認証失効なのかスキーマ不正なのかを
    サマリから判別できず、ログを取り直す必要があった。
    """
    entries = [entry(f"https://example.test/{i}") for i in range(3)]
    evaluator = FakeEvaluator(
        {
            "https://example.test/0": EvaluationOutcome(OutcomeKind.API_ERROR),
            "https://example.test/1": EvaluationOutcome(OutcomeKind.API_ERROR),
            "https://example.test/2": EvaluationOutcome(OutcomeKind.INVALID_VALUE, attempts=2),
        }
    )

    outcome = run(
        options(), adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator)
    )

    assert outcome.summary.evaluation_failure_reasons == {"api_error": 2, "invalid_value": 1}


def test_評価対象があり全件が評価に失敗すれば非0で終了する() -> None:
    """**実地の dry-run で発見**（2026-08-01）。API キーが無効で40件全滅したのに
    終了コードが 0 だった。

    無人実行では終了コードが唯一の異常検知手段であり（F-002 AC-010）、0 を返すと
    GitHub Actions は成功として通知しない。**供給が完全に途切れているのに
    運用者が気づけない**状態になる — 取得の全件失敗を非0にした TASK-072 と
    同じ論理が、評価段階にも当てはまる。
    """
    entries = [entry(f"https://example.test/{i}") for i in range(3)]
    evaluator = FakeEvaluator(
        {
            f"https://example.test/{i}": EvaluationOutcome(OutcomeKind.API_ERROR)
            for i in range(3)
        }
    )

    outcome = run(
        options(), adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator)
    )

    assert outcome.summary.evaluation_failures == 3
    assert outcome.exit_code == exit_codes.EVALUATE_ALL_FAILED


def test_一部でも評価に成功していれば正常終了する() -> None:
    """全件失敗のみを異常とする（REQ-F-010）。1件の障害で週次バッチを止めない。"""
    entries = [entry("https://example.test/ok"), entry("https://example.test/ng")]
    evaluator = FakeEvaluator(
        {"https://example.test/ng": EvaluationOutcome(OutcomeKind.API_ERROR)}
    )

    outcome = run(
        options(), adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator)
    )

    assert outcome.exit_code == exit_codes.OK


def test_評価対象が0件なら評価の全件失敗としない() -> None:
    """新着のない週を失敗扱いにしない（F-001 AC-022 と同じ論理）。"""
    known = StateRecord(
        url="https://example.test/a",
        title="記事",
        source_name="example",
        evaluated_at=NOW - timedelta(days=7),
        score=8,
    )
    outcome = run(options(), adapters(store=FakeStore(records=[known])))
    assert outcome.exit_code == exit_codes.OK


def test_取得の全滅と評価の全滅は同時に成立しない() -> None:
    """SPEC-005 §5 の優先順位の**前提**（T-026）。

    取得が全滅すれば評価対象が0件になり、`EVALUATE_ALL_FAILED` の条件
    （対象が1件以上）は成立しない。両者が同時に成立するのは「取得は一部
    成功したが評価は全滅した」場合のみであり、そのとき運用者が見るべきは
    評価側の障害である。**この前提が崩れると優先順位の根拠が失われる。**
    """
    failed = [SourceOutcome("example", error="接続できません")]
    outcome = run(options(), adapters(fetch=FakeFetcher(entries=[], outcomes=failed)))

    assert outcome.summary.new_entries == 0, "取得全滅なら評価対象は0件"
    assert outcome.exit_code == exit_codes.FETCH_ALL_FAILED


def test_全情報源の取得に失敗すれば_FETCH_ALL_FAILED() -> None:
    """SPEC-001 フロー #18 / TASK-072。"""
    failed = [SourceOutcome("example", error="接続できません")]
    outcome = run(
        options(), adapters(fetch=FakeFetcher(entries=[], outcomes=failed))
    )
    assert outcome.exit_code == exit_codes.FETCH_ALL_FAILED


def test_情報源の定義が0件なら正常終了() -> None:
    """§5: 定義0件は FETCH_ALL_FAILED に含まない（F-001 AC-024）。"""
    outcome = run(
        options(), adapters(sources=[], fetch=FakeFetcher(entries=[], outcomes=[]))
    )
    assert outcome.exit_code == exit_codes.OK


def test_永続化に失敗すれば_STATE_PERSIST_FAILED() -> None:
    """F-002 AC-014 / AC-017。"""
    store = FakeStore()
    store.persist_error = "状態の保存に失敗しました"

    outcome = run(options(), adapters(store=store))

    assert outcome.exit_code == exit_codes.STATE_PERSIST_FAILED
    assert outcome.summary.state_persist_error is not None


def test_永続化失敗は投入全件失敗より優先される() -> None:
    """T-020 / §5 優先順位: 次回実行の入力を壊す障害を優先して報せる。

    逆順にすると、記録が失われていることに運用者が気づけない。
    """
    store = FakeStore()
    store.persist_error = "push に失敗しました"
    result = IngestResult(attempted=2, ingested=0, failures=2)

    outcome = run(options(), adapters(store=store, ingestor=FakeIngestor(result)))

    assert outcome.exit_code == exit_codes.STATE_PERSIST_FAILED


def test_永続化失敗は_SPEC_ERROR_より優先される() -> None:
    """§5: 両者は同時に成立しうる（SPEC-003 フロー #15 → SPEC-002 フロー #19）。"""
    store = FakeStore()
    store.persist_error = "push に失敗しました"
    evaluator = FakeEvaluator(
        {"https://example.test/a": EvaluationOutcome(OutcomeKind.SPEC_ERROR)}
    )

    outcome = run(options(), adapters(store=store, evaluator=evaluator))

    assert outcome.exit_code == exit_codes.STATE_PERSIST_FAILED


def test_取得全件失敗は投入全件失敗より優先される() -> None:
    """§5 優先順位表: FETCH_ALL_FAILED(4位) > INGEST_ALL_FAILED(5位)。"""
    failed = [SourceOutcome("example", error="接続できません")]
    result = IngestResult(attempted=1, ingested=0, failures=1)

    outcome = run(
        options(),
        adapters(fetch=FakeFetcher(entries=[], outcomes=failed), ingestor=FakeIngestor(result)),
    )

    assert outcome.exit_code == exit_codes.FETCH_ALL_FAILED


# --- dry-run（F-005） --------------------------------------------------------


def test_dry_run_では状態を更新しない() -> None:
    """F-005 AC-004: dry-run では状態を更新しない。"""
    store = FakeStore()

    outcome = run(options(dry_run=True), adapters(store=store))

    assert store.appended == []
    assert store.appended_runs == []
    assert store.persisted == 0
    assert outcome.summary.dry_run is True
    assert outcome.exit_code == exit_codes.OK


def test_dry_run_でも評価は実行される() -> None:
    """F-005: スコアのみ出力するため評価そのものは行う。"""
    evaluator = FakeEvaluator()
    run(options(dry_run=True), adapters(evaluator=evaluator))
    assert evaluator.seen == ["https://example.test/a"]


def test_dry_run_では投入が行われない() -> None:
    """F-005 AC-001。"""
    ingestor = FakeIngestor(IngestResult(ingested=1))
    outcome = run(options(dry_run=True), adapters(ingestor=ingestor))
    assert outcome.summary.dry_run is True


def test_dry_run_の明細に閾値未満のエントリも含まれる() -> None:
    """F-005 AC-002: 明細は**評価した全件**を並べる。

    投入アダプタは判定を通ったものしか受け取らない（SPEC-004 §2）ため、
    明細の生成をあちらに任せると閾値未満の行が消える。dry-run は閾値の
    妥当性を確かめるための機能であり、**落ちた側こそが見たい情報**である。
    """
    entries = [entry("https://example.test/high"), entry("https://example.test/low")]
    evaluator = FakeEvaluator(
        {
            "https://example.test/high": EvaluationOutcome(
                OutcomeKind.OK, verdict=Verdict(score=8, reason="")
            ),
            "https://example.test/low": EvaluationOutcome(
                OutcomeKind.OK, verdict=Verdict(score=2, reason="")
            ),
        }
    )

    outcome = run(
        options(dry_run=True),
        adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator),
    )

    assert [(v.url, v.final_score, v.will_ingest) for v in outcome.summary.entries] == [
        ("https://example.test/high", 8, True),
        ("https://example.test/low", 2, False),
    ]


def test_通常実行では明細を作らない() -> None:
    """SPEC-006 §4: 明細は dry-run のみ。通常実行のサマリを肥大させない。"""
    outcome = run(options(), adapters())
    assert outcome.summary.entries == []


# --- 実行記録（SPEC-002 §4） -------------------------------------------------


def test_実行記録が追記される() -> None:
    store = FakeStore()
    run(options(), adapters(store=store))

    assert len(store.appended_runs) == 1
    assert store.appended_runs[0].run_at == NOW
    assert store.appended_runs[0].sources == {"example": 1}


def test_前回実行からの経過週数がサマリに入る() -> None:
    """F-004 AC-009 / SPEC-006。"""
    previous = RunRecord(run_at=NOW - timedelta(days=14), sources={"example": 5})
    outcome = run(options(), adapters(store=FakeStore(runs=[previous])))

    assert outcome.summary.weeks_since_previous_run == pytest.approx(2.0)
    assert outcome.summary.previous_sources == {"example": 5}


def test_初回実行では経過週数が未定義になる() -> None:
    outcome = run(options(), adapters())
    assert outcome.summary.weeks_since_previous_run is None
    assert outcome.summary.previous_sources == {}


# --- 上限（F-001 AC-025） ----------------------------------------------------


def test_評価件数の上限を超える分は次回へ持ち越される() -> None:
    """F-001 AC-025: 溢れた分は記録されず次回に持ち越される。"""
    entries = [entry(f"https://example.test/{i}") for i in range(5)]
    evaluator = FakeEvaluator()

    outcome = run(
        options(),
        adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator),
        evaluation_limit=3,
    )

    assert len(evaluator.seen) == 3
    assert outcome.summary.evaluated == 3


def test_SKIPPED_が混ざっても評価の全滅を検知する() -> None:
    """**diff-review の指摘（2026-08-01）。**

    分母を `len(targets)` にすると、SKIPPED（材料がなく評価しなかった件）が
    混ざるだけで `evaluation_failures < targets` となり全滅を見逃す。
    **TASK-099 で塞いだはずの穴が、SKIPPED 1件で再発する。**

    分母は「実際に評価を試みた件数」でなければならない。
    """
    entries = [entry(f"https://example.test/{i}") for i in range(3)]
    evaluator = FakeEvaluator(
        {
            "https://example.test/0": EvaluationOutcome(OutcomeKind.SKIPPED),
            "https://example.test/1": EvaluationOutcome(OutcomeKind.API_ERROR),
            "https://example.test/2": EvaluationOutcome(OutcomeKind.API_ERROR),
        }
    )

    outcome = run(
        options(), adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator)
    )

    assert outcome.exit_code == exit_codes.EVALUATE_ALL_FAILED


def test_全件が_SKIPPED_なら全滅としない() -> None:
    """SKIPPED は失敗ではない（F-001 AC-023a）。

    材料がないだけの記事しかない週を失敗扱いにすると、`FETCH_ALL_FAILED` と
    違って**運用者に是正できることがない**通知が飛ぶ。
    """
    entries = [entry(f"https://example.test/{i}") for i in range(2)]
    evaluator = FakeEvaluator(
        {
            f"https://example.test/{i}": EvaluationOutcome(OutcomeKind.SKIPPED)
            for i in range(2)
        }
    )

    outcome = run(
        options(), adapters(fetch=FakeFetcher(entries=entries), evaluator=evaluator)
    )

    assert outcome.exit_code == exit_codes.OK
