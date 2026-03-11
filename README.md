# ポケカ シティリーグ 分析ツール 運用ガイド

## システム概要

ポケモンカード公式サイトからシティリーグ（オープンリーグ）の大会結果・デッキ情報をスクレイピングし、データベースに蓄積・可視化するツールです。

```
スクレイピング → DB保存 → デッキタイプ判別 → GUI / レポートで分析
```

---

## ファイル一覧

| ファイル | 役割 |
|---|---|
| `update_all.py` | **一括更新スクリプト（メイン運用コマンド）** |
| `main.py` | スクレイピングパイプライン（イベント→結果→デッキ） |
| `scraper_events.py` | 公式APIからイベント一覧を取得 |
| `analyze_decks.py` | ルールベースでデッキタイプを判別・DB更新 |
| `deck_rules.json` | デッキタイプ判別ルール定義 |
| `analyzer_app.py` | GUIアプリ（Tkinter製 分析ツール） |
| `create_report.py` | デッキ一覧HTMLレポートを生成 |
| `normalize_data.py` | カード名の名寄せ処理 |
| `cleanup_database.py` | 不正データの削除ツール |
| `models.py` | DBモデル（SQLAlchemy） |
| `config.py` | 設定ファイル |
| `cityresu.db` | SQLiteデータベース |

---

## 通常運用（定期更新）

### `update_all.py` — 一括更新スクリプト

DBの最終更新日を自動検出し、**実行日の3日前まで**のデータを取得してデッキタイプも付与します。

```powershell
cd c:\Users\naga4\cityresu_scrape
python update_all.py
```

**処理順序:**
1. DBの最新イベント日付を取得（前回更新日）
2. 前回更新日+1日 〜 実行日-3日 の期間でスクレイピング
3. イベント情報 → 大会結果 → デッキリストの順に取得・DB保存
4. カード名の名寄せ（括弧付き表記を統一）
5. ルールベースでデッキタイプ（でっきたぷ）を自動付与

> **なぜ3日前まで？**  
> 公式サイトへのデッキ登録に若干のラグがあるため、直近3日は意図的に除外しています。

#### オプション

```powershell
# 実際のスクレイピングは行わず、対象期間だけ確認する
python update_all.py --dry-run

# 日付を手動指定する
python update_all.py --start-date 2026-02-01 --end-date 2026-03-01
```

ログは `update_all.log` にも保存されます。

---

## 個別スクリプトの使い方

### スクレイピング（`main.py`）

フェーズを個別実行したい場合に使用します。

```powershell
python main.py               # 全パイプライン実行
python main.py --events      # イベント検索のみ
python main.py --results     # 結果取得のみ
python main.py --decks       # デッキ取得のみ
python main.py --start-date 2026-01-23 --end-date 2026-02-28
```

### デッキタイプ判別（`analyze_decks.py`）

```powershell
python analyze_decks.py          # 未判別のデッキのみ処理
python analyze_decks.py --all    # 全デッキを再判別（ルール更新後などに使用）
```

デッキ判別ルールは `deck_rules.json` で管理しています。新しいデッキタイプを追加する場合はこのファイルを編集してください。

### GUIアプリ（`analyzer_app.py`）

```powershell
python analyzer_app.py
```

**機能タブ:**
- **1. シェア推移グラフ** — デッキタイプ別の採用率を日次/週次グラフで表示
- **2. 採用カード分析** — 指定デッキタイプのカード採用率・枚数分布を表示
- **3. ヘルプ** — 操作方法の説明

**主な操作:**
- 期間はカレンダーアイコンで選択
- 凡例クリックで該当デッキをハイライト／それ以外をグレーアウト
- テーブルはヘッダクリックでソート
- CSVエクスポートボタンで分析結果を出力

### HTMLレポート生成（`create_report.py`）

```powershell
python create_report.py
```

`deck_report.html` が生成されます。ブラウザで開くとデッキタイプ・プレイヤー名・カード内容でフィルタ検索が可能です。

### カード名名寄せ（`normalize_data.py`）

括弧付き表記のカード名（例: `ボスの指令(サカキ)` → `ボスの指令`）を正規化します。DBを更新したあとに実行してください。

```powershell
python normalize_data.py
```

### DBクリーンアップ（`cleanup_database.py`）

シティリーグ以外のイベントデータや不正データを削除します。

```powershell
python cleanup_database.py
```

---

## DB構造

```
events         大会情報
  id, event_holding_id, event_date, shop_name, prefecture, capacity

results        上位8名の結果
  id, event_id → events, rank, player_name, deck_type

deck_cards     デッキ内カード（約60枚）
  id, result_id → results, card_name, normalized_card_name, card_code, quantity
```

---

## 設定（`config.py`）

| 設定値 | デフォルト | 説明 |
|---|---|---|
| `START_DATE` | `2026-01-23` | データ収集の開始日（DB空時のフォールバック） |
| `TOP_N_PLAYERS` | `8` | 取得する上位プレイヤー数 |
| `LEAGUE_FILTER` | `オープン` | リーグ種別フィルタ |
| `TITLE_FILTER` | `シティリーグ` | 大会名フィルタ |
| `SLEEP_BETWEEN_EVENTS` | `3秒` | イベント間のスリープ |
| `SLEEP_BETWEEN_DECKS` | `3秒` | デッキ間のスリープ |

---

## 推奨運用フロー

```
【週次 or 任意のタイミングで】
1. python update_all.py     # データ一括更新（名寄せ・でっきたぷ付与まで全自動）
2. python analyzer_app.py   # GUIで分析
   または
   python create_report.py  # HTMLレポート確認
```

新シーズンやルール変更後に新しいデッキタイプが出た場合は、`deck_rules.json` にルールを追加してから `python analyze_decks.py --all` で全デッキを再判別してください。

---

## 依存パッケージ

```powershell
pip install -r requirements.txt
playwright install chromium
```
