"""状態ファイル（JSONL）の読み書きのテスト（SPEC-002 §3 フロー #1・#4・#10〜#16）。

読み込みは**寛容な側**に倒す — 1行の破損で全体を失うと R-002（重複ゼロ）に
直結するため、当該行をスキップして継続する。一方、書き込みの失敗は実行を止める。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feed_triage.contract.model import RunRecord, StateRecord
from feed_triage.implementation.adapters.store import (
    STATE_FIELDS,
    StateWriteError,
    append_records,
    append_run,
    load_runs,
    load_state,
)

AT = datetime(2026, 7, 27, 21, 17, 30, 123456, tzinfo=timezone.utc)


def record(url: str = "https://example.com/a", **kw: object) -> StateRecord:
    base: dict[str, object] = {
        "url": url,
        "title": "A",
        "source_name": "example",
        "evaluated_at": AT,
        "score": 7,
        "weight": 1,
        "final_score": 8,
        "ingested": True,
        "reason": "設計解説",
        "suggested_tags": ("arch",),
        "failure_count": 0,
    }
    base.update(kw)
    return StateRecord(**base)  # type: ignore[arg-type]


def write_lines(path: Path, *objs: object) -> Path:
    body = "\n".join(
        json.dumps(o, ensure_ascii=False) if not isinstance(o, str) else o for o in objs
    )
    path.write_text(body + "\n", encoding="utf-8")
    return path


# --- 往復（追記 → 読み込み） -------------------------------------------------


def test_追記した内容がそのまま読み戻せる(tmp_path: Path) -> None:
    path = tmp_path / "state.jsonl"
    append_records(path, [record()])
    loaded, ignored = load_state(path)

    assert ignored == 0
    assert len(loaded) == 1
    assert loaded[0] == record()


def test_多軸の判定を持つ行が往復する(tmp_path: Path) -> None:
    """ADR-006: 多軸化に向けた列を任意項目として追加する（Phase A）。

    この時点では評価アダプタは 0-10 のままで、状態が新形式を読み書きできる
    ことだけを保証する。
    """
    path = tmp_path / "state.jsonl"
    original = record(
        judgment=4,
        mechanism=2,
        scope="broad",
        unscorable=False,
        judgment_markers=("立場の表明", "他案の棄却"),
        priority=10,
        evaluated=True,
    )
    append_records(path, [original])
    loaded, ignored = load_state(path)

    assert ignored == 0
    assert loaded[0] == original


def test_多軸化以前の行が読め_評価済みとして復元される(tmp_path: Path) -> None:
    """ADR-006: 既存の記録を再評価させない。

    多軸化以前の行は `evaluated` を持たない。`score` があれば評価は成立して
    いたので、そこから補完する。**これが効かないと既存の全行が「未評価」に
    見えて再評価され、投入済みの記事が重複投入されうる**（R-002 違反）。
    """
    path = tmp_path / "state.jsonl"
    legacy = {
        "url": "https://example.com/legacy",
        "title": "旧基準で評価済み",
        "source_name": "example",
        "evaluated_at": AT.isoformat(),
        "score": 7,
        "weight": 1,
        "final_score": 8,
        "ingested": True,
        "reason": "設計解説",
        "suggested_tags": ["arch"],
        "failure_count": 0,
    }
    path.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")

    loaded, ignored = load_state(path)

    assert ignored == 0, "旧形式の行はスキップされない"
    assert loaded[0].evaluated is True, "score があるので評価済みとして復元する"
    assert loaded[0].judgment is None, "多軸の列は既定値のまま"
    assert loaded[0].unscorable is False


def test_追記は既存行を保持する(tmp_path: Path) -> None:
    """SPEC-002 §7: 追記モードでのみ開き、切り詰め・既存行の書き換えをしない。"""
    path = tmp_path / "state.jsonl"
    append_records(path, [record("https://example.com/1")])
    append_records(path, [record("https://example.com/2")])
    loaded, _ = load_state(path)
    assert [r.url for r in loaded] == ["https://example.com/1", "https://example.com/2"]


def test_evaluated_at_はマイクロ秒精度で往復する(tmp_path: Path) -> None:
    """SPEC-002 §4: 同一実行内で同値になると畳み込みが行順依存になる。"""
    path = tmp_path / "state.jsonl"
    append_records(path, [record()])
    loaded, _ = load_state(path)
    assert loaded[0].evaluated_at == AT
    assert loaded[0].evaluated_at.microsecond == 123456


def test_日本語とURLがエスケープされずに保存される(tmp_path: Path) -> None:
    """人間が git diff で読めることが JSONL を選んだ理由の一つ（ADR-005）。"""
    path = tmp_path / "state.jsonl"
    append_records(path, [record(title="設計解説の記事")])
    assert "設計解説の記事" in path.read_text(encoding="utf-8")


def test_1レコードが1行に収まる(tmp_path: Path) -> None:
    """改行が混じると行単位の追記・マージが壊れる（ADR-005）。"""
    path = tmp_path / "state.jsonl"
    append_records(path, [record(title="改行\nを含む", reason="複数\n行")])
    assert len(path.read_text(encoding="utf-8").strip().split("\n")) == 1


# --- 初回実行・空 ------------------------------------------------------------


def test_ファイルが存在しなければ空の状態を返す(tmp_path: Path) -> None:
    """フロー #10: 初回実行。CONFIG_ERROR にしない。"""
    loaded, ignored = load_state(tmp_path / "missing.jsonl")
    assert loaded == []
    assert ignored == 0


