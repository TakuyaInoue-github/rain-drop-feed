"""スコアの補正と投入可否の判定。副作用を持たない。

評価そのもの（確率的な処理）は adapters 側に隔離されており、
本モジュールはその出力を決定論的に検証・判定する
（ADR-004 設計原則(3)）。
"""

from __future__ import annotations

from feed_triage.contract.model import SCORE_MAX, SCORE_MIN

__all__ = [
    "SCORE_MAX",
    "SCORE_MIN",
    "DEFAULT_THRESHOLD",
    "DEFAULT_HOT_THRESHOLD",
    "is_valid_score",
    "adjust",
    "should_ingest",
    "is_hot",
]

DEFAULT_THRESHOLD = 5
"""投入可否を分ける閾値の初期値（REQ-F-005。変更には運用者の合意を要する）。"""

DEFAULT_HOT_THRESHOLD = 7
"""高評価帯の境界値（REQ-F-006。同上）。"""


def is_valid_score(score: object) -> bool:
    """評価が返したスコアが値域内の整数か。

    範囲外・非整数のスコアを投入判定に用いてはならない（F-001 AC-029）。
    bool は int の派生だが、スコアとしては不正とみなす。
    """
    if isinstance(score, bool) or not isinstance(score, int):
        return False
    return SCORE_MIN <= score <= SCORE_MAX


def adjust(score: int, weight: int) -> int:
    """情報源の重みを加算した補正後スコアを返す（REQ-F-004）。"""
    return score + weight


def should_ingest(final_score: int, threshold: int = DEFAULT_THRESHOLD) -> bool:
    """補正後スコアが閾値以上なら投入対象（REQ-F-005 / F-001 AC-020・AC-021）。"""
    return final_score >= threshold


def is_hot(final_score: int, hot_threshold: int = DEFAULT_HOT_THRESHOLD) -> bool:
    """レビュー時に識別するタグを付与する高評価帯か（REQ-F-006 / F-001 AC-003）。"""
    return final_score >= hot_threshold
