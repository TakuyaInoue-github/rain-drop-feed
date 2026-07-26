# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの現状

骨格とツールチェーンは導入済み（→ [ADR-004](docs/04_decisions/ADR-004_implementation_stack.md)）。**取得・評価・投入の本体は未実装**で、`pipeline.run()` は `NotImplementedError` を送出する。SPEC 層（`docs/03_specs/`）は未着手であり、本体の実装はその確定後に行う。

### コマンド

すべて `uv run` 経由で実行する。素の `python3` / `pip` は使わない。

```bash
uv sync --extra dev        # 依存のインストール
uv run pytest -q           # テスト
uv run pytest -q --cov     # テスト + カバレッジ（閾値 80%）
uv run ruff check .        # lint
uv run mypy src            # 型チェック（strict）
uv run lint-imports        # 層構造の依存方向チェック
```

CI（`.github/workflows/ci.yml`）は上記を Python 3.10 / 3.12 で実行する。**コード変更後はこの4つ（ruff / mypy / lint-imports / pytest）を通してから完了とすること。**

### 層構造

`src/feed_triage/` は4層。依存方向は `import-linter` が CI で強制する（`pyproject.toml` の `[tool.importlinter]`）。

```
cli.py                     argparse → RunOptions 構築、出力のみ
pipeline.py                run(options) -> RunSummary（I/O なし）
implementation/domain/     副作用のないロジック（state.py / scoring.py）
implementation/adapters/   副作用の隔離（フィード取得・LLM 評価・投入・状態の永続化）
contract/                  型定義（model.py / exit_codes.py）
```

**`domain → adapters` の単方向のみ許可し、逆は禁止**（ADR-004 設計原則: 決定論的部分と確率的部分の分離）。新しいモジュールを追加する際、副作用を持つなら `adapters/`、持たないなら `domain/` に置く。

## 何を作ろうとしているか

技術ブログの RSS を週次で取得し、LLM トリアージを通して Raindrop.io へ自動投入する CLI（`feed-triage`）。

> **`docs/.ref/spec.md` は起点となった参照資料であり、正典ではない。** 下記2点は ADR により覆っているため、`.ref` の記述をそのまま実装に持ち込まないこと（差異の解消は TASK-026 / TASK-049）。
> - `claude -p` によるスコアリング → **Anthropic API の直接呼び出し**（[ADR-001](docs/04_decisions/ADR-001_llm_invocation_method.md)）
> - `state.sqlite`（`url` を PRIMARY KEY） → **追記専用の JSONL**（[ADR-005](docs/04_decisions/ADR-005_state_file_format.md)）

想定フローは「feeds.yaml ロード → 全フィード取得 → 状態と突合して評価対象を抽出 → 各エントリを LLM で 0-10 にスコアリング → `score + source weight >= 5` を Raindrop API へ POST → 投入しなかったものも含め全件を状態に記録 → サマリ出力」。

設計上の要点：

- **冪等性が第一の受け入れ基準**。一意制約は DB ではなく**アプリ側で担保する**（ADR-005 のトレードオフ）。突合時に url をキーとする辞書を構築し、追記前に照合する。
- **状態は追記専用**。同一 url の行が複数存在しうるため、現在の状態は **url ごとに `evaluated_at` が最大の行**として再構成する（ADR-005 OQ-001）。行順に依存してはならない（push 競合時の rebase で順序が保証されないため）。
- **閾値以下のエントリも score 付きで記録する**。後から閾値を検証するための実測データであり、省略すると R-006 が満たせなくなる。
- **LLM の応答は untrusted input として扱う**。構造化出力を用いるためスキーマ違反は起きないが、**値の意味的不正（範囲外スコア）は残る**。範囲外のスコアを投入判定に用いてはならない（F-001 AC-029）。パース失敗・API 障害は1回リトライし、再失敗はスキップして失敗回数とともに記録する。例外でプロセスを落としてはならない（REQ-F-010）。
- **評価失敗は失敗回数が上限に達するまで次回実行で再評価する**（F-001 AC-018 / AC-019）。1回の失敗で恒久的に取りこぼしてはならない。
- **dry-run フラグ**で投入をスキップしスコアのみ出力できること。dry-run では状態を更新しない（F-005 AC-004）。
- **フィード取得は `httpx` で行い、バイト列を `feedparser` に渡す。** `feedparser.parse(url)` の URL モードは使わない（未修正の SSRF・メモリ枯渇 issue があるため → ADR-004 補遺B）。
- `docs/.ref/feeds.yaml` の各ソースは全て `verified: false`。実装時に HTTP 200 + 有効な RSS/Atom を全件疎通確認して yaml を更新する（AC-4）。`snowflake-blog` の URL には要確認 TODO が付いている。
- 秘匿値は `RAINDROP_TOKEN`（Bearer）と投入先コレクション ID。GitHub Actions では secrets 経由で渡す。

**要合意（勝手に変えない）:** `profile.md` のトリアージ基準、閾値 `5`、投入先コレクション構造。**委任可能:** `triage.py` の実装、workflow 定義、state スキーマ詳細、リトライ戦略。

