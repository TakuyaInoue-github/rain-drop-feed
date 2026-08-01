"""収集レイヤーへの投入・タグ付与のテスト（SPEC-004）。

観点番号（T-xxx）は SPEC-004 §10 の表に対応させる。HTTP は respx でモックし、
実ネットワークへは出ない。

T-022 / T-023 / T-024（起動時の秘匿値・コレクション ID の検証）は SPEC-005 の
管轄であり本モジュールには到達しないため、`tests/test_cli.py` 側で扱う。
"""

from __future__ import annotations

import httpx
import pytest
import respx

from feed_triage.contract.model import Entry, Verdict
from feed_triage.implementation.adapters.ingest import (
    API_URL,
    MAX_TAG_CHARS,
    MAX_TAGS,
    MIN_INTERVAL_SECONDS,
    TITLE_MAX_CHARS,
    Candidate,
    FailureReason,
    Ingestor,
    build_tags,
)
from feed_triage.implementation.domain.scoring import adjust, is_hot, should_ingest

TOKEN = "test-token-DO-NOT-LEAK"
COLLECTION_ID = 12345678


def entry(url: str = "https://example.com/a", title: str = "記事", summary: str = "要約") -> Entry:
    return Entry(
        url=url,
        title=title,
        summary=summary,
        published_at=None,
        source_name="example",
    )


def candidate(
    url: str = "https://example.com/a",
    score: int = 8,
    weight: int = 0,
    *,
    title: str = "記事",
    summary: str = "要約",
    suggested_tags: tuple[str, ...] = (),
    source_tags: tuple[str, ...] = (),
) -> Candidate:
    """`pipeline` が行う組み立てをテスト側で再現する。

    判定は `domain.scoring` が担い、`Ingestor` は結果を受け取るだけ
    （adapters → domain は import-linter が禁じている → ADR-004）。
    ここで閾値を再実装せず実物の関数を通すことで、境界値テスト（T-014 / T-015）が
    実際の判定関数を検証する。
    """
    final_score = adjust(score, weight)
    return Candidate(
        entry=entry(url, title, summary),
        verdict=Verdict(score=score, reason="理由", suggested_tags=suggested_tags),
        final_score=final_score,
        will_ingest=should_ingest(final_score),
        is_hot=is_hot(final_score),
        source_tags=source_tags,
    )


def ingestor(**kwargs: object) -> Ingestor:
    """待機を挟まない Ingestor。レート制御そのものは T-028 で個別に検証する。"""
    kwargs.setdefault("sleep", lambda _seconds: None)
    return Ingestor(token=TOKEN, collection_id=COLLECTION_ID, **kwargs)  # type: ignore[arg-type]


def ok_response() -> httpx.Response:
    return httpx.Response(200, json={"result": True, "item": {"_id": 1}})


def bodies(route: respx.Route) -> list[dict[str, object]]:
    import json

    return [json.loads(call.request.content) for call in route.calls]


# --- T-001 / T-006 / T-014 / T-015: 投入可否の判定 ---------------------------


@respx.mock
def test_閾値以上の記事だけが_POST_される() -> None:
    """T-001: 判定を通さず全件 POST すれば、閾値未満にも要求が飛びレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    result = ingestor().ingest_all(
        [
            candidate("https://example.com/high", score=8),
            candidate("https://example.com/low", score=2),
        ]
    )

    assert route.call_count == 1
    assert bodies(route)[0]["link"] == "https://example.com/high"
    assert result.ingested == 1
    assert result.attempted == 1


@respx.mock
def test_重みにより投入可否が変わる() -> None:
    """T-006: `adjust` が weight を無視すれば両者が同判定になりレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    ingestor().ingest_all(
        [
            candidate("https://example.com/boosted", score=4, weight=1),
            candidate("https://example.com/plain", score=4, weight=0),
        ]
    )

    assert [body["link"] for body in bodies(route)] == ["https://example.com/boosted"]


@respx.mock
@pytest.mark.parametrize(("score", "expected"), [(5, 1), (4, 0)])
def test_閾値の境界(score: int, expected: int) -> None:
    """T-014 / T-015: 比較を `>` にすれば 5 が落ちてレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())
    ingestor().ingest_all([candidate(score=score)])
    assert route.call_count == expected


@respx.mock
def test_投入対象が0件なら要求を発行せず成功する() -> None:
    """T-018: 「投入0件なら非0」にすれば新着ゼロの週が失敗扱いになりレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    result = ingestor().ingest_all([candidate(score=1)])

    assert route.call_count == 0
    assert result.attempted == 0
    assert result.all_failed is False, "投入対象0件は全件失敗ではない（F-001 AC-022）"


