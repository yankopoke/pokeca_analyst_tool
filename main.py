"""
ポケモンカード シティリーグ スクレイピング メインスクリプト

日次実行用のエントリーポイント。
処理フロー:
  1. 新規イベントを検索・DB保存 (API)
  2. 結果未取得のイベントの上位8名を取得・DB保存 (Playwright)
  3. デッキ未取得の結果からデッキリストを取得・DB保存 (Playwright)

使用方法:
  python main.py           -- 全パイプライン実行
  python main.py --events  -- イベント検索のみ
  python main.py --results -- 結果取得のみ
  python main.py --decks   -- デッキ取得のみ
"""

import argparse
import logging
import time
import re
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from config import (
    RESULT_PAGE_URL,
    DECK_PAGE_URL,
    TOP_N_PLAYERS,
    SLEEP_BETWEEN_EVENTS,
    SLEEP_BETWEEN_DECKS,
    PAGE_LOAD_TIMEOUT,
)
from models import Event, Result, DeckCard, init_db, get_session
from scraper_events import fetch_all_new_events

logger = logging.getLogger(__name__)


# ============================================================
# 大会結果スクレイピング
# ============================================================

def scrape_event_results(page, event_holding_id):
    """
    1つの大会の結果ページから上位8名を取得する。
    """
    url = RESULT_PAGE_URL.format(event_holding_id=event_holding_id)
    logger.info(f"  結果ページ: {url}")

    try:
        page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning(f"  ページロードタイムアウト")
        return []

    # 結果テーブルが表示されるまで待機
    try:
        page.wait_for_selector("tr", timeout=15000)
        page.wait_for_timeout(3000)  # 動的コンテンツの読み込み待ち
    except PlaywrightTimeout:
        logger.warning(f"  結果テーブルが見つかりません")
        return []

    # ページ内のJavaScriptで結果を解析
    results = page.evaluate("""
    () => {
        const results = [];
        const rows = document.querySelectorAll('tr');

        for (const row of rows) {
            const cells = row.querySelectorAll('td');
            if (cells.length < 3) continue;

            // 順位テキスト
            const rankText = cells[0]?.innerText?.trim();
            if (!rankText) continue;

            // プレイヤー名（改行で分割して最初の行）
            const playerName = cells[2]?.innerText?.trim()?.split('\\n')[0] || '';
            if (!playerName) continue;

            // デッキリンクからdeck_idを抽出
            let deckId = null;
            const deckLink = row.querySelector('a[href*="deckID"]');
            if (deckLink) {
                const href = deckLink.getAttribute('href');
                const match = href?.match(/deckID\\/([^\\/\\s?]+)/);
                if (match) deckId = match[1];
            }

            results.push({
                rank: rankText,
                player_name: playerName,
                deck_id: deckId
            });
        }

        return results;
    }
    """)

    top_results = results[:TOP_N_PLAYERS] if results else []
    logger.info(f"  → 取得: {len(top_results)} 名")
    return top_results


def run_results_scraper(browser):
    """結果未取得のイベントの結果を取得・保存する。"""
    session = get_session()

    # 既に結果が取得済みのイベントIDを取得
    events_with_results = set(
        row[0] for row in
        session.query(Result.event_id).distinct().all()
    )

    # 結果未取得のイベント
    events_to_scrape = (
        session.query(Event)
        .filter(Event.id.notin_(events_with_results) if events_with_results else True)
        .order_by(Event.event_date.desc())
        .all()
    )

    logger.info(f"結果未取得イベント: {len(events_to_scrape)} 件")

    if not events_to_scrape:
        session.close()
        return []

    page = browser.new_page()
    result_deck_pairs = []  # (result_id, deck_id) 後でデッキ取得に使用

    for i, event in enumerate(events_to_scrape):
        logger.info(f"[{i+1}/{len(events_to_scrape)}] {event.event_date} | {event.prefecture} | {event.shop_name}")

        results_data = scrape_event_results(page, event.event_holding_id)

        for r in results_data:
            result = Result(
                event_id=event.id,
                rank=r["rank"],
                player_name=r["player_name"],
            )
            session.add(result)
            session.flush()  # result.id を確定

            # デッキ取得用にペアを保存
            if r.get("deck_id"):
                result_deck_pairs.append((result.id, r["deck_id"]))

        session.commit()

        # ブロック対策のスリープ
        if i < len(events_to_scrape) - 1:
            time.sleep(SLEEP_BETWEEN_EVENTS)

    page.close()
    session.close()
    logger.info(f"結果取得完了。デッキ取得対象: {len(result_deck_pairs)} 件")
    return result_deck_pairs


