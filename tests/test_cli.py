"""CLI の引数解析と起動時検証のテスト（SPEC-005 / application_checklist C-I01）。

観点番号（T-xxx）は SPEC-005 §10 の表に対応させる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from feed_triage.cli import Settings, build_parser, load_settings, main
from feed_triage.contract import exit_codes

ENV_KEYS = ("RAINDROP_TOKEN", "RAINDROP_COLLECTION_ID", "ANTHROPIC_API_KEY")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """検証をすべて通過する状態を作る。個別のテストが1項目ずつ壊す。"""
    (tmp_path / "feeds.yaml").write_text(
        "sources:\n  - name: example\n    url: https://example.test/feed\n    weight: 0\n",
        encoding="utf-8",
    )
    (tmp_path / "profile.md").write_text("トリアージ基準\n", encoding="utf-8")
    monkeypatch.setenv("RAINDROP_TOKEN", "token-DO-NOT-LEAK")
    monkeypatch.setenv("RAINDROP_COLLECTION_ID", "12345678")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-DO-NOT-LEAK")
    monkeypatch.chdir(tmp_path)
    return tmp_path


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
    def test_version_を指定すると正常終了する(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == exit_codes.OK

    def test_help_は設定不備でも読める(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T-004: 起動時検証を引数解析より前に置けばレッド。

        設定が壊れている運用者こそヘルプを必要とする。
        """
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == exit_codes.OK


