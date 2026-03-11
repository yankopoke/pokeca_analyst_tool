"""
シティリーグ データ一括更新スクリプト

処理フロー:
  1. DBの最終更新日（events テーブルの最新 event_date）を取得
  2. 実行日の 3日前を終了日として設定
  3. 前回更新日の翌日〜終了日 の範囲でイベント・結果・デッキをスクレイピング
  4. normalize_data.py でカード名の名寄せ（括弧付き表記の統一）
  5. analyze_decks.py (ルールベース) でデッキタイプ（でっきたぷ）を付与

使用方法:
  python update_all.py              -- 自動範囲で全パイプライン実行
  python update_all.py --dry-run    -- 実際のスクレイピングは行わず日付のみ確認
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta

from models import Event, Result, DeckCard, init_db, get_session
from config import START_DATE

from analyze_decks import analyze_and_update_decks
from normalize_data import add_normalization_columns, run_normalization

logger = logging.getLogger(__name__)


def get_last_updated_date(session) -> str:
    """
    DBに登録されている最新のイベント開催日を返す。
    DBが空の場合は config.py の START_DATE を返す。

    Returns:
        'YYYY-MM-DD' 形式の文字列
    """
    row = session.query(Event.event_date).order_by(Event.event_date.desc()).first()
    if row:
        return row[0]  # すでに 'YYYY-MM-DD' 形式
    logger.info(f"DBにイベントが存在しないため START_DATE ({START_DATE}) を使用します。")
    return START_DATE


def calc_date_range(last_date_str: str, today: datetime) -> tuple[str, str]:
    """
    スクレイピング対象期間を算出する。

    start_date: 前回最終更新日の翌日
    end_date  : 実行日の 3日前

    Returns:
        (start_date_str, end_date_str)  両方 'YYYY-MM-DD' 形式
    """
    last_dt = datetime.strptime(last_date_str, "%Y-%m-%d")
    start_dt = last_dt + timedelta(days=1)
    end_dt = today - timedelta(days=3)
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def run_pipeline(start_date: str, end_date: str, dry_run: bool = False):
    """
    スクレイピング全パイプラインを実行する。

    Args:
        start_date: 取得開始日 ('YYYY-MM-DD')
        end_date  : 取得終了日 ('YYYY-MM-DD')
        dry_run   : True の場合は実際のスクレイピングを行わない
    """
    logger.info("=" * 60)
    logger.info("シティリーグ データ一括更新スクリプト 開始")
    logger.info(f"実行日時  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"取得対象  : {start_date} 〜 {end_date}")
    logger.info("=" * 60)

    if dry_run:
        logger.info("[DRY-RUN] スクレイピングをスキップします。")
        return

    # DB 初期化
    init_db()

    # ────────── Step 1〜3: main.py のパイプライン ──────────
    # main.py の関数を直接インポートして使う
    from main import run_results_scraper, run_deck_scraper
    from scraper_events import fetch_all_new_events
    from playwright.sync_api import sync_playwright

    # Step 1: イベント検索
    logger.info("\n--- Step 1: イベント検索 ---")
    new_events = fetch_all_new_events(start_date_str=start_date, end_date_str=end_date)
    logger.info(f"新規イベント: {len(new_events)} 件\n")

    # Step 2 & 3: 結果・デッキ取得
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        logger.info("--- Step 2: 結果取得 ---")
        result_deck_pairs = run_results_scraper(browser)

        logger.info("\n--- Step 3: デッキ取得 ---")
        run_deck_scraper(browser, result_deck_pairs if result_deck_pairs else None)

        browser.close()

    # ────────── Step 4: カード名名寄せ ──────────
    logger.info("\n--- Step 4: カード名名寄せ ---")
    add_normalization_columns()  # カラムが未存在の場合のみ追加
    run_normalization()

    # ────────── Step 5: でっきたぷ付与 ──────────
    logger.info("\n--- Step 5: デッキタイプ付与（でっきたぷ） ---")
    analyze_and_update_decks()

    # ────────── サマリー ──────────
    session = get_session()
    event_count  = session.query(Event).count()
    result_count = session.query(Result).count()
    deck_card_count = session.query(DeckCard).count()
    # deck_type が付いている Result 数
    typed_count = session.query(Result).filter(
        Result.deck_type.isnot(None),
        Result.deck_type != '',
    ).count()
    session.close()

    logger.info("\n" + "=" * 60)
    logger.info("一括更新 完了")
    logger.info(f"  DB内イベント数    : {event_count}")
    logger.info(f"  DB内結果数        : {result_count}")
    logger.info(f"  DB内デッキカード  : {deck_card_count}")
    logger.info(f"  デッキタイプ付与数: {typed_count}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="シティリーグ データ一括更新（スクレイピング＋でっきたぷ付与）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="スクレイピングを実行せず、対象期間の確認のみ行う",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="開始日を手動指定 (YYYY-MM-DD)。省略時は DB の最終更新日の翌日を使用。",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="終了日を手動指定 (YYYY-MM-DD)。省略時は実行日の 3日前を使用。",
    )
    args = parser.parse_args()

    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("update_all.log", encoding="utf-8"),
        ],
    )

    today = datetime.now()

    # ── 日付範囲の決定 ──
    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date   = args.end_date
        logger.info(f"手動指定の期間を使用: {start_date} 〜 {end_date}")
    else:
        # DB の最終更新日を取得
        init_db()
        session = get_session()
        last_date = get_last_updated_date(session)
        session.close()
        logger.info(f"DB最終更新日: {last_date}")

        start_date, end_date = calc_date_range(last_date, today)

        # 引数で片方だけ指定された場合も考慮
        if args.start_date:
            start_date = args.start_date
        if args.end_date:
            end_date = args.end_date

    # 範囲チェック
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")

    if start_dt > end_dt:
        logger.info(
            f"取得対象期間がありません（開始日 {start_date} > 終了日 {end_date}）。"
            " スクレイピングは不要です。"
        )
        sys.exit(0)

    run_pipeline(start_date, end_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
