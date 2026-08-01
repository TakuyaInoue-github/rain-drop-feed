"""収集レイヤー（Raindrop.io）への投入とタグ付与（SPEC-004）。

投入は逐次で 1 req/sec 以下に抑える（§7）。**個別の失敗は他の投入を止めない**
（REQ-NF-004 / F-001 AC-012）ため、例外を呼び出し元へ伝播させず必ず
`IngestResult` に落とす。唯一の例外が 401 / 403 で、残りも同じ結果になるため
打ち切る（フロー #11）。

**本仕様は重複排除を行わない。** 同一 URL を2回渡されれば2回投入する。
重複を防ぐのは SPEC-002 の突合であり、ここで自前の排除を足すと責務が
二重化する（§7 冪等性）。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlsplit

import httpx

from feed_triage.contract.model import Entry, EntryVerdict, Verdict

API_URL = "https://api.raindrop.io/rest/v1/raindrop"
"""投入先エンドポイント（§8）。**HTTPS 固定**（REQ-NF-006）。"""

TIMEOUT_SECONDS = 30.0
"""1件の投入あたりの HTTP タイムアウト（TASK-084 / §7）。

フィード取得（30秒）と同値に揃える。別の値にする積極的な根拠が実測前には
立たず、値を散らすと運用者が把握すべき数値が増えるため。週20〜30件が
全件タイムアウトしても15分で REQ-NF-001 の30分内に収まる。
"""

MIN_INTERVAL_SECONDS = 1.0
"""投入要求の最小間隔（§7 / REQ-NF-001）。

Raindrop の 120 req/min = 2 req/sec に対し 50% の余裕を取る。週次の投入数
20〜30件では所要30秒未満であり、実行時間目標を圧迫しない。
"""

TITLE_MAX_CHARS = 1_000
"""`title` の上限。**Raindrop の実上限に一致させた値**（§8 で一次情報を確認）。"""

EXCERPT_MAX_CHARS = 10_000
"""`excerpt` の上限。同じく Raindrop の実上限（§8）。

実測の全文配信フィード（9,238文字）は上限内に収まるため**要約は切り詰められない**。
自主的により小さい値にすると、収集レイヤー上の記事から元の要約が失われ、
F-003 の事後検証ができなくなる。
"""

MAX_TAG_CHARS = 50
MAX_TAGS = 30
"""タグの長さ・件数の上限（**本システム側の自主値** → OQ-004 / TASK-083）。

Raindrop の実上限は一次情報に記載がなく、超過時の挙動が不明なため保守的に
抑える。実運用で切り詰めが頻発するようなら実測して見直す。
"""

AUTO_TAG = "auto"
"""全投入エントリに付与する撤退用のタグ（要件定義 §7 のロールバック条件）。

