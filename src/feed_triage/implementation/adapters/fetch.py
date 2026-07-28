"""フィード取得とエントリ抽出（SPEC-001）。

取得は `httpx`、パースは `feedparser` に**バイト列を渡す**。
`feedparser.parse(url)` の URL モードは使わない — 未修正の SSRF・メモリ枯渇の
issue があるため（ADR-004 補遺B）。

1情報源の失敗は他を止めない（REQ-F-010 / F-001 AC-011）。例外を呼び出し元へ
伝播させず、必ず `SourceOutcome` に落とす。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import feedparser
import httpx

from feed_triage.contract.model import Entry, Source, SourceOutcome

TIMEOUT_SECONDS = 30.0
"""1情報源あたりの取得タイムアウト（REQ-NF-001）。

13情報源すべてがタイムアウトしても6.5分であり、実行全体の30分に収まる。
"""

MAX_RESPONSE_BYTES = 10 * 1024 * 1024
"""レスポンスサイズの上限（TASK-062 / SPEC-001 §7）。

実測の最大フィード（全文配信 9,238 字 ≒ 数十 KB）の3桁上。誤って正常なフィードを
落とす確率を実質ゼロにしつつ、メモリ枯渇の緩和として機能する。逐次処理のため
実際に同時に載るのは1情報源分のみ。
"""

MAX_REDIRECTS = 3
"""リダイレクト追従の上限（TASK-071 / SPEC-001 §7）。

正当な移転（旧ドメイン → 新ドメイン → 正規化 URL）を追従でき、かつ
無限ループを塞ぐ値。`https` → `http` のダウングレードは回数に関わらず拒否する。
"""


def fetch_all(sources: list[Source]) -> tuple[list[Entry], list[SourceOutcome]]:
    """全情報源を**定義順に逐次**取得し、エントリ列と情報源別の結果を返す。

    エントリの順序は「情報源の定義順 × フィード内の掲載順」（SPEC-001 §4 の取得順）。
    この順序が、評価件数の上限に達したときにどの記事が持ち越されるかを決めるため、
    並べ替えてはならない。

    **定義された全情報源が、成功・失敗・0件のいずれでも 1 要素として現れる。**
    定義0件なら空リストを返し、全件失敗なら全要素の `error` が非 null になる。
    下流はこの差で両者を区別する（F-004 AC-014 / AC-023）。
    """
    entries: list[Entry] = []
    outcomes: list[SourceOutcome] = []

    with httpx.Client(
        timeout=TIMEOUT_SECONDS,
        # 追従は自前で行う。httpx に任せるとダウングレード先へ要求が飛んでから
        # でないと検知できず、平文で送信済みになる（→ _get）
        follow_redirects=False,
        headers={
            "User-Agent": "feed-triage/0.1 (+https://github.com/TakuyaInoue-github/rain-drop-feed)"
        },
    ) as client:
        for source in sources:
            try:
                payload = _get(client, source.url)
            except FetchError as exc:
                outcomes.append(SourceOutcome(source.name, error=str(exc)))
                continue

            extracted = _extract(payload, source.name)
            if extracted is None:
                outcomes.append(SourceOutcome(source.name, error="フィードを解釈できません"))
                continue

            entries.extend(extracted)
            outcomes.append(SourceOutcome(source.name, fetched=len(extracted)))

    return entries, outcomes


class FetchError(Exception):
    """1情報源の取得失敗。**メッセージはサマリへ出るため秘匿値を含めない。**"""


def _get(client: httpx.Client, url: str) -> bytes:
    """1件の GET。リダイレクトを自前で追従し、本文を上限まで読む。"""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _require_https(current)
        try:
            with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("Location", "")
                    if not location:
                        raise FetchError("リダイレクト先が示されていません")
                    current = str(httpx.URL(current).join(location))
                    continue
                if response.status_code != httpx.codes.OK:
                    raise FetchError(f"HTTP {response.status_code}")
                return _read_limited(response)
        except httpx.TimeoutException:
            raise FetchError(f"取得がタイムアウトしました（{TIMEOUT_SECONDS:.0f}秒）") from None
        except httpx.HTTPError as exc:
            # 例外の全文は URL のクエリ（トークンを含みうる）を引用するため種別のみ
            raise FetchError(f"接続できません（{type(exc).__name__}）") from None

    raise FetchError(f"リダイレクトが上限（{MAX_REDIRECTS}回）を超えました")


def _require_https(url: str) -> None:
    """https 以外への要求を**送る前に**弾く（REQ-NF-006 / TASK-071）。

    追従後に検査すると平文で1回送信済みになるため、必ず送信前に判定する。
    """
    if urlsplit(url).scheme != "https":
        raise FetchError("https 以外の宛先には接続しません")


def _read_limited(response: httpx.Response) -> bytes:
    """上限までチャンクを読み、超過したら接続を切って失敗にする。

    `Content-Length` のみに依拠しない（チャンク転送では存在しないため）。
    **部分的に受信したバイト列はパースしない** — 途中で切れた XML から
    不完全なエントリを作らないため（SPEC-001 フロー #15）。
    """
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise FetchError(f"応答が上限（{MAX_RESPONSE_BYTES // (1024 * 1024)} MB）を超えました")
        chunks.append(chunk)
    return b"".join(chunks)


def _extract(payload: bytes, source_name: str) -> list[Entry] | None:
    """バイト列をパースしてエントリ列を返す。パース不能なら None。

    `bozo` が立っていてもエントリが1件以上得られれば成功として扱う
    （実在のフィードは軽微な不正を含むことが多いため → SPEC-001 §5）。
    """
    parsed = feedparser.parse(payload)

    # `version` が空文字なら RSS/Atom として認識できていない（HTML エラーページ等）。
    # bozo では判別できない — HTML を渡しても bozo は立たず、feed 属性も生える。
    # 一方、正常な空フィードは version が 'rss20' 等になる。
    if not getattr(parsed, "version", ""):
        return None

    items = getattr(parsed, "entries", [])
    if not items:
        # エントリ0件のフィードは「成功・0件」（失敗と区別する → F-004 AC-022）
        return []

    entries: list[Entry] = []
    for raw in items:
        url = _clean(raw.get("link"))
        if not _is_fetchable(url):
            # URL は一意性のキー（REQ-F-002）。欠くと重複排除が成立しないため
            # 当該エントリのみ落とし、同一フィードの他は残す（フロー #17）
            continue
        entries.append(
            Entry(
                url=url,
                title=_clean(raw.get("title")),
                summary=_summary_of(raw),
                published_at=_published_at(raw),
                source_name=source_name,
            )
        )
    return entries


def _is_fetchable(url: str) -> bool:
    return bool(url) and urlsplit(url).scheme in ("http", "https")


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _summary_of(raw: object) -> str:
    """要約を取り出す。名称の差（summary / description / content）は feedparser が吸収する。

    空でもエントリを落とさない（F-001 AC-023。タイトルのみで評価する）。
    """
    assert isinstance(raw, dict)
    for key in ("summary", "description"):
        text = _clean(raw.get(key))
        if text:
            return text
    content = raw.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return _clean(first.get("value"))
    return ""


def _published_at(raw: object) -> datetime | None:
    """公開日時を UTC の datetime へ。欠落・解釈不能は None。

    **None を最古の日時で代用しない** — 「日時がない」と「非常に古い」は
    別の事実であり、代用すると区別が失われる（F-001 AC-026）。
    """
    assert isinstance(raw, dict)
    for key in ("published_parsed", "updated_parsed"):
        parsed = raw.get(key)
        if parsed is None:
            continue
        try:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    return None
