"""評価コストの算出テスト（REQ-NF-002a / F-004 AC-004 / SPEC-006 OQ-001）。"""

from __future__ import annotations

from feed_triage.implementation.domain.cost import estimate_cost_usd


class TestEstimateCostUsd:
    """入力・出力トークンから USD を算出する。"""

    def test_入力トークンの単価を用いる(self) -> None:
        """Haiku 4.5: 入力 $1.00 per 1M tokens。

        **出力側と非対称な値で検証する** — 入力と出力を同数にすると、
        単価を取り違えても合計が一致してしまい取り違えを検出できない。
        """
        assert estimate_cost_usd(1_000_000, 0) == 1.0

    def test_出力トークンの単価を用いる(self) -> None:
        """Haiku 4.5: 出力 $5.00 per 1M tokens。→ 入力側の単価と取り違えない。"""
        assert estimate_cost_usd(0, 1_000_000) == 5.0

    def test_入力と出力を合算する(self) -> None:
        assert estimate_cost_usd(1_000_000, 1_000_000) == 6.0

    def test_トークンが両方0なら0を返す(self) -> None:
        # 評価0件（対象なし）の正常な実行。0.0 は「未算出」ではなく
        # 「0 件評価」を意味する（SPEC-006 §4 入力表）
        assert estimate_cost_usd(0, 0) == 0.0