# --- T-019 / T-020: 補正後スコアを丸めない ----------------------------------


def test_補正後スコアは上限を超えても丸めない() -> None:
    """T-019: `min(10, ...)` で丸めれば 11 が 10 になりレッド。

    `final_score` は F-003 が任意の閾値を当て直して事後検証する値であり、
    丸めると端点のデータが失われる（SPEC-004 §4 注記）。
    """
    assert candidate(score=10, weight=1).final_score == 11


def test_補正後スコアは下限を下回っても丸めない() -> None:
    """T-020: `max(0, ...)` で丸めればレッド。"""
    assert candidate(score=0, weight=-1).final_score == -1


@respx.mock
def test_値域を超えた補正後スコアがそのままタグになる() -> None:
    """SPEC-004 §4: `score-11` / `score--1` もそのまま出す。"""
    route = respx.post(API_URL).mock(return_value=ok_response())
    ingestor().ingest_all([candidate(score=10, weight=1)])
    assert "score-11" in bodies(route)[0]["tags"]  # type: ignore[operator]


# --- T-002 / T-003 / T-004 / T-005: タグ集合の構築 --------------------------


def test_auto_とスコア帯タグが付与される() -> None:
    """T-002: `#auto` を落とすか `score-` を固定文字列にすればレッド。"""
    tags = build_tags(candidate(score=8))
    assert "auto" in tags
    assert "score-8" in tags


def test_スコアタグは補正後スコアを用いる() -> None:
    """OQ-001 の決定: タグだけで投入判定（n >= 閾値）を再現できるようにする。"""
    tags = build_tags(candidate(score=4, weight=1))
    assert "score-5" in tags
    assert "score-4" not in tags


def test_情報源タグが付与される() -> None:
    """T-003: `source_tags` を捨てればレッド。"""
    assert "aws" in build_tags(candidate(source_tags=("aws",)))


def test_提案タグが付与される() -> None:
    """T-004: `suggested_tags` を捨てればレッド。"""
    assert "llm" in build_tags(candidate(suggested_tags=("llm",)))


@pytest.mark.parametrize(("score", "present"), [(7, True), (6, False)])
def test_高評価帯の境界で_hot_が付く(score: int, present: bool) -> None:
    """T-005: `is_hot` を `>` にすれば 7 で落ち、閾値 5 を使えば 6 でも付いてレッド。"""
    assert ("hot" in build_tags(candidate(score=score))) is present


def test_タグの重複が除去される() -> None:
    """T-030: 単純な連結にすれば同一タグが2回現れてレッド。"""
    tags = build_tags(candidate(source_tags=("aws",), suggested_tags=("AWS", "aws")))
    assert [tag.lower() for tag in tags].count("aws") == 1


def test_タグの先頭の記号が除去される() -> None:
    """OQ-004 の決定: Raindrop の `tags` はプレフィックスなしの文字列配列。

    `#` を残すと `#auto` による撤退（OQ-006）が機能しない。
    """
    tags = build_tags(candidate(source_tags=("#aws",)))
    assert "aws" in tags
    assert not any(tag.startswith("#") for tag in tags)


def test_空白のみのタグは捨てられる() -> None:
    """§5: 前後の空白を除去し、空文字になった要素を捨てる。"""
    tags = build_tags(candidate(source_tags=("  ", "", " aws ")))
    assert "aws" in tags
    assert "" not in tags


def test_長すぎるタグは切り詰められる() -> None:
    """§5: 実上限が未確認のため自主値で保守的に抑える（OQ-004）。"""
    tags = build_tags(candidate(source_tags=("a" * 100,)))
    assert all(len(tag) <= MAX_TAG_CHARS for tag in tags)


def test_タグ件数の上限を超える分は優先順に採られる() -> None:
    """§5: `auto` → `score-{n}` → `hot` → 情報源タグ → 提案タグ の順。

    **上限を超える情報源タグを与えて、先頭3つが残り末尾が捨てられることを見る。**
    優先順を無視して末尾から採ると、撤退の起点である `auto`（要件定義 §7）と
    `score-{n}` が落ちる。件数だけを見る検証では、この取り違えを検出できない。
    """
    overflow = tuple(f"s{i}" for i in range(MAX_TAGS + 10))
    tags = build_tags(candidate(score=8, source_tags=overflow))

    assert len(tags) == MAX_TAGS
    assert tags[:3] == ["auto", "score-8", "hot"], "優先度の高いタグが落ちている"
    assert "s0" in tags, "情報源タグの先頭は残る"
    assert overflow[-1] not in tags, "超過分は末尾から捨てる"