def test_空ファイルは空の状態を返す(tmp_path: Path) -> None:
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl"))
    assert loaded == []


def test_空行は無視するが破損とは数えない(tmp_path: Path) -> None:
    path = write_lines(tmp_path / "state.jsonl", "", "   ", "")
    loaded, ignored = load_state(path)
    assert loaded == []
    assert ignored == 0


# --- 破損行のスキップ（フロー #11〜#14） -------------------------------------


def test_JSON_として壊れた行をスキップし他は残す(tmp_path: Path) -> None:
    """フロー #11: 1行の破損で全体を失わない（R-002 に直結）。"""
    path = write_lines(
        tmp_path / "state.jsonl",
        "{壊れた",
        {"url": "https://example.com/ok", "evaluated_at": AT.isoformat()},
    )
    loaded, ignored = load_state(path)
    assert [r.url for r in loaded] == ["https://example.com/ok"]
    assert ignored == 1


@pytest.mark.parametrize(
    "obj",
    [
        {"evaluated_at": "2026-07-27T21:17:30.123456+00:00"},
        {"url": "", "evaluated_at": "2026-07-27T21:17:30.123456+00:00"},
        {"url": None, "evaluated_at": "2026-07-27T21:17:30.123456+00:00"},
        {"url": "https://example.com/a"},
        {"url": "https://example.com/a", "evaluated_at": "いつか"},
        {"url": "https://example.com/a", "evaluated_at": None},
    ],
)
def test_必須項目を欠く行や解釈不能な日時の行をスキップする(
    tmp_path: Path, obj: dict[str, object]
) -> None:
    """フロー #12〜#14: url は一意性のキー、evaluated_at は順序判定に使う。"""
    loaded, ignored = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert loaded == []
    assert ignored == 1


def test_JSON_オブジェクトでない行をスキップする(tmp_path: Path) -> None:
    loaded, ignored = load_state(write_lines(tmp_path / "state.jsonl", [1, 2], "42"))
    assert loaded == []
    assert ignored == 2


# --- 値の丸め（SPEC-002 §5。行はスキップしない） -----------------------------