# ============================================================
# デッキリストスクレイピング
# ============================================================

def parse_deck_text(text):
    """
    デッキページのテキストからカードリストを解析する。
    
    ページのテキスト構造:
      - セクションヘッダ: "ポケモン (20)", "グッズ (15)" など
      - ポケモンカード: 名前 / セットコード / カード番号 / N枚 (4行)
      - その他カード: 名前\tN枚 (1行)
    """
    cards = []
    lines = text.split("\n")
    
    # セクションヘッダのパターン (例: "ポケモン (20)", "グッズ (15)")
    section_pattern = re.compile(r"^(ポケモン|グッズ|ポケモンのどうぐ|サポート|スタジアム|エネルギー)\s*\(\d+\)")
    # 枚数パターン
    qty_pattern = re.compile(r"(\d+)枚")
    
    in_section = False
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # セクションヘッダを検出
        if section_pattern.match(line):
            in_section = True
            i += 1
            continue
        
        if not in_section:
            i += 1
            continue
        
        # 空行やフッターでセクション終了
        if not line or line.startswith("TO PAGE TOP") or line.startswith("お問い合わせ"):
            in_section = False
            i += 1
            continue
        
        # 新しいセクションが始まったら
        if section_pattern.match(line):
            i += 1
            continue
        
        # パターン1: タブ区切り 「カード名\tN枚」(グッズ・サポート・エネルギー等)
        if "\t" in line:
            parts = line.split("\t")
            card_name = parts[0].strip()
            qty_match = qty_pattern.search(line)
            if card_name and qty_match:
                cards.append({
                    "card_name": card_name,
                    "card_code": "",
                    "quantity": int(qty_match.group(1))
                })
            i += 1
            continue
        
        # パターン2: 複数行ポケモンカード
        # line = カード名, 次の行 = セットコード, その次 = カード番号, その次 = N枚
        qty_match = qty_pattern.search(line)
        if qty_match:
            # 現在行が「N枚」の場合はスキップ（前のイテレーションで処理済み）
            i += 1
            continue
        
        # カード名の候補 - 次の数行を調べて枚数行を探す
        card_name = line
        card_code = ""
        found = False
        
        for j in range(1, 4):  # 最大3行先まで確認
            if i + j >= len(lines):
                break
            next_line = lines[i + j].strip()
            qty_match = qty_pattern.search(next_line)
            if qty_match:
                # セットコードとカード番号を結合
                code_parts = []
                for k in range(1, j):
                    part = lines[i + k].strip()
                    if part:
                        code_parts.append(part)
                card_code = " ".join(code_parts)
                
                cards.append({
                    "card_name": card_name,
                    "card_code": card_code,
                    "quantity": int(qty_match.group(1))
                })
                i += j + 1
                found = True
                break
        
        if not found:
            i += 1
    
    return cards


def scrape_deck_list(page, deck_id):
    """
    1つのデッキページからカードリストを取得する。
    テキストベースの解析を使用。
    """
    url = DECK_PAGE_URL.format(deck_id=deck_id)
    logger.info(f"  デッキページ: {url}")

    try:
        page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning(f"  ページロードタイムアウト")
        return []

    # 「リスト表示」ボタンをクリック
    try:
        list_btn = page.locator('text=リスト表示').first
        if list_btn.is_visible(timeout=5000):
            list_btn.click()
            page.wait_for_timeout(2000)
    except Exception as e:
        logger.debug(f"  リスト表示ボタンのクリック: {e}")

    # ページ全体のテキストを取得して解析
    body_text = page.evaluate("() => document.body.innerText")
    cards = parse_deck_text(body_text)

    logger.info(f"  → カード種類数: {len(cards)}")
    return cards


