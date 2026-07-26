# LLMプロンプト集 (インデックス)

> Claude Code でドキュメントを生成・レビューするときのプロンプト集。
> 各ドキュメント種別ごとに専用ファイルを用意している。
>
> **基本的な使い方:**
> 1. 対象のプロンプトファイルを開く
> 2. 目的のプロンプトをコピーする
> 3. `[...]` を埋めて Claude Code に貼り付ける
>
> Claude Code は `docs/SKILL.md` を読み込んで動作する。
> 初回または新しいセッション開始時は先に `docs/SKILL.md を読んでください` と伝えると確実。

---

## プロンプトファイル一覧

| 対象ドキュメント | プロンプトファイル | 収録プロンプト |
|---|---|---|
| 要求定義 | [prompts/business_requirements.md](prompts/business_requirements.md) | 初稿生成 / レビュー / スコープ拡大レビュー |
| 要件定義 | [prompts/system_requirements.md](prompts/system_requirements.md) | 初稿生成 / レビュー / 非機能要件の根拠レビュー |
| 機能 (F-xxx) | [prompts/feature.md](prompts/feature.md) | 初稿生成 / 複数機能一括生成 / レビュー / 粒度チェック |
| 仕様 (SPEC-xxx) | [prompts/spec.md](prompts/spec.md) | 初稿生成 / 機能から仕様への展開 / レビュー / 例外系チェック |
| ADR | [prompts/adr.md](prompts/adr.md) | 初稿生成 / 選択肢比較表生成 / レビュー / supersede / 粒度チェック |
| 独立検証（全種別共通） | [prompts/independent_review.md](prompts/independent_review.md) | SPEC / Feature / ADR 共通の独立コンテキストレビュー |
| 実装コンプライアンス検証（任意） | [prompts/compliance_verification.md](prompts/compliance_verification.md) | SPEC / Feature の記述と実装コードの一致を検証 |

---

## よくある使い方パターン

### 新規プロジェクトの立ち上げ

```
1. prompts/business_requirements.md「初稿生成」
        ↓
2. prompts/system_requirements.md「初稿生成」
        ↓
3. prompts/feature.md「複数機能の一括生成」
        ↓
4. prompts/spec.md「機能から仕様への展開」
```

### ドキュメントのレビューサイクル

```
各プロンプトファイルの「レビュー」プロンプトを実行
        ↓
指摘事項を修正
        ↓
README.md のタスク一覧を更新
        ↓
（reviewing → approved へ上げる前に）
prompts/independent_review.md を新しいセッション・サブエージェントで実行
```

### 技術的意思決定のとき

```
1. prompts/adr.md「選択肢の比較表生成」で整理
        ↓
2. チームで合意
        ↓
3. prompts/adr.md「初稿生成」で ADR を作成
```

### 仕様の抜け漏れが心配なとき

```
prompts/spec.md「例外系の網羅性チェック」を実行
```

### 実装完了後、仕様との整合性を確認したいとき

```
SPEC/Feature が approved になり、対応する実装が完了している前提で
prompts/compliance_verification.md を実行
        ↓
不一致が見つかった場合は README.md のタスク一覧に IMPL として登録
```