def test_提案タグより情報源タグが優先される() -> None:
    """§5: 上限に達したとき、後段の提案タグから捨てる。"""
    tags = build_tags(
        candidate(
            source_tags=tuple(f"s{i}" for i in range(MAX_TAGS)),
            suggested_tags=("proposed",),
        )
    )
    assert "proposed" not in tags


def test_提案タグが空でも投入できる() -> None:
    """T-016: 空配列で早期リターン・例外を投げればレッド。"""
    assert "auto" in build_tags(candidate(suggested_tags=()))


def test_情報源タグが無くても投入できる() -> None:
    """T-017: 欠落を None のまま結合すれば TypeError でレッド。"""
    assert "auto" in build_tags(candidate(source_tags=()))


# --- T-007 / T-027: 要求の形 -------------------------------------------------


@respx.mock
def test_要求本体と認証ヘッダが仕様どおりであること() -> None:
    """T-007: ヘッダ名を `Token` にする・`collection` を送らなければレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    ingestor().ingest_all([candidate(title="タイトル", summary="要約本文")])

    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Content-Type"] == "application/json"

    body = bodies(route)[0]
    assert body["link"] == "https://example.com/a"
    assert body["title"] == "タイトル"
    assert body["excerpt"] == "要約本文"
    assert body["collection"] == {"$id": COLLECTION_ID}
    assert body["pleaseParse"] == {}
    assert isinstance(body["tags"], list)


def test_エンドポイントが_HTTPS_であること() -> None:
    """T-027: `http://` にすればレッド。証明書検証も無効化しない。"""
    assert API_URL.startswith("https://")


def test_証明書検証を無効化しないこと(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-027: `verify=False` を渡せばレッド。

    httpx は `verify` を SSL コンテキストへ畳み込むため、構築後の Client からは
    値を復元できない。**構築時の引数を捕捉して**検証する。
    """
    captured: dict[str, object] = {}
    original = httpx.Client

    def spy(**kwargs: object) -> httpx.Client:
        captured.update(kwargs)
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", spy)
    ingestor()

    assert captured.get("verify", True) is True


# --- T-021 / T-031: 送信前の整形 ---------------------------------------------


@respx.mock
def test_タイトルが上限を超えるとき切り詰められる() -> None:
    """T-021: 切り詰めを外せば送信本体の長さ検証でレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    ingestor().ingest_all([candidate(title="あ" * (TITLE_MAX_CHARS + 500))])

    title = bodies(route)[0]["title"]
    assert isinstance(title, str)
    assert len(title) == TITLE_MAX_CHARS


@respx.mock
def test_要約が空でも投入され_excerpt_を空文字で送る() -> None:
    """T-031: 要約を必須とすれば、全文配信でないフィードが全件投入されずレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    result = ingestor().ingest_all([candidate(summary="")])

    assert result.ingested == 1
    assert bodies(route)[0]["excerpt"] == ""


@respx.mock
def test_タイトルが空でも投入され_title_を空文字で送る() -> None:
    """§4: Raindrop 側が `link` から補完する（`pleaseParse`）。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    result = ingestor().ingest_all([candidate(title="")])

    assert result.ingested == 1
    assert bodies(route)[0]["title"] == ""


@respx.mock
@pytest.mark.parametrize("url", ["", "   ", "ftp://example.com/a", "javascript:alert(1)"])
def test_投入できない_URL_は要求を発行せず失敗として記録する(url: str) -> None:
    """§5: `link` は Raindrop の必須項目。空・非 http(s) は送信しない。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    result = ingestor().ingest_all([candidate(url=url)])

    assert route.call_count == 0
    assert result.failures == 1
    assert result.failure_reasons == {FailureReason.INVALID_LINK.value: 1}


# --- T-008 / T-009 / T-012 / T-013: 個別の失敗 -------------------------------


@respx.mock
def test_1件の失敗が他の投入を止めない() -> None:
    """T-008: 例外を捕捉せず伝播させれば2件目が実行されずレッド。"""
    route = respx.post(API_URL).mock(
        side_effect=[httpx.Response(500), ok_response(), ok_response()]
    )

    result = ingestor().ingest_all(
        [
            candidate("https://example.com/1"),
            candidate("https://example.com/2"),
            candidate("https://example.com/3"),
        ]
    )

    assert route.call_count == 3
    assert result.ingested == 2
    assert result.failures == 1
    assert result.failure_reasons == {FailureReason.SERVER_ERROR.value: 1}


