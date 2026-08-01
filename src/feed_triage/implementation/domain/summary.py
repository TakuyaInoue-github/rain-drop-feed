"""実行サマリの整形（SPEC-006）。

`RunSummary` を人間可読のテキストへ整形する。**集計は行わない** — 各項目の
定義は生成元の SPEC が持ち、本モジュールは受け取った値をそのまま並べる。
ここで数え直すと各 SPEC の定義とずれた第二の定義が生まれ、無人実行では
誰も気づかない（SPEC-006 §1）。
"""

from __future__ import annotations

from feed_triage.contract.model import EntryVerdict, RunSummary, SourceOutcome

STALE_RUN_WEEKS = 2.0
"""定期実行の不発火を疑う経過週数の下限（F-002 AC-015 / SPEC-006 §5）。"""

DEGENERATE_MIN_EVALUATED = 2
"""スコア分布の縮退を警告する最小の評価成功件数（SPEC-006 §5）。

1 件は必然的に全件同一値になるため、警告すると新着が少ない週に毎回出て
警告そのものが無視されるようになる。
"""

TITLE_MAX_LEN = 60
"""dry-run 明細のタイトル表示長。URL は識別子のため切り詰めない。"""

_NO_NAME = "(名称なし)"


def format_summary(summary: RunSummary, *, run_at: str, verbose: bool = False) -> str:
    """サマリ全体を整形して返す。

    `verbose` は**出力を変えない**（F-004 AC-007）。詳細化されるのは標準エラー側で
    あり、引数を受け取るのは呼び出し側が条件分岐せずに済むようにするため。
    """
    del verbose  # サマリの内容は verbose に依存しない（F-004 AC-007）

    blocks: list[str] = [
        _heading(summary, run_at),
        _overview(summary),
        _sources_block(summary),
        _metrics_block(summary),
    ]
    if summary.dry_run and summary.entries:
        blocks.append(_verdicts_block(summary.entries))
    if summary.state_persist_error is not None:
        blocks.append(_persist_warning(summary.state_persist_error))
    return "\n\n".join(block for block in blocks if block) + "\n"


def _heading(summary: RunSummary, run_at: str) -> str:
    marks = " [DRY-RUN]" if summary.dry_run else ""
    incomplete = " （未完了）" if not summary.completed else ""
    return f"=== feed-triage 実行サマリ{marks} ({run_at}) ==={incomplete}"


def _overview(summary: RunSummary) -> str:
    """概況。0 件でも省略しない（F-004 AC-020 / AC-021）。

    0 であること自体が異常の兆候であり、省略すると「実行されなかった」との
    区別がつかない。
    """
    fetched = sum(source.fetched for source in summary.sources)
    if summary.dry_run:
        ingest_part = f"投入対象 {summary.ingested} 件 (投入は行っていません)"
    else:
        ingest_part = f"投入 {summary.ingested} 件"
    head = (
        f"取得 {fetched} 件 / 新規 {summary.new_entries} 件 / "
        f"評価 {summary.evaluated} 件 / {ingest_part}"
    )

    lines = [head]
    if _all_sources_failed(summary.sources):
        lines.append(f"**全 {len(summary.sources)} 情報源の取得に失敗しました**")
    if _all_ingests_failed(summary):
        lines.append(f"**投入対象 {summary.ingest_attempted} 件がすべて失敗しました**")
    return "\n".join(lines)


def _all_ingests_failed(summary: RunSummary) -> bool:
    """投入の全件失敗か（F-004 AC-016 / SPEC-004 フロー #15）。

    概況の `投入 0 件` だけでは「投入対象が0件だった週」と区別できないため、
    専用の警告を出す。分母は `ingest_attempted` であり、401/403 の打ち切りで
    未試行となった分は含めない。dry-run では POST を行わないため発生しない。
    """
    if summary.dry_run:
        return False
    return summary.ingest_attempted > 0 and summary.ingested == 0


def _all_sources_failed(sources: list[SourceOutcome]) -> bool:
    """全件失敗か（F-004 AC-014）。

    「1件以上失敗」ではない。一部失敗と全滅は運用者の対処が異なる。
    """
    return bool(sources) and all(source.error is not None for source in sources)


