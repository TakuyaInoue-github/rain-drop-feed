"""評価コストの算出。副作用を持たない。

**目的はコスト削減ではなく異常検知**（REQ-NF-002a）。週次の無人実行では、
モデルの誤指定・リトライの暴走・状態消失による全件再評価に気づく契機が
実行サマリしかない。
"""

from __future__ import annotations

__all__ = [
    "INPUT_USD_PER_MTOK",
    "OUTPUT_USD_PER_MTOK",
    "estimate_cost_usd",
]

_TOKENS_PER_MTOK = 1_000_000

INPUT_USD_PER_MTOK = 1.00
"""入力トークン 100 万件あたりの単価（Haiku 4.5）。

**`adapters/evaluate.py` の `MODEL_ID` と対で維持する。** 層の依存方向
（`domain → adapters` のみ）によりモデル定数をここから参照できないため、
モデルを変えたら単価も手で合わせる必要がある。
"""

OUTPUT_USD_PER_MTOK = 5.00
"""出力トークン 100 万件あたりの単価（Haiku 4.5）。→ `INPUT_USD_PER_MTOK`。"""


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """トークン数から評価コスト（USD）を算出する。"""
    return (
        input_tokens * INPUT_USD_PER_MTOK + output_tokens * OUTPUT_USD_PER_MTOK
    ) / _TOKENS_PER_MTOK
