"""フィード取得・エントリ抽出のテスト（SPEC-001）。

観点番号（T-xxx）は SPEC-001 §10 の表に対応させる。
HTTP は respx でモックし、実ネットワークへは出ない。
"""

from __future__ import annotations

import httpx
import pytest
import respx

from feed_triage.contract.model import Source
from feed_triage.implementation.adapters.fetch import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    fetch_all,
)

FEED_URL = "https://example.com/feed.xml"


def rss(*items: str, title: str = "Example Blog") -> bytes:
    body = "".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<rss version="2.0"><channel><title>{title}</title>{body}</channel></rss>'
    ).encode()


def item(
    link: str = "https://example.com/a",
    title: str = "A",
    description: str = "本文の要約",
    pub_date: str | None = "Mon, 27 Jul 2026 09:00:00 +0000",
) -> str:
    date = f"<pubDate>{pub_date}</pubDate>" if pub_date else ""
    return f"<item><title>{title}</title><link>{link}</link><description>{description}</description>{date}</item>"


def source(name: str = "example", url: str = FEED_URL, weight: int = 0) -> Source:
    return Source(name=name, url=url, weight=weight, tags=("t",))


# --- T-001 / T-004: 抽出 -----------------------------------------------------


@respx.mock
def test_エントリの各項目が抽出される() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=rss(item())))
    entries, outcomes = fetch_all([source()])

    assert len(entries) == 1
    entry = entries[0]
    assert entry.url == "https://example.com/a"
    assert entry.title == "A"
    assert "本文の要約" in entry.summary
    assert entry.published_at is not None
    assert outcomes[0].fetched == 1
    assert outcomes[0].error is None


@respx.mock
def test_source_name_はフィード側のタイトルではなく定義名を使う() -> None:
    """T-001: feeds.yaml の name が情報源別集計のキー（F-004 AC-003）。"""
    respx.get(FEED_URL).mock(
        return_value=httpx.Response(200, content=rss(item(), title="全然ちがう名前"))
    )
    entries, _ = fetch_all([source(name="my-source")])
    assert entries[0].source_name == "my-source"


# --- T-002 / T-003: 順序 -----------------------------------------------------


@respx.mock
def test_フィード内は掲載順を保持する() -> None:
    """T-003: 公開日時で並べ替えない（SPEC-001 §4）。"""
    feed = rss(
        item(link="https://example.com/1", pub_date="Mon, 20 Jul 2026 00:00:00 +0000"),
        item(link="https://example.com/2", pub_date="Mon, 27 Jul 2026 00:00:00 +0000"),
        item(link="https://example.com/3", pub_date="Mon, 13 Jul 2026 00:00:00 +0000"),
    )
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=feed))
    entries, _ = fetch_all([source()])
    assert [e.url[-1] for e in entries] == ["1", "2", "3"]


@respx.mock
def test_情報源は定義順に連結される() -> None:
    """T-002: 第一キーは feeds.yaml の記載順（取得の完了順ではない）。"""
    respx.get("https://a.example/feed").mock(
        return_value=httpx.Response(200, content=rss(item(link="https://a.example/x")))
    )
    respx.get("https://b.example/feed").mock(
        return_value=httpx.Response(200, content=rss(item(link="https://b.example/y")))
    )
    entries, outcomes = fetch_all(
        [
            source(name="a", url="https://a.example/feed"),
            source(name="b", url="https://b.example/feed"),
        ]
    )
    assert [e.source_name for e in entries] == ["a", "b"]
    assert [o.source_name for o in outcomes] == ["a", "b"]


# --- T-008 / T-010: 部分障害の分離 -------------------------------------------


@respx.mock
def test_1情報源が失敗しても他の情報源は継続する() -> None:
    """T-008 / F-001 AC-011。1件の障害で週次バッチを止めない。"""
    respx.get("https://ng.example/feed").mock(return_value=httpx.Response(404))
    respx.get("https://ok.example/feed").mock(
        return_value=httpx.Response(200, content=rss(item(link="https://ok.example/x")))
    )
    entries, outcomes = fetch_all(
        [
            source(name="ng", url="https://ng.example/feed"),
            source(name="ok", url="https://ok.example/feed"),
        ]
    )
    assert len(entries) == 1
    assert outcomes[0].error is not None and "404" in outcomes[0].error
    assert outcomes[1].error is None


