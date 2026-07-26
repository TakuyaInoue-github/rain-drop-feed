# spec: feed-triage v0

技術ブログRSSを週次で取得し、LLMトリアージを通して Raindrop.io に自動投入する CLI。

## R (背景・動機)

- 収集レイヤー (Raindrop) への流入を自動化し、週次レビュー→deep-inquiry→tech-learning-note のパイプラインに素材を供給する
- 公式ベンダーブログは告知系と設計解説系が混在するため、人手前の LLM トリアージが必須
- 方針: 週20本以上を広く拾い、レビューの視線は `#hot` タグで絞る二層方式

## REQ (要求)

- REQ-1: feeds.yaml に定義された全フィードを取得し、新着エントリを抽出できる
- REQ-2: 処理済み URL は永続化され、再実行しても重複投入されない (冪等)
- REQ-3: 各エントリを profile.md の基準で 0-10 にスコアリングする (claude -p 使用)
- REQ-4: score + source weight >= 5 のエントリを Raindrop の指定コレクションに投入する
- REQ-5: 投入時タグ: `#auto`, `#score-{n}`, ソース由来タグ, LLM提案タグ。score>=7 は `#hot` を追加
- REQ-6: GitHub Actions cron (週1、月曜 06:00 JST) で無人実行できる
- REQ-7: 1回の実行結果 (取得数/新規数/投入数/スコア分布) を標準出力にサマリする

## SPEC (仕様)

### 構成
```
feed-triage/
├ profile.md          # トリアージ基準 (別添 v0 確定済み)
├ feeds.yaml          # フィード定義 (別添 v0)
├ triage.py           # 本体 CLI
├ state.sqlite        # 処理済み URL (url TEXT PRIMARY KEY, processed_at, score)
└ .github/workflows/weekly.yml
```

### 処理フロー
1. feeds.yaml をロード → feedparser で全フィード取得
2. state.sqlite と突合し新規 URL のみ残す
3. 新規エントリごとに `claude -p` へ title + summary + profile.md を渡す
   - 出力は JSON 固定: `{"score": n, "reason": "...", "suggested_tags": [...]}`
   - JSON パース失敗時は 1 回リトライ、再失敗はスキップしてログ
4. score + weight >= 5 のものを Raindrop API へ POST
5. state.sqlite へ全件記録 (投入しなかったものも score 付きで記録 = 後の閾値検証用)
6. サマリ出力

### Raindrop API
- エンドポイント: `POST https://api.raindrop.io/rest/v1/raindrop`
- 認証: `Authorization: Bearer $RAINDROP_TOKEN` (Test token。Actions では secrets)
- ボディ: `{"link": url, "title": ..., "excerpt": summary, "tags": [...], "collection": {"$id": AUTO_COLLECTION_ID}}`
- レート制限 120 req/min。週次バッチのため実質考慮不要だが、安全のため 1 req/sec に抑える
- 投入先コレクション `Inbox/auto` は事前に手動作成し、ID を env で渡す

### claude -p 呼び出し
- モデル・オプションは既定。プロンプトは profile.md 全文 + エントリ情報
- コスト概算: 週 100 エントリ x 短プロンプト。無視できる規模

## 受け入れ基準

- AC-1: 同一 feeds.yaml で 2 回連続実行したとき、2 回目の投入数が 0 (冪等性)
- AC-2: モック LLM 応答 (不正 JSON 含む) でパース例外がプロセスを落とさない
- AC-3: dry-run フラグで Raindrop POST をスキップしてスコアのみ出力できる
- AC-4: verified: false のフィード URL を実装時に全件疎通確認し、yaml を更新する
- AC-5: (運用検証・2週間後) score 7+ のうち #digest-candidate に昇格した割合を測定可能
        = state.sqlite に全 score が残っていること

## スコープ外 (YAGNI)

- 記事本文の取得・要約 (title + RSS summary のみで判定する)
- フィードの自動発見、OPML インポート
- 重み・閾値の自動チューニング
- 通知 (Slack 等)。サマリは Actions ログで見る

## 委任可能 / 要合意の切り分け

- 委任可能: triage.py 実装、workflow 定義、state スキーマ詳細、リトライ戦略
- 要合意: profile.md の基準変更、閾値 (5) の変更、投入先コレクション構造の変更