def run_deck_scraper(browser, result_deck_pairs=None):
    """
    デッキを取得・保存する。

    Args:
        browser: Playwright browser instance
        result_deck_pairs: [(result_id, deck_id), ...] 指定しない場合はDB内の未取得分を処理
    """
    session = get_session()

    if result_deck_pairs is None:
        logger.info("result_deck_pairs が未指定。不足分のdeck_idを結果ページから再取得します。")
        result_deck_pairs = []
        page = browser.new_page()
        
        # DB内で deck_cards が0件の results を取得
        results_without_decks = session.query(Result).outerjoin(DeckCard).filter(DeckCard.id == None).all()
        
        events_map = {}
        for r in results_without_decks:
            if r.event not in events_map:
                events_map[r.event] = []
            events_map[r.event].append(r)
            
        logger.info(f"デッキ未取得を含むイベント数: {len(events_map)}")
        
        for i, (event, db_results) in enumerate(events_map.items()):
            logger.info(f"[{i+1}/{len(events_map)}] deck_id再取得: {event.event_date} | {event.shop_name}")
            scraped_results = scrape_event_results(page, event.event_holding_id)
            
            for db_r in db_results:
                for sc_r in scraped_results:
                    if sc_r['rank'] == db_r.rank and sc_r['player_name'] == db_r.player_name:
                        if sc_r.get('deck_id'):
                            result_deck_pairs.append((db_r.id, sc_r['deck_id']))
                        break
            time.sleep(SLEEP_BETWEEN_EVENTS)
            
        page.close()

    if not result_deck_pairs:
        logger.info("デッキ取得対象がありません。")
        session.close()
        return

    logger.info(f"デッキ取得対象: {len(result_deck_pairs)} 件")
    page = browser.new_page()

    for i, (result_id, deck_id) in enumerate(result_deck_pairs):
        if not deck_id:
            continue

        # 既に取得済みか確認
        existing = session.query(DeckCard).filter(DeckCard.result_id == result_id).first()
        if existing:
            logger.info(f"  [{i+1}/{len(result_deck_pairs)}] 既に取得済み - スキップ")
            continue

        logger.info(f"  [{i+1}/{len(result_deck_pairs)}] deck_id={deck_id}")
        cards_data = scrape_deck_list(page, deck_id)

        for card in cards_data:
            deck_card = DeckCard(
                result_id=result_id,
                card_name=card["card_name"],
                card_code=card.get("card_code", ""),
                quantity=card["quantity"],
            )
            session.add(deck_card)

        session.commit()

        # ブロック対策のスリープ
        if i < len(result_deck_pairs) - 1:
            time.sleep(SLEEP_BETWEEN_DECKS)

    page.close()
    session.close()
    logger.info("デッキ取得が完了しました。")


# ============================================================
# メイン処理
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="ポケモンカード シティリーグ スクレイピングツール"
    )
    parser.add_argument("--events", action="store_true", help="イベント検索のみ実行")
    parser.add_argument("--results", action="store_true", help="結果取得のみ実行")
    parser.add_argument("--decks", action="store_true", help="デッキ取得のみ実行")
    parser.add_argument("--start-date", type=str, help="イベント取得開始日 (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="イベント取得終了日 (YYYY-MM-DD)")
    args = parser.parse_args()

    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("scraper.log", encoding="utf-8"),
        ]
    )

    # 引数がない場合は全て実行
    run_all = not (args.events or args.results or args.decks)

    logger.info("=" * 60)
    logger.info("ポケモンカード シティリーグ スクレイピング開始")
    logger.info(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # DB初期化
    init_db()

    # Step 1: イベント検索
    if run_all or args.events:
        logger.info("\n--- Step 1: イベント検索 ---")
        new_events = fetch_all_new_events(start_date_str=args.start_date, end_date_str=args.end_date)
        logger.info(f"新規イベント: {len(new_events)} 件\n")

    # Step 2 & 3: 結果 & デッキ取得 (Playwright使用)
    result_deck_pairs = []

    if run_all or args.results or args.decks:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Step 2: 結果取得
            if run_all or args.results:
                logger.info("\n--- Step 2: 結果取得 ---")
                result_deck_pairs = run_results_scraper(browser)

            # Step 3: デッキ取得
            if run_all or args.decks:
                logger.info("\n--- Step 3: デッキ取得 ---")
                # If result_deck_pairs is empty (not running results step), pass None to trigger resumption
                run_deck_scraper(browser, result_deck_pairs if result_deck_pairs else None)

            browser.close()

    # サマリー
    session = get_session()
    event_count = session.query(Event).count()
    result_count = session.query(Result).count()
    deck_card_count = session.query(DeckCard).count()
    session.close()

    logger.info("\n" + "=" * 60)
    logger.info("スクレイピング完了")
    logger.info(f"  DB内イベント数:   {event_count}")
    logger.info(f"  DB内結果数:       {result_count}")
    logger.info(f"  DB内デッキカード: {deck_card_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
