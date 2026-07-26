"""実行フローの組み立て。I/O は行わず、adapters を介して副作用を実行する。

現時点では層構造の骨格のみ。取得・評価・投入の実装は SPEC 層の確定後に追加する。
"""

from __future__ import annotations

from dataclasses import dataclass

from feed_triage.contract.model import RunSummary


@dataclass(frozen=True)
class RunOptions:
    """1回の実行に与えるオプション。"""

    dry_run: bool = False
    verbose: bool = False


def run(options: RunOptions) -> RunSummary:
    """1回の実行を行いサマリを返す。

    未実装。SPEC 層の確定後に、取得 → 重複排除 → 評価 → 判定 → 投入 →
    記録の順で組み立てる（F-001 §4）。
    """
    raise NotImplementedError("取得・評価・投入の実装は SPEC 確定後に行う")
