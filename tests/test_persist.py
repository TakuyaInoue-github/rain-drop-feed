"""状態ブランチへの永続化のテスト（SPEC-002 フロー #5・#17〜#21、ADR-002）。

実際の git リポジトリ（ローカルの bare をリモートに見立てる）に対して実行する。
git の挙動そのものが仕様の前提であり、モックにすると「union merge で行が残る」
「非 fast-forward が拒否される」といった検証対象が消えるため。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from feed_triage.implementation.adapters.persist import (
    MAX_PUSH_ATTEMPTS,
    STATE_BRANCH,
    PersistError,
    load_persisted,
    persist_state,
)


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """リモートに見立てた bare リポジトリ。"""
    path = tmp_path / "remote.git"
    path.mkdir()
    git("init", "-q", "--bare", cwd=path)
    return path


@pytest.fixture
def repo(tmp_path: Path, remote: Path) -> Path:
    """作業側のリポジトリ。既定ブランチに1コミットだけ持つ。"""
    path = tmp_path / "work"
    path.mkdir()
    git("init", "-q", "-b", "main", cwd=path)
    git("config", "user.email", "test@example.com", cwd=path)
    git("config", "user.name", "test", cwd=path)
    (path / "README.md").write_text("work\n", encoding="utf-8")
    git("add", "-A", cwd=path)
    git("commit", "-qm", "init", cwd=path)
    git("remote", "add", "origin", str(remote), cwd=path)
    git("push", "-q", "origin", "main", cwd=path)
    return path


def remote_lines(remote: Path, name: str = "state.jsonl") -> list[str]:
    """リモートの状態ブランチに保存されている行を読む。"""
    body = git("show", f"{STATE_BRANCH}:{name}", cwd=remote)
    return [line for line in body.splitlines() if line.strip()]


def push_from_elsewhere(tmp_path: Path, remote: Path, line: str) -> None:
    """別の実行が先に push した状況を作る（同時実行の競合を再現する）。"""
    other = tmp_path / "other"
    git("clone", "-q", str(remote), str(other), cwd=tmp_path)
    git("config", "user.email", "other@example.com", cwd=other)
    git("config", "user.name", "other", cwd=other)
    git("checkout", "-q", STATE_BRANCH, cwd=other)
    path = other / "state.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    git("commit", "-qam", "other run", cwd=other)
    git("push", "-q", "origin", STATE_BRANCH, cwd=other)


# --- 正常系（フロー #5） -----------------------------------------------------


def test_初回実行で状態ブランチを作成して_push_する(repo: Path, remote: Path) -> None:
    """状態ブランチが無ければ orphan branch として作る（ADR-002）。"""
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    assert remote_lines(remote) == ['{"url":"a"}']


def test_2回目の実行は既存行の後ろへ追記される(repo: Path, remote: Path) -> None:
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    persist_state(repo, {"state.jsonl": '{"url":"b"}\n'})
    assert remote_lines(remote) == ['{"url":"a"}', '{"url":"b"}']


def test_state_と_runs_を同時に永続化できる(repo: Path, remote: Path) -> None:
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n', "runs.jsonl": '{"run_at":"x"}\n'})
    assert remote_lines(remote) == ['{"url":"a"}']
    assert remote_lines(remote, "runs.jsonl") == ['{"run_at":"x"}']


def test_既定ブランチの作業ツリーを汚さない(repo: Path, remote: Path) -> None:
    """worktree を使う理由。実行後に main が変更されていてはならない。"""
    before = git("rev-parse", "HEAD", cwd=repo).strip()
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})

    assert git("rev-parse", "HEAD", cwd=repo).strip() == before
    assert git("branch", "--show-current", cwd=repo).strip() == "main"
    assert git("status", "--porcelain", cwd=repo).strip() == ""


def test_状態ブランチは既定ブランチと履歴を共有しない(repo: Path, remote: Path) -> None:
    """orphan branch であること（ADR-002）。既定ブランチの履歴を汚さない。"""
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    merge_base = subprocess.run(
        ["git", "merge-base", "main", STATE_BRANCH],
        cwd=remote,
        capture_output=True,
        text=True,
    )
    assert merge_base.returncode != 0, "共通の祖先を持ってはならない"


def test_永続化する内容がなければ何もしない(repo: Path, remote: Path) -> None:
    """フロー #6 の一部。空コミットを積むと履歴が読みにくくなる。"""
    persist_state(repo, {})
    branches = git("branch", cwd=remote)
    assert STATE_BRANCH not in branches