スコープ外（YAGNI）として明示されているもの: 記事本文の取得・要約、フィードの自動発見/OPML インポート、重み・閾値の自動チューニング、Slack 等への通知。

## ドキュメント体系

`docs/` は 5 層構造で、各層の責務と ID プレフィックスが厳密に分かれている。**層をまたいだ記述の混入がこの体系で最も起きやすい失敗。**

| 層 | 場所 | ID | 答える問い | 書かないこと |
|---|---|---|---|---|
| 要求定義 | `01_requirements/business_requirements.md` | `R-xxx` | なぜ作るか | 解決方法 (How) |
| 要件定義 | `01_requirements/system_requirements.md` | `REQ-F-xxx` / `REQ-NF-xxx` | 満たすべき性質 | 実装の詳細 |
| 機能 | `02_features/F-xxx_*.md` | `F-xxx` | ユーザーが何を"できる"か | 内部動作・実装詳細 |
| 仕様 | `03_specs/SPEC-xxx_*.md` | `SPEC-xxx` | 具体的にどう動くか | ユーザーゴールの定義 |
| 意思決定 | `04_decisions/ADR-xxx_*.md` | `ADR-xxx` | なぜその設計にしたか | 実装手順 |

現状（最新は `docs/README.md` のドキュメント進捗表を参照する）:

| 層 | 状態 |
|---|---|
| `01_requirements/` | 上流2層と両チェックリストを記述済み（`draft`）。独立レビューの指摘を反映済み |
| `02_features/` | F-001〜005 を作成済み（`draft`）。AC 計 109 件 |
| `03_specs/` | **未着手。** `_template.md` のみ |
| `04_decisions/` | ADR-001〜005。うち **002 / 004 / 005 が `accepted`**、001 / 003 が `proposed` |

**タスク・未解決事項は `docs/README.md` のタスク一覧が単一の情報源**。件数のサマリーも同ファイルにある。

- **ドキュメントを生成・レビューする作業に入る前に `docs/SKILL.md` を読む。** 種別ごとの必要コンテキスト、生成時の禁止事項、レビュー報告フォーマットがそこに定義されている。
- **粒度・境界の判断は `docs/05_guides/granularity_guide.md` に従う。** F/SPEC/ADR の分割統合ルール（Rule F-1〜4 / S-1〜4 / ADR-1〜4 / B-1〜4）と早見表、アンチパターン集がある。SKILL.md にあるのは概要のみ。
- 各種別の生成・レビュー用プロンプトは `docs/05_guides/prompts/` に種別ごとのファイルとして置かれている。

## ドキュメント作業時の規約

- **トレーサビリティ:** 各ドキュメントに `traces:` セクションを設け、上位・下位の ID を明示する。F と SPEC は 1:1 にしない（1F が複数 SPEC を持つ、複数 F が 1 SPEC を共有、どちらも自然）。
- **タスク・OQ は必ず `docs/README.md` のタスク一覧に登録する。** OQ 発生時、チェックリストに未検討項目がある時、レビューで「要確認」が出た時、ADR の後続アクション定義時が登録トリガー。`resolved` / `wontfix` になっても行は消さずステータスを更新して残す。一覧を更新したらサマリーの件数も手動で合わせる。
- **新出のドメイン用語は `docs/00_glossary.md` に追記する。** 既存用語と意味が重複する場合は正式名称を統一する。
- **`YYYY-MM-DD` プレースホルダーは生成時の実際の日付に置き換える。**
- **ステータス遷移:** `draft` → `reviewing` → `approved`（廃止時 `deprecated`）。`reviewing` に上げる前に、そのドキュメントの完了チェックリスト全項目と、由来するタスクの全件登録を確認する。
- **独立検証:** `approved` に上げる前に `docs/05_guides/prompts/independent_review.md` を、**執筆に使ったセッションとは別のセッション／サブエージェント**で実行する。セルフレビューは執筆時の暗黙の前提を引き継ぐため検出力が低い、というのがこの体系の明示的な前提。
- **セクションの必須/任意化の判断は保留する。** F/SPEC/ADR の実文書がそれぞれ 5 本以上溜まるまで、テンプレートのどのセクションを任意化するかを推測で決め打ちしない。

## 生成時の禁止事項（SKILL.md より）

- 受け入れ基準から `[正常系]` `[エラー系]` `[境界値]` `[権限]` のカテゴリを省略しない
- フロー定義表から例外系を省略しない（「後で追記」は不可）。例外系は 9 項目を必ず確認する: 未認証 / 権限違反 / 必須項目未入力 / 最大値超過 / 空文字 NULL / 外部システム障害 / タイムアウト / 同時操作競合 / リソース不存在
- 入力定義の「NULL・空文字の扱い」列を全項目に記載する（空欄にしない）
- 成功基準を定性的な表現（「改善する」「使いやすくする」）で書かない。定量値・測定方法・計測タイミングをセットで書く
- 非機能要件の数値には必ず根拠を記載する（「なんとなく 2 秒」は不可）
- テスト観点には「反証可能性（どう壊せばレッドになるか）」を明記する。「〜を確認する」としか書けない観点は AC 自体かテスト設計を見直す