class TestStartupValidation:
    """SPEC-005 フロー #8〜12。**処理本体を開始する前に**すべて検証する。"""

    def test_すべて揃っていれば検証を通過する(self, workspace: Path) -> None:
        settings = load_settings(dry_run=False)
        assert isinstance(settings, Settings)
        assert settings.collection_id == 12345678
        assert [s.name for s in settings.sources] == ["example"]

    @pytest.mark.parametrize("key", ENV_KEYS)
    def test_環境変数が未設定なら設定エラー(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch, key: str
    ) -> None:
        """T-005 / T-007: フロー #8〜10。"""
        monkeypatch.delenv(key)
        assert load_settings(dry_run=False) is None

    @pytest.mark.parametrize("key", ENV_KEYS)
    def test_環境変数が空文字なら未設定と同じ扱い(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch, key: str
    ) -> None:
        """T-011: 存在チェックのみ（`in os.environ`）にすればレッド。"""
        monkeypatch.setenv(key, "")
        assert load_settings(dry_run=False) is None

    def test_コレクションIDが非整数なら設定エラー(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T-006: 例外を握り潰して既定値へフォールバックすればレッド。"""
        monkeypatch.setenv("RAINDROP_COLLECTION_ID", "not-a-number")
        assert load_settings(dry_run=False) is None

    @pytest.mark.parametrize("value", ["0", "-1", "-42"])
    def test_コレクションIDの0や負値は整数として受理する(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        """T-012: **暫定**（SPEC-004 OQ-007 / TASK-085 に従属）。

        正の整数のみを受理する実装にすると、未決の OQ-007 を先取りしてしまう。
        """
        monkeypatch.setenv("RAINDROP_COLLECTION_ID", value)
        settings = load_settings(dry_run=False)
        assert settings is not None
        assert settings.collection_id == int(value)

    def test_feeds_yaml_が無ければ設定エラー(self, workspace: Path) -> None:
        """T-008: 不在時に空リストで続行すれば、全情報源の消失を検知できずレッド。"""
        (workspace / "feeds.yaml").unlink()
        assert load_settings(dry_run=False) is None

    def test_profile_md_が無ければ設定エラー(self, workspace: Path) -> None:
        """T-009: 基準なしで評価すれば全件のスコアが無意味になりレッド。"""
        (workspace / "profile.md").unlink()
        assert load_settings(dry_run=False) is None

    def test_情報源が必須項目を欠けば設定エラー(self, workspace: Path) -> None:
        """T-008a: 欠落を既定値で補完すれば重み・タグの引き当てが壊れてレッド。"""
        (workspace / "feeds.yaml").write_text(
            "sources:\n  - url: https://example.test/feed\n", encoding="utf-8"
        )
        assert load_settings(dry_run=False) is None

    def test_情報源名が重複すれば設定エラー(self, workspace: Path) -> None:
        """T-008b: 重複を許せば情報源別の集計が合算されてレッド（F-004 AC-003）。"""
        (workspace / "feeds.yaml").write_text(
            "sources:\n"
            "  - name: dup\n    url: https://a.test/feed\n"
            "  - name: dup\n    url: https://b.test/feed\n",
            encoding="utf-8",
        )
        assert load_settings(dry_run=False) is None


class TestDryRunValidation:
    """F-005 AC-030: dry-run で緩める対象は収集レイヤーの2項目のみ。"""

    @pytest.mark.parametrize("key", ["RAINDROP_TOKEN", "RAINDROP_COLLECTION_ID"])
    def test_収集レイヤーの秘匿値は未設定でも続行する(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch, key: str
    ) -> None:
        """T-013: dry-run でも全項目を検証すれば、基準の試行ができずレッド。"""
        monkeypatch.delenv(key)
        assert load_settings(dry_run=True) is not None

    def test_APIキーは_dry_run_でも必須(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T-007: dry-run の分岐に API キーを含めればレッド。評価は実行する。"""
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        assert load_settings(dry_run=True) is None

    @pytest.mark.parametrize("name", ["feeds.yaml", "profile.md"])
    def test_設定ファイルは_dry_run_でも必須(self, workspace: Path, name: str) -> None:
        (workspace / name).unlink()
        assert load_settings(dry_run=True) is None

    def test_不足している項目が警告として出力される(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """T-014 / F-005 AC-030a: 警告がないと、dry-run で OK を確認した後に
        定期実行が失敗する落とし穴が残る。"""
        monkeypatch.delenv("RAINDROP_TOKEN")
        load_settings(dry_run=True)

        captured = capsys.readouterr()
        assert "RAINDROP_TOKEN" in captured.err
        assert captured.out == "", "警告は標準エラーへ出す（REQ-NF-007）"


class TestMainWiring:
    """`main` の結線（フロー #3・#4）。外部通信は差し替える。"""

    def _patch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        score: int = 8,
        entries: int = 1,
    ) -> dict[str, object]:
        """取得・評価・投入・永続化を偽物に差し替える。"""
        from feed_triage import cli as module
        from feed_triage.contract.model import Entry, SourceOutcome, Verdict
        from feed_triage.implementation.adapters.evaluate import (
            EvaluationOutcome,
            OutcomeKind,
        )

        seen: dict[str, object] = {"posted": [], "persisted": 0}

        def fake_fetch(sources: object) -> tuple[list[Entry], list[SourceOutcome]]:
            items = [
                Entry(
                    url=f"https://example.test/{i}",
                    title=f"記事{i}",
                    summary="要約",
                    published_at=None,
                    source_name="example",
                )
                for i in range(entries)
            ]
            return items, [SourceOutcome("example", fetched=entries)]

        class FakeEvaluator:
            def __init__(self, *args: object, **kwargs: object) -> None: ...

            def evaluate(self, entry: Entry) -> EvaluationOutcome:
                return EvaluationOutcome(
                    OutcomeKind.OK, verdict=Verdict(score=score, reason="理由")
                )

        def fake_persist(repo: object, files: dict[str, str]) -> None:
            seen["persisted"] = int(seen["persisted"]) + 1  # type: ignore[call-overload]

        monkeypatch.setattr(module.fetch, "fetch_all", fake_fetch)
        monkeypatch.setattr(module, "Evaluator", FakeEvaluator)
        monkeypatch.setattr(module, "build_client", lambda key: object())
        monkeypatch.setattr(module.persist, "persist_state", fake_persist)
        return seen

    def test_dry_run_は投入も永続化も行わず正常終了する(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """F-005 AC-001 / AC-004: 投入も状態更新も行わない。"""
        seen = self._patch(monkeypatch)

        code = main(["--dry-run"])

        assert code == exit_codes.OK
        assert seen["persisted"] == 0
        assert not (workspace / "state.jsonl").exists()
        assert capsys.readouterr().out.strip() != "", "サマリは標準出力へ出す"

    def test_通常実行では状態が永続化される(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import respx

        seen = self._patch(monkeypatch)
        with respx.mock:
            respx.post("https://api.raindrop.io/rest/v1/raindrop").mock(
                return_value=__import__("httpx").Response(200, json={"result": True})
            )
            code = main([])

        assert code == exit_codes.OK
        assert seen["persisted"] == 1
        assert (workspace / "state.jsonl").exists()

    def test_サマリは標準出力_ログは標準エラーへ分離される(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """REQ-NF-007 / F-004 AC-005: 出力先を混ぜるとパイプ処理が壊れる。"""
        import httpx
        import respx

        self._patch(monkeypatch)
        with respx.mock:
            respx.post("https://api.raindrop.io/rest/v1/raindrop").mock(
                return_value=httpx.Response(200, json={"result": True})
            )
            main([])

        captured = capsys.readouterr()
        assert "投入しました" in captured.err, "個別の投入ログは標準エラー"
        assert "投入しました" not in captured.out, "サマリに混ぜない"

    def test_投入が全件失敗すれば非0で終了する(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F-001 AC-014: 終了コードが GitHub Actions の失敗通知を発火させる。"""
        import httpx
        import respx

        self._patch(monkeypatch)
        with respx.mock:
            respx.post("https://api.raindrop.io/rest/v1/raindrop").mock(
                return_value=httpx.Response(500)
            )
            code = main([])

        assert code == exit_codes.INGEST_ALL_FAILED

    def test_出力に秘匿値が現れない(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """T-015 / T-026: トークンとコレクション ID を出力しない。"""
        import httpx
        import respx

        self._patch(monkeypatch)
        with respx.mock:
            respx.post("https://api.raindrop.io/rest/v1/raindrop").mock(
                return_value=httpx.Response(500)
            )
            main([])

        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "token-DO-NOT-LEAK" not in combined
        assert "sk-ant-DO-NOT-LEAK" not in combined
        assert "12345678" not in combined


class TestSecrecy:
    """REQ-NF-006 / F-001 AC-031 / AC-033。"""

    def test_エラーメッセージに環境変数の値が含まれない(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """T-015: メッセージに値を埋め込めば CI のログに秘匿情報が残りレッド。"""
        monkeypatch.setenv("RAINDROP_COLLECTION_ID", "not-a-number-SECRET")
        load_settings(dry_run=False)

        captured = capsys.readouterr()
        assert "not-a-number-SECRET" not in captured.err + captured.out
        assert "RAINDROP_COLLECTION_ID" in captured.err, "変数名は示す"

    def test_検証済み設定の_repr_に秘匿情報が含まれない(self, workspace: Path) -> None:
        """T-016: `__repr__` の抑止を外せば、例外のスタックトレースに値が出てレッド。"""
        settings = load_settings(dry_run=False)
        assert settings is not None

        text = repr(settings)
        assert "token-DO-NOT-LEAK" not in text
        assert "sk-ant-DO-NOT-LEAK" not in text
        assert "12345678" not in text, "投入先コレクション ID も出さない（F-004 AC-030）"


class TestExitCodes:
    """application_checklist C-I01: 終了コードの意味を文書化する。"""

    def test_正常終了は0(self) -> None:
        assert exit_codes.OK == 0

    def test_異常終了はすべて非0(self) -> None:
        codes = [
            exit_codes.INGEST_ALL_FAILED,
            exit_codes.CONFIG_ERROR,
            exit_codes.STATE_PERSIST_FAILED,
            exit_codes.SPEC_ERROR,
            exit_codes.FETCH_ALL_FAILED,
        ]
        assert all(c != 0 for c in codes)

    def test_終了コードは互いに重複しない(self) -> None:
        codes = [
            exit_codes.OK,
            exit_codes.INGEST_ALL_FAILED,
            exit_codes.CONFIG_ERROR,
            exit_codes.STATE_PERSIST_FAILED,
            exit_codes.SPEC_ERROR,
            exit_codes.FETCH_ALL_FAILED,
        ]
        assert len(set(codes)) == len(codes)

    def test_運用者の設定ミスと実装バグが別のコードになること(self) -> None:
        """SPEC-005 §5: 是正の主体が異なるため値を分ける。"""
        assert exit_codes.CONFIG_ERROR != exit_codes.SPEC_ERROR

    def test_取得の全件失敗と投入の全件失敗が別のコードになること(self) -> None:
        """SPEC-005 §5: どちらの段階で供給が途切れたかを終了コードで判別する。

        同じ値に畳むと、運用者は通知を受けても原因が取得側か投入側かを
        調べ直すことになる（F-002 AC-010）。
        """
        assert exit_codes.FETCH_ALL_FAILED != exit_codes.INGEST_ALL_FAILED

    def test_既存の終了コードの値が変わっていないこと(self) -> None:
        """FETCH_ALL_FAILED の追加で既存の値を動かさない。

        終了コードは運用者が覚える契約であり、値の変更は黙って解釈を狂わせる。
        """
        assert (exit_codes.OK, exit_codes.INGEST_ALL_FAILED) == (0, 1)
        assert (exit_codes.CONFIG_ERROR, exit_codes.STATE_PERSIST_FAILED) == (2, 3)
        assert exit_codes.SPEC_ERROR == 4


class TestStateRoundTrip:
    """状態ブランチとの往復（TASK-112）。

    **実地の Actions 実行で発覚した。** 書き込みは状態ブランチ、読み込みは
    CWD のファイルという非対称があり、CI のようにまっさらな checkout から
    始まる環境では毎回「記録なし＝全件新規」になっていた。ローカルでは前回
    実行がファイルを残すため表面化しなかった。
    """

    def _repo(self, tmp_path: Path) -> Path:
        import subprocess

        def git(*a: str, cwd: Path) -> None:
            subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)

        remote = tmp_path / "r.git"
        remote.mkdir()
        git("init", "-q", "--bare", cwd=remote)
        work = tmp_path / "w"
        work.mkdir()
        git("init", "-q", "-b", "main", cwd=work)
        git("config", "user.email", "t@example.com", cwd=work)
        git("config", "user.name", "t", cwd=work)
        (work / "README.md").write_text("x", encoding="utf-8")
        git("add", "-A", cwd=work)
        git("commit", "-qm", "init", cwd=work)
        git("remote", "add", "origin", str(remote), cwd=work)
        git("push", "-q", "origin", "main", cwd=work)
        return work

    def test_別チェックアウトでも記録が引き継がれる(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**冪等性の要（R-002）。** これが壊れると毎週全件を再評価・重複投入する。"""
        from datetime import datetime, timezone

        from feed_triage.cli import _Store
        from feed_triage.contract.model import RunRecord, StateRecord

        work = self._repo(tmp_path)
        monkeypatch.chdir(work)

        record = StateRecord(
            url="https://example.test/a",
            title="記事",
            source_name="s",
            evaluated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            score=8,
        )
        first = _Store(work)
        first.load_state()
        first.append([record], RunRecord(run_at=datetime(2026, 8, 1, tzinfo=timezone.utc)))
        first.persist()

        # **ファイルを消して別チェックアウトを再現する**（CI はこの状態で始まる）
        (work / "state.jsonl").unlink()
        (work / "runs.jsonl").unlink()

        second = _Store(work)
        restored = second.load_state()

        assert [r.url for r in restored] == ["https://example.test/a"]
        assert second.load_runs() != [], "実行記録も引き継がれること"

    def test_2回永続化しても行が重複しない(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`persist_state` は**追記**であり、読み戻した全文を渡すと二重になる。

        `_Store` は今回の増分だけを送ることでこれを避ける。
        """
        from datetime import datetime, timezone

        from feed_triage.cli import _Store
        from feed_triage.contract.model import StateRecord

        work = self._repo(tmp_path)
        monkeypatch.chdir(work)

        def record(url: str) -> StateRecord:
            return StateRecord(
                url=url,
                title="記事",
                source_name="s",
                evaluated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                score=8,
            )

        s1 = _Store(work)
        s1.load_state()
        s1.append([record("https://example.test/a")], None)
        s1.persist()

        (work / "state.jsonl").unlink()

        s2 = _Store(work)
        s2.load_state()
        s2.append([record("https://example.test/b")], None)
        s2.persist()

        # **3回目も別チェックアウトを再現する。** 消さないとローカルに残った
        # ファイルが読まれ、ブランチ側の内容を検証したことにならない
        (work / "state.jsonl").unlink()

        s3 = _Store(work)
        urls = [r.url for r in s3.load_state()]
        assert sorted(urls) == ["https://example.test/a", "https://example.test/b"]
        assert len(urls) == 2, f"行が重複している: {urls}"

    def test_日本語を含む記録でも増分が壊れない(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**マルチバイトで露見するバグの回帰テスト。**

        増分の位置は `st_size`（バイト数）で持つため、`str` の文字数スライスと
        混ぜると日本語のタイトル・理由を含む行でズレる。**行の途中から切り出され、
        壊れた JSON が push される**（読み戻し時に捨てられ記録が消える）。
        ASCII だけのデータでは一致してしまい検出できない。
        """
        from datetime import datetime, timezone

        from feed_triage.cli import _Store
        from feed_triage.contract.model import StateRecord

        work = self._repo(tmp_path)
        monkeypatch.chdir(work)

        def record(url: str) -> StateRecord:
            return StateRecord(
                url=url,
                title="日本語のタイトル・全角記号を含む記事",
                source_name="s",
                evaluated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                score=8,
                reason="設計思想が明確で、実運用の知見が語られている。",
            )

        s1 = _Store(work)
        s1.load_state()
        s1.append([record("https://example.test/a")], None)
        s1.persist()

        (work / "state.jsonl").unlink()

        s2 = _Store(work)
        s2.load_state()
        s2.append([record("https://example.test/b")], None)
        s2.persist()

        (work / "state.jsonl").unlink()

        restored = _Store(work).load_state()
        assert sorted(r.url for r in restored) == [
            "https://example.test/a",
            "https://example.test/b",
        ]
        assert all(r.title.startswith("日本語") for r in restored), "内容が壊れている"