@respx.mock
def test_接続エラーでも他の情報源は継続する() -> None:
    respx.get("https://ng.example/feed").mock(side_effect=httpx.ConnectError("boom"))
    respx.get("https://ok.example/feed").mock(return_value=httpx.Response(200, content=rss(item())))
    entries, outcomes = fetch_all(
        [
            source(name="ng", url="https://ng.example/feed"),
            source(name="ok", url="https://ok.example/feed"),
        ]
    )
    assert len(entries) == 1
    assert outcomes[0].error is not None


@respx.mock
def test_タイムアウトは失敗として記録し継続する() -> None:
    """T-009 / F-001 AC-013。"""
    respx.get(FEED_URL).mock(side_effect=httpx.ReadTimeout("timeout"))
    entries, outcomes = fetch_all([source()])
    assert entries == []
    assert outcomes[0].error is not None and "タイムアウト" in outcomes[0].error


@respx.mock
def test_パース不能なバイト列は取得失敗として扱う() -> None:
    """T-011: HTML エラーページ等（SPEC-001 フロー #16）。"""
    respx.get(FEED_URL).mock(
        return_value=httpx.Response(200, content=b"<html><body>404</body></html>")
    )
    entries, outcomes = fetch_all([source()])
    assert entries == []
    assert outcomes[0].error is not None


# --- T-013 / T-014: 境界値 ---------------------------------------------------


@respx.mock
def test_エントリ0件は失敗ではなく成功0件() -> None:
    """T-013 / F-004 AC-022。行が省略されると供給停止に気づけない。"""
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=rss()))
    entries, outcomes = fetch_all([source()])
    assert entries == []
    assert outcomes[0].fetched == 0
    assert outcomes[0].error is None


def test_情報源の定義が0件なら空リストを返す() -> None:
    """T-014 / F-001 AC-024。全件失敗（全要素が error 非 null）と区別する。"""
    entries, outcomes = fetch_all([])
    assert entries == []
    assert outcomes == []


# --- T-015 / T-016 / T-017: 欠落項目 -----------------------------------------


@respx.mock
def test_要約が空でもエントリを残す() -> None:
    """T-015 / F-001 AC-023。タイトルのみで評価する。"""
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=rss(item(description=""))))
    entries, _ = fetch_all([source()])
    assert len(entries) == 1
    assert entries[0].summary == ""


@respx.mock
def test_公開日時が欠落してもエントリを残す() -> None:
    """T-016 / F-001 AC-026。None を最古の日時で代用しない。"""
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=rss(item(pub_date=None))))
    entries, _ = fetch_all([source()])
    assert len(entries) == 1
    assert entries[0].published_at is None


@respx.mock
def test_タイトルが空でもエントリを残す() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=rss(item(title=""))))
    entries, _ = fetch_all([source()])
    assert len(entries) == 1
    assert entries[0].title == ""


@respx.mock
def test_URL_を欠くエントリのみ除外し同一フィードの他は残す() -> None:
    """T-017: URL は一意性のキー。欠くと重複排除が成立しない。"""
    feed = rss(item(link=""), item(link="https://example.com/ok"))
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=feed))
    entries, outcomes = fetch_all([source()])
    assert [e.url for e in entries] == ["https://example.com/ok"]
    assert outcomes[0].error is None


@respx.mock
def test_http_https_以外のスキームのエントリは除外する() -> None:
    """SSRF の足がかりを作らない（SPEC-001 §5）。"""
    feed = rss(item(link="javascript:alert(1)"), item(link="https://example.com/ok"))
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=feed))
    entries, _ = fetch_all([source()])
    assert [e.url for e in entries] == ["https://example.com/ok"]


# --- T-020 / T-021: 一意化しない ---------------------------------------------


@respx.mock
def test_同一フィード内の重複_URL_を一意化しない() -> None:
    """T-020: 一意化は SPEC-002 の責務。ここで落とすと state に残らない。"""
    feed = rss(item(link="https://example.com/dup"), item(link="https://example.com/dup"))
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=feed))
    entries, _ = fetch_all([source()])
    assert len(entries) == 2


