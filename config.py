# ポケモンカード シティリーグ スクレイピング設定

# === API設定 ===
EVENT_SEARCH_URL = "https://players.pokemon-card.com/event_search"
EVENT_SEARCH_PARAMS_BASE = {
    "order": 4,  # 新しい順
    "result_resist": 1,  # 結果登録済みのみ
}
# シティリーグのイベントタイプ (3:1=オープン, 3:2=ジュニア, 3:7=シニア)
EVENT_TYPE_VALUES = ["3:1", "3:2", "3:7"]
# コード内でオープンリーグのみにフィルタする
LEAGUE_FILTER = "オープン"
# 大会名に含まれるべき文字列
TITLE_FILTER = "シティリーグ"
EVENT_PAGE_SIZE = 20  # 1回のAPIリクエストで取得する件数

# === ページURL ===
RESULT_PAGE_URL = "https://players.pokemon-card.com/event/detail/{event_holding_id}/result"
DECK_PAGE_URL = "https://www.pokemon-card.com/deck/confirm.html/deckID/{deck_id}"

# === データ取得設定 ===
TOP_N_PLAYERS = 8  # 上位何名まで取得するか
START_DATE = "2026-01-23"  # データ取得開始日

# === DB設定 ===
import os
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cityresu.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# === スクレイピングマナー設定 ===
SLEEP_BETWEEN_EVENTS = 3  # イベント結果取得間のスリープ（秒）
SLEEP_BETWEEN_DECKS = 3   # デッキ取得間のスリープ（秒）
SLEEP_BETWEEN_PAGES = 2   # ページング間のスリープ（秒）
PAGE_LOAD_TIMEOUT = 30000  # ページロードタイムアウト（ミリ秒）
