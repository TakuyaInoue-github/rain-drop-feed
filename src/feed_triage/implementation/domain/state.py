"""状態レコードの畳み込みと突合。副作用を持たない。

ADR-005 の決定により、状態は追記専用の JSONL として保持され、
同一 url の行が複数存在しうる。現在の状態は url ごとに
evaluated_at が最大の行として再構成する（ADR-005 OQ-001）。
行順ではなくタイムスタンプで決めるのは、push 競合時の rebase により
行順が保証されないため（ADR-002 OQ-004）。
"""

from __future__ import annotations

from collections.abc import Iterable

from feed_triage.contract.model import StateRecord


def fold_records(records: Iterable[StateRecord]) -> dict[str, StateRecord]:
    """レコード列を url ごとの現在状態に畳み込む。

    同一 url が複数ある場合は evaluated_at が最大のものを採用する。
    evaluated_at が同値の場合は後に現れたほうを採用する（決定的に振る舞う）。
    """
    current: dict[str, StateRecord] = {}
    for record in records:
        existing = current.get(record.url)
        if existing is None or record.evaluated_at >= existing.evaluated_at:
            current[record.url] = record
    return current


def is_processed(record: StateRecord, max_failures: int) -> bool:
    """このレコードを「処理済み」とみなすか。

    評価に成功していれば処理済み。失敗している場合は、失敗回数が上限に
    達したときのみ処理済みとして扱い、以降再評価しない（REQ-F-010 の結論。
    F-001 AC-018 / AC-019）。
    """
    if record.score is not None:
        return True
    return record.failure_count >= max_failures


def select_new_entry_urls(
    candidate_urls: Iterable[str],
    state: dict[str, StateRecord],
    max_failures: int,
) -> list[str]:
    """候補 url のうち、評価対象とすべきものを順序を保って返す。

    未知の url に加え、評価に失敗したが失敗回数が上限未満のものも
    再評価の対象に含める（F-001 AC-018）。
    """
    selected: list[str] = []
    seen: set[str] = set()
    for url in candidate_urls:
        if url in seen:
            continue
        seen.add(url)
        record = state.get(url)
        if record is None or not is_processed(record, max_failures):
            selected.append(url)
    return selected