@respx.mock
def test_情報源をまたぐ重複_URL_も一意化しない() -> None:
    """T-021: どちらの情報源由来かを保ったまま SPEC-002 へ渡す。"""
    for host in ("a", "b"):
        respx.get(f"https://{host}.example/feed").mock(
            return_value=httpx.Response(200, content=rss(item(link="https://same.example/x")))
        )
    entries, _ = fetch_all(
        [
            source(name="a", url="https://a.example/feed"),
            source(name="b", url="https://b.example/feed"),
        ]
    )
    assert [e.source_name for e in entries] == ["a", "b"]


# --- T-018 / T-019: サイズ上限（10 MB） --------------------------------------


def test_サイズ上限は10MB() -> None:
    """TASK-062。実測の3桁上で誤検知を実質ゼロにする。"""
    assert MAX_RESPONSE_BYTES == 10 * 1024 * 1024


@respx.mock
def test_上限ちょうどなら取得に成功する() -> None:
    """T-018: 比較演算子を1つずらすと落ちる。"""
    body = rss(item())
    padding = b"<!--" + b"x" * (MAX_RESPONSE_BYTES - len(body) - 7) + b"-->"
    payload = body.replace(b"</channel>", padding + b"</channel>")
    assert len(payload) == MAX_RESPONSE_BYTES
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=payload))
    _, outcomes = fetch_all([source()])
    assert outcomes[0].error is None


@respx.mock
def test_上限超過は打ち切り部分データをパースしない() -> None:
    """T-019: 途中で切れた XML から不完全なエントリを作らない。"""
    payload = rss(item()) + b"<!--" + b"x" * MAX_RESPONSE_BYTES + b"-->"
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=payload))
    entries, outcomes = fetch_all([source()])
    assert entries == []
    assert outcomes[0].error is not None and "上限" in outcomes[0].error


# --- T-018a / T-018b: リダイレクト（TASK-071） -------------------------------


def test_リダイレクト上限は3回() -> None:
    assert MAX_REDIRECTS == 3


@respx.mock
def test_https間のリダイレクトは追従する() -> None:
    respx.get(FEED_URL).mock(
        return_value=httpx.Response(301, headers={"Location": "https://example.com/new"})
    )
    respx.get("https://example.com/new").mock(return_value=httpx.Response(200, content=rss(item())))
    entries, outcomes = fetch_all([source()])
    assert len(entries) == 1
    assert outcomes[0].error is None


@respx.mock
def test_https_から_http_へのダウングレードを拒否する() -> None:
    """T-018a: ダウングレード先へ要求を送らない（REQ-NF-006）。"""
    respx.get(FEED_URL).mock(
        return_value=httpx.Response(301, headers={"Location": "http://example.com/plain"})
    )
    downgraded = respx.get("http://example.com/plain").mock(
        return_value=httpx.Response(200, content=rss(item()))
    )
    entries, outcomes = fetch_all([source()])

    assert entries == []
    assert outcomes[0].error is not None
    assert not downgraded.called, "平文の宛先へ要求を送ってはならない"


@respx.mock
def test_リダイレクトが上限を超えると取得失敗になる() -> None:
    """T-018b: 無制限だと循環リダイレクトで終わらない。"""
    for i in range(MAX_REDIRECTS + 2):
        respx.get(f"https://example.com/r{i}").mock(
            return_value=httpx.Response(301, headers={"Location": f"https://example.com/r{i + 1}"})
        )
    _, outcomes = fetch_all([source(url="https://example.com/r0")])
    assert outcomes[0].error is not None


# --- セキュリティ ------------------------------------------------------------


@respx.mock
def test_失敗理由に秘匿値が混じらない() -> None:
    """SourceOutcome.error はサマリへ出る（F-004 AC-031 / SPEC-006 OQ-004）。"""
    secret = "token-DO-NOT-LEAK"
    respx.get(FEED_URL).mock(side_effect=httpx.ConnectError(f"failed {secret}"))
    _, outcomes = fetch_all([source(url=f"{FEED_URL}?key={secret}")])
    assert outcomes[0].error is not None
    assert secret not in outcomes[0].error


@pytest.mark.parametrize("scheme", ["http", "ftp", "file"])
def test_https以外の情報源URLは要求を送らず失敗にする(scheme: str) -> None:
    """定義側の URL も https に限る（SPEC-001 §4 入力(a)）。"""
    _, outcomes = fetch_all([source(url=f"{scheme}://example.com/feed")])
    assert outcomes[0].error is not None