@respx.mock
def test_レート制限は他の失敗と区別される() -> None:
    """T-009: ステータスを見ず一律 `server_error` を返せば両者が同値になりレッド。"""
    route = respx.post(API_URL).mock(side_effect=[httpx.Response(429), httpx.Response(500)])

    result = ingestor().ingest_all(
        [candidate("https://example.com/1"), candidate("https://example.com/2")]
    )

    assert route.call_count == 2
    assert result.failure_reasons == {
        FailureReason.RATE_LIMITED.value: 1,
        FailureReason.SERVER_ERROR.value: 1,
    }


@respx.mock
def test_レート制限ではリトライしない() -> None:
    """フロー #10 / OQ-002: 本仕様ではリトライしない。"""
    route = respx.post(API_URL).mock(return_value=httpx.Response(429))
    ingestor().ingest_all([candidate()])
    assert route.call_count == 1


@respx.mock
@pytest.mark.parametrize("status", [400, 404, 409])
def test_4xx_は当該エントリのみ失敗として次へ進む(status: int) -> None:
    """フロー #12: 同じ要求は再送しても通らないためリトライしない。"""
    route = respx.post(API_URL).mock(side_effect=[httpx.Response(status), ok_response()])

    result = ingestor().ingest_all(
        [candidate("https://example.com/1"), candidate("https://example.com/2")]
    )

    assert route.call_count == 2
    assert result.ingested == 1
    assert result.failure_reasons == {FailureReason.CLIENT_ERROR.value: 1}


@respx.mock
def test_ネットワーク障害は当該エントリのみ失敗として次へ進む() -> None:
    """フロー #13: 5xx と同じ扱い。"""
    route = respx.post(API_URL).mock(
        side_effect=[httpx.ConnectError("boom"), ok_response()]
    )

    result = ingestor().ingest_all(
        [candidate("https://example.com/1"), candidate("https://example.com/2")]
    )

    assert route.call_count == 2
    assert result.ingested == 1
    assert result.failure_reasons == {FailureReason.SERVER_ERROR.value: 1}


@respx.mock
def test_タイムアウトは当該エントリのみ失敗として次へ進む() -> None:
    """T-012: タイムアウトを設定せず無期限に待てばテストがハングしてレッド。"""
    route = respx.post(API_URL).mock(
        side_effect=[httpx.TimeoutException("timeout"), ok_response()]
    )

    result = ingestor().ingest_all(
        [candidate("https://example.com/1"), candidate("https://example.com/2")]
    )

    assert route.call_count == 2
    assert result.ingested == 1
    assert result.failure_reasons == {FailureReason.TIMEOUT.value: 1}


@respx.mock
def test_一部だけ失敗したときは全件失敗としない() -> None:
    """T-013: 「1件でも失敗したら非0」にすればレッド（AC-014 は**全件**失敗が条件）。"""
    respx.post(API_URL).mock(side_effect=[httpx.Response(500), ok_response()])

    result = ingestor().ingest_all(
        [candidate("https://example.com/1"), candidate("https://example.com/2")]
    )

    assert result.all_failed is False


@respx.mock
def test_試行した全件が失敗したら全件失敗とする() -> None:
    """T-011: 失敗件数を数えず常に OK を返せばレッド（→ INGEST_ALL_FAILED）。"""
    respx.post(API_URL).mock(return_value=httpx.Response(500))

    result = ingestor().ingest_all(
        [candidate("https://example.com/1"), candidate("https://example.com/2")]
    )

    assert result.attempted == 2
    assert result.ingested == 0
    assert result.all_failed is True


# --- T-010: 401 / 403 による打ち切り -----------------------------------------


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
def test_認証失敗なら残りの投入対象へ要求を発行しない(status: int) -> None:
    """T-010: 他の 4xx と同じ「次へ進む」扱いにすれば後続へ要求が飛びレッド。"""
    route = respx.post(API_URL).mock(return_value=httpx.Response(status))

    result = ingestor().ingest_all(
        [
            candidate("https://example.com/1"),
            candidate("https://example.com/2"),
            candidate("https://example.com/3"),
        ]
    )

    assert route.call_count == 1, "打ち切り後も要求を発行している"
    assert result.attempted == 1
    assert result.failure_reasons == {FailureReason.UNAUTHORIZED.value: 1}