def _sources_block(summary: RunSummary) -> str:
    if not summary.sources:
        return "情報源が定義されていません。feeds.yaml を確認してください"

    # 前回比は通常実行でのみ出す。dry-run は runs.jsonl に追記しないため、
    # 挟むたびに「前回」の指す実行がずれて誤読を生む（SPEC-006 §5）。
    show_previous = not summary.dry_run
    width = max(len(source.source_name or _NO_NAME) for source in summary.sources)

    lines = ["情報源別:"]
    for source in summary.sources:
        name = (source.source_name or _NO_NAME).ljust(width)
        if source.error is not None:
            lines.append(f"  {name}  取得失敗 ({source.error})")
            continue
        line = f"  {name}  {source.fetched} 件"
        if show_previous:
            previous = summary.previous_sources.get(source.source_name)
            line += f" (前回 {previous if previous is not None else '-'})"
        lines.append(line)
    return "\n".join(lines)


def _metrics_block(summary: RunSummary) -> str:
    lines = [_score_distribution(summary)]

    # 失敗系は 0 なら省く。常時表示すると平常時のサマリが 0 件の行で埋まり、
    # 異常時に増える行が目立たなくなる（SPEC-006 §9）。
    for count, label in (
        (summary.evaluation_failures, "評価失敗"),
        (summary.abandoned, "再評価打ち切り"),
        (summary.ingest_failures, "投入失敗"),
        (summary.ingest_unattempted, "投入未試行"),
        (summary.deferred, "持ち越し"),
    ):
        if count:
            lines.append(f"{label} {count} 件")
        if label == "投入失敗" and count and summary.ingest_failure_reasons:
            reasons = " ".join(
                f"{code}: {n}" for code, n in sorted(summary.ingest_failure_reasons.items())
            )
            lines.append(f"  失敗理由: {reasons}")

    lines.append(f"評価コスト: ${summary.cost_usd:.3f} ({summary.evaluated} 件)")
    if not summary.dry_run:
        lines.append(_elapsed(summary.weeks_since_previous_run))
    return "\n".join(lines)


def _score_distribution(summary: RunSummary) -> str:
    distribution = summary.score_distribution
    if not distribution:
        return "スコア分布: (評価に成功した記事がありません)"

    body = " ".join(f"{score}:{n}" for score, n in sorted(distribution.items()))
    line = f"スコア分布: {body}"
    if len(distribution) == 1:
        ((score, count),) = distribution.items()
        if count >= DEGENERATE_MIN_EVALUATED:
            line += (
                f"\n**スコア分布が全件同一値 ({score}) です。"
                "トリアージ基準の破損またはモデル誤指定を疑ってください**"
            )
    return line


def _elapsed(weeks: float | None) -> str:
    if weeks is None:
        return "前回実行から: - (初回)"
    line = f"前回実行から {weeks:.1f} 週"
    if weeks >= STALE_RUN_WEEKS:
        line += " **（定期実行が起動しなかった可能性があります）**"
    return line


def _verdicts_block(entries: list[EntryVerdict]) -> str:
    lines = ["判定結果:"]
    for entry in entries:
        if entry.final_score is None:
            label, score = "[失敗]", "-"
        else:
            label = "[投入]" if entry.will_ingest else "[見送]"
            # 値域外（-1 / 11）でも丸めない。丸めると F-003 の事後検証で
            # 端点のデータが失われる（SPEC-004 §4）。
            score = str(entry.final_score)
        title = entry.title[:TITLE_MAX_LEN]
        suffix = f"  {title}" if title else ""
        lines.append(f"  {label} {score} {entry.url}{suffix}")
    return "\n".join(lines)


def _persist_warning(error: str) -> str:
    """永続化失敗の警告（F-004 AC-015）。

    標準出力へ出す。標準エラーへ分離すると、リダイレクトしたサマリから警告が
    消え「サマリで識別できる」を満たせなくなる（SPEC-006 §4）。
    """
    return (
        f"**記録の永続化に失敗しました: {error}。"
        "次回実行で重複投入が発生しうるため、状態ブランチを確認してください**"
    )
