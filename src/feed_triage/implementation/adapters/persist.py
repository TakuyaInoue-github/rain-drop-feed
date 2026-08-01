"""状態ブランチへの永続化（SPEC-002 フロー #5・#17〜#21、ADR-002）。

状態は既定ブランチとは履歴を共有しない orphan branch `state` に置く。
既定ブランチにボットコミットを積まず、ブランチ保護とも両立させるため（ADR-002）。

操作は **`git worktree` を使って隔離する**。既定ブランチの作業ツリーで
`checkout` すると、実行中のファイルが切り替わって処理本体を壊しうるため。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

STATE_BRANCH = "state"
"""状態を保持する orphan branch の名前（ADR-002）。"""

MAX_PUSH_ATTEMPTS = 3
"""push の試行回数の上限（SPEC-002 フロー #17 / #19）。

競合は他の実行との同時実行で起きる。3回で収束しない状況は競合以外の原因
（権限・ネットワーク）が濃厚であり、粘っても解決しない。
"""

GIT_TIMEOUT_SECONDS = 60.0
"""1つの git コマンドのタイムアウト（SPEC-002 フロー #21 / REQ-NF-004）。

無期限に待つと週次バッチが終わらない。
"""

MERGE_DRIVER = "git merge-file --union -L %P -L %P -L %P %A %O %B"
"""競合時に**両方の行を残す**マージドライバ（フロー #18）。

