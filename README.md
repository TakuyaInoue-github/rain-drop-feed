# feed-triage

技術ブログの RSS を週次で取得し、LLM トリアージを通して学習価値の高い記事だけを
[Raindrop.io](https://raindrop.io) へ自動投入する CLI。

手動の巡回に依存していた記事収集を無人化し、「読む価値のあるものが自動で溜まっている」
状態を作ることを目的にしている。

## 何をするか

```
feeds.yaml の情報源を取得
  → 状態と突合して未評価のものを抽出
  → 各記事を LLM が 0-10 でスコアリング
  → score + 情報源の重み >= 5 なら Raindrop へ投入
  → 投入しなかったものも含め全件を記録
  → 実行サマリを出力
```

GitHub Actions で毎週日曜 21:17 UTC（月曜 06:17 JST）に実行される。
処理済みの状態は orphan branch `state` に JSONL で蓄積される。

**現在 58 の情報源**を購読している（クラウドベンダー、企業テックブログ、
設計・関数型プログラミング・処理系の個人ブログ、Hacker News の絞り込みフィード）。

## 使い方

### 必要なもの

- Python 3.10 以上
- [uv](https://docs.astral.sh/uv/)
- Anthropic API キー
- Raindrop.io のトークンと投入先コレクション ID

### セットアップ

```bash
uv sync --extra dev
```

環境変数を設定する。

| 変数 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | 記事の評価に使う |
| `RAINDROP_TOKEN` | Raindrop への投入に使う（Bearer トークン） |
| `RAINDROP_COLLECTION_ID` | 投入先のコレクション |

### 実行

```bash
uv run feed-triage              # 取得・評価・投入まで行う
uv run feed-triage --dry-run    # 投入せず評価結果とサマリだけ出す
uv run feed-triage --verbose    # 処理経過の詳細ログを出す
```

`--dry-run` は状態を更新しないため、閾値やトリアージ基準を調整するときに
同じ記事を何度でも評価し直せる（そのぶん評価コストは毎回かかる）。

### 終了コード

無人実行で異常を検知できるよう、失敗の種類ごとに分けている。

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 投入対象がすべて失敗した |
| 2 | 設定の不備（環境変数・`feeds.yaml`・`profile.md`） |
| 3 | 状態の永続化に失敗した |
| 4 | API リクエストの仕様不正（実装の是正が必要） |
| 5 | すべての情報源から取得できなかった |
| 6 | すべての評価が失敗した |

## 設定

### `feeds.yaml` — 購読する情報源

```yaml
sources:
  - name: netflix-tech
    url: https://netflixtechblog.com/feed
    weight: +1      # LLM スコアへの事前補正（+1 / 0 / -1）
    tags: [eng-blog]
    verified: true  # HTTP 200 + 有効な RSS/Atom を確認済み
```

`weight` は一次情報の設計解説が多い情報源を優遇し、告知の比率が高いものを
減点するために使う。追加するときは実際に取得して `verified: true` にする。

> **注意:** ローカルで取得できても GitHub Actions のランナーからは弾かれる
> ことがある（Substack や一部 CDN はデータセンター IP を拒否する）。
> 追加後の初回実行で結果を確認すること。

### `profile.md` — トリアージ基準

LLM に渡す評価基準。「どういう記事を学習価値が高いと判断するか」を記述する。
スコアの分布が偏るときは、閾値より先にこちらを見直すことが多い。

## 開発

```bash
uv run pytest -q           # テスト
uv run pytest -q --cov     # カバレッジ（閾値 80%）
uv run ruff check .        # lint
uv run mypy src            # 型チェック（strict）
uv run lint-imports        # 層構造の依存方向チェック
```

CI はこの4つを Python 3.10 / 3.12 で実行する。**コード変更後はすべて通してから
完了とすること。**

### 構成

`src/feed_triage/` は4層で、依存方向を `import-linter` が強制する。

```
cli.py                     argparse → RunOptions 構築、出力のみ
pipeline.py                run(options) -> RunSummary（I/O なし）
implementation/domain/     副作用のないロジック
implementation/adapters/   副作用の隔離（取得・評価・投入・永続化）
contract/                  型定義
```

`domain → adapters` の単方向のみ許可している。決定論的な部分と確率的な部分を
分離するためで、新しいモジュールは副作用を持つなら `adapters/`、持たないなら
`domain/` に置く。

### コードレビュー

[code-review-toolkits](https://github.com/TakuyaInoue-github/code-review-toolkits) の
`diff-review` を使う。pre-push hook は git 管理外なので clone 後に各自インストールする。

```bash
cp scripts/pre-push "$(git rev-parse --git-path hooks)/pre-push"
chmod +x "$(git rev-parse --git-path hooks)/pre-push"
```

## ドキュメント

設計と意思決定の記録は [`docs/`](docs/) にある。5層構造で、それぞれ答える問いが違う。

| 層 | 場所 | 答える問い |
|---|---|---|
| 要求定義 | [`01_requirements/business_requirements.md`](docs/01_requirements/business_requirements.md) | なぜ作るか |
| 要件定義 | [`01_requirements/system_requirements.md`](docs/01_requirements/system_requirements.md) | 満たすべき性質 |
| 機能 | [`02_features/`](docs/02_features/) | ユーザーが何を"できる"か |
| 仕様 | [`03_specs/`](docs/03_specs/) | 具体的にどう動くか |
| 意思決定 | [`04_decisions/`](docs/04_decisions/) | なぜその設計にしたか |

[`docs/README.md`](docs/README.md) が各層への入口で、未解決事項とタスクの
一覧もそこにある。

設計上の主要な判断は以下に記録している。

- [ADR-001](docs/04_decisions/ADR-001_llm_invocation_method.md) — LLM の呼び出しを Anthropic API 直接にした理由
- [ADR-002](docs/04_decisions/ADR-002_state_persistence.md) — 状態を専用ブランチへのコミットで永続化する
- [ADR-003](docs/04_decisions/ADR-003_triage_model_selection.md) — 評価モデルの選定
- [ADR-004](docs/04_decisions/ADR-004_implementation_stack.md) — 実装スタックと層構造
- [ADR-005](docs/04_decisions/ADR-005_state_file_format.md) — 状態を追記専用の JSONL で保持する

## 設計上の要点

- **冪等性が第一の受け入れ基準。** 同じ記事を二度投入しない。一意制約は DB ではなく
  アプリ側で担保する（状態は追記専用の JSONL のため）
- **状態は url ごとに `evaluated_at` が最大の行**として再構成する。行順に依存しない
  （push 競合時の rebase で順序が保証されないため）
- **閾値以下の記事も score 付きで記録する。** 後から閾値を検証するための実測データ
- **LLM の応答は untrusted input として扱う。** 範囲外のスコアを投入判定に用いない。
  パース失敗・API 障害は1回リトライし、再失敗はスキップして失敗回数とともに記録する
- **評価失敗は上限に達するまで次回実行で再評価する。** 1回の失敗で恒久的に取りこぼさない
- **評価コストの算出は節約ではなく異常検知が目的。** モデル誤指定やリトライ暴走に
  気づく契機が、週次の無人実行ではサマリしかない

## スコープ外

意図的に作らないもの（YAGNI）。

- 記事本文の取得・要約
- フィードの自動発見 / OPML インポート
- 重み・閾値の自動チューニング
- Slack 等への通知
