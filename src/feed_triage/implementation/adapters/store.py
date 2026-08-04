"""状態ファイル（JSONL）の読み書き（SPEC-002 §3 フロー #1・#4・#10〜#16）。

ADR-005 の決定により状態は**追記専用**の JSONL として保持する。同一 url の行が
複数存在しうるため、現在の状態は `domain/state.fold_records` で再構成する。

**読み込みは寛容な側へ倒す** — 1行の破損で全体を失うと、次回実行で全件が新規と
扱われ重複投入（R-002 違反）に直結するため、当該行をスキップして継続する。
**書き込みの失敗は実行を止める** — 記録できないまま投入を続けると重複が確定するため。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from feed_triage.contract.model import (
    JUDGMENT_MAX,
    JUDGMENT_MIN,
    MECHANISM_MAX,
    MECHANISM_MIN,
    SCOPE_VALUES,
    SCORE_MAX,
    SCORE_MIN,
    RunRecord,
    StateRecord,
)

STATE_FIELDS = (
    "url",
    "title",
    "source_name",
    "evaluated_at",
    "score",
    "weight",
    "final_score",
    "ingested",
    "reason",
    "suggested_tags",
    "failure_count",
    # 多軸判定（ADR-006）
    "judgment",
    "mechanism",
    "scope",
    "unscorable",
    "judgment_markers",
    "priority",
    "evaluated",
)
"""`state.jsonl` の1行が持つ項目（SPEC-002 §4）。

**秘匿情報のフィールドを持たない**（REQ-NF-006）。記録に含めるのは公開記事の
メタデータと判定結果のみである。

**この定数が書き出しキーの正典である。** `_to_json` はここから導出し、
テストもここを参照する。以前は3箇所（`_to_json` / 本定数 / テスト内の
リテラル）に重複しており、本定数だけ更新し忘れても誰も気づかなかった。
"""


class StateWriteError(Exception):
    """状態の書き込み失敗（終了コード `STATE_PERSIST_FAILED` → SPEC-005 §5）。"""


def load_state(path: Path) -> tuple[list[StateRecord], int]:
    """`state.jsonl` を読み、レコード列と**無視した行数**を返す。

    ファイルが無ければ空を返す（初回実行 → フロー #10）。空の状態で続行するのは
    ここだけであり、**読み込みに失敗した場合は呼び出し元が実行を止める**
    （F-002 AC-018。空と誤認すると全件が新規になり重複投入する）。
    """
    records: list[StateRecord] = []
    ignored = 0
    for raw in _iter_json_lines(path):
        if raw is None:
            ignored += 1
            continue
        record = _build_state(raw)
        if record is None:
            ignored += 1
            continue
        records.append(record)
    return records, ignored


def load_runs(path: Path) -> list[RunRecord]:
    """`runs.jsonl` を読み実行記録の列を返す（F-004 AC-003a / AC-008 の供給元）。"""
    runs: list[RunRecord] = []
    for raw in _iter_json_lines(path):
        if raw is None:
            continue
        run_at = _as_datetime(raw.get("run_at"))
        if run_at is None:
            # 順序判定に使えないためスキップする（SPEC-002 §4）
            continue
        runs.append(
            RunRecord(
                run_at=run_at,
                sources=_as_int_map(raw.get("sources")),
                source_errors=_as_str_map(raw.get("source_errors")),
                new_entries=_as_count(raw.get("new_entries")),
                evaluated=_as_count(raw.get("evaluated")),
                ingested=_as_count(raw.get("ingested")),
                deferred=_as_count(raw.get("deferred")),
            )
        )
    return runs


def append_records(path: Path, records: list[StateRecord]) -> int:
    """レコードを `state.jsonl` の末尾へ追記し、追記した行数を返す。

    **同一実行内で同じ URL を二重に追記しない**（フロー #15）。JSONL は DB のような
    一意制約を持たないため、一意性はここで担保する（ADR-005 のトレードオフ / R-002）。
    """
    if not records:
        # 0件のときはファイルを作らない。空ファイルと「未実行」を区別する必要がない一方、
        # 不要なコミットを生むと状態ブランチの履歴が読みにくくなる
        return 0

    seen: set[str] = set()
    lines: list[str] = []
    for record in records:
        if record.url in seen:
            continue
        seen.add(record.url)
        lines.append(json.dumps(_to_json(record), ensure_ascii=False))

    try:
        # 追記モードでのみ開く。切り詰め（truncate）・既存行の書き換えをしない（SPEC-002 §7）
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError as exc:
        raise StateWriteError(f"状態を追記できません: {path} ({exc.strerror})") from None
    return len(lines)


def append_run(path: Path, run: RunRecord) -> None:
    """実行記録を `runs.jsonl` の末尾へ1行追記する。

    エントリ単位の状態からは「新着0件で実行された週」と「実行されなかった週」を
    区別できないため別に持つ（TASK-048）。**dry-run では呼ばない**（フロー #8）。
    """
    payload = {
        "run_at": run.run_at.isoformat(),
        "sources": run.sources,
        "source_errors": run.source_errors,
        "new_entries": run.new_entries,
        "evaluated": run.evaluated,
        "ingested": run.ingested,
        "deferred": run.deferred,
    }
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise StateWriteError(f"実行記録を追記できません: {path} ({exc.strerror})") from None


def _iter_json_lines(path: Path) -> list[dict[str, Any] | None]:
    """1行1オブジェクトとして読む。壊れた行は None を返し、呼び出し元が数える。

    空行は無視するが**破損とは数えない**（末尾改行で必ず生じるため）。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        # 読めないのは「空」ではない。空と誤認すると全件が新規になり重複投入する
        raise StateWriteError(f"状態を読み込めません: {path} ({exc.strerror})") from None

    parsed: list[dict[str, Any] | None] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            parsed.append(None)
            continue
        parsed.append(obj if isinstance(obj, dict) else None)
    return parsed


