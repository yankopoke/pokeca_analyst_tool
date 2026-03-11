"""
イベント検索スクレイパー

公式APIを使用してシティリーグ（オープン）のイベント一覧を取得する。
Playwright不要 - requestsのみ使用。
"""

import time
import logging
import requests
from datetime import datetime

from config import (
    EVENT_SEARCH_URL,
    EVENT_SEARCH_PARAMS_BASE,
    EVENT_TYPE_VALUES,
    LEAGUE_FILTER,
    TITLE_FILTER,
    EVENT_PAGE_SIZE,
    START_DATE,
    SLEEP_BETWEEN_PAGES,
)
from models import Event, get_session, init_db

logger = logging.getLogger(__name__)


def fetch_events_page(offset=0):
    """APIから1ページ分のイベントを取得"""
    params = {
        **EVENT_SEARCH_PARAMS_BASE,
        "offset": offset,
        "event_type[]": EVENT_TYPE_VALUES,
    }
    response = requests.get(EVENT_SEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("event", []), data.get("eventCount", 0)


def parse_event_date(event_date_params):
    """'20260305' 形式の日付を 'YYYY-MM-DD' に変換"""
    try:
        dt = datetime.strptime(event_date_params, "%Y%m%d")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def fetch_all_new_events(start_date_str=None, end_date_str=None):
    """
    新規イベントを全て取得する。
    START_DATE以降のイベントのみ対象。必要に応じて引数でオーバーライド可能。
    既にDBに登録済みのイベントはスキップ。
    """
    session = get_session()
    
    # 既存のevent_holding_idを取得
    existing_ids = set(
        row[0] for row in session.query(Event.event_holding_id).all()
    )
    logger.info(f"DB登録済みイベント数: {len(existing_ids)}")
    
    target_start_date = start_date_str if start_date_str else START_DATE
    start_dt = datetime.strptime(target_start_date, "%Y-%m-%d")
    
    end_dt = None
    if end_date_str:
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
        logger.info(f"取得対象期間: {target_start_date} 〜 {end_date_str}")
    else:
        logger.info(f"取得対象期間: {target_start_date} 以降")

    new_events = []
    offset = 0
    total_count = None
    stop_fetching = False
    
    while not stop_fetching:
        logger.info(f"イベント検索中... offset={offset}")
        events_data, event_count = fetch_events_page(offset)
        
        if total_count is None:
            total_count = event_count
            logger.info(f"全イベント数: {total_count}")
        
        if not events_data:
            break
        
        for ev in events_data:
            # 日付を解析
            event_date_str = parse_event_date(ev.get("event_date_params"))
            if not event_date_str:
                continue
            
            event_date = datetime.strptime(event_date_str, "%Y-%m-%d")
            
            # 終了日(end_dt)より未来のイベントはスキップ (APIは新しい順で返る)
            if end_dt and event_date > end_dt:
                continue
                
            # START_DATE以前のイベントに到達したら終了
            # (order=4 で新しい順なので、古いイベントが出たら終了)
            if event_date < start_dt:
                logger.info(f"開始日 {target_start_date} 以前のイベントに到達。取得終了。")
                stop_fetching = True
                break
            
            # オープンリーグのみフィルタ
            league_name = ev.get("leagueName", "")
            if league_name != LEAGUE_FILTER:
                continue
            
            # 大会タイトルでフィルタ（「シティリーグ」を含むもののみ）
            event_title = ev.get("event_title", "")
            if TITLE_FILTER not in event_title:
                continue
            
            holding_id = ev.get("event_holding_id")
            if holding_id in existing_ids:
                continue
            
            # 新規イベントとして追加
            new_event = Event(
                event_holding_id=holding_id,
                event_date=event_date_str,
                shop_name=ev.get("shop_name", ""),
                prefecture=ev.get("prefecture_name", ""),
                capacity=ev.get("capacity"),
            )
            new_events.append(new_event)
            existing_ids.add(holding_id)
        
        offset += len(events_data)
        
        # 全件取得済み
        if offset >= total_count:
            break
        
        # ブロック対策のスリープ
        time.sleep(SLEEP_BETWEEN_PAGES)
    
    # DB保存
    if new_events:
        session.add_all(new_events)
        session.commit()
        logger.info(f"新規イベント {len(new_events)} 件をDBに保存しました。")
    else:
        logger.info("新規イベントはありません。")
    
    session.close()
    return new_events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    init_db()
    events = fetch_all_new_events()
    for ev in events[:5]:
        print(f"  {ev.event_date} | {ev.prefecture} | {ev.shop_name}")
    if len(events) > 5:
        print(f"  ... 他 {len(events) - 5} 件")