@respx.mock
def test_打ち切られた未試行分は未試行として返る() -> None:
    """フロー #11 / §4: 未試行分は成功にも失敗にも数えない。

    状態に記録すると処理済み扱いとなり、認証失効1回でその週の投入対象が
    恒久的に失われる（R-001 違反）。
    """
    respx.post(API_URL).mock(return_value=httpx.Response(401))

    result = ingestor().ingest_all(
        [
            candidate("https://example.com/1"),
            candidate("https://example.com/2"),
            candidate("https://example.com/3"),
        ]
    )

    assert result.unattempted == 2
    assert result.failures == 1
    assert [c.entry.url for c in result.unattempted_candidates] == [
        "https://example.com/2",
        "https://example.com/3",
    ]


@respx.mock
def test_未試行分は全件失敗の分母に含めない() -> None:
    """フロー #15: 打ち切りにより未試行となったエントリは分母に含めない。

    **1件成功したあとに 401 で打ち切られた状況で検証する。** 先頭で 401 に
    なる例だと `ingested == 0` が両方の実装で成り立ち、分母の違いが
    結果に現れない（`attempted` を使うか `attempted + unattempted` を
    使うかを区別できない）。
    """
    respx.post(API_URL).mock(side_effect=[ok_response(), httpx.Response(401)])

    result = ingestor().ingest_all(
        [
            candidate("https://example.com/1"),
            candidate("https://example.com/2"),
            candidate("https://example.com/3"),
            candidate("https://example.com/4"),
        ]
    )

    assert (result.attempted, result.ingested, result.unattempted) == (2, 1, 2)
    assert result.all_failed is False


@respx.mock
def test_未試行が生じるのは必ず1件以上試行したあとである() -> None:
    """打ち切りは POST の応答を見て初めて起きるため `attempted >= 1` が保たれる。

    この不変条件があるので `all_failed` の分母に未試行を含めるか否かは
    結果を変えない。**将来「送信前に打ち切る」経路を足すと崩れる**ため、
    分母の定義（フロー #15）を守る番人としてここで固定しておく。
    """
    respx.post(API_URL).mock(return_value=httpx.Response(401))

    result = ingestor().ingest_all(
        [candidate("https://example.com/1"), candidate("https://example.com/2")]
    )

    assert result.unattempted > 0
    assert result.attempted >= 1


@respx.mock
def test_打ち切り前に成功が1件もなければ全件失敗とする() -> None:
    """分母から未試行を除いても、試行分が全滅していれば全件失敗である。"""
    respx.post(API_URL).mock(side_effect=[httpx.Response(500), httpx.Response(401)])

    result = ingestor().ingest_all(
        [
            candidate("https://example.com/1"),
            candidate("https://example.com/2"),
            candidate("https://example.com/3"),
        ]
    )

    assert (result.attempted, result.unattempted) == (2, 1)
    assert result.all_failed is True


# --- T-028: レート制御 -------------------------------------------------------


@respx.mock
def test_投入の間隔が1秒以上空く() -> None:
    """T-028: 待機を外す・並列化すれば間隔が 0 に近づきレッド。"""
    respx.post(API_URL).mock(return_value=ok_response())
    slept: list[float] = []

    Ingestor(
        token=TOKEN, collection_id=COLLECTION_ID, sleep=slept.append
    ).ingest_all(
        [
            candidate("https://example.com/1"),
            candidate("https://example.com/2"),
            candidate("https://example.com/3"),
        ]
    )

    assert len(slept) == 2, "2件目以降の直前にのみ待機する"
    assert all(seconds > 0 for seconds in slept)
    assert all(seconds <= MIN_INTERVAL_SECONDS for seconds in slept)


@respx.mock
def test_1件目の投入前には待機しない() -> None:
    """先頭で待つと週次バッチの所要時間が無駄に伸びる。"""
    respx.post(API_URL).mock(return_value=ok_response())
    slept: list[float] = []

    Ingestor(token=TOKEN, collection_id=COLLECTION_ID, sleep=slept.append).ingest_all(
        [candidate()]
    )

    assert slept == []


