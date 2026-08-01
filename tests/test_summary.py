"""SPEC-006 §10 のテスト観点に対応する。

観点番号（T-xxx）は SPEC-006 §10 の表と 1:1 で対応させる。
"""

from __future__ import annotations

import pytest

from feed_triage.contract.model import EntryVerdict, RunSummary, SourceOutcome
from feed_triage.implementation.domain.summary import format_summary

RUN_AT = "2026-07-28T09:00:00Z"


def _summary(**kwargs: object) -> RunSummary:
    """既定値の RunSummary に差分だけを与える。"""
    return RunSummary(**kwargs)  # type: ignore[arg-type]


# --- T-001: 概況 -------------------------------------------------------------


def test_概況に取得数と新規数と評価数と投入数が現れる() -> None:
    summary = _summary(
        sources=[SourceOutcome("jane-street", fetched=42)],
        new_entries=8,
        evaluated=8,
        ingested=3,
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "取得 42 件 / 新規 8 件 / 評価 8 件 / 投入 3 件" in out


def test_概況の取得件数は情報源別の合計と一致する() -> None:
    """独立フィールドで受け取ると、内訳と合計がずれた出力を検出できない（§1）。"""
    summary = _summary(
        sources=[
            SourceOutcome("a", fetched=5),
            SourceOutcome("b", fetched=3),
            SourceOutcome("c", error="HTTP 404"),
        ]
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "取得 8 件" in out


def test_見出しに実行時刻が現れる() -> None:
    out = format_summary(_summary(), run_at=RUN_AT)
    assert f"=== feed-triage 実行サマリ ({RUN_AT}) ===" in out


# --- T-002: スコア分布 -------------------------------------------------------


def test_スコア分布がスコア昇順で出力される() -> None:
    summary = _summary(score_distribution={7: 2, 3: 2, 9: 1, 5: 3}, evaluated=8)
    out = format_summary(summary, run_at=RUN_AT)
    assert "スコア分布: 3:2 5:3 7:2 9:1" in out


# --- T-003 / T-014: 情報源別 -------------------------------------------------


def test_定義された全情報源が1行ずつ出力される() -> None:
    summary = _summary(
        sources=[
            SourceOutcome("jane-street", fetched=5),
            SourceOutcome("netflix-techblog", fetched=3),
        ]
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "jane-street" in out
    assert "netflix-techblog" in out


def test_取得0件の情報源も行が省略されない() -> None:
    """T-014: F-004 AC-022。0 件を落とすと供給停止に気づけない。"""
    summary = _summary(sources=[SourceOutcome("snowflake-blog", fetched=0)])
    out = format_summary(summary, run_at=RUN_AT)
    assert "snowflake-blog" in out
    assert "0 件" in out


def test_情報源名は切り詰めない() -> None:
    long_name = "a" * 80
    summary = _summary(sources=[SourceOutcome(long_name, fetched=1)])
    out = format_summary(summary, run_at=RUN_AT)
    assert long_name in out


def test_情報源名が空文字なら名称なしと表示する() -> None:
    summary = _summary(sources=[SourceOutcome("", fetched=1)])
    out = format_summary(summary, run_at=RUN_AT)
    assert "(名称なし)" in out


# --- T-004: 前回比 -----------------------------------------------------------


def test_前回の取得件数が各情報源の行に併記される() -> None:
    summary = _summary(
        sources=[SourceOutcome("jane-street", fetched=5)],
        previous_sources={"jane-street": 4},
        weeks_since_previous_run=1.0,
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "(前回 4)" in out


def test_前回に存在しない情報源の前回比はハイフンになる() -> None:
    """OQ-006 の暫定挙動を固定する。決着したらこのテストを更新する。"""
    summary = _summary(
        sources=[SourceOutcome("new-source", fetched=5)],
        previous_sources={"jane-street": 4},
        weeks_since_previous_run=1.0,
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "(前回 -)" in out


# --- T-005: verbose ----------------------------------------------------------


def test_verbose_はサマリの内容を変えない() -> None:
    """T-005: F-004 AC-007。詳細化されるのは標準エラー側のみ。"""
    summary = _summary(
        sources=[SourceOutcome("jane-street", fetched=5)],
        new_entries=2,
        evaluated=2,
        ingested=1,
    )
    assert format_summary(summary, run_at=RUN_AT, verbose=True) == format_summary(
        summary, run_at=RUN_AT, verbose=False
    )


# --- T-006 / T-019: 経過期間 -------------------------------------------------


def test_前回実行からの経過週数が出力される() -> None:
    summary = _summary(weeks_since_previous_run=1.0, previous_sources={"a": 1})
    out = format_summary(summary, run_at=RUN_AT)
    assert "前回実行から 1.0 週" in out


def test_経過が2週以上なら定期実行の不発火を併記する() -> None:
    summary = _summary(weeks_since_previous_run=2.4, previous_sources={"a": 1})
    out = format_summary(summary, run_at=RUN_AT)
    assert "2.4 週" in out
    assert "定期実行が起動しなかった可能性があります" in out


def test_経過が2週未満なら不発火の警告を出さない() -> None:
    """境界値: 1.9 週は正常。閾値を緩めると毎週警告が出て無視されるようになる。"""
    summary = _summary(weeks_since_previous_run=1.9, previous_sources={"a": 1})
    out = format_summary(summary, run_at=RUN_AT)
    assert "定期実行が起動しなかった可能性があります" not in out


def test_初回実行では前回比と経過期間がハイフンになる() -> None:
    """T-019: null を 0 に変換すると `前回 0` / `0.0 週` となり初回と区別できない。"""
    summary = _summary(
        sources=[SourceOutcome("jane-street", fetched=5)],
        weeks_since_previous_run=None,
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "(前回 -)" in out
    assert "前回実行から: - (初回)" in out


# --- T-007 / T-010: 取得失敗 -------------------------------------------------


def test_取得に失敗した情報源は件数ではなく失敗として出る() -> None:
    summary = _summary(
        sources=[
            SourceOutcome("jane-street", fetched=5),
            SourceOutcome("uber-engineering", error="HTTP 404"),
        ]
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "取得失敗 (HTTP 404)" in out


def test_全情報源が失敗したとき専用の警告が出る() -> None:
    summary = _summary(
        sources=[
            SourceOutcome("a", error="タイムアウト"),
            SourceOutcome("b", error="HTTP 503"),
        ]
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "**全 2 情報源の取得に失敗しました**" in out


def test_一部失敗では全件失敗の警告を出さない() -> None:
    """T-010 の反証: 判定を「1件以上失敗」に緩めるとここがレッドになる。"""
    summary = _summary(
        sources=[
            SourceOutcome("a", fetched=3),
            SourceOutcome("b", error="HTTP 503"),
        ]
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "情報源の取得に失敗しました**" not in out


# --- T-008: 評価失敗と打ち切り -----------------------------------------------


def test_評価失敗と打ち切りが別行で出る() -> None:
    """T-008: F-004 AC-011a。合算すると一時障害と恒久的取りこぼしを区別できない。"""
    summary = _summary(evaluated=10, evaluation_failures=2, abandoned=1)
    out = format_summary(summary, run_at=RUN_AT)
    assert "評価失敗 2 件" in out
    assert "再評価打ち切り 1 件" in out


def test_打ち切りのみが非0でも独立して出る() -> None:
    summary = _summary(evaluated=10, evaluation_failures=0, abandoned=3)
    out = format_summary(summary, run_at=RUN_AT)
    assert "再評価打ち切り 3 件" in out
    assert "評価失敗" not in out


# --- T-009: 投入失敗 ---------------------------------------------------------


def test_投入失敗件数と失敗理由の内訳が出る() -> None:
    summary = _summary(
        ingested=2,
        ingest_failures=3,
        ingest_failure_reasons={"rate_limited": 2, "server_error": 1},
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "投入失敗 3 件" in out
    assert "rate_limited: 2" in out
    assert "server_error: 1" in out


def test_未試行件数は投入失敗と別行で出る() -> None:
    """SPEC-004 §4: 未試行は成功にも失敗にも数えない。"""
    summary = _summary(ingested=1, ingest_failures=2, ingest_unattempted=5)
    out = format_summary(summary, run_at=RUN_AT)
    assert "投入未試行 5 件" in out


def test_投入を試行して全件失敗したとき専用の警告が出る() -> None:
    """T-030: F-004 AC-016。概況の `投入 0 件` だけでは投入対象0件の週と区別できない。"""
    summary = _summary(ingested=0, ingest_attempted=3, ingest_failures=3)
    out = format_summary(summary, run_at=RUN_AT)
    assert "**投入対象 3 件がすべて失敗しました**" in out


def test_投入対象が0件なら全件失敗の警告を出さない() -> None:
    """T-030 の反証: 「投入0件なら警告」に緩めると新着ゼロの週に誤警告が出る。"""
    out = format_summary(_summary(ingested=0, ingest_attempted=0), run_at=RUN_AT)
    assert "すべて失敗しました" not in out


def test_打ち切りによる未試行は全件失敗の分母に含めない() -> None:
    """SPEC-004 フロー #15。1件成功 + 打ち切り5件は「全件失敗」ではない。"""
    summary = _summary(ingested=1, ingest_attempted=1, ingest_unattempted=5)
    out = format_summary(summary, run_at=RUN_AT)
    assert "すべて失敗しました" not in out


def test_dry_run_では全件失敗の警告を出さない() -> None:
    """dry-run では POST を行わないため、この警告は発生しえない。"""
    summary = _summary(dry_run=True, ingested=3, ingest_attempted=0)
    out = format_summary(summary, run_at=RUN_AT)
    assert "すべて失敗しました" not in out


# --- T-011: 永続化失敗 -------------------------------------------------------


def test_永続化失敗時に重複投入の可能性が警告される() -> None:
    summary = _summary(state_persist_error="push が3回とも失敗しました")
    out = format_summary(summary, run_at=RUN_AT)
    assert "記録の永続化に失敗しました" in out
    assert "push が3回とも失敗しました" in out
    assert "重複投入" in out


# --- T-012: 未完了 -----------------------------------------------------------


def test_未完了の実行には標識が付く() -> None:
    summary = _summary(new_entries=3, evaluated=1, completed=False)
    out = format_summary(summary, run_at=RUN_AT)
    assert "（未完了）" in out


def test_完了した実行には未完了の標識が付かない() -> None:
    out = format_summary(_summary(completed=True), run_at=RUN_AT)
    assert "（未完了）" not in out


# --- T-013: 0 件の明示 -------------------------------------------------------


def test_新規0件と投入0件が明示的に出力される() -> None:
    """T-013: 概況に「0なら省略」を適用すると実行されなかった週と区別できない。"""
    out = format_summary(_summary(), run_at=RUN_AT)
    assert "新規 0 件" in out
    assert "投入 0 件" in out


@pytest.mark.parametrize(
    "field_name,label",
    [
        ("evaluation_failures", "評価失敗"),
        ("abandoned", "再評価打ち切り"),
        ("ingest_failures", "投入失敗"),
        ("ingest_unattempted", "投入未試行"),
        ("deferred", "持ち越し"),
    ],
)
def test_失敗系は0件なら行を省略する(field_name: str, label: str) -> None:
    """平常時のサマリを短く保ち、異常時に増える行を目立たせる（§9）。"""
    out = format_summary(_summary(**{field_name: 0}), run_at=RUN_AT)
    assert label not in out


def test_持ち越しが非0なら出力される() -> None:
    summary = _summary(deferred=12)
    out = format_summary(summary, run_at=RUN_AT)
    assert "持ち越し 12 件" in out


# --- T-015 / T-016 / T-017 / T-018: 空・縮退 ---------------------------------


def test_情報源の定義が0件のとき専用の文言が出る() -> None:
    out = format_summary(_summary(sources=[]), run_at=RUN_AT)
    assert "情報源が定義されていません" in out


def test_評価成功0件のときスコア分布が空と判別できる() -> None:
    out = format_summary(_summary(score_distribution={}), run_at=RUN_AT)
    assert "スコア分布: (評価に成功した記事がありません)" in out


def test_全件同一スコアのとき縮退の警告が出る() -> None:
    summary = _summary(score_distribution={5: 8}, evaluated=8)
    out = format_summary(summary, run_at=RUN_AT)
    assert "スコア分布が全件同一値 (5) です" in out


def test_評価成功が1件なら縮退の警告を出さない() -> None:
    """T-018: 1件は必然的に同一値。警告すると新着が少ない週に毎回出て無視される。"""
    summary = _summary(score_distribution={5: 1}, evaluated=1)
    out = format_summary(summary, run_at=RUN_AT)
    assert "全件同一値" not in out


def test_スコアが2種類以上なら縮退の警告を出さない() -> None:
    summary = _summary(score_distribution={5: 4, 7: 4}, evaluated=8)
    out = format_summary(summary, run_at=RUN_AT)
    assert "全件同一値" not in out


# --- T-020 / T-021 / T-022 / T-023 / T-024: dry-run --------------------------


def test_dry_run_の見出しに標識が付き投入欄が投入対象になる() -> None:
    summary = _summary(dry_run=True, ingested=3, new_entries=8, evaluated=8)
    out = format_summary(summary, run_at=RUN_AT)
    assert "[DRY-RUN]" in out
    assert "投入対象 3 件 (投入は行っていません)" in out


def test_通常実行では投入対象という文言を使わない() -> None:
    summary = _summary(dry_run=False, ingested=3)
    out = format_summary(summary, run_at=RUN_AT)
    assert "投入 3 件" in out
    assert "投入対象" not in out


def test_dry_run_で記事ごとのURLとスコアと投入可否が出る() -> None:
    summary = _summary(
        dry_run=True,
        entries=[
            EntryVerdict("https://example.com/a", "A", final_score=9, will_ingest=True),
            EntryVerdict("https://example.com/b", "B", final_score=4, will_ingest=False),
        ],
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "[投入] 9 https://example.com/a" in out
    assert "[見送] 4 https://example.com/b" in out


def test_dry_run_で評価失敗の明細はスコアがハイフンになる() -> None:
    summary = _summary(
        dry_run=True,
        entries=[EntryVerdict("https://example.com/broken", final_score=None)],
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "[失敗] - https://example.com/broken" in out


@pytest.mark.parametrize("final_score", [-1, 11])
def test_dry_run_の明細は値域外スコアを丸めない(final_score: int) -> None:
    """T-020: SPEC-004 §4。丸めると F-003 の事後検証で端点のデータが失われる。"""
    summary = _summary(
        dry_run=True,
        entries=[EntryVerdict("https://example.com/x", final_score=final_score)],
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert f"{final_score} https://example.com/x" in out


def test_dry_run_の明細はタイトルを切り詰めるがURLは切り詰めない() -> None:
    """URL は記事の識別子であり、切ると特定できなくなる（§5）。"""
    long_url = "https://example.com/" + "b" * 200
    summary = _summary(
        dry_run=True,
        entries=[EntryVerdict(long_url, "t" * 120, final_score=8, will_ingest=True)],
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert long_url in out
    assert "t" * 60 in out
    assert "t" * 61 not in out


def test_dry_run_では前回比と経過期間を出力しない() -> None:
    """T-023: dry-run は runs.jsonl に追記しないため「前回」がずれて誤読を生む。"""
    summary = _summary(
        dry_run=True,
        sources=[SourceOutcome("jane-street", fetched=5)],
        previous_sources={"jane-street": 4},
        weeks_since_previous_run=1.0,
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert "前回" not in out
    assert "週" not in out


def test_通常実行とdry_runのサマリが3点以外は同一構造である() -> None:
    """T-024: dry-run 側への項目追加漏れを検出する（F-005 AC-003 の中核）。"""
    common: dict[str, object] = {
        "sources": [
            SourceOutcome("jane-street", fetched=5),
            SourceOutcome("netflix-techblog", fetched=0),
        ],
        "new_entries": 8,
        "evaluated": 8,
        "ingested": 3,
        "score_distribution": {3: 2, 7: 6},
        "cost_usd": 0.021,
        "evaluation_failures": 1,
        "abandoned": 1,
        "ingest_failures": 2,
        "ingest_failure_reasons": {"rate_limited": 2},
        "ingest_unattempted": 1,
        "deferred": 2,
    }
    normal = format_summary(_summary(**common), run_at=RUN_AT).splitlines()
    dry = format_summary(_summary(dry_run=True, **common), run_at=RUN_AT).splitlines()

    def blocks(lines: list[str]) -> set[tuple[int, str]]:
        """(インデント, 行頭ラベル) を取り出し、値の差を無視して構成を比較する。

        インデントを含めるのは、字下げされた行（情報源別・失敗理由の内訳）を
        区別するため。行頭トークンのみで比較すると字下げ行がすべて空文字へ潰れ、
        dry-run 側から情報源行が丸ごと消えても検出できない。
        """
        out: set[tuple[int, str]] = set()
        for line in lines:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            out.add((indent, line.strip().split(":")[0].split(" ")[0]))
        return out

    # dry-run 固有（判定結果ブロック）と通常固有（前回実行から）を除いて一致する
    assert blocks(normal) - blocks(dry) <= {(0, "前回実行から")}
    assert blocks(dry) - blocks(normal) <= {
        (0, "判定結果"),
        (2, "[投入]"),
        (2, "[見送]"),
        (2, "[失敗]"),
    }


# --- T-025 / T-026: セキュリティ ---------------------------------------------


def test_サマリに秘匿情報が現れない() -> None:
    """T-025: RunSummary は秘匿情報をフィールドとして持たない（型で防ぐ）。"""
    secret = "test-token-DO-NOT-LEAK"
    summary = _summary(
        sources=[SourceOutcome("jane-street", fetched=5)],
        new_entries=1,
        ingested=1,
    )
    out = format_summary(summary, run_at=RUN_AT)
    assert secret not in out
    assert not hasattr(summary, "raindrop_token")
    assert not hasattr(summary, "collection_id")
    assert not hasattr(summary, "api_key")


# --- コスト ------------------------------------------------------------------


def test_評価コストが小数第3位まで出力される() -> None:
    summary = _summary(cost_usd=0.0214, evaluated=8)
    out = format_summary(summary, run_at=RUN_AT)
    assert "評価コスト: $0.021 (8 件)" in out


def test_評価0件でもコスト行を出力する() -> None:
    out = format_summary(_summary(), run_at=RUN_AT)
    assert "評価コスト: $0.000 (0 件)" in out
