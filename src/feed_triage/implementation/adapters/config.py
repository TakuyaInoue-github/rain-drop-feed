"""設定ファイルの読み込みと構造検証（SPEC-005 §2 / フロー #11・#12）。

`feeds.yaml` と `profile.md` を読み、不備があれば処理本体を開始する前に
`ConfigError` を送出する（F-001 AC-030a）。**空の情報源リストや基準なしへ
フォールバックしない** — 基準なしで評価すると全件のスコアが無意味になり、
空リストで続行すると「取得0件」と「定義されていない」が区別できなくなる。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeGuard

import yaml

from feed_triage.contract.model import Source


class ConfigError(Exception):
    """運用者が是正すべき設定の不備（終了コード `CONFIG_ERROR` → SPEC-005 §5）。

    メッセージは運用者向けの日本語1文とし、**設定ファイルの中身を含めない**
    （秘匿値が書かれていても出力へ漏らさないため → REQ-NF-006）。
    """


def load_sources(path: Path) -> list[Source]:
    """`feeds.yaml` を読み、定義順を保った `Source` の列を返す。

    順序は SPEC-001 §4 の「取得順」の第一キーであり、評価件数の上限に達した
    ときにどの記事が持ち越されるかを決める。並べ替えてはならない。
    """
    raw = _load_yaml(path)
    if not isinstance(raw, dict) or "sources" not in raw:
        raise ConfigError(f"フィード定義を解釈できません: {path} (sources キーがありません)")

    entries = raw["sources"]
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise ConfigError(f"フィード定義を解釈できません: {path} (sources が配列ではありません)")

    sources: list[Source] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        source = _build_source(path, index, entry)
        if source.name in seen:
            raise ConfigError(f"フィード定義に重複した情報源名があります: {source.name}")
        seen.add(source.name)
        sources.append(source)
    return sources


def load_profile(path: Path) -> str:
    """`profile.md`（トリアージ基準）の全文を返す。

    空ファイルは「基準なし」と同義のため読めた扱いにしない（SPEC-003 §2）。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"トリアージ基準が見つかりません: {path}") from None
    except OSError as exc:
        raise ConfigError(f"トリアージ基準を読み込めません: {path} ({exc.strerror})") from None

    if not text.strip():
        raise ConfigError(f"トリアージ基準が空です: {path}")
    return text


def _load_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"フィード定義が見つかりません: {path}") from None
    except OSError as exc:
        raise ConfigError(f"フィード定義を読み込めません: {path} ({exc.strerror})") from None

    try:
        # safe_load: 任意オブジェクトの構築を許さない（設定ファイルは信頼できるが、
        # 誤って full_load を使うと YAML から任意コードを実行しうる）
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        # 例外の全文は設定ファイルの中身を引用しうるため、種別のみを出す
        raise ConfigError(f"フィード定義を解釈できません: {path} ({type(exc).__name__})") from None


def _build_source(path: Path, index: int, entry: object) -> Source:
    if not isinstance(entry, dict):
        raise ConfigError(f"フィード定義の情報源が不正です: {path} sources[{index}]")

    name = entry.get("name")
    url = entry.get("url")
    if not _is_nonempty_str(name) or not _is_nonempty_str(url):
        raise ConfigError(f"フィード定義の情報源に必須項目がありません: {path} sources[{index}]")

    return Source(
        name=name.strip(),
        url=url.strip(),
        weight=0,
        tags=_as_tags(entry.get("tags")),
    )


def _is_nonempty_str(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _as_tags(value: object) -> tuple[str, ...]:
    """欠落・NULL・空配列はいずれも空タプル（F-001 AC-028）。

    `None` を下流へ流すと SPEC-004 のタグ結合で `TypeError` になる。
    """
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if _is_nonempty_str(item))
