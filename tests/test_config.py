"""起動時の設定読み込みのテスト（SPEC-005 §2 / フロー #11・#12、F-001 AC-030a）。

feeds.yaml と profile.md の読み込み・検証は SPEC-005 の管轄であり、
不備があれば処理本体を開始する前に ConfigError を送出する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from feed_triage.contract.model import Source
from feed_triage.implementation.adapters.config import (
    ConfigError,
    load_profile,
    load_sources,
)

VALID_YAML = """
sources:
  - name: aws-big-data
    url: https://aws.amazon.com/blogs/big-data/feed/
    weight: 0
    tags: [aws]
    verified: false
  - name: jane-street
    url: https://blog.janestreet.com/feed.xml
    weight: 1
    tags: [functional, ocaml]
    verified: true
"""


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


# --- 正常系 ------------------------------------------------------------------


def test_定義順を保ったまま情報源を読み込む(tmp_path: Path) -> None:
    """SPEC-001 §4: 第一キーは feeds.yaml の記載順（取得の完了順ではない）。"""
    sources = load_sources(write(tmp_path, "feeds.yaml", VALID_YAML))
    assert [s.name for s in sources] == ["aws-big-data", "jane-street"]


def test_各項目が_Source_へ写される(tmp_path: Path) -> None:
    sources = load_sources(write(tmp_path, "feeds.yaml", VALID_YAML))
    assert sources[1] == Source(
        name="jane-street",
        url="https://blog.janestreet.com/feed.xml",
        weight=1,
        tags=("functional", "ocaml"),
    )


def test_weight_の欠落は0として扱う(tmp_path: Path) -> None:
    """SPEC-001 §4 入力(a): 欠落・NULL は 0（補正なし）。"""
    body = "sources:\n  - name: a\n    url: https://example.com/feed\n"
    assert load_sources(write(tmp_path, "feeds.yaml", body))[0].weight == 0


@pytest.mark.parametrize("tags_line", ["", "    tags:\n", "    tags: []\n"])
def test_tags_の欠落_NULL_空配列はいずれも空タプル(tmp_path: Path, tags_line: str) -> None:
    """SPEC-001 §4 入力(a) / F-001 AC-028。None を下流へ流さない。"""
    body = f"sources:\n  - name: a\n    url: https://example.com/feed\n{tags_line}"
    assert load_sources(write(tmp_path, "feeds.yaml", body))[0].tags == ()


def test_verified_が_false_でも読み込む(tmp_path: Path) -> None:
    """SPEC-001 §4: verified は本仕様の振る舞いに影響しない（運用者の注記）。"""
    body = "sources:\n  - name: a\n    url: https://example.com/feed\n    verified: false\n"
    assert len(load_sources(write(tmp_path, "feeds.yaml", body))) == 1


def test_情報源の定義が0件でも正常に読み込む(tmp_path: Path) -> None:
    """F-001 AC-024: 0件は正常系。CONFIG_ERROR にしない。"""
    assert load_sources(write(tmp_path, "feeds.yaml", "sources: []\n")) == []


# --- 例外系: feeds.yaml（SPEC-005 フロー #11） -------------------------------


def test_feeds_が存在しないとき中止する(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="フィード定義が見つかりません"):
        load_sources(tmp_path / "missing.yaml")


def test_YAML_として解釈できないとき中止する(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="フィード定義を解釈できません"):
        load_sources(write(tmp_path, "feeds.yaml", "sources: [\n  - broken"))


def test_sources_キーを欠くとき中止する(tmp_path: Path) -> None:
    """空の情報源リストへフォールバックしない（SPEC-005 フロー #11）。"""
    with pytest.raises(ConfigError, match="フィード定義を解釈できません"):
        load_sources(write(tmp_path, "feeds.yaml", "feeds:\n  - name: a\n"))


@pytest.mark.parametrize(
    "body",
    [
        "sources:\n  - url: https://example.com/feed\n",
        "sources:\n  - name: a\n",
        "sources:\n  - name: ''\n    url: https://example.com/feed\n",
    ],
)
def test_name_または_url_を欠く要素があるとき中止する(tmp_path: Path, body: str) -> None:
    with pytest.raises(ConfigError, match="必須項目がありません"):
        load_sources(write(tmp_path, "feeds.yaml", body))


def test_欠落した要素の位置がメッセージに含まれる(tmp_path: Path) -> None:
    """どの要素が悪いか分からないと運用者が是正できない（SPEC-005 フロー #11）。"""
    body = "sources:\n  - name: a\n    url: https://example.com/a\n  - url: https://example.com/b\n"
    with pytest.raises(ConfigError, match=r"sources\[1\]"):
        load_sources(write(tmp_path, "feeds.yaml", body))


def test_name_が重複するとき中止する(tmp_path: Path) -> None:
    """一意でないと情報源別の集計（F-004 AC-003）が破綻する。"""
    body = (
        "sources:\n"
        "  - name: dup\n    url: https://example.com/a\n"
        "  - name: dup\n    url: https://example.com/b\n"
    )
    with pytest.raises(ConfigError, match="重複した情報源名があります: dup"):
        load_sources(write(tmp_path, "feeds.yaml", body))


# --- 例外系: profile.md（SPEC-005 フロー #12） -------------------------------


def test_profile_を読み込む(tmp_path: Path) -> None:
    path = write(tmp_path, "profile.md", "# トリアージ基準\n\n設計解説を優遇する。\n")
    assert "設計解説を優遇する" in load_profile(path)


def test_profile_が存在しないとき中止する(tmp_path: Path) -> None:
    """基準なしで評価すると全件のスコアが無意味になる（SPEC-003 §2）。"""
    with pytest.raises(ConfigError, match="トリアージ基準が見つかりません"):
        load_profile(tmp_path / "missing.md")


def test_profile_が空のとき中止する(tmp_path: Path) -> None:
    """空ファイルは「基準なし」と同義であり、読めた扱いにしない。"""
    with pytest.raises(ConfigError, match="トリアージ基準が空です"):
        load_profile(write(tmp_path, "profile.md", "   \n\n"))


# --- セキュリティ ------------------------------------------------------------


def test_エラーメッセージにファイルの中身を含めない(tmp_path: Path) -> None:
    """設定ファイルに秘匿値が書かれていても出力へ漏らさない（REQ-NF-006）。"""
    secret = "sk-ant-DO-NOT-LEAK"
    body = f"sources:\n  - name: a\n    token: {secret}\n"
    with pytest.raises(ConfigError) as exc:
        load_sources(write(tmp_path, "feeds.yaml", body))
    assert secret not in str(exc.value)
