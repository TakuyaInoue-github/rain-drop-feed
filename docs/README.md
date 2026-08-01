# プロジェクト名: rain-drop-feed
<!-- template: project-spec-templates v1.0.0-5-gb2775e3 (deployed: 2026-07-26) -->

> **一行サマリー:** 技術ブログの RSS を週次で自動取得し、LLM によるトリアージを通して
> 学習価値の高い記事だけを Raindrop.io へ投入することで、手動の巡回に依存していた
> 収集レイヤーへの供給を無人化する CLI。

---

## ドキュメント構成

```
docs/
├── SKILL.md                         # Claude Code スキル定義（生成・レビューの指示）
├── README.md                        # このファイル（ナビゲーション）
├── 00_glossary.md                   # 用語定義
├── 01_requirements/
│   ├── business_requirements.md     # 要求定義 (R-xxx)
│   ├── system_requirements.md       # 要件定義 (REQ-F-xxx / REQ-NF-xxx)
│   ├── enterprise_checklist.md      # 非機能・品質観点チェックリスト（全種別共通）
│   └── application_checklist.md    # アプリ種別チェックリスト（Web / GUI / CUI）
├── 02_features/
│   ├── _template.md                 # 機能テンプレート
│   └── F-001_*.md                   # 機能ごとのファイル
├── 03_specs/
│   ├── _template.md                 # 仕様テンプレート
│   └── SPEC-001_*.md                # 仕様ごとのファイル
├── 04_decisions/
│   ├── _template.md                 # ADRテンプレート
│   └── ADR-001_*.md                 # 意思決定記録
└── 05_guides/
    ├── granularity_guide.md         # F-xxx / SPEC-xxx / ADR-xxx の粒度・境界ガイド
    └── llm_prompts.md               # Claude Code 用プロンプト集
```

### Claude Code での使い方

```
① Claude Code に「docs/SKILL.md を読んでください」と指示する
        ↓
② 05_guides/llm_prompts.md から目的のプロンプトをコピー
        ↓
③ [...] を埋めて実行
```

