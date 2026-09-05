"""スコア補正と投入判定のテスト（REQ-F-004・005・006 / F-001 AC-020・021・029）。"""

from __future__ import annotations

import pytest

from feed_triage.implementation.domain.scoring import (
    DEFAULT_HOT_THRESHOLD,
    DEFAULT_THRESHOLD,
    SCORE_MAX,
    SCORE_MIN,
    adjusted_score,
    is_hot,
    is_valid_score,
    should_ingest,
)


class TestIsValidScore:
    """F-001 AC-029: 範囲外のスコアが投入判定に用いられないこと。"""

    @pytest.mark.parametrize("score", [0, 5, 10])
    def test_値域内の整数は妥当(self, score: int) -> None:
        assert is_valid_score(score) is True

    @pytest.mark.parametrize("score", [-1, 11, 100])
    def test_値域外の整数は不正(self, score: int) -> None:
        assert is_valid_score(score) is False

    @pytest.mark.parametrize("score", [5.5, "8", None, [], {}])
    def test_整数でない値は不正(self, score: object) -> None:
        assert is_valid_score(score) is False

    @pytest.mark.parametrize("score", [True, False])
    def test_boolは整数の派生だがスコアとしては不正(self, score: bool) -> None:
        assert is_valid_score(score) is False


class TestShouldIngest:
    """REQ-F-005 / F-001 AC-020・AC-021: 閾値による投入可否。"""

    def test_閾値ちょうどなら投入する(self) -> None:
        assert should_ingest(DEFAULT_THRESHOLD) is True

    def test_閾値の1つ下なら投入しない(self) -> None:
        assert should_ingest(DEFAULT_THRESHOLD - 1) is False

    def test_閾値を上回れば投入する(self) -> None:
        assert should_ingest(DEFAULT_THRESHOLD + 1) is True

    def test_閾値を明示的に指定できる(self) -> None:
        assert should_ingest(3, threshold=3) is True
        assert should_ingest(2, threshold=3) is False


class TestIsHot:
    """REQ-F-006 / F-001 AC-003: 高評価帯の識別。"""

    def test_高評価帯の境界ちょうどなら該当する(self) -> None:
        assert is_hot(DEFAULT_HOT_THRESHOLD) is True

    def test_境界の1つ下なら該当しない(self) -> None:
        assert is_hot(DEFAULT_HOT_THRESHOLD - 1) is False

    def test_投入されるが高評価帯ではないスコアが存在する(self) -> None:
        """二層方式: 広く投入した上で視線を絞る（R-004）。"""
        between = DEFAULT_THRESHOLD
        assert should_ingest(between) is True
        assert is_hot(between) is False


def test_スコアの値域が_contract_層で定義されている() -> None:
    """adapters と domain の両方が参照するため contract に置く。

    adapters → domain は import-linter が禁じており（ADR-004 設計原則: 決定論的
    部分と確率的部分の分離）、値域を domain に置くと adapters 側で重複定義するか
    層構造を崩すかの二択になる。
    """
    from feed_triage.contract import model

    assert (model.SCORE_MIN, model.SCORE_MAX) == (0, 10)
    assert (SCORE_MIN, SCORE_MAX) == (model.SCORE_MIN, model.SCORE_MAX)


class TestWeightAbolished:
    """TASK-118: weight を廃止し、補正後スコアは素点と一致する。"""

    def test_補正後スコアは素点と一致する(self) -> None:
        assert adjusted_score(7) == 7

    def test_値域の両端でも素点のまま(self) -> None:
        assert adjusted_score(0) == 0
        assert adjusted_score(10) == 10