# --- 競合（フロー #17・#18） -------------------------------------------------


def test_競合したら行マージして両方の行を残す(tmp_path: Path, repo: Path, remote: Path) -> None:
    """フロー #18: 追記専用のため行順に意味がなく、両方を残すのが正しい。

    片方を捨てると、捨てられた側の実行が記録した投入が次回「新規」となり
    重複投入（R-002 違反）を招く。
    """
    persist_state(repo, {"state.jsonl": '{"url":"first"}\n'})
    push_from_elsewhere(tmp_path, remote, '{"url":"other"}')

    persist_state(repo, {"state.jsonl": '{"url":"mine"}\n'})

    lines = remote_lines(remote)
    assert '{"url":"other"}' in lines, "先行した実行の行が失われている"
    assert '{"url":"mine"}' in lines, "自分の行が失われている"
    assert not any("<<<<" in line for line in lines), "競合マーカーが残っている"


def test_競合が解決されれば実行は成功する(tmp_path: Path, repo: Path, remote: Path) -> None:
    persist_state(repo, {"state.jsonl": '{"url":"first"}\n'})
    push_from_elsewhere(tmp_path, remote, '{"url":"other"}')
    persist_state(repo, {"state.jsonl": '{"url":"mine"}\n'})  # 例外が出ないこと


# --- 失敗（フロー #19・#20・#21） --------------------------------------------


def test_リモートが存在しなければ失敗として送出する(repo: Path) -> None:
    """フロー #21 / #20。記録できないまま投入を続けると重複が確定する。"""
    git("remote", "set-url", "origin", "/nonexistent/remote.git", cwd=repo)
    with pytest.raises(PersistError):
        persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})


def test_書き込み権限がなければ失敗として送出する(repo: Path, tmp_path: Path) -> None:
    """フロー #20: 権限がなくても静かに成功扱いにしない。

    記録できないまま投入を続けると重複投入（R-002 違反）が確定するため、
    push できないことは必ず実行の失敗として表面化させる。

    `objects` / `refs` を読み取り専用にする — bare リポジトリの**トップだけ**を
    readonly にしても、既存サブディレクトリへの書き込みは通ってしまう。
    """
    readonly = tmp_path / "readonly.git"
    readonly.mkdir()
    git("init", "-q", "--bare", cwd=readonly)
    git("remote", "set-url", "origin", str(readonly), cwd=repo)
    locked = [readonly / "objects", readonly / "refs"]
    for path in locked:
        path.chmod(0o500)
    try:
        with pytest.raises(PersistError):
            persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    finally:
        for path in locked:
            path.chmod(0o700)


def test_再試行の上限は3回(repo: Path) -> None:
    """フロー #17 / #19: 上限に達したら STATE_PERSIST_FAILED で終了する。"""
    assert MAX_PUSH_ATTEMPTS == 3


# --- 冪等性 ------------------------------------------------------------------


def test_同じ内容を2回永続化しても行が重複しない(repo: Path, remote: Path) -> None:
    """一意化は append_records の責務だが、永続化が行を複製しないことも確認する。"""
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    persist_state(repo, {"state.jsonl": ""})
    assert remote_lines(remote) == ['{"url":"a"}']


# --- セキュリティ ------------------------------------------------------------


def test_エラーメッセージにリモート_URL_の資格情報を含めない(repo: Path) -> None:
    """REQ-NF-006: push URL にトークンが埋め込まれる運用がありうる。"""
    secret = "ghp_DO_NOT_LEAK"
    git(
        "remote",
        "set-url",
        "origin",
        f"https://x-access-token:{secret}@invalid.example/r.git",
        cwd=repo,
    )
    with pytest.raises(PersistError) as exc:
        persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    assert secret not in str(exc.value)


# --- 実行不能・タイムアウト（フロー #21） ------------------------------------


