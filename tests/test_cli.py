"""CLI の引数解析のテスト（F-005 / application_checklist C-I01）。"""

from __future__ import annotations

import pytest

from feed_triage.cli import build_parser, main
from feed_triage.contract import exit_codes


class TestBuildParser:
    def test_既定では_dry_run_が無効(self) -> None:
        args = build_parser().parse_args([])
        assert args.dry_run is False

    def test_dry_run_を指定できる(self) -> None:
        """F-005: 投入を伴わない実行方法を提供する。"""
        args = build_parser().parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_verbose_を指定できる(self) -> None:
        """F-004 AC-007: 詳細ログの任意有効化。"""
        args = build_parser().parse_args(["--verbose"])
        assert args.verbose is True

    def test_両方を同時に指定できる(self) -> None:
        args = build_parser().parse_args(["--dry-run", "--verbose"])
        assert (args.dry_run, args.verbose) == (True, True)

    def test_未知のオプションはエラーになる(self) -> None:
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--unknown"])
        assert exc.value.code != exit_codes.OK


class TestMain:
    def test_未実装のため設定エラーで終了する(self) -> None:
        """実装完了時にこのテストは書き換える（現在は骨格のみ）。"""
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == exit_codes.CONFIG_ERROR

    def test_version_を指定すると正常終了する(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == exit_codes.OK


class TestExitCodes:
    """application_checklist C-I01: 終了コードの意味を文書化する。"""

    def test_正常終了は0(self) -> None:
        assert exit_codes.OK == 0

    def test_異常終了はすべて非0(self) -> None:
        codes = [
            exit_codes.INGEST_ALL_FAILED,
            exit_codes.CONFIG_ERROR,
            exit_codes.STATE_PERSIST_FAILED,
        ]
        assert all(c != 0 for c in codes)

    def test_終了コードは互いに重複しない(self) -> None:
        codes = [
            exit_codes.OK,
            exit_codes.INGEST_ALL_FAILED,
            exit_codes.CONFIG_ERROR,
            exit_codes.STATE_PERSIST_FAILED,
        ]
        assert len(set(codes)) == len(codes)
