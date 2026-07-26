"""コマンドライン入口。引数解析と出力のみを担う。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from feed_triage import __version__
from feed_triage.contract import exit_codes
from feed_triage.pipeline import RunOptions


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _options = RunOptions(dry_run=args.dry_run, verbose=args.verbose)
    parser.exit(
        exit_codes.CONFIG_ERROR,
        "feed-triage はまだ実装されていません（SPEC 層の確定待ち）\n",
    )