def _build_state(raw: dict[str, Any]) -> StateRecord | None:
    """1行を `StateRecord` へ。必須項目を欠くなら None（当該行をスキップ）。"""
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        # url は一意性のキー（REQ-F-002）。欠くと重複排除が成立しない
        return None
    evaluated_at = _as_datetime(raw.get("evaluated_at"))
    if evaluated_at is None:
        # evaluated_at は畳み込みの順序判定に使う（ADR-005 OQ-001）
        return None

    score = raw.get("score")
    if not _is_valid_score(score):
        # 範囲外・非整数は null に丸める。**行はスキップしない** — 評価に失敗した
        # 事実は残す必要があるため（F-001 AC-015 / AC-029）
        score = None

    weight = _as_weight(raw.get("weight"))
    return StateRecord(
        url=url.strip(),
        title=_as_text(raw.get("title")),
        source_name=_as_text(raw.get("source_name")),
        evaluated_at=evaluated_at,
        score=score,
        weight=weight,
        # final_score は保存値を信用せず再計算する（SPEC-002 §5）
        final_score=None if score is None else score + weight,
        ingested=raw.get("ingested") is True,
        reason=_as_text(raw.get("reason")),
        suggested_tags=_as_tags(raw.get("suggested_tags")),
        failure_count=_as_count(raw.get("failure_count")),
        judgment=_as_axis(raw.get("judgment"), JUDGMENT_MIN, JUDGMENT_MAX),
        mechanism=_as_axis(raw.get("mechanism"), MECHANISM_MIN, MECHANISM_MAX),
        scope=_as_scope(raw.get("scope")),
        unscorable=raw.get("unscorable") is True,
        judgment_markers=_as_tags(raw.get("judgment_markers")),
        priority=_as_priority(raw.get("priority")),
        # **旧行の後方互換はこの1行が担う。** 多軸化以前に書かれた行は
        # `evaluated` を持たないが、score があれば評価は成立していた
        # （ADR-006）。これにより既存の記録が「未評価」に見えて再評価
        # されるのを防ぐ
        evaluated=_as_evaluated(raw, score),
    )


def _as_axis(value: object, low: int, high: int) -> int | None:
    """判定軸の値。値域外・非整数は `None` に丸める（行はスキップしない）。

    `score` と同じ方針 — 壊れた値を捨てても、評価を試みた事実は残す。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if low <= value <= high else None


def _as_scope(value: object) -> str | None:
    """射程。未知の文字列は `None` に丸める。"""
    return value if isinstance(value, str) and value in SCOPE_VALUES else None


def _as_priority(value: object) -> int | None:
    """優先度。**値域は制約しない** — 合成規則が変われば取りうる幅も変わる。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _as_evaluated(raw: dict[str, Any], score: int | None) -> bool:
    """評価が成立したか。**旧行は `score` の有無から補完する**（ADR-006）。"""
    value = raw.get("evaluated")
    if isinstance(value, bool):
        return value
    return score is not None


def _to_json(record: StateRecord) -> dict[str, Any]:
    """`STATE_FIELDS` の順にキーを並べた辞書へ変換する。

    **キーの集合は `STATE_FIELDS` から導出する** — 手で二重管理すると、
    列を足したときに片方だけ更新して気づかない事故が起きる。
    """
    encoded: dict[str, Any] = {}
    for field_name in STATE_FIELDS:
        value = getattr(record, field_name)
        if isinstance(value, datetime):
            encoded[field_name] = value.isoformat()
        elif isinstance(value, tuple):
            encoded[field_name] = list(value)
        else:
            encoded[field_name] = value
    return encoded


def _is_valid_score(value: object) -> bool:
    """値域内の整数か。`domain.scoring.is_valid_score` と同一の判定。

    adapters → domain の import は層構造が禁じるため、判定そのものはここに置く。
    値域の定義は contract 層で共有しており、二重管理にはならない。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return SCORE_MIN <= value <= SCORE_MAX


def _as_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_weight(value: object) -> int:
    """非整数は 0 に丸める。値域は制約しない（SPEC-002 §5）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _as_count(value: object) -> int:
    """0 以上の整数へ。負値は 0 に丸める（書き込み側のバグの兆候）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _as_tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _as_int_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {k: _as_count(v) for k, v in value.items() if isinstance(k, str)}


def _as_str_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}