@pytest.mark.parametrize("score", [-1, 11, 100, "7", True])
def test_範囲外や非整数のスコアは_null_に丸める(tmp_path: Path, score: object) -> None:
    """F-001 AC-029: 範囲外のスコアを投入判定に用いてはならない。"""
    obj = {"url": "https://example.com/a", "evaluated_at": AT.isoformat(), "score": score}
    loaded, ignored = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert ignored == 0
    assert loaded[0].score is None


@pytest.mark.parametrize("judgment", [-1, 6, 100, "3", True])
def test_範囲外や非整数の_judgment_は_null_に丸める(
    tmp_path: Path, judgment: object
) -> None:
    """ADR-006: `score` と同じ方針。壊れた値は捨てるが行は残す。"""
    obj = {
        "url": "https://example.com/a",
        "evaluated_at": AT.isoformat(),
        "judgment": judgment,
    }
    loaded, ignored = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert ignored == 0, "行はスキップしない"
    assert loaded[0].judgment is None


@pytest.mark.parametrize("mechanism", [-1, 3, "1", True])
def test_範囲外や非整数の_mechanism_は_null_に丸める(
    tmp_path: Path, mechanism: object
) -> None:
    obj = {
        "url": "https://example.com/a",
        "evaluated_at": AT.isoformat(),
        "mechanism": mechanism,
    }
    loaded, ignored = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert ignored == 0
    assert loaded[0].mechanism is None


@pytest.mark.parametrize("scope", ["unknown", "", 3, None])
def test_未知の_scope_は_null_に丸める(tmp_path: Path, scope: object) -> None:
    """射程は列挙値。未知の文字列を通すと配架の判定が壊れる。"""
    obj = {"url": "https://example.com/a", "evaluated_at": AT.isoformat(), "scope": scope}
    loaded, ignored = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert ignored == 0
    assert loaded[0].scope is None


def test_既知の_scope_はそのまま読める(tmp_path: Path) -> None:
    obj = {
        "url": "https://example.com/a",
        "evaluated_at": AT.isoformat(),
        "scope": "periphery",
    }
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert loaded[0].scope == "periphery"


def test_負の失敗回数は0に丸める(tmp_path: Path) -> None:
    obj = {
        "url": "https://example.com/a",
        "evaluated_at": AT.isoformat(),
        "failure_count": -3,
    }
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert loaded[0].failure_count == 0


def test_非整数の重みは0に丸める(tmp_path: Path) -> None:
    obj = {"url": "https://example.com/a", "evaluated_at": AT.isoformat(), "weight": "x"}
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert loaded[0].weight == 0


def test_final_score_が不整合なら再計算する(tmp_path: Path) -> None:
    """SPEC-002 §5: score + weight と一致しない行は再計算した値を用いる。"""
    obj = {
        "url": "https://example.com/a",
        "evaluated_at": AT.isoformat(),
        "score": 5,
        "weight": 1,
        "final_score": 99,
    }
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert loaded[0].final_score == 6


def test_スコアが_null_なら_final_score_も_null(tmp_path: Path) -> None:
    obj = {
        "url": "https://example.com/a",
        "evaluated_at": AT.isoformat(),
        "score": None,
        "weight": 1,
        "final_score": 3,
    }
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert loaded[0].final_score is None


def test_欠落した任意項目は既定値で補完する(tmp_path: Path) -> None:
    obj = {"url": "https://example.com/a", "evaluated_at": AT.isoformat()}
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl", obj))
    r = loaded[0]
    assert (r.title, r.source_name, r.reason) == ("", "", "")
    assert (r.suggested_tags, r.ingested, r.failure_count) == ((), False, 0)


def test_suggested_tags_の非文字列要素を除去する(tmp_path: Path) -> None:
    obj = {
        "url": "https://example.com/a",
        "evaluated_at": AT.isoformat(),
        "suggested_tags": ["ok", 1, None, "  ", "another"],
    }
    loaded, _ = load_state(write_lines(tmp_path / "state.jsonl", obj))
    assert loaded[0].suggested_tags == ("ok", "another")


