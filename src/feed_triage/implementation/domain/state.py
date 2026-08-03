"""状態レコードの畳み込みと突合。副作用を持たない。

ADR-005 の決定により、状態は追記専用の JSONL として保持され、
同一 url の行が複数存在しうる。現在の状態は url ごとに
evaluated_at が最大の行として再構成する（ADR-005 OQ-001）。
行順ではなくタイムスタンプで決めるのは、push 競合時の rebase により
行順が保証されないため（ADR-002 OQ-004）。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from feed_triage.contract.model import StateRecord

DEFAULT_EVALUATION_LIMIT = 500
"""1回の実行で評価する件数の上限（F-001 AC-025 / SPEC-002 OQ-001）。

**暫定値。実測後に見直す**（TASK-028）。**上限に達すること自体が異常の兆候**
として機能させるため、平常時の新着を吸収できる値に置く。

**2026-08-03 に 200 → 500 へ引き上げた。** 情報源を 12 → 58 件に拡大した
結果、初回実行の取得が約 1,900 件（既知分を含む総数）に達し、200 のままでは
定常状態に入るまで9週かかる見込みだった。

**REQ-NF-001（30分）との関係:** 評価1件 2.7〜4.8秒の実測から、500件では
22〜40分となり**上振れ時は目標を超える**。以下の理由でこの値を採る。
- 超過しても Actions の `timeout-minutes: 45` 内であり、途中で切れても
  未評価分は次回へ持ち越すため取りこぼしは生じない
- 上限に達するのは初回とその数週のみで、定常状態では新着数が上限を大きく
  下回る（週あたり数十〜百件程度の見込み）

**見直し条件:** 定常状態に入った後も持ち越しが継続する、または実行時間が
45分に迫る場合。実測は TASK-028 に記録する。
"""

DEFAULT_MAX_FAILURES = 3
"""評価失敗の打ち切り上限。週数ではなく**総試行回数**（F-001 AC-015 / AC-019）。

**暫定値。実測後に見直す**（TASK-053）。実行内リトライ1回（SPEC-003 OQ-002）と
組み合わさるため実質2週分の追跡にあたる。一時的な API 障害は週をまたげば
解消することが多く、恒久的に壊れたエントリを3週以上追いかけてもコストが増えるだけ。
"""


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

    評価に成功していれば処理済み（F-001 AC-018a）。失敗している場合は、
    失敗回数が上限に達したときのみ処理済みとして扱い、以降再評価しない
    （F-001 AC-018 / AC-019）。

    `max_failures` は週数ではなく**総試行回数**の上限である。失敗回数は
    実行内の試行回数分だけ増加するため（F-001 AC-015）、実行内リトライの
    回数を変えると追いかける実行回数も連動して変わる。
    """
    if record.score is not None:
        return True
    return record.failure_count >= max_failures


def select_evaluation_targets(
    new_urls: Iterable[str],
    state: dict[str, StateRecord],
    max_failures: int,
    limit: int | None = None,
) -> list[str]:
    """評価対象の url を、新規を優先した順序で返す。

    未知の url に加え、評価に失敗したが失敗回数が上限未満のものも
    再評価の対象に含める（F-001 AC-018）。

    `limit` を与えた場合、**新規 url を優先して枠を埋める**（F-001 AC-025a）。
    恒久的に失敗する記事が上限枠を占有して新規の供給を止めないため
    （R-001）。溢れた分は記録されず次回に持ち越される（AC-025）。

    新規どうしは入力順（フィードからの取得順）を保つ。再評価対象どうしは
    `evaluated_at` が古い順に並べる。選ばれなかった対象は次回さらに古くなり
    先頭へ近づくため、すべての再評価対象がいずれ必ず選ばれる（SPEC-002 §6）。
    """
    fresh: list[str] = []
    retry: list[tuple[datetime, str]] = []
    seen: set[str] = set()
    for url in new_urls:
        if url in seen:
            continue
        seen.add(url)
        record = state.get(url)
        if record is None:
            fresh.append(url)
        elif not is_processed(record, max_failures):
            retry.append((record.evaluated_at, url))
    retry.sort(key=lambda pair: pair[0])
    selected = fresh + [url for _, url in retry]
    if limit is None:
        return selected
    return selected[:limit]
