"""状態レコードの畳み込みと突合のテスト（ADR-005 / F-001 AC-018・AC-019）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from feed_triage.contract.model import StateRecord
from feed_triage.implementation.domain.state import (
    fold_records,
    is_processed,
    select_new_entry_urls,
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


class TestSelectNewEntryUrls:
    def test_未知のurlは評価対象になる(self) -> None:
        assert select_new_entry_urls(["https://example.com/new"], {}, max_failures=3) == [
            "https://example.com/new"
        ]

    def test_評価済みのurlは除外される(self) -> None:
        state = fold_records([record("https://example.com/a", score=8)])
        assert select_new_entry_urls(["https://example.com/a"], state, max_failures=3) == []

    def test_失敗回数が上限未満のurlは再評価対象に含まれる(self) -> None:
        state = fold_records([record("https://example.com/a", score=None, failure_count=1)])
        assert select_new_entry_urls(["https://example.com/a"], state, max_failures=3) == [
            "https://example.com/a"
        ]

    def test_失敗回数が上限に達したurlは除外される(self) -> None:
        state = fold_records([record("https://example.com/a", score=None, failure_count=3)])
        assert select_new_entry_urls(["https://example.com/a"], state, max_failures=3) == []

    def test_重複するurlは一度だけ返る(self) -> None:
        urls = ["https://example.com/a", "https://example.com/a"]
        assert select_new_entry_urls(urls, {}, max_failures=3) == ["https://example.com/a"]

    def test_入力の順序が保たれる(self) -> None:
        urls = ["https://example.com/b", "https://example.com/a"]
        assert select_new_entry_urls(urls, {}, max_failures=3) == urls
