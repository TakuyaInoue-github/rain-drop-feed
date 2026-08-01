"""コマンドライン入口（SPEC-005）。引数解析・起動時検証・出力を担う。

**起動時にまとめて検証する理由:** 設定不備を処理の途中で発見すると、それまでの
フィード取得・LLM 評価のコストが無駄になり、かつ一部だけ投入された中途半端な
状態が残りうる（F-001 AC-030）。

**終了コードの正典は SPEC-005 §5。** 本モジュールは `pipeline` が決めた値を
そのまま返し、起動時検証の失敗のみ `CONFIG_ERROR` を自前で返す。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from feed_triage import __version__
from feed_triage.contract import exit_codes
from feed_triage.contract.model import RunRecord, Source, StateRecord
from feed_triage.implementation.adapters import fetch, persist, store
from feed_triage.implementation.adapters.config import ConfigError, load_profile, load_sources
from feed_triage.implementation.adapters.evaluate import Evaluator, build_client
from feed_triage.implementation.adapters.ingest import Ingestor
from feed_triage.implementation.domain.summary import format_summary
from feed_triage.pipeline import Adapters, RunOptions, run

FEEDS_PATH = Path("feeds.yaml")
PROFILE_PATH = Path("profile.md")
STATE_PATH = Path("state.jsonl")
RUNS_PATH = Path("runs.jsonl")

RAINDROP_KEYS = ("RAINDROP_TOKEN", "RAINDROP_COLLECTION_ID")
"""dry-run で検証を緩める対象（F-005 AC-030）。**これ以外は緩めない。**"""


@dataclass
class Settings:
    """起動時検証を通過した設定（SPEC-005 §4 出力）。

    秘匿値は `repr=False` を付けて `__repr__` から外す。例外のスタック
    トレースやログへ誤って出力されるのを**型で**防ぐため（REQ-NF-006）。
    """

    sources: list[Source]
    profile: str
    anthropic_api_key: str = field(repr=False)
    raindrop_token: str | None = field(default=None, repr=False)
    collection_id: int | None = field(default=None, repr=False)
    """**コレクション ID も `repr` から外す**（F-004 AC-030 / SPEC-005 §4）。

    トークンほど機微ではないが、投入先を特定できる値であり「サマリに出力しない」
    と規定されている。トークンだけを隠して ID を残すと、例外のスタックトレース
    経由で CI のログに残る。
    """


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feed-triage",
        description="RSS を取得し LLM トリアージを通して Raindrop.io へ投入する",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="収集レイヤーへの投入を行わず、評価結果とサマリのみを出力する",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="処理経過の詳細ログを出力する（サマリの内容は変化しない）",
    )
    return parser


def load_settings(*, dry_run: bool) -> Settings | None:
    """§2 の項目をすべて検証する。1つでも欠ければ `None` を返す。

    **エラーメッセージには変数名のみを示し、値を出力しない**（F-001 AC-031 /
    AC-033）。CI のログに秘匿情報が残るのを防ぐ。
    """
    api_key = _env("ANTHROPIC_API_KEY")
    if api_key is None:
        # **dry-run でも必須** — 評価は dry-run でも実際に行う
        _error("環境変数 ANTHROPIC_API_KEY が設定されていません")
        return None

    try:
        sources = load_sources(FEEDS_PATH)
        profile = load_profile(PROFILE_PATH)
    except ConfigError as exc:
        # ConfigError のメッセージはファイル内容を含まない（config.py の規約）
        _error(str(exc))
        return None

    token = _env("RAINDROP_TOKEN")
    collection_id = _collection_id()

    if dry_run:
        missing = [
            key
            for key, value in zip(RAINDROP_KEYS, (token, collection_id), strict=True)
            if value is None
        ]
        if missing:
            # 通常実行では起動時に失敗する状態であることを報せる（F-005 AC-030a）。
            # 出さないと dry-run で OK を確認した後に定期実行が失敗する
            _error(
                "dry-run のため続行しますが、通常実行に必要な設定が不足しています: "
                + ", ".join(missing)
            )
    else:
        if token is None:
            _error("環境変数 RAINDROP_TOKEN が設定されていません")
            return None
        if collection_id is None:
            _error(
                "環境変数 RAINDROP_COLLECTION_ID が設定されていないか、整数ではありません"
            )
            return None

    return Settings(
        sources=sources,
        profile=profile,
        anthropic_api_key=api_key,
        raindrop_token=token,
        collection_id=collection_id,
    )


class _Store:
    """状態の読み書きと永続化を束ねて `pipeline` へ渡す（SPEC-002）。"""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._pending_state = ""
        self._pending_runs = ""

    def load_state(self) -> list[StateRecord]:
        records, _ = store.load_state(STATE_PATH)
        return records

    def load_runs(self) -> list[RunRecord]:
        return store.load_runs(RUNS_PATH)

    def append(self, records: list[StateRecord], run_record: RunRecord | None) -> None:
        store.append_records(STATE_PATH, records)
        if run_record is not None:
            store.append_run(RUNS_PATH, run_record)

    def persist(self) -> None:
        """状態ブランチへ push する（ADR-002）。

        **失敗は握り潰さない** — 記録できないまま投入を続けると、次回実行で
        重複投入（R-002 違反）が確定する。
        """
        files = {
            name: path.read_text(encoding="utf-8")
            for name, path in (("state.jsonl", STATE_PATH), ("runs.jsonl", RUNS_PATH))
            if path.exists()
        }
        persist.persist_state(self.repo, files)


def main(argv: Sequence[str] | None = None) -> int:
    """引数を解析し、検証を通してから処理本体を起動する（フロー #1〜#4）。

    **`--help` / `--version` は起動時検証より前に処理される**（argparse が
    その場で終了するため）。設定が壊れている運用者こそヘルプを必要とする。
    """
    args = build_parser().parse_args(argv)
    options = RunOptions(dry_run=args.dry_run, verbose=args.verbose)

    settings = load_settings(dry_run=options.dry_run)
    if settings is None:
        return exit_codes.CONFIG_ERROR

    run_at = datetime.now(timezone.utc)
    ingestor = Ingestor(
        token=settings.raindrop_token,
        collection_id=settings.collection_id,
        dry_run=options.dry_run,
    )
    adapters = Adapters(
        sources=settings.sources,
        profile=settings.profile,
        fetch=fetch.fetch_all,
        evaluator=Evaluator(build_client(settings.anthropic_api_key), settings.profile),
        ingestor=ingestor,
        store=_Store(Path.cwd()),
        now=lambda: run_at,
    )

    outcome = run(options, adapters)

    # サマリは標準出力、ログ・警告は標準エラー（REQ-NF-007 / F-004 AC-005）
    for message in outcome.messages:
        _error(message)
    print(
        format_summary(
            outcome.summary, run_at=run_at.strftime("%Y-%m-%d %H:%M"), verbose=args.verbose
        )
    )
    return outcome.exit_code


def _env(name: str) -> str | None:
    """環境変数を読む。**未設定と空文字を同じ扱いにする**（§4 入力(b)）。

    空文字のトークンで API を呼べば必ず 401 になり未設定と同じ結果に至る。
    区別しても運用者の対処（値を設定する）は同一であるため分岐を減らす。
    """
    value = os.environ.get(name, "").strip()
    return value or None


def _collection_id() -> int | None:
    """コレクション ID を整数として解釈する。

    **既定のコレクション（`$id: -1` = Unsorted）へフォールバックしない**
    （F-001 AC-032）。`0` / 負値の受理は暫定（SPEC-004 OQ-007 / TASK-085）。
    """
    raw = _env("RAINDROP_COLLECTION_ID")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        # **値そのものは出力しない**（REQ-NF-006）
        return None


def _error(message: str) -> None:
    print(message, file=sys.stderr)
