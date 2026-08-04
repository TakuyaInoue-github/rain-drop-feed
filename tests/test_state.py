"""状態レコードの畳み込みと突合のテスト（ADR-005 / F-001 AC-018・AC-019）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from feed_triage.contract.model import StateRecord
from feed_triage.implementation.domain.state import (
    DEFAULT_EVALUATION_LIMIT,
    DEFAULT_MAX_FAILURES,
    fold_records,
    is_processed,
    select_evaluation_targets,
)

BASE = datetime(2026, 7, 27, 21, 17, tzinfo=timezone.utc)


def record(
    url: str,
    *,
    at: datetime = BASE,
    score: int | None = 8,
    failure_count: int = 0,
    evaluated: bool | None = None,
    unscorable: bool = False,
) -> StateRecord:
    """`evaluated` を省略すると `score` の有無から補完する。

    多軸化以前の行（`evaluated` を持たない）を読み戻したときと同じ状態になる。
    """
    return StateRecord(
        url=url,
        title=f"title of {url}",
        source_name="example-blog",
        evaluated_at=at,
        score=score,
        failure_count=failure_count,
        evaluated=(score is not None) if evaluated is None else evaluated,
        unscorable=unscorable,
    )


class TestFoldRecords:
    def test_単一のレコードはそのまま現在状態になる(self) -> None:
        r = record("https://example.com/a")
        assert fold_records([r]) == {"https://example.com/a": r}

    def test_同一urlはevaluated_atが最大の行が採用される(self) -> None:
        old = record("https://example.com/a", at=BASE, score=3)
        new = record("https://example.com/a", at=BASE + timedelta(days=7), score=9)
        assert fold_records([old, new])["https://example.com/a"].score == 9

    def test_行順が逆でもevaluated_atが最大の行が採用される(self) -> None:
        """rebase により行順は保証されない（ADR-002 OQ-004）。"""
        old = record("https://example.com/a", at=BASE, score=3)
        new = record("https://example.com/a", at=BASE + timedelta(days=7), score=9)
        assert fold_records([new, old])["https://example.com/a"].score == 9

    def test_異なるurlは別々に保持される(self) -> None:
        a = record("https://example.com/a")
        b = record("https://example.com/b")
        assert set(fold_records([a, b])) == {"https://example.com/a", "https://example.com/b"}

    def test_空の入力は空の辞書になる(self) -> None:
        assert fold_records([]) == {}


class TestIsProcessed:
    def test_評価に成功していれば処理済み(self) -> None:
        assert is_processed(record("u", score=5), max_failures=3) is True

    def test_失敗回数が上限未満なら未処理として再評価対象になる(self) -> None:
        r = record("u", score=None, failure_count=1)
        assert is_processed(r, max_failures=3) is False

    def test_失敗回数が上限ちょうどなら処理済みとして打ち切る(self) -> None:
        r = record("u", score=None, failure_count=3)
        assert is_processed(r, max_failures=3) is True

    def test_失敗回数が上限を超えていても処理済み(self) -> None:
        r = record("u", score=None, failure_count=4)
        assert is_processed(r, max_failures=3) is True

    def test_多軸化以前の行は評価済みとして扱う(self) -> None:
        """ADR-006: 旧行は `evaluated` を持たないが再評価してはならない。

        読み戻し時に `score` から補完されるため、ここでは補完済みの
        レコードが処理済みと判定されることを固定する。
        """
        r = record("u", score=7, evaluated=True)
        assert is_processed(r, max_failures=3) is True

    def test_採点不能は評価済みとして扱い再評価しない(self) -> None:
        """ADR-006 の中核: `unscorable` は「評価失敗」ではない。

        判断材料がなく採点できなかった記事は、評価そのものは成立している。
        失敗として扱うと失敗回数の上限に達するまで**毎週再評価され続け**、
        材料が増えないまま API コストだけがかかる。
        """
        r = record("u", score=None, evaluated=True, unscorable=True, failure_count=0)
        assert is_processed(r, max_failures=3) is True

    def test_評価が成立していなければ失敗回数で判断する(self) -> None:
        """`evaluated` が偽のときだけ失敗回数を見る（値域から独立させた帰結）。"""
        assert is_processed(record("u", score=None, evaluated=False), max_failures=3) is False


class TestSelectEvaluationTargets:
    def test_未知のurlは評価対象になる(self) -> None:
        assert select_evaluation_targets(["https://example.com/new"], {}, max_failures=3) == [
            "https://example.com/new"
        ]

    def test_評価済みのurlは除外される(self) -> None:
        """F-001 AC-018a: 再評価で成功した記事は以降対象外。"""
        state = fold_records([record("https://example.com/a", score=8)])
        assert select_evaluation_targets(["https://example.com/a"], state, max_failures=3) == []

    def test_失敗回数が上限未満のurlは再評価対象に含まれる(self) -> None:
        state = fold_records([record("https://example.com/a", score=None, failure_count=1)])
        assert select_evaluation_targets(["https://example.com/a"], state, max_failures=3) == [
            "https://example.com/a"
        ]

    def test_失敗回数が上限に達したurlは除外される(self) -> None:
        state = fold_records([record("https://example.com/a", score=None, failure_count=3)])
        assert select_evaluation_targets(["https://example.com/a"], state, max_failures=3) == []

    def test_重複するurlは一度だけ返る(self) -> None:
        urls = ["https://example.com/a", "https://example.com/a"]
        assert select_evaluation_targets(urls, {}, max_failures=3) == ["https://example.com/a"]

    def test_新規同士の入力順序は保たれる(self) -> None:
        urls = ["https://example.com/b", "https://example.com/a"]
        assert select_evaluation_targets(urls, {}, max_failures=3) == urls


class TestEvaluationTargetPriority:
    """F-001 AC-025a: 上限に達したとき新規を優先し、再評価で飢餓させない。"""

    def _state_with_failure(self, *urls: str) -> dict[str, StateRecord]:
        return fold_records([record(u, score=None, failure_count=1) for u in urls])

    def test_上限がなければ新規を先に再評価を後に返す(self) -> None:
        state = self._state_with_failure("https://example.com/old")
        got = select_evaluation_targets(
            ["https://example.com/old", "https://example.com/new"], state, max_failures=3
        )
        assert got == ["https://example.com/new", "https://example.com/old"]

    def test_上限に達したとき新規が優先される(self) -> None:
        state = self._state_with_failure("https://example.com/old")
        got = select_evaluation_targets(
            ["https://example.com/old", "https://example.com/new"],
            state,
            max_failures=3,
            limit=1,
        )
        assert got == ["https://example.com/new"]

    def test_再評価対象が上限を超えても新規は締め出されない(self) -> None:
        """再評価が上限枠を占有して新規の供給を止めないこと（R-001）。"""
        old = [f"https://example.com/old{i}" for i in range(5)]
        state = self._state_with_failure(*old)
        got = select_evaluation_targets(
            [*old, "https://example.com/new"], state, max_failures=3, limit=3
        )
        assert "https://example.com/new" in got
        assert got[0] == "https://example.com/new"

    def test_新規だけで上限に達したら再評価は次回に持ち越される(self) -> None:
        state = self._state_with_failure("https://example.com/old")
        new = [f"https://example.com/new{i}" for i in range(3)]
        got = select_evaluation_targets(
            [*new, "https://example.com/old"], state, max_failures=3, limit=3
        )
        assert got == new
        assert "https://example.com/old" not in got

    def test_再評価対象はevaluated_atが古い順に選ばれる(self) -> None:
        """SPEC-002 §6: 飢餓を構造的に防ぐ。取得順に依存しない。"""
        newest = record(
            "https://example.com/newest", at=BASE + timedelta(days=14), score=None, failure_count=1
        )
        oldest = record("https://example.com/oldest", at=BASE, score=None, failure_count=1)
        middle = record(
            "https://example.com/middle", at=BASE + timedelta(days=7), score=None, failure_count=1
        )
        state = fold_records([newest, oldest, middle])
        # 入力順は新しい順だが、選定は古い順になる
        got = select_evaluation_targets(
            [
                "https://example.com/newest",
                "https://example.com/middle",
                "https://example.com/oldest",
            ],
            state,
            max_failures=3,
        )
        assert got == [
            "https://example.com/oldest",
            "https://example.com/middle",
            "https://example.com/newest",
        ]

    def test_上限があるとき最も古い再評価対象が選ばれる(self) -> None:
        newest = record(
            "https://example.com/newest", at=BASE + timedelta(days=14), score=None, failure_count=1
        )
        oldest = record("https://example.com/oldest", at=BASE, score=None, failure_count=1)
        state = fold_records([newest, oldest])
        got = select_evaluation_targets(
            ["https://example.com/newest", "https://example.com/oldest"],
            state,
            max_failures=3,
            limit=1,
        )
        assert got == ["https://example.com/oldest"]

    def test_上限が候補数を上回るときは全件返る(self) -> None:
        state = self._state_with_failure("https://example.com/old")
        got = select_evaluation_targets(
            ["https://example.com/old", "https://example.com/new"],
            state,
            max_failures=3,
            limit=99,
        )
        assert len(got) == 2


# --- 暫定値の定数（2026-07-28 に確定。実測後に見直す） --------------------


def test_評価件数の上限は500件() -> None:
    """TASK-028。情報源 58 件の規模に対し、平常時に持ち越しが出ない値。

    上限に達すること自体が異常の兆候として機能する値であり、
    小さすぎると平常時に持ち越しが発生して兆候として使えなくなる。
    """
    assert DEFAULT_EVALUATION_LIMIT == 500


def test_失敗回数の上限は3回() -> None:
    """TASK-053。実行内リトライ1回と組み合わさり実質2週分の追跡になる。"""
    assert DEFAULT_MAX_FAILURES == 3


def test_上限件数が既定値のとき超過分が持ち越される() -> None:
    """定数が select_evaluation_targets の limit として機能すること。"""
    records: dict[str, StateRecord] = {}
    urls = [f"https://example.com/{i}" for i in range(DEFAULT_EVALUATION_LIMIT + 5)]
    selected = select_evaluation_targets(
        urls,
        records,
        max_failures=DEFAULT_MAX_FAILURES,
        limit=DEFAULT_EVALUATION_LIMIT,
    )
    assert len(selected) == DEFAULT_EVALUATION_LIMIT