# --- 同一実行内の一意化（フロー #15） ----------------------------------------


def test_同一実行内で同じ_URL_を二重に追記しない(tmp_path: Path) -> None:
    """フロー #15: 一意制約はアプリ側で担保する（ADR-005 / R-002）。"""
    path = tmp_path / "state.jsonl"
    written = append_records(
        path, [record("https://example.com/dup"), record("https://example.com/dup")]
    )
    loaded, _ = load_state(path)
    assert written == 1
    assert len(loaded) == 1


def test_異なる実行では同じ_URL_を追記できる(tmp_path: Path) -> None:
    """追記専用であり、再評価の結果は新しい行として積まれる（ADR-005）。"""
    path = tmp_path / "state.jsonl"
    append_records(path, [record("https://example.com/a")])
    append_records(path, [record("https://example.com/a", score=9)])
    loaded, _ = load_state(path)
    assert len(loaded) == 2


def test_追記対象が0件ならファイルを作らない(tmp_path: Path) -> None:
    """フロー #6: 評価対象0件でも state.jsonl への追記は行わない。"""
    path = tmp_path / "state.jsonl"
    assert append_records(path, []) == 0
    assert not path.exists()


# --- 書き込み失敗（フロー #16） ----------------------------------------------


def test_書き込めない場所への追記は失敗として送出する(tmp_path: Path) -> None:
    """フロー #16: 記録できないまま投入を続けると重複投入が確定する。"""
    path = tmp_path / "no-such-dir" / "state.jsonl"
    with pytest.raises(StateWriteError):
        append_records(path, [record()])


# --- runs.jsonl（実行単位の記録） --------------------------------------------


def test_実行記録を追記して読み戻せる(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    run = RunRecord(
        run_at=AT,
        sources={"a": 5, "b": 0},
        source_errors={"c": "HTTP 404"},
        new_entries=3,
        evaluated=3,
        ingested=1,
        deferred=0,
    )
    append_run(path, run)
    assert load_runs(path) == [run]


def test_取得0件の情報源も記録に残る(tmp_path: Path) -> None:
    """F-004 AC-003a: 前回比の算出に必要。省略すると 0 件が判別できない。"""
    path = tmp_path / "runs.jsonl"
    append_run(path, RunRecord(run_at=AT, sources={"zero": 0}))
    assert load_runs(path)[0].sources == {"zero": 0}


def test_実行記録がなければ空リストを返す(tmp_path: Path) -> None:
    assert load_runs(tmp_path / "missing.jsonl") == []


def test_run_at_を欠く行はスキップする(tmp_path: Path) -> None:
    """順序判定に使えないため（SPEC-002 §4）。"""
    path = write_lines(tmp_path / "runs.jsonl", {"sources": {"a": 1}})
    assert load_runs(path) == []


# --- セキュリティ ------------------------------------------------------------


def test_記録に秘匿情報のフィールドを持たない(tmp_path: Path) -> None:
    """REQ-NF-006: 記録には公開記事のメタデータと判定結果のみを含める。

    **許可集合は `STATE_FIELDS` が正典**。以前はここにキーをリテラルで
    再記述しており、列を足したときに `STATE_FIELDS` だけ更新し忘れても
    テストが通ってしまった。

    反証可能性: `StateRecord` に `token` のような項目を足して `STATE_FIELDS`
    に載せると、下の許可集合の照合で落ちる。
    """
    path = tmp_path / "state.jsonl"
    append_records(path, [record()])
    saved = json.loads(path.read_text(encoding="utf-8").strip())

    assert set(saved) == set(STATE_FIELDS)
    # 秘匿情報を思わせる語が混ざっていないこと（許可集合そのものの検証）
    forbidden = ("token", "key", "secret", "credential", "password")
    assert not [f for f in STATE_FIELDS if any(w in f.lower() for w in forbidden)]
