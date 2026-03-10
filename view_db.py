import argparse
from sqlalchemy import func
from models import Event, Result, DeckCard, get_session

def print_summary(session):
    print("=== データベース概要 ===")
    print(f"大会数:   {session.query(Event).count()}件")
    print(f"結果数:   {session.query(Result).count()}件")
    print(f"カード数: {session.query(DeckCard).count()}件\n")

def print_events(session, limit=5):
    print(f"=== 最近の大会 (最新{limit}件) ===")
    events = session.query(Event).order_by(Event.event_date.desc()).limit(limit).all()
    for e in events:
        print(f"ID:{e.id} | {e.event_date} | {e.prefecture} | {e.shop_name}")
    print()

def print_deck(session, event_id, rank="優勝"):
    print(f"=== 大会ID: {event_id} の {rank} デッキ ===")
    result = session.query(Result).filter(Result.event_id == event_id, Result.rank == rank).first()
    if not result:
        print(f"該当のデッキが見つかりません。")
        return
        
    print(f"プレイヤー: {result.player_name}\n")
    cards = session.query(DeckCard).filter(DeckCard.result_id == result.id).all()
    
    if not cards:
        print("デッキデータがまだ取得されていません。")
        return
        
    for c in cards:
        code_str = f" [{c.card_code}]" if c.card_code else ""
        print(f" {c.card_name}{code_str} x{c.quantity}")
    print(f"\n合計: {sum(c.quantity for c in cards)}枚")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DB参照ツール")
    parser.add_argument("--summary", action="store_true", help="全体の概要を表示")
    parser.add_argument("--events", type=int, default=0, metavar="N", help="最近の大会をN件表示")
    parser.add_argument("--deck", type=int, metavar="EVENT_ID", help="指定した大会IDの優勝デッキを表示")
    args = parser.parse_args()
    
    session = get_session()
    
    if args.summary or (not args.events and not args.deck):
        print_summary(session)
    
    if args.events > 0:
        print_events(session, args.events)
        
    if args.deck is not None:
        print_deck(session, args.deck)
        
    session.close()