@respx.mock
def test_経過時間が1秒を超えていれば待機しない() -> None:
    """§7: 直前の要求の開始時刻から1秒が経過するまで待つ（差分だけ）。"""
    respx.post(API_URL).mock(return_value=ok_response())
    slept: list[float] = []
    clock = iter([0.0, 10.0, 20.0, 30.0])

    Ingestor(
        token=TOKEN,
        collection_id=COLLECTION_ID,
        sleep=slept.append,
        monotonic=lambda: next(clock),
    ).ingest_all([candidate("https://example.com/1"), candidate("https://example.com/2")])

    assert slept == []


# --- dry-run（T-029） --------------------------------------------------------


@respx.mock
def test_dry_run_では_HTTP_クライアントが呼ばれない() -> None:
    """T-029 / F-005 AC-001: dry-run 分岐を削除すれば要求が発生してレッド。"""
    route = respx.post(API_URL).mock(return_value=ok_response())

    result = Ingestor(token=None, collection_id=None, dry_run=True).ingest_all(
        [candidate(score=8), candidate(score=1)]
    )

    assert route.call_count == 0
    assert result.attempted == 0


@respx.mock
def test_dry_run_では投入対象件数を返す() -> None:
    """F-005 AC-003 / §4: dry-run のときのみ `ingested` に対象件数を詰める。"""
    respx.post(API_URL).mock(return_value=ok_response())

    result = Ingestor(token=None, collection_id=None, dry_run=True).ingest_all(
        [candidate("https://example.com/1", score=8), candidate("https://example.com/2", score=1)]
    )

    assert result.ingested == 1, "投入対象と判定された件数"
    assert result.failures == 0


@respx.mock
def test_dry_run_では全件失敗にならない() -> None:
    """POST を行わない以上、全件失敗はありえない。"""
    result = Ingestor(token=None, collection_id=None, dry_run=True).ingest_all([candidate()])
    assert result.all_failed is False


@respx.mock
def test_dry_run_でも明細が返る() -> None:
    """F-005 AC-002 / SPEC-006 §4: 明細行の供給元。"""
    result = Ingestor(token=None, collection_id=None, dry_run=True).ingest_all(
        [
            candidate("https://example.com/1", score=8, title="採用"),
            candidate("https://example.com/2", score=1, title="不採用"),
        ]
    )

    assert [(v.url, v.final_score, v.will_ingest) for v in result.entries] == [
        ("https://example.com/1", 8, True),
        ("https://example.com/2", 1, False),
    ]


# --- T-025 / T-026: セキュリティ ---------------------------------------------


@respx.mock
def test_失敗のメッセージにトークンが含まれない() -> None:
    """T-025: 捕捉した例外を `str(e)` で出力すれば要求ヘッダごと露出してレッド。"""
    respx.post(API_URL).mock(return_value=httpx.Response(401))

    result = ingestor().ingest_all([candidate()])

    assert TOKEN not in "".join(result.messages)
    assert TOKEN not in "".join(result.failure_reasons)


@respx.mock
def test_失敗のメッセージにコレクション_ID_が含まれない() -> None:
    """T-026: 「コレクション {id} への投入に失敗」と埋め込めばレッド。"""
    respx.post(API_URL).mock(return_value=httpx.Response(500))

    result = ingestor().ingest_all([candidate()])

    assert str(COLLECTION_ID) not in "".join(result.messages)


@respx.mock
def test_ネットワーク例外の全文をメッセージに含めない() -> None:
    """REQ-NF-006 / §7: httpx の例外は要求 URL・ヘッダを引用しうる。"""
    respx.post(API_URL).mock(side_effect=httpx.ConnectError(f"failed to {API_URL}?t={TOKEN}"))

    result = ingestor().ingest_all([candidate()])

    assert TOKEN not in "".join(result.messages)


# --- 冪等性（§7） ------------------------------------------------------------


@respx.mock
def test_同一_URL_を2回渡されれば2回投入する() -> None:
    """§7: POST は冪等でない。重複を防ぐのは SPEC-002 の突合であり本仕様ではない。

    ここで自前の重複排除を足すと、責務が二重化して SPEC-002 の突合が
    効いているかを検証できなくなる。
    """
    route = respx.post(API_URL).mock(return_value=ok_response())

    ingestor().ingest_all([candidate(), candidate()])

    assert route.call_count == 2


@respx.mock
def test_Raindrop_上の既存記事を重複として扱わない() -> None:
    """フロー #16: 収集レイヤー側の内容は判定に用いない（ADR-002 選択肢 D の不採用）。"""
    route = respx.post(API_URL).mock(return_value=ok_response())
    ingestor().ingest_all([candidate()])
    assert route.call_count == 1, "投入前に既存チェックの GET を発行してはならない"