| やりたいこと | 使うプロンプト |
|---|---|
| 要求定義の初稿を書く | [prompts/business_requirements.md](05_guides/prompts/business_requirements.md) |
| 要件定義の初稿を書く | [prompts/system_requirements.md](05_guides/prompts/system_requirements.md) |
| 機能の初稿を書く | [prompts/feature.md](05_guides/prompts/feature.md) |
| 仕様の初稿を書く | [prompts/spec.md](05_guides/prompts/spec.md) |
| ADRを書く | [prompts/adr.md](05_guides/prompts/adr.md) |
| ドキュメントをレビューする | 各プロンプトファイルの「レビュー」セクション |
| F/SPECの粒度を確認する | [prompts/feature.md §粒度チェック](05_guides/prompts/feature.md#粒度チェック単体) |
| 例外系の網羅性を確認する | [prompts/spec.md §例外系チェック](05_guides/prompts/spec.md#例外系の網羅性チェック単体) |

### チェックリストの使い方

```
① enterprise_checklist.md    すべてのアプリケーションで記入する（共通ベースライン）
        ↓
② application_checklist.md   自分のアプリ種別の該当セクションを記入する
   ├── Section 1: Web
   ├── Section 2: Local GUI
   └── Section 3: Local CUI / CLI
```

---

## 層の定義と責務

| 層 | ファイル | IDプレフィックス | 問いに答える |
|---|---|---|---|
| **要求定義** | `01_requirements/business_requirements.md` | `R-xxx` | なぜ作るか・誰が困っているか |
| **要件定義** | `01_requirements/system_requirements.md` | `REQ-F-xxx` / `REQ-NF-xxx` | システムが満たすべき性質・制約 |
| **機能** | `02_features/F-xxx_*.md` | `F-xxx` | ユーザーが何を"できる"か |
| **仕様** | `03_specs/SPEC-xxx_*.md` | `SPEC-xxx` | システムが具体的にどう動くか |
| **意思決定** | `04_decisions/ADR-xxx_*.md` | `ADR-xxx` | なぜその設計にしたか |

> **F/SPEC/ADRの粒度・境界に迷ったら:** [05_guides/granularity_guide.md](05_guides/granularity_guide.md) を参照する。

---

## トレーサビリティマップ

> 各ドキュメントに `traces:` セクションを設け、上位・下位のIDを明示する。

```
R-001 ビジネス課題
  └─ REQ-F-001 機能要件
        └─ F-001 機能
              └─ SPEC-001 仕様A
              └─ SPEC-002 仕様B
  └─ REQ-NF-001 非機能要件（パフォーマンス）
```

---

## ステータス定義

| ステータス | 意味 |
|---|---|
| `draft` | 作成中・未レビュー |
| `reviewing` | レビュー中 |
| `approved` | 合意済み・基準線 |
| `deprecated` | 廃止・後継あり |

---

## ドキュメント進捗

| 層 | ファイル | ステータス | 備考 |
|---|---|---|---|
| 要求定義 | [business_requirements.md](01_requirements/business_requirements.md) | `draft` | R-001〜R-008 を定義済み。独立レビュー（TASK-020）の指摘を反映済み（v0.3.0） |
| 要件定義 | [system_requirements.md](01_requirements/system_requirements.md) | `draft` | REQ-F-001〜011 / REQ-NF-001〜008 を定義済み。独立レビューの指摘を反映済み（v0.3.0） |
| 非機能チェックリスト | [enterprise_checklist.md](01_requirements/enterprise_checklist.md) | `draft` | 全100項目記入済み（未検討6件は TASK 化） |
| アプリ種別チェックリスト | [application_checklist.md](01_requirements/application_checklist.md) | `draft` | CLI (Section 3) を適用。未検討4件は TASK 化 |
| 用語定義 | [00_glossary.md](00_glossary.md) | - | 上流2層で使用する用語を定義済み |
| 機能 (F-xxx) | `02_features/` | `draft` | F-001〜005 を作成済み。独立レビューの指摘を反映済み（各 v0.2.0）。AC 計 109 件 |
| 仕様 (SPEC-xxx) | `03_specs/` | 着手 | 全6本構成のうち **4本を執筆済み**（001 / 002 / 003 / 004）。SPEC-002 はレビュー反映済み（v0.4.0）、001 / 003 / 004 はレビュー待ち（TASK-086）。SPEC-005 / 006 は未着手 |
| 意思決定 (ADR-xxx) | `04_decisions/` | 一部確定 | **ADR-002 / 004 / 005 が `accepted`**（状態の永続化方式・形式、実装スタック）。ADR-001 / 003 は `proposed`（TASK-024 / TASK-023 が未決） |

---

## 機能一覧

| ID | 機能名 | ステータス | 担当 | 対応要件 |
|---|---|---|---|---|
| [F-001](02_features/F-001_triage_and_ingest.md) | 新着記事を選別して収集レイヤーへ投入する | `draft` | t_inoue | REQ-F-001, 002, 003, 004, 005, 006, 010 |
| [F-002](02_features/F-002_scheduled_execution.md) | 週次で無人実行される | `draft` | t_inoue | REQ-F-011 |
| [F-003](02_features/F-003_verify_triage_criteria.md) | 投入されなかった記事の評価結果を後から検証する | `draft` | t_inoue | REQ-F-007 |
| [F-004](02_features/F-004_execution_summary.md) | 実行結果のサマリで供給状況を把握する | `draft` | t_inoue | REQ-F-008 |
| [F-005](02_features/F-005_dry_run.md) | 投入せずに選別結果を確認する | `draft` | t_inoue | REQ-F-009 |

---

## 仕様一覧

> 全6本の構成で進める。SPEC-002（状態管理）を先行して執筆し、独立レビュー（TASK-066）を
> 経てから残り5本を書く方針。

| ID | 仕様名 | ステータス | 担当 | 対応機能 |
|---|---|---|---|---|
| [SPEC-001](03_specs/SPEC-001_feed_fetching.md) | フィード取得・エントリ抽出 | `draft`（レビュー反映済み v0.6.0） | t_inoue | F-001, F-002, F-004, F-005 |
| [SPEC-002](03_specs/SPEC-002_state_management.md) | 処理済み状態の記録・突合・永続化 | `draft`（レビュー反映済み v0.7.0） | t_inoue | F-001, F-002, F-003, F-005 |
| [SPEC-003](03_specs/SPEC-003_entry_evaluation.md) | エントリ評価（トリアージ） | `draft`（レビュー反映済み v0.5.0） | t_inoue | F-001, F-005 |
| [SPEC-004](03_specs/SPEC-004_ingestion.md) | 収集レイヤーへの投入・タグ付与 | `draft`（レビュー反映済み v0.5.0） | t_inoue | F-001 |
| [SPEC-005](03_specs/SPEC-005_cli.md) | CLI インターフェースと起動時検証 | `draft` | t_inoue | F-001, F-002, F-005 |
| [SPEC-006](03_specs/SPEC-006_execution_summary.md) | 実行サマリの出力 | `draft`（レビュー反映済み v0.2.0） | t_inoue | F-004, F-005 |

---

## 意思決定一覧

| ID | タイトル | ステータス | 決定日 | 関連 |
|---|---|---|---|---|
| [ADR-001](04_decisions/ADR-001_llm_invocation_method.md) | トリアージのLLM呼び出しに Anthropic API を直接使用する | `proposed` | 2026-07-26 | REQ-F-003, REQ-NF-002a, REQ-F-011 |
| [ADR-002](04_decisions/ADR-002_state_persistence.md) | 処理済み状態を専用ブランチへのコミットで永続化する | **`accepted`** | 2026-07-26 | REQ-F-002, REQ-F-007, REQ-NF-003, REQ-NF-004, ADR-005 |
| [ADR-003](04_decisions/ADR-003_triage_model_selection.md) | トリアージの評価モデルに Claude Haiku 4.5 を採用する（暫定） | `proposed` | 2026-07-26 | ADR-001, REQ-F-003, REQ-NF-002a |
| [ADR-004](04_decisions/ADR-004_implementation_stack.md) | 実装スタックを diff-review リポジトリの構成に揃える | **`accepted`** | 2026-07-26 | REQ-NF-008, ADR-001, ADR-005 |
| [ADR-005](04_decisions/ADR-005_state_file_format.md) | 処理済み状態を追記専用の JSONL で保持する | **`accepted`** | 2026-07-26 | ADR-002, REQ-F-002, REQ-F-007 |

---

## タスク・未解決事項一覧

> **運用ルール:**
> - 各ドキュメントでタスク・OQが発生したら **必ずここに追記する**
> - ドキュメントを `reviewing` に上げる前に、そのドキュメント由来のタスクが全件登録されていることを確認する
> - `resolved` / `wontfix` になったタスクは行を消さず、ステータスを更新して残す（経緯の記録）
> - `wontfix` には必ず理由を備考欄に記入する

### ステータス定義

| ステータス | 意味 |
|---|---|
| `open` | 未着手・未解決 |
| `in-progress` | 対応中 |
| `resolved` | 解決済み |
| `wontfix` | 対応しないと決定 |

### サマリー

| `open` | `in-progress` | `resolved` | `wontfix` |
|---|---|---|---|
| 44 | 4 | 49 | 1 |

> サマリーの件数は一覧を更新するたびに手動で合わせる。

### 一覧

> **種別:**
> `OQ` 未解決の問い / `CL` チェックリスト未検討項目 / `IMPL` 実装タスク / `DOC` ドキュメントタスク

| ID | 種別 | タイトル | 発生元 | 担当 | 期限 | ステータス | 備考 |
|---|---|---|---|---|---|---|---|
| TASK-001 | `OQ` | 現状値（巡回の途切れ・登録数の振れ）の実測ベースラインを確定する | [business_requirements §OQ-001](01_requirements/business_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-09 | `open` | 実測を断念する場合も「稼働後の実測のみで評価する」と明記して閉じる |
| TASK-002 | `OQ` | 週20本に到達しない場合の方針（フィード追加 or 閾値引き下げ）を決める | [business_requirements §OQ-002](01_requirements/business_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 稼働2週間の実測を待って判断する |
| TASK-003 | `OQ` | トリアージ基準 (`profile.md`) をどの層で管理するか決める | [business_requirements §OQ-003](01_requirements/business_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-09 | `open` | R-003 の成否がこの基準の質に依存する |
| TASK-004 | `OQ` | 収集レイヤー (Raindrop) が利用不能になった場合の撤退・移行基準を定めるか | [business_requirements §OQ-004](01_requirements/business_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-09-30 | `open` | 優先度は低い。前提が崩れた際の判断材料として |
| TASK-005 | `OQ` | 処理済み状態の永続化方式を決定し ADR 化する | [system_requirements §OQ-001](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: [ADR-002](04_decisions/ADR-002_state_persistence.md) を **`accepted`**。**状態専用の orphan branch `state` へ `state.jsonl` をコミットする**方式。形式は [ADR-005](04_decisions/ADR-005_state_file_format.md) に分離し同日 `accepted` |
| TASK-006 | `OQ` | 評価失敗エントリを処理済みとするか、次回再試行対象として残すか決める | [system_requirements §OQ-002](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **回数制限付きで再試行する**。失敗回数を状態に持ち、上限（暫定3回 → TASK-053）に達するまで次回実行で再評価。一時障害による恒久的取りこぼしと、壊れたエントリの無限リトライの両方を回避 |
| TASK-007 | `OQ` | 1エントリあたりの評価所要時間を実測し、実行時間目標を確定する | [system_requirements §OQ-003](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-26 実測: 1件 2.7〜4.8秒、100件で5〜8分。目標30分は妥当 |
| TASK-008 | `OQ` | 定期実行環境で `claude -p` が利用可能か検証する | [system_requirements §OQ-004](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-09 | `in-progress` | 2026-07-26: ローカル非対話実行とJSON応答・判定精度を確認。Actions 上の認証手段は未確認（→ TASK-021） |
| TASK-021 | `OQ` | 評価の呼び出し方式（`claude` CLI vs Anthropic API 直接）を ADR で決定する | [system_requirements §OQ-006](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-09 | `in-progress` | [ADR-001](04_decisions/ADR-001_llm_invocation_method.md) を `proposed` で起票。独立レビュー後に改訂（認証の事実誤認を訂正、選択肢を5案に再構成）。API 直接を維持。`accepted` で resolved にする |
| TASK-023 | `OQ` | 使用モデルを確定する（Haiku 4.5 vs Sonnet 5） | [ADR-003](04_decisions/ADR-003_triage_model_selection.md) | t_inoue | 2026-08-23 | `in-progress` | ADR-001 から分離し [ADR-003](04_decisions/ADR-003_triage_model_selection.md) として起票。**Haiku 4.5 を暫定採用**。独立レビューで n=5 の外挿が不当と指摘され、投入率の推定を判断根拠から削除。実フィード20〜30件で再検証が必要 |
| TASK-024 | `OQ` | 構造化出力を前提としたリトライ戦略を確定する | [ADR-001 §OQ-001](04_decisions/ADR-001_llm_invocation_method.md#未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **暫定 1 回で確定（実測後に見直す）**。意味的不正は再試行で直ることがあるが2回以上はコストが線形に増えるだけ。**API 呼び出し自体の失敗は SDK の既定リトライに委ね追加しない**（二重リトライで REQ-NF-001 の30分を圧迫するため）。あわせて SDK の `max_retries` を明示指定する。**見直し条件:** 評価失敗件数が定常的に非0なら `error_detail` の内訳で判断 |
| TASK-025 | `IMPL` | `ANTHROPIC_API_KEY` を GitHub Secrets に登録する | [ADR-001 §後続アクション](04_decisions/ADR-001_llm_invocation_method.md#後続アクション) | t_inoue | 2026-08-09 | `open` | ADR-001 が `accepted` になってから実施する |
| TASK-026 | `DOC` | `.ref/spec.md` の構成記述と ADR-001 の差異を SPEC 層に反映する | [ADR-001 §後続アクション](04_decisions/ADR-001_llm_invocation_method.md#後続アクション) | t_inoue | 2026-08-23 | `open` | `.ref` は `claude -p` 前提の構成図を持つ。SPEC 作成時に解消する |
| TASK-027 | `IMPL` | `blef-fr` のフィードURLを修正する（現URLは HTTP 404） | [system_requirements §REQ-NF-002a](01_requirements/system_requirements.md#req-nf-002a-評価コストの上限) | t_inoue | 2026-08-09 | `wontfix` | **理由: 当該サイトがフィードを提供していないため修正不能。** 2026-07-26 の疎通確認で 404 が判明し、同日の追加調査で候補6件（`/rss` `/feed` `/rss.xml` `/index.xml` `www.blef.fr/rss/` 等）も全て 404、トップページの HTML にも feed の link 要素なし。運用者確認でもフィード提供なしと判断。**情報源から削除**（14件 → 13件）し、`.ref/feeds.yaml` に経緯をコメントとして残した。`.ref/spec.md` AC-4（全件疎通確認）は「確認の上で除外した」形で満たす |
| TASK-028 | `OQ` | 1回の実行で評価する件数の上限を決める | [system_requirements §OQ-007](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **暫定 200 件で確定（実測後に見直す）**。実測（評価1件 2.7〜4.8秒）から200件で9〜16分、REQ-NF-001 の30分内。週31〜49件・上振れ100件に対し2倍の余裕があり、**上限到達自体が異常の兆候**として機能する。`domain/state.py` の `DEFAULT_EVALUATION_LIMIT` に定数化。**見直し条件:** サマリの持ち越し件数が2回連続で非0 |
| TASK-029 | `OQ` | 全文配信フィードの要約切り詰め上限（文字数）を決める | [system_requirements §OQ-008](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **暫定 4,000 文字で確定（実測後に見直す）**。実測の全文配信2件（8,800字・9,238字）は超えるが、**トリアージに必要なのは主題と論の方向であり冒頭数千字で判断できる**。入力トークン約1,500相当で REQ-NF-002a の試算の3倍内。**元の要約は切り詰めず投入される**ため（excerpt 上限10,000）F-003 の事後検証で全文を参照できる |
| TASK-030 | `OQ` | 状態ファイルの形式（SQLite / JSONL / CSV）を決める | [ADR-002 §OQ-001](04_decisions/ADR-002_state_persistence.md#未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **追記専用の JSONL を採用**（→ [ADR-005](04_decisions/ADR-005_state_file_format.md)）。ADR-002 の採用理由「履歴が監査証跡を兼ねる」が SQLite では成立しないことが決め手 |
| TASK-049 | `DOC` | `.ref/spec.md` の `state.sqlite` 指定との差異を SPEC 層に反映する | [ADR-005 §後続アクション](04_decisions/ADR-005_state_file_format.md#後続アクション) | t_inoue | 2026-08-23 | `open` | `.ref` は SQLite + `url` PRIMARY KEY を前提とした記述を持つ。TASK-026 と同種の差異 |
| TASK-050 | `OQ` | 同一 URL が複数行現れた場合の読み取り規則を定める | [ADR-005 §OQ-001](04_decisions/ADR-005_state_file_format.md#未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **各行に `evaluated_at` を持たせ、URL ごとに最大値の行を正とする**。行順ではなくタイムスタンプで決めることで ADR-002 OQ-004 の「順序に意味がない」と両立する。SPEC への明示が残作業 |
| TASK-061 | `DOC` | F-003 OQ-001 を `resolved` に更新し、AC-013 が ADR-005 の読み取り規則に従属することを明記する | [ADR-005 §後続アクション](04_decisions/ADR-005_state_file_format.md#後続アクション) | t_inoue | 2026-08-23 | `open` | TASK-030 は resolved だが F-003 の OQ 表が `open` のまま。`approved` 昇格時に矛盾する |
| TASK-051 | `IMPL` | 一意制約をアプリ側で担保する処理を SPEC に明示し、テスト観点に含める | [ADR-005 §後続アクション](04_decisions/ADR-005_state_file_format.md#後続アクション) | t_inoue | 2026-08-23 | `open` | JSONL は DB のような一意制約を持たない。R-002（重複ゼロ）に直結するため実装とテストで担保する |
| TASK-052 | `DOC` | ADR-005 の独立レビューを実施する | [ADR-005 §完了チェックリスト](04_decisions/ADR-005_state_file_format.md#完了チェックリスト) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26 実施。中核前提の誤り（「更新が稀」が REQ-F-010 と矛盾）と事実誤認2件（textconv / ADR-002 への誤帰属）を検出し全件反映。→ [補遺A](04_decisions/ADR-005_state_file_format.md#補遺a-独立レビューの記録2026-07-26) |
| TASK-053 | `OQ` | 評価失敗の再試行回数の上限を確定する（暫定3回） | [system_requirements §OQ-002](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **暫定 3 回（総試行回数）で確定（実測後に見直す）**。実行内リトライ1回と組み合わさり**実質2週分の追跡**。一時障害は週をまたげば解消することが多く、恒久的に壊れたエントリを3週以上追うのはコスト増のみ。`DEFAULT_MAX_FAILURES` に定数化。**見直し条件:** 再評価打ち切り件数が定常的に非0 |
| TASK-031 | `OQ` | 状態ブランチの名称・orphan 化の要否・コミットメッセージ規約を決める | [ADR-002 §OQ-002](04_decisions/ADR-002_state_persistence.md#未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-26: **orphan branch `state`**。コミットメッセージは `chore(state): record <N> entries (<YYYY-MM-DD>)`。`[skip ci]` は不要（`GITHUB_TOKEN` の push は再トリガーしない） |
| TASK-032 | `OQ` | 状態更新のコミット粒度を決める（実行ごと / 投入ごと） | [ADR-002 §OQ-003](04_decisions/ADR-002_state_persistence.md#未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **ローカルには投入直後に追記し、commit + push は実行末尾に1回**。投入ごとの push は週20〜30回となり所要時間・競合確率が悪化。強制終了時の記録喪失は ADR-002 のトレードオフとして受け入れる |
| TASK-033 | `OQ` | push 競合時の挙動を決める（rebase リトライ / 実行失敗 / `concurrency` 直列化） | [ADR-002 §OQ-004](04_decisions/ADR-002_state_persistence.md#未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **`git pull --rebase` + 行マージ + 再 push**（最大3回、全失敗で非0終了）。ADR-005 の JSONL 採用により両方の行を残すマージが成立するため選べた選択肢 |
| TASK-034 | `OQ` | cron の実行時刻を毎時0分から外すか判断する | [ADR-002 §OQ-005](04_decisions/ADR-002_state_persistence.md#未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-26: **外す。月曜 06:17 JST（= 日曜 21:17 UTC）**。公式が高負荷時のドロップを明記しており毎時0分は最も混み合う。0/15/30/45 分も避けた値。REQ-F-011 / F-002 AC-001 に反映済み |
| TASK-035 | `OQ` | 閾値（現在5）の感度を検証する | [ADR-003 §OQ-002](04_decisions/ADR-003_triage_model_selection.md#未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | モデルより閾値のほうが投入件数に効くレバーの可能性。TASK-023 と一体で検証する |
| TASK-036 | `IMPL` | API キーに支出上限を設定し、ワークスペースを分離する | [ADR-001 §後続アクション](04_decisions/ADR-001_llm_invocation_method.md#後続アクション) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26 完了。**専用ワークスペースを作成し、月 $10 の支出上限を設定**。最悪の複合ケース（年 $31.20 = 月 $2.60）に対しても正常運用を妨げず、暴走時には停止する水準。API キーはこのワークスペースを指定して発行する（→ TASK-025） |
| TASK-037 | `CL` | API キーのローテーション方針を定める（S-S03 / OQ-001 のスコープに追加） | [ADR-001 §後続アクション](04_decisions/ADR-001_llm_invocation_method.md#後続アクション) | t_inoue | 2026-08-23 | `open` | enterprise_checklist S-S03 は現在 `-`。対象が Raindrop トークンのみだったため拡張が必要 |
| TASK-038 | `OQ` | REQ-NF-001 の実測根拠を API 直接呼び出しで再測定するか判断する | [ADR-001 §OQ-002](04_decisions/ADR-001_llm_invocation_method.md#未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 現行の根拠は `claude -p` での測定値。安全側のため実害はないが根拠と決定が乖離 |
| TASK-022 | `IMPL` | 評価コストを年 $150 以下に抑える（軽量モデル＋最小システムプロンプト） | [system_requirements §REQ-NF-002a](01_requirements/system_requirements.md#req-nf-002a-評価コストの上限) | t_inoue | 2026-08-23 | `open` | 既定モデルのままだと年 $600。`.ref/spec.md` の「無視できる規模」という前提は実測により否定された |
| TASK-009 | `OQ` | 複数の情報源から同一記事を取得した場合の名寄せ要否を決める | [system_requirements §OQ-005](01_requirements/system_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 公式ブログと HN の重複が想定される |
| TASK-010 | `CL` | 機械可読出力（`--json` 等）の提供要否を判断する | [application_checklist §C-I05](01_requirements/application_checklist.md#32-インターフェース設計) | t_inoue | 2026-08-23 | `open` | - |
| TASK-011 | `CL` | カラー出力の要否と `NO_COLOR` 対応を判断する | [application_checklist §C-I06](01_requirements/application_checklist.md#32-インターフェース設計) | t_inoue | 2026-08-23 | `open` | - |
| TASK-012 | `CL` | シグナルハンドリング / グレースフル終了の実装要否を判断する | [application_checklist §C-I07](01_requirements/application_checklist.md#32-インターフェース設計), [enterprise_checklist §R-G02](01_requirements/enterprise_checklist.md#23-縮退動作グレースフルデグレード) | t_inoue | 2026-08-09 | `open` | 2つのチェックリストで同一論点。TASK-005 と併せて判断する |
| TASK-013 | `CL` | 設定ファイル・状態ファイルの配置方針（XDG 準拠 or リポジトリ内固定）を決める | [application_checklist §C-F01](01_requirements/application_checklist.md#34-設定ファイル管理) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **リポジトリ内固定**。状態は orphan branch `state` のルート直下に `state.jsonl`（→ [ADR-005](04_decisions/ADR-005_state_file_format.md) OQ-002）。設定（`feeds.yaml` / `profile.md`）は既定ブランチのリポジトリ内。XDG 準拠は採らない（状態が Git 管理下にあるため） |
| TASK-014 | `CL` | Raindrop トークンのローテーション方針を定めるか判断する | [enterprise_checklist §S-S03](01_requirements/enterprise_checklist.md#15-シークレット管理) | t_inoue | 2026-08-23 | `open` | - |
| TASK-015 | `CL` | 依存ライブラリの脆弱性スキャン導入要否を判断する | [enterprise_checklist §S-SC01](01_requirements/enterprise_checklist.md#17-サプライチェーン依存ライブラリ), [ADR-004 §後続アクション](04_decisions/ADR-004_implementation_stack.md#後続アクション) | t_inoue | 2026-08-23 | `open` | **feedparser に未修正の security issue が3件残る**（SSRF / メモリ枯渇 / ReDoS。うち SSRF は本システムでは該当しない）。上流の未修正 issue を継続的に検知する必要があるかを、この事実を踏まえて判断する |
| TASK-016 | `CL` | 静的解析（lint / 型チェック / SAST）の CI 組み込み方針を決める | [enterprise_checklist §S-T01](01_requirements/enterprise_checklist.md#18-セキュリティテスト) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: [ADR-004](04_decisions/ADR-004_implementation_stack.md) `accepted`。**ruff / mypy strict / import-linter / カバレッジ80% を Python 3.10・3.12 のマトリクスで CI 実行する**。要件定義 REQ-NF-008「実装品質のゲート」が上位要件。ワークフローの実定義は TASK-054 に含む |
| TASK-054 | `IMPL` | `pyproject.toml` を作成しツールチェーンを導入する | [ADR-004 §後続アクション](04_decisions/ADR-004_implementation_stack.md#後続アクション) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26 完了。`pyproject.toml` / `uv.lock` / CI ワークフローを追加し、ruff・mypy strict・import-linter・pytest（カバレッジ 99.31%）が全て通過することを確認済み |
| TASK-055 | `IMPL` | 本システムの層構造を設計し `import-linter` の契約を定義する | [ADR-004 §OQ-001](04_decisions/ADR-004_implementation_stack.md#未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-26 完了。**契約2本を定義**: (1) `cli → pipeline → implementation → contract` の4層（diff-review の5層から `pipeline`/`cli` の分離を維持しつつ `utilization` は不要と判断し削減）、(2) `implementation` 内部の `domain → adapters`。CI で KEPT を確認済み |
| TASK-056 | `IMPL` | `diff-review` を開発フローに導入する | [ADR-004 §後続アクション](04_decisions/ADR-004_implementation_stack.md#後続アクション) | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **`.diff-review.yml` と `scripts/pre-push` を追加した。** pre-push は `--no-claude`（決定論チェックのみ）とし、LLM レビューは PR 前に手動（`diff-review review --base main`）で回す — push のたびに Claude を呼ぶとコストと待ち時間が積み上がり、hook を迂回する動機になるため（上流 ADR-006 決定事項1に倣う）。**`docs/**` を除外**した（SPEC 層だけで2,000行超あり、ドキュメントのレビューは `independent_review.md` が担うため責務が重複する）。`--ci` は使わない（リポジトリ設定が無視されるため）。**ADR-001 とは矛盾しない** — ADR-001 の対象は「トリアージの LLM 呼び出し」であり、開発ツールは範囲外 |
| TASK-057 | `DOC` | プロジェクト `CLAUDE.md` の「実装コードもツールチェーンも存在しない」節を実コマンドに更新する | [ADR-004 §後続アクション](04_decisions/ADR-004_implementation_stack.md#後続アクション) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26 完了。実コマンド・層構造・ドキュメント進捗を追記し、あわせて `.ref/spec.md` 由来の古い前提（`state.sqlite` / `claude -p`）が ADR で覆っている旨を明記した |
| TASK-058 | `DOC` | ADR-004 の独立レビューを実施する | [ADR-004 §完了チェックリスト](04_decisions/ADR-004_implementation_stack.md#完了チェックリスト) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26 実施。参照元リポジトリとの突き合わせで事実誤認3件（設計原則の数 / 層構造 / ruff 設定）を検出し全件反映。→ [補遺A](04_decisions/ADR-004_implementation_stack.md#補遺a-独立レビューの記録2026-07-26) |
| TASK-059 | `OQ` | フィード取得・パースに使うライブラリを決める | [ADR-004 §OQ-002](04_decisions/ADR-004_implementation_stack.md#未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **`httpx` で取得し `feedparser` にバイト列を渡す**（URL モードは使わない）。一次情報の調査で `defusedxml` は2021年が最終リリースで未保守、feedparser は XXE 対策を自前で持つと判明。真のリスクは SSRF・メモリ枯渇・ReDoS だった → [ADR-004 補遺B](04_decisions/ADR-004_implementation_stack.md#補遺b-フィード取得方式の調査2026-07-26) |
| TASK-060 | `OQ` | Anthropic SDK のバージョンを固定するか範囲指定にするか決める | [ADR-004 §OQ-003](04_decisions/ADR-004_implementation_stack.md#未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-26: **`pyproject.toml` は下限指定、実バージョンは `uv.lock` で固定**（全依存に同方針）。モデル ID は SDK と独立に設定値として持ち、deprecation はモデル ID の変更で追従する |
| TASK-062 | `OQ` | フィード取得時のレスポンスサイズ上限を決定する | [ADR-004 §後続アクション](04_decisions/ADR-004_implementation_stack.md#後続アクション) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **10 MB**。実測の最大フィード（全文配信 9,238 字 ≒ 数十 KB）の3桁上。誤って正常なフィードを落とす確率を実質ゼロにしつつメモリ枯渇の緩和として機能する。13情報源すべてが上限でも 130 MB で標準ランナー（7GB）に対し十分小さく、逐次処理のため実際に同時に載るのは1情報源分のみ |
| TASK-063 | `OQ` | REQ-NF-003 の実行成功率の初期判定規則（実行8回未満時）を定める | [TASK-020 の独立レビュー](05_guides/prompts/independent_review.md) | t_inoue | 2026-08-23 | `open` | 「直近8回のうち7回以上」は稼働4週時点でサンプルが足りない。要求定義 §4 の計測タイミング（稼働4週後）と噛み合っていない |
| TASK-064 | `OQ` | フィード取得タイムアウト30秒の独立した根拠を示す | [TASK-020 の独立レビュー](05_guides/prompts/independent_review.md) | t_inoue | 2026-08-23 | `open` | 現在は「30分に収まるから」で正当化しており、30分の根拠も「タイムアウト合計6.5分だから」で循環参照になっている。稼働後の実測で解消する |
| TASK-065 | `DOC` | `#score-{n}` タグの n が補正前スコアか補正後スコアかを定義する | [TASK-020 の独立レビュー](05_guides/prompts/independent_review.md) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **補正後スコア**。タグだけで投入判定（`n >= 閾値`）を再現できるため。補正前だと `weight` を別途参照しないと投入理由が分からない。値域超過（`score-11` / `score--1`）もそのまま出す。glossary の「スコア」（補正前）との用語のずれは意図的であり SPEC-004 §4 に注記 |
| TASK-066 | `DOC` | SPEC-002 の独立レビューを実施する | [SPEC-002 §完了チェックリスト](03_specs/SPEC-002_state_management.md#完了チェックリスト) | t_inoue | 2026-08-09 | `resolved` | 2026-07-27 実施。必須9件を全件反映。ADR-005 と矛盾する行順依存のタイブレークと、上位に根拠のない決定（フロー #21）を検出。後続5本への申し送りも取得 |
| TASK-067 | `OQ` | 状態ファイルの増大時に古いエントリをアーカイブするか決める | [SPEC-002 §OQ-003](03_specs/SPEC-002_state_management.md#11-未解決事項-open-questions) | t_inoue | 2026-09-30 | `open` | ADR-005 の再検討条件（20,000行）に達した場合の具体的な手順が未定 |
| TASK-068 | `OQ` | 状態に書き込む url の制御文字・改行の扱いを決める（拒否かエスケープか） | [SPEC-002 §OQ-004](03_specs/SPEC-002_state_management.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | JSONL は1行1レコードのため、改行が混入すると状態ファイルが破壊される |
| TASK-069 | `OQ` | 状態の読み込み失敗時に実行を止める判断を F-002 の AC として新設する | [SPEC-002 §OQ-005](03_specs/SPEC-002_state_management.md#11-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-27: **F-002 AC-018 を新設**（読み込み失敗時は1件も投入せず失敗終了）。REQ-NF-004 に「状態を読めない場合の扱い」行を追加し、読み込み失敗が「例外時に一度」ではなく「構造的に毎回起こりうる」側にあたるため許容範囲外であると既存の線引きに位置づけた。SPEC-002 のフロー #21・§7・T-014 の対応先を付け替え済み |
| TASK-070 | `OQ` | 状態ブランチへの書き込み権限を起動時に事前検証するか決める | [SPEC-002 §OQ-006](03_specs/SPEC-002_state_management.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | ADR-002 が「実行末尾に push」を選んだ帰結として、権限不備は評価コストを全部払った後に発覚する（REQ-NF-002a）。事前検証するなら F-001 AC-030 の対象を拡張する |
| TASK-071 | `OQ` | HTTP リダイレクトの追従方針を決める（回数上限・https→http のダウングレード・ホスト制限） | [SPEC-001 §OQ-003](03_specs/SPEC-001_feed_fetching.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **追従する（上限3回）。`https` → `http` のダウングレードは拒否**。移転（301）は実運用で起こり追従しないと静かに失敗し続ける。一方ダウングレードを許すと ADR-004 補遺B が「`feeds.yaml` の固定値だから該当しない」として退けた **SSRF 判定の前提が崩れる**（追従先は固定値ではない）。リダイレクト先ホストの制限は行わない（移転先は事前に知りえない） |
| TASK-072 | `OQ` | 全情報源の取得に失敗した実行を非0終了とすべきか決める | [SPEC-001 §OQ-004](03_specs/SPEC-001_feed_fetching.md#11-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **`FETCH_ALL_FAILED = 5` を新設して非0で終了する**（→ F-001 AC-017a）。GitHub 公式ドキュメントで**スケジュール実行の失敗通知がワークフロー作成者へ送られる**ことを確認したため、非0にすれば運用者はその週のうちに気づける。REQ-NF-003 の「投入0件の2回連続」は運用者がサマリを見るまで検知が働かないのに対し、全件失敗は供給停止が**確定した**状態で推測を要さない。`INGEST_ALL_FAILED` と分けるのは、どちらの段階で途切れたかを終了コードだけで判別するため（F-002 AC-010）。**情報源の定義が0件の実行は `OK` のまま** |
| TASK-073 | `OQ` | `feeds.yaml` の `verified: false` を実行時にどう扱うか決める | [SPEC-001 §OQ-005](03_specs/SPEC-001_feed_fetching.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **警告を出さない（現状維持）**。TASK-027 で13件すべてが `verified: true` になり、`false` のまま実行される状況が当面存在しない。`verified` は運用者が疎通確認の済否を記録する注記であり、実行の可否を左右させると「未確認の情報源は取得しない」という別の振る舞いを暗黙に導入することになる |
| TASK-074 | `OQ` | 新規エントリ側の飢餓の扱いを決める | [SPEC-001 §OQ-006](03_specs/SPEC-001_feed_fetching.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 上限超過が続くと `feeds.yaml` 末尾の情報源が継続的に持ち越されうる。SPEC-002 は再評価側の飢餓を `evaluated_at` 昇順で防いだが、新規側は取得順のまま |
| TASK-075 | `DOC` | 用語「取得順」を `00_glossary.md` に追記する | [SPEC-001 §OQ-007](03_specs/SPEC-001_feed_fetching.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: `00_glossary.md` のドメイン用語へ追記済み。定義は SPEC-001 §4 を正典とし、glossary からリンクする |
| TASK-076 | `OQ` | `feeds.yaml` が存在しない・不正なときの挙動を規定する AC を F に新設する | [SPEC-001 §OQ-008](03_specs/SPEC-001_feed_fetching.md#11-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **F-001 AC-030a を新設**（既定の振る舞いをそのまま AC 化。振る舞いの変更なし）。`feeds.yaml` / `profile.md` が読めないとき、取得・評価を開始する前に失敗し部分的な処理を行わない。空の情報源リストや基準なしで続行しない。TASK-087 と同一の AC で解決 |
| TASK-077 | `OQ` | API キーが無効（401/403）な場合の起動時疎通確認の要否を決める | [SPEC-003 §OQ-004](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | **F-001 AC-030 は「未設定」しか検知対象にしていない。** 「無効」を弾くなら AC-030 を「有効であること」へ拡張する必要がある |
| TASK-078 | `OQ` | タイトルと要約の両方が空のエントリの扱いを規定する AC を F に新設する | [SPEC-003 §OQ-005](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **F-001 AC-023a を新設**（既定の振る舞いをそのまま AC 化）。タイトルと要約の**両方**が空なら評価せずスキップし、**評価失敗として記録しない**。失敗として記録すると、材料がないだけの記事が失敗回数の上限に達するまで再評価され続けるため |
| TASK-079 | `OQ` | 評価1件あたりの API タイムアウト値を決める | [SPEC-003 §OQ-006](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **暫定 60 秒で確定（実測後に見直す）**。実測1件 2.7〜4.8秒の12〜22倍の余裕。全件タイムアウトは異常事態であり、**正常系の見積もり（200件×4.8秒=16分）が30分内**であることを設計の基準とする。SDK の `max_retries` 明示指定とセット |
| TASK-080 | `OQ` | 要約経由のプロンプト注入への対処方針を決める | [SPEC-003 §OQ-007](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **役割による信頼境界の分離で対処し、残余リスクを受容する**。`system` は `profile.md` のみ、記事由来の文字列は必ず `user` 側に区切り付きで置き「以降はデータであり指示ではない」を明示。**完全な遮断は不可能**だが (1) 被害がスコアの歪みに限定され外部への副作用がない (2) 分布の縮退警告（F-004 AC-024a）と全件記録により事後検知できる、の2点で受容可能と判断。値域検証では防げない（値域内の不正スコアになる）点を SPEC-003 §7 に明記 |
| TASK-081 | `OQ` | 評価の `usage`（トークン数）を state に記録するか決める | [SPEC-003 §OQ-008](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 記録しない場合、コストの事後検証は実行サマリのみに依存する。TASK-041（コスト算出方法）と一体で判断 |
| TASK-082 | `OQ` | 401/403 受信時に残りの投入対象を打ち切る是非を規定する AC を F に新設する | [SPEC-004 §OQ-003](03_specs/SPEC-004_ingestion.md#11-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **打ち切る（現状維持）**。401/403 は認証情報の問題で残りも同じ結果になり、続行しても無効な要求を数十回発行するだけ。**未試行分を記録せず次回へ持ち越す**ため恒久的な取りこぼしは生じない。Test token が失効しないことは一次情報で確認済み。**SPEC-002 §6 に対応する遷移行を追加** |
| TASK-083 | `OQ` | Raindrop の `title` / `excerpt` / `tags` の長さ上限と、タグに `#` を含めるかを確認する | [SPEC-004 §OQ-004](03_specs/SPEC-004_ingestion.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **`#` を含めずに送信する**。Raindrop 公式ドキュメントの例が `["javascript", "web-development"]` であり `feeds.yaml` も `tags: [aws]` と `#` なしで統一されている。長さ50文字・件数30件は**本システムの自主値として維持**（実上限は一次情報に記載がなく超過時の挙動が不明なため保守的に抑える） |
| TASK-084 | `OQ` | 1件の投入あたりの HTTP タイムアウト値を決める | [SPEC-004 §OQ-005](03_specs/SPEC-004_ingestion.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **暫定 30 秒で確定（実測後に見直す）**。投入は小さな JSON の POST でフィード取得より軽いが、**別の値にする積極的な根拠が実測前には立たず、値を散らすと運用者が把握すべき数値が増える**ため同値に揃える。週20〜30件が全件タイムアウトしても15分で30分内 |
| TASK-085 | `OQ` | コレクション ID に `-1`（Unsorted）等を明示指定された場合に拒否するか決める | [SPEC-004 §OQ-007](03_specs/SPEC-004_ingestion.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | **F-001 AC-032 は「未設定」のときしか述べていない。** 明示指定された場合を拒否するなら AC の文言拡張が要る |
| TASK-086 | `DOC` | SPEC-001 / 003 / 004 の独立レビューを実施する | [SPEC-001](03_specs/SPEC-001_feed_fetching.md) / [SPEC-003](03_specs/SPEC-003_entry_evaluation.md) / [SPEC-004](03_specs/SPEC-004_ingestion.md) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28 実施（SPEC-001 / 003 / 004 を3本並列）。必須19件を全件反映。**最も重い3件:** (1) SPEC-001 T-020 が §5 の「一意化しない」と正面から矛盾（実装すると SPEC-002 と二重に重複排除し R-006 の事後検証が壊れる）、(2) SPEC-006 が「生成元: SPEC-004」と宣言している `ingest_attempted` / `ingest_failure_reasons` が SPEC-004 §4 に存在せず、`ingested` の詰め方次第で**全件失敗しても警告も非0終了も出ない**（F-004 AC-016 違反）、(3) SPEC-002 §6 に `spec_error` の遷移行が欠落。他に SPEC-003 フロー #15 の `CONFIG_ERROR` 参照が `SPEC_ERROR` 新設に追随していなかった点、v0.4.0 のフロー番号詰めの取りこぼし7箇所など |
| TASK-087 | `OQ` | 設定ファイル（`feeds.yaml` / `profile.md`）が読めない場合の挙動を規定する AC を F に新設する | [SPEC-001 §OQ-008](03_specs/SPEC-001_feed_fetching.md#11-未解決事項-open-questions) / [SPEC-003 §OQ-009](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **F-001 AC-030a を新設**（TASK-076 と同一の AC）。設定ファイル2種を1つの AC で扱う。SPEC-001 OQ-008 / SPEC-003 OQ-009 / SPEC-005 OQ-001 がいずれもこの AC を参照する形で解決 |
| TASK-088 | `OQ` | 提案タグの一部だけが不正だったときの部分採用の是非を F の AC として決める | [SPEC-003 §OQ-010](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **F-001 AC-027a を新設**（既定の振る舞いをそのまま AC 化）。提案タグの一部だけが不正なら不正な要素のみ除外し、残りは採用して投入を成功させる。1要素の不正で提案タグ全体を捨てない |
| TASK-089 | `OQ` | HTTP 400 の失敗分類を見直す（無限リトライ経路の解消） | [SPEC-003 §OQ-011](03_specs/SPEC-003_entry_evaluation.md#11-未解決事項-open-questions) | t_inoue | 2026-08-09 | `open` | 2026-07-27: **`spec_error` を第3の分類として立て、実行を即座に中止する**（SPEC-003 フロー #15 / OQ-011 resolved）。F への AC 新設の要否は引き続き検討 |
| TASK-090 | `OQ` | `--dry-run` 以外に必要な CLI オプションがあるか決める | [SPEC-005 §OQ-004](03_specs/SPEC-005_cli.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **増やさない。** SPEC-006 を執筆した結果、サマリの出力先・書式はいずれも引数での切り替えを要さないと確認できた。`--json`（TASK-010）・`NO_COLOR`（TASK-011）が決着すれば増えうるが、それは各タスクの管轄。SPEC-005 §4 の「オプションを増やさない方針」を維持する |
| TASK-091 | `DOC` | SPEC-005 の独立レビューを実施する | [SPEC-005 §完了チェックリスト](03_specs/SPEC-005_cli.md#完了チェックリスト) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28 実施。**正典が自己矛盾していた**（`CONFIG_ERROR` が「処理本体を開始する前に決定する」としながら SPEC-003 の HTTP 400 を発生源に含めていた）。`SPEC_ERROR = 4` を新設して解消。優先順位の根拠の誤り・集約漏れ3件・C-I01 が要求する規定の欠落も指摘され全件反映 |
| TASK-092 | `DOC` | SPEC-006 の独立レビューを実施する | [SPEC-006 §完了チェックリスト](03_specs/SPEC-006_execution_summary.md#完了チェックリスト) | t_inoue | 2026-08-09 | `resolved` | 2026-07-28 実施。必須6件。**F-004 AC-016（投入の全件失敗をサマリで識別）を担保する規定が SPEC-006 に存在しなかった**（SPEC-004 は明示的に SPEC-006 へ委譲していたため宙に浮いていた）。**T-024 の反証可能性が実際には成立していなかった**（字下げ行が比較で潰れ、dry-run から情報源行が丸ごと消えても通過した）。失敗系6行の書式が §9 に不在で実装がラベルを独自に発明していた点、dry-run の差分が実際は4点だった点も指摘され全件反映 |
| TASK-093 | `OQ` | dry-run の明細行数に上限を設けるか決める | [SPEC-006 §OQ-002](03_specs/SPEC-006_execution_summary.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 新規が上限（暫定200件 → TASK-028）に達すると200行出力される。**初回実行では全件が新規になる**ため必ず顕在化する |
| TASK-094 | `OQ` | 失敗理由の文字列に外部由来の値をどこまで含めるか決める | [SPEC-006 §OQ-004](03_specs/SPEC-006_execution_summary.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 例外メッセージやレスポンス本文に秘匿情報が混入する経路がないか確認する。**2026-07-28 追記: dry-run 明細の URL・タイトルも対象**（§5 は URL を識別子として切り詰めないと規定しており、フィード配信 URL のクエリにトークンが含まれる経路が残る）。F-004 AC-031 に直結（→ SPEC-006 T-026） |
| TASK-095 | `OQ` | 前回比で新規追加された情報源をどう表示するか決める | [SPEC-006 §OQ-006](03_specs/SPEC-006_execution_summary.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | `feeds.yaml` の編集後の初回実行で必ず発生する。暫定は `(前回 -)`（初回実行と同じ表示になり区別できない点が論点） |
| TASK-096 | `OQ` | dry-run で秘匿情報が未設定である旨の警告をサマリ本体へ出すか決める | [SPEC-006 §OQ-007](03_specs/SPEC-006_execution_summary.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | F-005 AC-030a。現状は SPEC-005 フロー #6 が標準エラーへ出す。`--dry-run > result.txt` で保存した運用者は見落とし、**AC-030a が防ごうとした落とし穴そのものに落ちる**。AC-014 / AC-015 と同じ論理 |
| TASK-097 | `OQ` | F-005 の境界値 AC-020 / AC-021 / AC-022 の担保先を決める | [SPEC-006 §OQ-008](03_specs/SPEC-006_execution_summary.md#11-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-28: **判定は SPEC-004、表示は SPEC-006**。3件はいずれも「投入可否の判定結果」であり SPEC-004 が T-014 / T-015 / T-018 / T-029 で既に担保していた（F-001 の AC 番号で追跡されていたため F-005 側から見えなかっただけ）。dry-run と通常実行で判定ロジックは同一のため別観点は不要。両 SPEC の該当テスト観点に F-005 の AC 番号を併記して追跡可能にした |
| TASK-098 | `IMPL` | 全情報源の疎通確認と `verified` の更新（`.ref/spec.md` AC-4） | [.ref/spec.md](.ref/spec.md) AC-4 | t_inoue | 2026-08-09 | `resolved` | 2026-07-28: **13件すべて疎通確認済み**（HTTP 200 + 有効な RSS/Atom、計198エントリ）。`feeds.yaml` の `verified` を全件 `true` に更新し、`snowflake-blog` の URL 要確認 TODO も解消（`https://www.snowflake.com/feed/` で20件取得できることを確認）。**`hn-databricks` は初回 HTTP 502 / 2回目タイムアウトだったが再試行で成功** — hnrss.org 側の断続的な不調であり定義の誤りではない。個別失敗が他を止めない設計（F-001 AC-011）が実地で機能した |
| TASK-099 | `IMPL` | 評価が全件失敗した実行を非0終了にする（`EVALUATE_ALL_FAILED = 6`） | 実地 dry-run（2026-08-01） | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **実地の dry-run で発見。** API キーが無効で40件全滅したのに終了コードが `OK` だった。無人実行では終了コードが唯一の異常検知手段であり（F-002 AC-010）、GitHub Actions が成功として扱い運用者が気づけない。`FETCH_ALL_FAILED`（TASK-072）と同じ論理を評価段階へ適用。**取得より下位・投入より上位**に置く（取得が全滅すれば評価対象が0件になり、そちらが根本原因のため）。評価対象0件は `OK` のまま。**SPEC-005 §5 への反映が必要** → TASK-101 |
| TASK-100 | `IMPL` | 評価失敗の理由をサマリに出す（`evaluation_failure_reasons`） | 実地 dry-run（2026-08-01） | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **実地の dry-run で発見。** 「評価失敗 40 件」としか出ず、認証失効かスキーマ不正かを切り分けられずログを取り直す必要があった。投入失敗（F-004 AC-012）には既に失敗理由の表示があり、評価側だけ欠けていた。`OutcomeKind` の値を分類として集計する |
| TASK-101 | `DOC` | `EVALUATE_ALL_FAILED = 6` を SPEC-005 §5 と SPEC-003 に反映する | [TASK-099](#一覧) | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **SPEC-005 を v0.4.0 へ更新し、実装が正典に先行していた状態を解消した。** §5 の終了コード表・`OK` 行・優先順位表・「非0にしないもの」節・dry-run 節の5箇所を更新し、テスト観点 T-023〜T-026 を追加。優先順位の根拠として「取得全滅なら評価対象が0件になり両者は同時に成立しない」ことを明記し、**その前提自体をテストで固定した**（前提が崩れると順位の根拠が失われるため）。**F-002 に対応する AC がない点は未解決** → TASK-106 |
| TASK-102 | `IMPL` | 構造化出力のスキーマから `minimum` / `maximum` を除去する | 実 API 検証（2026-08-01） | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **実 API で発見。** `output_config.format.schema` は integer への値域制約をサポートせず、`minimum` / `maximum` を指定すると HTTP 400（`For 'integer' type, properties maximum, minimum are not supported`）。**全40件が spec_error となり評価が全滅した。** 値域は `description` へ移し、担保は `_is_valid_score` に委ねる（もともと「範囲外スコアは残る」前提の設計であり F-001 AC-029 の防御は変わらない）。再追加されると再び全滅するためテストで固定した。**分類は `spec_error`（実装が是正すべき）として正しく機能していた** |
| TASK-103 | `OQ` | 閾値 5 の妥当性と Databricks 系記事の評価の厳しさを実測で検証する | 実地 dry-run（2026-08-01） | t_inoue | 2026-09-30 | `open` | 2026-08-01 の3フィード40件で、**databricks-blog の投入3件がすべて補正後 5 ちょうど**（素点4 + weight+1）。weight がなければ全件落ちていた。また補正後 4 が4件あり「あと1点」の帯に溜まっている。基準が Databricks の記事に厳しすぎる可能性と、閾値5の妥当性の両方を、13フィード全件（約198件）の分布で判断する。R-006 の事後検証そのもの。**判断材料が40件では不足** |
| TASK-104 | `IMPL` | 要約の HTML タグ・URL をプロンプト投入前に除去する | 実地 dry-run（2026-08-01） | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **実地で発見。** hnrss.org は要約に本文を含まず `<p>Article URL: <a href=...>` 等の HTML 断片のみを返す（269字 → 均すと53字）。生の HTML を渡すと (1) タグがトークンを浪費し（REQ-NF-002a）、(2) **`href` の URL が注入の足場になる**。`<a href="x">x</a>` はリンクの表示テキストにも URL を持つため、タグ除去だけでは残る点に注意。切り詰めはタグ除去の**後**に行う（先だとマークアップが文字数を食い本文が短く切られる） |
| TASK-105 | `OQ` | `hn-*` を情報源として維持するか判断する | 実地 dry-run（2026-08-01） | t_inoue | 2026-09-30 | `open` | 2026-08-01: 2つの問題。(1) **HTTP 502 が再発**（TASK-098 でも観測。再試行では成功するため断続的）。(2) **要約に記事本文がなく、実質タイトルのみで採点している。** 正規化の前後でスコアが ±1〜2 揺れることを実測で確認しており、判断が不安定。ビジネスニュース（買収・資金調達）は 0〜2 に落ち技術記事は 4〜6 と序列自体は妥当だが、**内容を見ずに投入されうる**。選択肢: (a) 維持、(b) `weight: -1` で補正、(c) 削除、(d) 本文取得（→ スコープ外 YAGNI に抵触） |
| TASK-106 | `OQ` | 評価の全件失敗を運用者が識別できることを F 層の AC として起こすか | [TASK-101](#一覧) | t_inoue | 2026-08-23 | `open` | `EVALUATE_ALL_FAILED` は SPEC-005 §5 と実装にあるが、**対応する AC が F 層にない**。F-001 AC-014 は投入側の全件失敗のみを扱い、F-002（無人実行）にも評価側の規定がない。終了コードは運用者が観察できる振る舞いであり Rule B-1 上は F の領分。`FETCH_ALL_FAILED`（TASK-072）が同じ状態のままかも併せて確認する |
| TASK-107 | `IMPL` | 要約の HTML 復号とタグ除去の順序を是正する | diff-review（2026-08-01） | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **diff-review が検出。** タグ除去を `html.unescape` より先に行っていたため、`&lt;system&gt;` のようにエンコードされた擬似タグが除去をすり抜け、**その後の復号でリテラルなタグへ復元されてプロンプトへ渡っていた**。TASK-104 で「タグと属性が注入の足場になる」ことを理由に除去を入れた当人が、順序の取り違えで防御をバイパスさせていた。復号 → タグ除去 → URL 除去の順に是正 |
| TASK-108 | `IMPL` | `EVALUATE_ALL_FAILED` の分母から SKIPPED を除く | diff-review（2026-08-01） | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **diff-review が検出。** 分母を `len(targets)` にしていたため、SKIPPED（材料がなく評価しなかった件 → F-001 AC-023a）が1件混ざるだけで`evaluation_failures < targets` となり全滅を見逃した。**TASK-099 で塞いだ穴が再発する経路**。分母を「実際に評価を試みた件数」へ変更。全件 SKIPPED の週は `OK` のまま（運用者に是正できることがないため） |
| TASK-109 | `IMPL` | `state.jsonl` / `runs.jsonl` を `.gitignore` へ追加する | diff-review（2026-08-01） | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: **diff-review が検出。** `cli.py` が CWD へ相対パスで書き出すため、ローカル実行後の `git add -A` で既定ブランチへ混入しうる。状態の正典は orphan branch `state` 側（ADR-002 / ADR-005） |
| TASK-110 | `IMPL` | 週次実行のワークフローを定義する | [F-002](02_features/F-002_scheduled_execution.md) | t_inoue | 2026-08-01 | `resolved` | 2026-08-01: `.github/workflows/weekly.yml` を追加。cron は**日曜 21:17 UTC（月曜 06:17 JST）**（F-002 OQ-001 の決定に従い毎時0分を回避）。`workflow_dispatch` で手動起動と dry-run を可能にした（AC-003）。`permissions: contents: write`（状態ブランチへの push / ADR-002）、`concurrency` は `cancel-in-progress: false`（実行中の投入を中断すると投入済みが記録されず重複投入を招く → AC-021）、`timeout-minutes: 45`（実測170件で13分 / AC-022）。**`shell: bash` の明示が pipefail を有効にする** — 未指定だと `bash -e`（pipefail なし）で動き、`\| tee` を挟むと非0終了コードが消えて全件失敗が成功扱いになる。明示すると `bash --noprofile --norc -eo pipefail` になる（GitHub 公式仕様。diff-review の指摘を受け一次情報で確認し、実測でも裏づけた）。**Secrets 未登録では実行できない** → TASK-025 |
| TASK-111 | `OQ` | `vutr-substack` が GitHub Actions から HTTP 403 になる件の扱いを決める | 実地の Actions 実行（2026-08-01） | t_inoue | 2026-09-30 | `open` | 2026-08-01: **初回の Actions 実行で発覚。** 同一フィードがローカルからは20件取得できるのに、**ランナーからは 403**。Substack がクラウドの IP レンジをブロックしていると見られる（実装のバグではなく実行環境依存）。**週次実行では恒久的にこの情報源が欠落する**ため、ローカル dry-run の結果と本番の結果が食い違う。選択肢: (a) User-Agent を変えて再試行、(b) 情報源から削除、(c) 欠落を許容し記録のみ、(d) セルフホストランナー。**F-001 AC-011（個別の取得失敗が他を止めない）は設計どおり機能**しており、170件は正常に処理された |
| TASK-017 | `CL` | シークレット（トークン・Secrets）の定期棚卸しを行うか判断する | [enterprise_checklist §C-G03](01_requirements/enterprise_checklist.md#33-アクセス管理ガバナンス) | t_inoue | 2026-09-30 | `open` | 対象が数個のため優先度は低い |
| TASK-018 | `CL` | 復旧手順（状態ファイル喪失時・重複投入発生時）を Runbook 化するか判断する | [enterprise_checklist §O-I02](01_requirements/enterprise_checklist.md#42-インシデント対応) | t_inoue | 2026-08-23 | `open` | 発生確率が低くない事象であり手順化の価値がある |
| TASK-019 | `DOC` | 要件定義の承認後、F-xxx（機能）を作成する | [system_requirements §8](01_requirements/system_requirements.md#8-トレーサビリティマトリクス) | t_inoue | 2026-08-23 | `resolved` | 2026-07-26 に F-001〜005 を作成。トレーサビリティマトリクスの「機能」列を更新済み |
| TASK-020 | `DOC` | 上流2層 + F-001〜005 の独立コンテキストレビューを実施する | [SKILL.md §独立検証](SKILL.md) | t_inoue | 2026-08-09 | `open` | `reviewing` → `approved` の前に、別セッションで [independent_review.md](05_guides/prompts/independent_review.md) を実行する。**F 作成後にまとめて実施する方針に変更**（要件が F へ落ちるかは F を書くまで検証できないため） |
| TASK-039 | `OQ` | 起動時の秘匿情報チェックに `ANTHROPIC_API_KEY` を含めるか | [F-001 §OQ-005](02_features/F-001_triage_and_ingest.md#8-未解決事項-open-questions) | t_inoue | 2026-08-09 | `resolved` | 2026-07-26: **含める**。要件定義 §5 GitHub Secrets 行の「未設定・不正な場合は起動直後に検知し、明示的なエラーで終了する」が API キーにも適用される。F-001 AC-030 に反映済み |
| TASK-046 | `OQ` | レート制限による投入拒否の識別を F-001 と F-004 のどちらで担保するか | [F-001 §OQ-006](02_features/F-001_triage_and_ingest.md#8-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 状態全損時に数千件が投入対象になると 429 の現実的経路がある。現状どちらの F にも「投入失敗の理由を区別する」AC がなかった |
| TASK-047 | `OQ` | フィード保持件数上限による取りこぼしを許容するか、欠落検知を設けるか | [F-002 §OQ-004](02_features/F-002_scheduled_execution.md#8-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 実測で複数フィードが取得20件で頭打ち。2〜3週間の実行欠落で取りこぼしが確定的に発生し、AC-011 の「恒久化しない」が原理的に満たせない |
| TASK-048 | `OQ` | サマリの「直近の実行における取得件数」の取得元を決める | [F-004 §OQ-004](02_features/F-004_execution_summary.md#8-未解決事項-open-questions) | t_inoue | 2026-08-23 | `resolved` | 2026-07-27: **状態ブランチに `runs.jsonl`（実行単位の記録）を追加する。** エントリ単位の `state.jsonl` では (a)「新着0件で実行された週」と「実行されなかった週」の区別、(b) 情報源ごとの取得件数（既処理分を含む）が復元できず、F-004 AC-003a を原理的に満たせないため。dry-run では追記しない。SPEC-002 v0.4.0 / ADR-005 OQ-003 に反映済み |
| TASK-040 | `OQ` | 蓄積した評価記録が全損した場合の扱いを決める | [F-003 §OQ-003](02_features/F-003_verify_triage_criteria.md#8-未解決事項-open-questions) | t_inoue | 2026-08-09 | `in-progress` | 2026-07-26: 要件定義 REQ-NF-003 の RPO を「重複排除の情報: 1週間 / 評価記録: 復旧不能」に分割し、非対称性を明記した。**許容するかの結論を F-003 AC-005 に反映してから `approved` へ上げる** |
| TASK-041 | `OQ` | 実行サマリの評価コストの算出方法を決める | [F-004 §OQ-003](02_features/F-004_execution_summary.md#8-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | API 応答のトークン数から算出するか、件数からの概算に留めるか。REQ-NF-002a の検知手段。**2026-07-28 追記:** `usage` が得られない実装だと `evaluated > 0` でも `cost_usd` が 0.0 になりうる。その場合コスト超過検知が「$0.000 なのに評価 200 件」の形で静かに壊れるため、算出失敗を警告する規定の要否も一緒に決める（SPEC-006 OQ-001） |
| TASK-042 | `OQ` | dry-run の出力範囲を決める（スコアと判定のみか、付与予定タグまで再現するか） | [F-005 §OQ-001](02_features/F-005_dry_run.md#8-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | - |
| TASK-043 | `OQ` | dry-run の反復実行に伴う評価コストに上限を設けるか | [F-005 §OQ-002](02_features/F-005_dry_run.md#8-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | 記録を更新しない仕様のため、繰り返すたびに同じ記事の評価コストが発生する。TASK-028 の件数上限と併せて判断 |
| TASK-044 | `OQ` | 成功基準「週20本以上」の判定単位を決める（単週 or 平均） | [business_requirements §OQ-005](01_requirements/business_requirements.md#9-未解決事項-open-questions) | t_inoue | 2026-08-23 | `open` | §3.3 が「登録数が週によって振れる」ことを症状として挙げているため、単週判定では自然なばらつきを失敗と誤判定しうる。TASK-002 と一体で判断 |
| TASK-045 | `DOC` | 上流2層の独立レビュー指摘のうち SPEC 層送りとしたものを SPEC 作成時に反映する | [TASK-020 の独立レビュー結果](05_guides/prompts/independent_review.md) | t_inoue | 2026-09-30 | `open` | 権限マトリクスの強制手段の明示（E-1）、Raindrop のタグ一括削除の可否確認（E-4）、`enterprise_checklist` S-I04 / `application_checklist` C-S01 の `claude -p` 前提の見直し（ADR-001 でサブプロセス起動自体がなくなるため `✗` に変わる可能性が高い） |

---

## 更新履歴

| 日付 | 更新者 | 内容 |
|---|---|---|
| 2026-07-26 | - | 初版作成 |
| 2026-07-26 | t_inoue | 一行サマリーを記入。`docs/.ref/spec.md` を基に上流2層（要求定義・要件定義）と両チェックリスト・用語定義を作成し、TASK-001〜020 を登録 |
| 2026-07-26 | t_inoue | F-001〜005 を作成（REQ-F-001〜011 を5つのゴール単位に整理）。TASK-039〜043 を登録し、TASK-019 を `resolved` に更新。TASK-020 の対象を「上流2層 + F」へ拡大 |
| 2026-07-26 | t_inoue | TASK-020 の独立レビュー（上流2層 / F-001・002 / F-003〜005 の3セッション）を実施し、必須指摘 37 件を全件反映。上流2層と F-001〜005 を改訂。TASK-044〜048 を登録、TASK-039 を `resolved`、TASK-040 を `in-progress` に更新。用語「投入対象」を追加、`application_checklist` C-I01 を非0終了に修正 |
| 2026-07-26 | t_inoue | 実装ブロッカーの状態系 OQ を決着。[ADR-005](04_decisions/ADR-005_state_file_format.md)（JSONL）を起票し、TASK-030/006/031/032/033/013 を `resolved` に。ADR-002 のトレードオフ表と OQ を決着後の内容へ更新、F-001/002/003 の AC に反映。TASK-049〜053 を登録 |
| 2026-07-26 | t_inoue | [ADR-004](04_decisions/ADR-004_implementation_stack.md)（実装スタック）を起票。[code-review-toolkits](https://github.com/TakuyaInoue-github/code-review-toolkits) の構成（Python 3.10+ / uv / pytest / ruff / mypy strict / import-linter）を踏襲する決定。TASK-016 を `in-progress` に、TASK-054〜060 を登録。要件定義 §1 の宛先のない ADR-001 参照を ADR-004 へ修正 |
| 2026-07-26 | t_inoue | ADR-004 / ADR-005 の独立レビュー（TASK-058 / TASK-052）を実施し、必須指摘10件を全件反映。ADR-005 は中核前提を「更新が稀」から「追記による論理的上書き」へ訂正し OQ-001 を `evaluated_at` 最大値で決着、ADR-004 は参照元の事実誤認3件を訂正。両 ADR に補遺Aとして経緯を記録。REQ-NF-008 に「実装品質のゲート」を追加。TASK-050/052/058 を `resolved`、TASK-061 を登録。**両 ADR とも結論は不変** |
| 2026-07-26 | t_inoue | **ADR-002 / ADR-005 を `accepted` に昇格。** 前提として ADR-002 OQ-005（cron 実行時刻）を決着し月曜 06:17 JST とした（REQ-F-011 / F-002 AC-001 に反映）。TASK-005 / TASK-034 を `resolved`。状態管理の設計が確定し、実装着手の主要ブロッカーが解消 |
| 2026-07-26 | t_inoue | **ADR-004 を `accepted` に昇格。** OQ-001〜003 を決着（層構造は `domain → adapters` の契約を設ける方針、フィード取得は `httpx` + `feedparser`、依存は下限指定 + `uv.lock`）。**初稿の `defusedxml` 方針は一次情報の調査により撤回** — 未保守（2021年が最終リリース）かつ feedparser が XXE 対策を自前で持つため。真のリスクは SSRF・メモリ枯渇・ReDoS だった。TASK-016 / 055 / 059 / 060 を更新、TASK-062 を登録 |
| 2026-07-26 | t_inoue | **実装の骨格を導入**（TASK-054 / 055 / 057 を `resolved`）。`pyproject.toml`・`uv.lock`・CI ワークフローを追加し、import-linter の契約2本（4層 + `domain → adapters`）を定義。domain 層に ADR-005 の畳み込み規則と F-001 AC-029 を実装しテストで担保（49件・カバレッジ 99.31%）。TASK-027 は候補6件を疎通確認したが全て 404 のため運用者の確認待ちとして記録 |
| 2026-07-26 | t_inoue | 運用者確認により `blef-fr` のフィード未提供が確定。情報源から削除し、件数の記載を 14 → 13 に更新（REQ-NF-001 の測定条件・タイムアウト根拠、REQ-NF-002、§5 連携表、F-002 AC-022）。TASK-027 を `wontfix` で閉じ、経緯を `.ref/feeds.yaml` にコメントとして残した |
| 2026-07-26 | t_inoue | TASK-036 完了。Anthropic Console に専用ワークスペースを作成し**月 $10 の支出上限**を設定。REQ-NF-002a に「コスト超過の強制的な停止」の行を追加し、目標値のみだった状態に実際の強制手段を紐づけた（検知はサマリを見るまで働かないため、気づく前に止まる手段を別に持つ） |
| 2026-07-27 | t_inoue | **TASK-020 の独立レビュー（第2回）を実施**し、必須指摘23件を全件反映。上流2層 + F-001〜005 と実装コードを対象とした2セッション。変更の波及漏れ（13情報源・frontmatter・決着済み OQ）と、TASK-006 の決定と矛盾する記述（REQ-NF-003 RTO 行）を解消。判断を要した4件を決着（API 失敗は failure_count に計上しない / 失敗回数は試行回数分増加 / 上限時は新規を優先 / 記録の全損は許容）。TASK-063〜065 を登録 |
| 2026-07-27 | t_inoue | **SPEC 層に着手**（全6本構成）。SPEC-002（状態管理）を執筆し独立レビュー（TASK-066）の必須9件を全件反映。ADR-005 が排除した行順依存のタイブレークを `evaluated_at` のマイクロ秒精度規定で解消し、再評価対象の選定順序を「古い順」と規定して飢餓を構造的に防いだ。用語6語を glossary に追加。TASK-069 / 070 を登録 |
| 2026-07-27 | t_inoue | TASK-069 を決着。SPEC-002 が上位の根拠なく決めていた「読み込み失敗時に実行を止める」を **F-002 AC-018** として F 層へ還流し、REQ-NF-004 との衝突も要件側で解消した（読み込み失敗は「構造的に毎回起こりうる」側にあたるため許容範囲外、と既存の線引きに位置づけ） |
| 2026-07-27 | t_inoue | TASK-048 を決着。**`runs.jsonl`（実行単位の記録）を状態ブランチに追加**。エントリ単位の状態では F-004 AC-003a（情報源別の前回比）を原理的に満たせないため。SPEC-002 を v0.4.0 に、ADR-005 に OQ-003 を追記、`RunRecord` 型と用語を追加 |
| 2026-07-27 | t_inoue | **SPEC-001 / 003 / 004 をサブエージェント3本の並列で執筆**。SPEC-002 を雛形とし、独立レビューの申し送り（踏襲4点・回避6点）を共通の制約として与えた。3本とも終了コードを新設せず、上位に AC がない振る舞いは勝手に決めず OQ に落としている（計6件）。TASK-071〜086 を登録 |
| 2026-07-27 | t_inoue | SPEC-001 / 003 / 004 の独立レビュー（TASK-086）を実施し、**単独で解消できる15件を反映**。一次情報の再確認で SPEC-004 §8 の事実誤認3件を訂正（Test token は失効しない / `title` max 1000 / `excerpt` max 10000）。SPEC-003 に `should_record` を追加して SPEC-002 §6 との対応を機械的に検証可能にした。TASK-087〜089 を登録。**3本にまたがる4件は未着手** |
| 2026-07-27 | t_inoue | **3本にまたがる4件を決着。** (1) 同一 URL の一意化を SPEC-002 の責務と確定（R-002 違反の経路を解消）、(2) 401/403 打ち切り後の未試行エントリは記録せず持ち越す、(3) 投入の失敗理由は状態に記録せずサマリで集計、(4) HTTP 400 を `spec_error` として即時中止（無限リトライ経路を解消）。SPEC-001〜004 を改訂 |
| 2026-07-27 | t_inoue | **SPEC-005（CLI と起動時検証）を追加。** 終了コードの正典を §5 に集約し、優先順位（`CONFIG_ERROR` > `STATE_PERSIST_FAILED` > `INGEST_ALL_FAILED` > `OK`）と dry-run 時に返りうる値を規定。SPEC-001 / SPEC-004 から委譲された起動時検証を統合し、他4本の終了コードの数値直書きを正典への参照へ統一。TASK-090 / 091 を登録 |
| 2026-07-28 | t_inoue | SPEC-005 の独立レビュー（TASK-091）を実施し必須7件を反映。**正典の自己矛盾を解消**するため `SPEC_ERROR = 4` を新設し、運用者が是正すべき設定不備と実装が是正すべき要求不正を終了コードで区別できるようにした。優先順位の根拠を「次回実行の入力を壊す障害を優先する」へ訂正（旧根拠は F-001 AC-006 に反していた）。`feeds.yaml` の構造検証を SPEC-005 へ一元化し、`application_checklist` C-I01 を SPEC-005 §5 への参照へ更新 |
| 2026-07-28 | t_inoue | [SPEC-006](03_specs/SPEC-006_execution_summary.md)（実行サマリの出力）を追加し、**SPEC 層6本が出揃った**。執筆の過程で `RunSummary` に F-004 / F-005 の AC が要求する受け口が5つ欠けていることが判明し（失敗理由の内訳・未試行件数・前回比・dry-run 明細・未完了標識）、`contract/model.py` に追加。整形処理を domain 層に実装しテスト48件で担保（計106件・カバレッジ 99.69%）。TASK-090 を `resolved`、TASK-092〜095 を登録 |
| 2026-07-28 | t_inoue | SPEC-006 の独立レビュー（TASK-092）を実施し必須6件を反映。**F-004 AC-016（投入の全件失敗をサマリで識別）を担保する規定がどの SPEC にも存在しなかった**ため、フロー #17 と `ingest_attempted` を新設。**T-024 の反証可能性が実際には成立していなかった**（字下げ行が比較で潰れ、dry-run から情報源行が消えても通過）ため比較方法を是正しミューテーションで検証。失敗系6行の書式を §9 に正典化。TASK-096 / 097 を登録 |
| 2026-07-28 | t_inoue | **SPEC-001 / 003 / 004 の独立レビューを3本並列で実施**（TASK-086）し、必須19件を全件反映。SPEC 層6本すべてが独立レビュー済みになった。特に SPEC-004 → SPEC-006 の受け渡し欠落は、`ingested` の詰め方次第で投入が全滅しても警告も非0終了も出ない経路であり、F-004 AC-016 が実装で静かに破れる状態だった。あわせて TASK-075（用語「取得順」）と TASK-097（F-005 境界値の担保先）を `resolved` に |
| 2026-07-28 | t_inoue | **実装をブロックしていた OQ 6件を決着**（TASK-062 / 071 / 065 / 083 / 082 / 080）。3人のレビュアーが揃って「実装前に決める必要がある」と判定したもの。サイズ上限 10 MB・リダイレクト上限3回とダウングレード拒否・`#score-{n}` は補正後・タグは `#` なしで送信・401/403 は打ち切って持ち越し・プロンプト注入は役割分離で緩和し残余リスクを受容。**SPEC-001/003/004 で実装を止める OQ は解消した** |
| 2026-07-28 | t_inoue | **実測待ちだった数値 OQ 6件を暫定値で確定**（TASK-028 / 053 / 024 / 029 / 079 / 084）。いずれも根拠と**見直し条件**をセットで記述し、`draft` のまま実装に入って「どの SPEC が合意済みか」が失われる状態を避けた。評価件数200件・失敗上限3回は `domain/state.py` に定数として実装（テスト3件追加、計113件） |
| 2026-07-28 | t_inoue | **「F に AC がない」系5件を解消**（TASK-072 / 076 / 078 / 087 / 088）。SPEC が振る舞いを決めているのに上位の F に対応する AC がなかったトレーサビリティ上の欠落。4件は既定の振る舞いをそのまま AC 化（F-001 AC-023a / AC-027a / AC-030a）。TASK-072 のみ設計判断を伴い、**`FETCH_ALL_FAILED = 5` を新設して全情報源の取得失敗を非0終了とした**（GitHub がスケジュール実行の失敗を作成者へ通知することを一次情報で確認したため、非0にすれば供給停止にその週のうちに気づける） |
| 2026-07-28 | t_inoue | **実装に着手。adapters 層の最初の2本（設定読み込み・フィード取得）を実装**。`config.py`（SPEC-005 フロー #11/#12）と `fetch.py`（SPEC-001）で、10 MB のサイズ上限・リダイレクト上限3回・https ダウングレード拒否を実装。テスト48件を追加し計163件（カバレッジ 96.27%）。**実データで13情報源すべての疎通を確認**（198エントリ）し TASK-027 / TASK-073 を `resolved` に |