手動登録分と機械的に区別するための起点であり、**タグ件数の上限に達しても
最初に採る**（§5 の優先順）。
"""

HOT_TAG = "hot"


class FailureReason(Enum):
    """投入失敗の理由コード（§4 出力）。

    **呼び出し元へ返すのみで状態には記録しない。** `state.jsonl` は
    `ingested: false` のみを持ち、理由の集計はサマリが行う（SPEC-006）。
    """

    RATE_LIMITED = "rate_limited"
    UNAUTHORIZED = "unauthorized"
    CLIENT_ERROR = "client_error"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    INVALID_LINK = "invalid_link"


@dataclass(frozen=True)
class Candidate:
    """投入判定を**済ませた**1件分の入力（§4 入力）。

    **判定そのものは `domain.scoring` が行い、本モジュールは結果を受け取る。**
    `adapters → domain` の import は禁じられており（ADR-004 設計原則: 決定論的
    部分と確率的部分の分離）、判定を adapters に持ち込むと層構造が崩れる。
    組み立ては `pipeline` が担う。
    """

    entry: Entry
    verdict: Verdict
    final_score: int
    """補正後スコア（`score + weight`）。**0〜10 に丸められていないこと。**

    丸めると `state.jsonl` の `final_score` から端点のデータが失われ、
    F-003 が任意の閾値を当て直す事後検証（R-006）ができなくなる（§4 の注記）。
    """
    will_ingest: bool
    """`domain.scoring.should_ingest` の判定結果。"""
    is_hot: bool = False
    """`domain.scoring.is_hot` の判定結果。`hot` タグの付与に用いる。"""
    source_tags: tuple[str, ...] = ()


@dataclass
class IngestResult:
    """投入段階の結果（§4 出力）。`RunSummary` の各フィールドへ詰められる。"""

    ingested: int = 0
    """通常実行では**投入に成功した件数**、dry-run では**投入対象と判定された件数**。

    両者は排他である（dry-run では POST を行わないため成功件数は常に0）。
    **通常実行で投入対象件数を詰めてはならない** — 全件失敗しても `ingested` が
    非0になり、SPEC-006 フロー #17 の判定が成立せず、警告も非0終了も出ないまま
    投入が全滅する（F-004 AC-016 / F-001 AC-014 違反）。
    """
    attempted: int = 0
    """実際に POST を発行した件数（成功 + 失敗）。**未試行件数を含まない。**

    `all_failed` の分母であり、`ingested + failures` で導出せず独立して持つ。
    """
    failures: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)
    unattempted: int = 0
    """401/403 の打ち切りで POST を試行しなかった件数（フロー #11）。

    **成功にも失敗にも数えず、`all_failed` の分母にも含めない。**
    """
    unattempted_candidates: list[Candidate] = field(default_factory=list)
    """打ち切られた未試行のエントリ。**状態に記録せず次回実行へ持ち越す。**

    記録すると処理済み扱いとなり、認証失効1回でその週の投入対象が恒久的に
    失われる（R-001 違反 → フロー #11）。
    """
    ingested_urls: list[str] = field(default_factory=list)
    """投入に**成功した** url。呼び出し元が `ingested: true` を立てる（F-001 AC-006）。

    件数だけでは「どの行に立てるか」が決まらないため url を返す。失敗した分に
    立てると、投入されていない記事が投入済みとして記録され次回も投入されない。
    """
    entries: list[EntryVerdict] = field(default_factory=list)
    """dry-run の明細（F-005 AC-002 / SPEC-006 §4）。"""
    messages: list[str] = field(default_factory=list)
    """標準エラー出力へ流す文言（§3）。**秘匿値を含めない**（REQ-NF-006）。"""

    @property
    def all_failed(self) -> bool:
        """POST を試行したものが全件失敗したか（フロー #15 → `INGEST_ALL_FAILED`）。

        投入対象0件は**全件失敗ではない**（新着ゼロの週を失敗扱いにしない
        → F-001 AC-014 括弧書き / AC-022）。
        """
        return self.attempted > 0 and self.ingested == 0


def build_tags(candidate: Candidate) -> list[str]:
    """付与するタグ集合を構築する（§4 出力 / §5）。

    **送信値に `#` を含めない** — Raindrop の `tags` はプレフィックスなしの
    文字列配列であり、公式ドキュメントの例も `feeds.yaml` も `#` なしで
    書かれている（OQ-004）。`#` を残すと `#auto` による撤退が機能しない。

    `score-{n}` の n は**補正後スコア**（OQ-001）。タグだけを見て投入判定
    （`n >= 閾値`）を再現できるようにするためで、**値域を超えた場合も
    そのまま出す**（`score-11` / `score--1`）。

    優先順は `auto` → `score-{n}` → `hot` → 情報源タグ → 提案タグ。
    上限超過時にこの順で先頭から採るため、撤退の起点である `auto` が落ちない。
    """
    ordered: list[str] = [AUTO_TAG, f"score-{candidate.final_score}"]
    if candidate.is_hot:
        ordered.append(HOT_TAG)
    ordered.extend(candidate.source_tags)
    ordered.extend(candidate.verdict.suggested_tags)

    return _normalize_tags(ordered)


class Ingestor:
    """投入対象を判定し、1件ずつ POST する。

    `sleep` / `monotonic` を差し替え可能にしているのは、レート制御が
    **仕様上の要件**（§7）でありテストで検証する必要があるため。
    """

    def __init__(
        self,
        *,
        token: str | None,
        collection_id: int | None,
        dry_run: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.token = token
        self.collection_id = collection_id
        self.dry_run = dry_run
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self._client: httpx.Client | None = None

    def close(self) -> None:
        """HTTP クライアントを閉じる。`ingest_all` が `finally` で必ず呼ぶ。"""
        if self._client is not None:
            self._client.close()
            self._client = None

    def ingest_all(self, candidates: Iterable[Candidate]) -> IngestResult:
        """全候補を判定し、投入対象を**定義順に逐次** POST する。

        並列化しない（§7 レート制御）。例外を送出しない。
        """
        result = IngestResult()
        selected = self._select(list(candidates), result)

        if self.dry_run:
            # HTTP リクエストを一切発行しない（F-005 AC-001 / T-029）。
            # 認証情報・コレクション ID が未設定でも中止しない（F-005 AC-030）
            result.ingested = len(selected)
            return result

        try:
            for index, candidate in enumerate(selected):
                if not self._post_one(candidate, result):
                    # 401 / 403。残りも同じ結果になるため打ち切る（フロー #11）
                    remaining = selected[index + 1 :]
                    self._record_unattempted(remaining, result)
                    break
        finally:
            self.close()

        if not selected:
            result.messages.append("投入対象がありません")
        return result

    def _select(self, candidates: Sequence[Candidate], result: IngestResult) -> list[Candidate]:
        """投入対象を抜き出す（フロー #2・#5）。

        **判定は済んでいる** — `will_ingest` は `domain.scoring` が決めた値であり、
        ここで閾値と比較し直さない。
        """
        selected: list[Candidate] = []
        for candidate in candidates:
            if candidate.will_ingest:
                selected.append(candidate)
            if self.dry_run:
                result.entries.append(
                    EntryVerdict(
                        url=candidate.entry.url,
                        title=candidate.entry.title,
                        final_score=candidate.final_score,
                        will_ingest=candidate.will_ingest,
                    )
                )
        return selected

    def _post_one(self, candidate: Candidate, result: IngestResult) -> bool:
        """1件を投入する。**打ち切るべきときのみ False** を返す（401 / 403）。"""
        link = candidate.entry.url.strip()
        if not _is_ingestable(link):
            # `link` は Raindrop の必須項目。送信しても 400 になるだけなので
            # 要求を発行せずローカルで弾く（§5）
            self._fail(result, FailureReason.INVALID_LINK, f"投入できない URL のためスキップします: {link}")
            return True

        self._throttle()
        result.attempted += 1
        try:
            response = self._http().post(API_URL, json=self._payload(candidate, link))
        except httpx.TimeoutException:
            self._fail(result, FailureReason.TIMEOUT, f"投入がタイムアウトしました: {link}")
            return True
        except httpx.HTTPError as exc:
            # **例外の全文を出力しない** — httpx の例外は要求 URL・ヘッダを
            # 引用しうるため、トークンが露出する（REQ-NF-006 / §7）
            self._fail(
                result,
                FailureReason.SERVER_ERROR,
                f"投入に失敗しました: {link}（{type(exc).__name__}）",
            )
            return True

        return self._classify(response, link, result)

    def _classify(self, response: httpx.Response, link: str, result: IngestResult) -> bool:
        """応答を分類する。**ステータスコードのみで分岐し本体をパースしない。**

        4xx / 5xx の本体の形は一次情報で未確認であり（§8）、本体に依存すると
        形が変わったときに分岐が壊れる。
        """
        status = response.status_code
        if response.is_success:
            result.ingested += 1
            result.ingested_urls.append(link)
            result.messages.append(f"投入しました: {link}")
            return True

        if status in (401, 403):
            # トークンの値をメッセージに含めない（F-001 AC-031）
            self._fail(
                result,
                FailureReason.UNAUTHORIZED,
                f"収集レイヤーの認証に失敗しました（HTTP {status}）。"
                "以降の投入を中止し、次回実行へ持ち越します",
            )
            return False

        if status == 429:
            # 他の失敗と区別可能な理由コードで返す（F-001 AC-017）。
            # 本仕様ではリトライしない（フロー #10 / OQ-002）
            self._fail(
                result, FailureReason.RATE_LIMITED, f"レート制限により投入できませんでした: {link}"
            )
            return True

        reason = (
            FailureReason.SERVER_ERROR if status >= 500 else FailureReason.CLIENT_ERROR
        )
        self._fail(result, reason, f"投入に失敗しました: {link}（HTTP {status}）")
        return True

    def _payload(self, candidate: Candidate, link: str) -> dict[str, object]:
        """要求本体を組み立てる（§8）。

        `title` / `excerpt` は**空文字のまま送る** — Raindrop 側が `pleaseParse`
        で `link` から補完するため（§4 入力）。空値を除去するのはタグのみ。
        """
        return {
            "link": link,
            "title": candidate.entry.title[:TITLE_MAX_CHARS],
            "excerpt": candidate.entry.summary[:EXCERPT_MAX_CHARS],
            "tags": build_tags(candidate),
            "collection": {"$id": self.collection_id},
            "pleaseParse": {},
        }

    def _record_unattempted(self, remaining: Sequence[Candidate], result: IngestResult) -> None:
        """打ち切られた分を未試行として記録する（フロー #11 / §4）。"""
        result.unattempted += len(remaining)
        result.unattempted_candidates.extend(remaining)

    def _fail(self, result: IngestResult, reason: FailureReason, message: str) -> None:
        result.failures += 1
        result.failure_reasons[reason.value] = result.failure_reasons.get(reason.value, 0) + 1
        result.messages.append(message)

    def _throttle(self) -> None:
        """直前の要求開始から `MIN_INTERVAL_SECONDS` 経つまで**差分だけ**待つ（§7）。

        経過済みなら待たない。先頭でも待たない（週次バッチの所要時間を
        無駄に伸ばさないため）。
        """
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = MIN_INTERVAL_SECONDS - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_at = now

    def _http(self) -> httpx.Client:
        """HTTP クライアントを遅延生成する。

        dry-run では一度も生成されない。**証明書検証を無効化しない**
        （`verify` を渡さず httpx の既定に委ねる → REQ-NF-006 / T-027）。
        """
        if self._client is None:
            self._client = httpx.Client(
                timeout=TIMEOUT_SECONDS,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            )
        return self._client


def _is_ingestable(link: str) -> bool:
    """`link` として送信してよい URL か（§5）。"""
    return bool(link) and urlsplit(link).scheme in ("http", "https")


def _normalize_tags(tags: Iterable[str]) -> list[str]:
    """空白除去・`#` 除去・切り詰め・重複除去を順に適用する（§5）。

    重複は**大文字小文字を区別せず**除去し、先に現れた表記を採る。
    """
    seen: set[str] = set()
    normalized: list[str] = []
    for tag in tags:
        cleaned = tag.strip().lstrip("#").strip()[:MAX_TAG_CHARS]
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
        if len(normalized) == MAX_TAGS:
            break
    return normalized
