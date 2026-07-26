"""状態レコードの畳み込みと突合のテスト（ADR-005 / F-001 AC-018・AC-019）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from feed_triage.contract.model import StateRecord
from feed_triage.implementation.domain.state import (
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
) -> StateRecord:
    return StateRecord(
        url=url,
        title=f"title of {url}",
        source_name="example-blog",
        evaluated_at=at,
        score=score,
        failure_count=failure_count,
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
        got = select_evaluation_targets([*new, "https://example.com/old"], state, max_failures=3, limit=3)
        assert got == new
        assert "https://example.com/old" not in got

    def test_上限が候補数を上回るときは全件返る(self) -> None:
        state = self._state_with_failure("https://example.com/old")
        got = select_evaluation_targets(
            ["https://example.com/old", "https://example.com/new"],
            state,
            max_failures=3,
            limit=99,
        )
        assert len(got) == 2