追記専用の JSONL は行順に意味がないため、片方を捨てず両方を残すのが正しい
（捨てると、捨てられた側が記録した投入が次回「新規」となり重複投入を招く）。
"""

_CREDENTIAL_PATTERN = re.compile(r"//[^/@\s]*@")


class PersistError(Exception):
    """状態の永続化失敗（終了コード `STATE_PERSIST_FAILED` → SPEC-005 §5）。"""


def persist_state(repo: Path, files: dict[str, str]) -> None:
    """`files`（ファイル名 → 追記する内容）を状態ブランチへ追記して push する。

    競合したら `pull --rebase` で行マージし、最大 `MAX_PUSH_ATTEMPTS` 回まで
    再試行する。すべて失敗したら `PersistError` を送出する — 記録できないまま
    投入を続けると重複投入（R-002 違反）が確定するため、静かに成功扱いにしない。
    """
    additions = {name: body for name, body in files.items() if body}
    if not additions:
        # 空コミットを積むと状態ブランチの履歴が読みにくくなる（フロー #6）
        return

    worktree = Path(tempfile.mkdtemp(prefix="feed-triage-state-"))
    try:
        _prepare_worktree(repo, worktree)
        for name, body in additions.items():
            target = worktree / name
            with target.open("a", encoding="utf-8") as handle:
                handle.write(body)
        _commit_and_push(worktree, len(additions))
    finally:
        _cleanup(repo, worktree)


def load_persisted(repo: Path, names: list[str]) -> dict[str, str]:
    """状態ブランチから `names` の内容を読み出す（SPEC-002 フロー #2）。

    **`persist_state` と対になる。** 書き込みが状態ブランチなのに読み込みが
    作業ディレクトリのファイルだと、CI のようにまっさらな checkout から
    始まる環境では**状態が読めず全件が新規として扱われる**（冪等性 R-002 が
    成立しない → TASK-112。実地の Actions 実行で発覚した）。

    ブランチが無い初回は空を返す。**例外にしない** — 状態がないことは
    異常ではなく、正常な初回実行である。
    """
    _git(repo, "fetch", "--quiet", "origin", STATE_BRANCH, allow_failure=True)
    ref = f"origin/{STATE_BRANCH}"
    if _git(repo, "rev-parse", "--verify", "--quiet", ref, allow_failure=True) is None:
        return {}

    files: dict[str, str] = {}
    for name in names:
        # ファイル単位で失敗を許容する。`runs.jsonl` が後から増えた場合など、
        # 片方だけ存在する状態がありうる
        body = _git(repo, "show", f"{ref}:{name}", allow_failure=True)
        if body is not None:
            files[name] = body
    return files


def _prepare_worktree(repo: Path, worktree: Path) -> None:
    """状態ブランチを worktree として展開する。無ければ orphan branch を作る。"""
    _git(repo, "fetch", "--quiet", "origin", STATE_BRANCH, allow_failure=True)

    exists = (
        _git(repo, "rev-parse", "--verify", "--quiet", f"origin/{STATE_BRANCH}", allow_failure=True)
        is not None
    )
    # worktree の追加先は既に mkdtemp が作っているため、git には空でないと見える。
    # 一度消してから追加させる
    shutil.rmtree(worktree, ignore_errors=True)

    if exists:
        _git(
            repo,
            "worktree",
            "add",
            "--quiet",
            "-B",
            STATE_BRANCH,
            str(worktree),
            f"origin/{STATE_BRANCH}",
        )
    else:
        # 初回実行。既定ブランチと履歴を共有しない orphan branch を作る（ADR-002）
        _git(repo, "worktree", "add", "--quiet", "--detach", str(worktree))
        _git(worktree, "checkout", "--quiet", "--orphan", STATE_BRANCH)
        _git(worktree, "rm", "-rq", "--cached", "-r", ".", allow_failure=True)
        for stale in worktree.iterdir():
            if stale.name != ".git":
                if stale.is_dir():
                    shutil.rmtree(stale, ignore_errors=True)
                else:
                    stale.unlink()
        # JSONL は行単位で追記されるため union マージで両方を残す（フロー #18）。
        # **競合が起きる前に置く必要がある** — 分岐後に追加しても適用されない
        (worktree / ".gitattributes").write_text("*.jsonl merge=union\n", encoding="utf-8")


def _commit_and_push(worktree: Path, file_count: int) -> None:
    """コミットして push。競合したら行マージして再試行する。"""
    _git(worktree, "add", "-A")
    _git(
        worktree,
        "commit",
        "--quiet",
        "-m",
        f"chore(state): 実行結果を記録する（{file_count}ファイル）",
    )

    last_error = ""
    for attempt in range(1, MAX_PUSH_ATTEMPTS + 1):
        pushed = _git(worktree, "push", "--quiet", "origin", STATE_BRANCH, allow_failure=True)
        if pushed is not None:
            return

        if attempt == MAX_PUSH_ATTEMPTS:
            break
        # 競合したら行マージして再試行する（フロー #17 / #18）
        merged = _git(
            worktree,
            "-c",
            f"merge.union.driver={MERGE_DRIVER}",
            "pull",
            "--rebase",
            "--quiet",
            "origin",
            STATE_BRANCH,
            allow_failure=True,
        )
        if merged is None:
            # rebase が途中で止まっていると次の試行が必ず失敗するため戻す
            _git(worktree, "rebase", "--abort", allow_failure=True)
            last_error = "統合に失敗しました"

    raise PersistError(
        f"状態の保存に失敗しました（{MAX_PUSH_ATTEMPTS}回試行）。"
        f"次回実行で重複投入が発生しうるため状態ブランチを確認してください。{last_error}".strip()
    )


def _cleanup(repo: Path, worktree: Path) -> None:
    """worktree を必ず片付ける。残すと次回の `worktree add` が失敗する。"""
    _git(repo, "worktree", "remove", "--force", str(worktree), allow_failure=True)
    shutil.rmtree(worktree, ignore_errors=True)
    _git(repo, "worktree", "prune", allow_failure=True)


def _git(cwd: Path, *args: str, allow_failure: bool = False) -> str | None:
    """git を実行する。`allow_failure` なら失敗時に None を返す。

    **stderr をそのままメッセージにしない** — リモート URL に資格情報が
    埋め込まれる運用があり、出力へ漏らすと秘匿情報が露出する（REQ-NF-006）。
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        if allow_failure:
            return None
        raise PersistError(
            f"git の実行がタイムアウトしました（{GIT_TIMEOUT_SECONDS:.0f}秒）"
        ) from None
    except OSError as exc:
        if allow_failure:
            return None
        raise PersistError(f"git を実行できません（{type(exc).__name__}）") from None

    if result.returncode != 0:
        if allow_failure:
            return None
        raise PersistError(f"git {args[0]} に失敗しました: {_redact(result.stderr)}")
    return result.stdout


def _redact(text: str) -> str:
    """リモート URL の資格情報部分（`//user:token@`）を伏せる。"""
    return _CREDENTIAL_PATTERN.sub("//***@", text).strip().splitlines()[-1] if text.strip() else ""