def test_git_の実行がタイムアウトしたら失敗として送出する(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """フロー #21: 無期限に待つと週次バッチが終わらない。"""
    from feed_triage.implementation.adapters import persist as module

    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="git", timeout=module.GIT_TIMEOUT_SECONDS)

    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(PersistError, match="タイムアウト"):
        persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})


def test_git_が実行できなければ失敗として送出する(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from feed_triage.implementation.adapters import persist as module

    def missing(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(module.subprocess, "run", missing)
    with pytest.raises(PersistError):
        persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})


def test_競合が解消しなければ上限まで試行して失敗する(
    tmp_path: Path, repo: Path, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """フロー #19: 3回とも失敗したら静かに成功扱いにしない。

    push を常に失敗させ、再試行が尽きることを確認する。**成功扱いにすると
    記録が失われたまま次回が動き、重複投入（R-002 違反）が確定する。**
    """
    from feed_triage.implementation.adapters import persist as module

    real_run = subprocess.run
    attempts = 0

    def failing_push(args: list[str], **kwargs: object) -> object:
        nonlocal attempts
        if "push" in args:
            attempts += 1
            return subprocess.CompletedProcess(args, 1, "", "rejected")
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(module.subprocess, "run", failing_push)
    with pytest.raises(PersistError, match="状態の保存に失敗しました"):
        persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    assert attempts == MAX_PUSH_ATTEMPTS


# --- 状態ブランチからの読み出し（フロー #2） ---------------------------------


def test_状態ブランチから内容を読み出せる(repo: Path, remote: Path) -> None:
    """**実地の Actions 実行で発覚（2026-08-01 / TASK-112）。**

    書き込みは状態ブランチ、読み込みは CWD のファイルという非対称があり、
    **CI では毎回まっさらな checkout のため状態が読めず全件が新規になっていた**
    （冪等性 R-002 が本番で成立していなかった）。ローカルでは前回実行が
    ファイルを残すため気づけなかった。
    """
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})

    files = load_persisted(repo, ["state.jsonl"])

    assert files["state.jsonl"] == '{"url":"a"}\n'


def test_複数ファイルをまとめて読み出せる(repo: Path, remote: Path) -> None:
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n', "runs.jsonl": '{"run_at":"x"}\n'})

    files = load_persisted(repo, ["state.jsonl", "runs.jsonl"])

    assert files["state.jsonl"] == '{"url":"a"}\n'
    assert files["runs.jsonl"] == '{"run_at":"x"}\n'


def test_状態ブランチが無ければ空を返す(repo: Path) -> None:
    """初回実行。**例外にしない** — 状態がないことは異常ではない。"""
    assert load_persisted(repo, ["state.jsonl"]) == {}


def test_ブランチにファイルが無ければ欠落として返す(repo: Path, remote: Path) -> None:
    """`runs.jsonl` だけ後から増えた場合など。片方だけでも読める。"""
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})

    files = load_persisted(repo, ["state.jsonl", "runs.jsonl"])

    assert "state.jsonl" in files
    assert "runs.jsonl" not in files


def test_2回の永続化がすべて読み出せる(repo: Path, remote: Path) -> None:
    """追記が累積すること（ADR-005）。"""
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    persist_state(repo, {"state.jsonl": '{"url":"b"}\n'})

    body = load_persisted(repo, ["state.jsonl"])["state.jsonl"]

    assert body.splitlines() == ['{"url":"a"}', '{"url":"b"}']


def test_読み戻した内容をそのまま渡すと行が重複する(repo: Path, remote: Path) -> None:
    """**`persist_state` は追記である**ことを固定する（ADR-005）。

    読み戻した全文をそのまま渡すと既存行が二重に積まれる。呼び出し側は
    **今回の増分だけ**を渡さなければならない（→ `cli.py` の `_Store`）。
    この非対称は TASK-112 の修正で踏みやすい罠であり、明示的に固定する。
    """
    persist_state(repo, {"state.jsonl": '{"url":"a"}\n'})
    whole = load_persisted(repo, ["state.jsonl"])["state.jsonl"]

    persist_state(repo, {"state.jsonl": whole + '{"url":"b"}\n'})

    lines = remote_lines(remote)
    assert lines.count('{"url":"a"}') == 2, "全文を渡すと重複する（＝増分のみを渡すこと）"
