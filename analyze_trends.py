import sqlite3
import csv
import argparse
from config import DATABASE_URL


def _get_db_path():
    return DATABASE_URL.replace('sqlite:///', '')


def _period_expr(interval: str) -> str:
    if interval == 'W':
        return "strftime('%Y-W%W', e.event_date)"
    elif interval == 'M':
        return "strftime('%Y-%m', e.event_date)"
    else:
        raise ValueError("Interval must be 'W' or 'M'")


# ============================================================
# 1) デッキタイプ別 時系列入賞数
# ============================================================
def analyze_deck_type_trend(interval: str, output_file: str | None = None):
    """
    全デッキタイプの入賞数を時系列で集計する。
    出力: 開催期間, デッキタイプ名, 入賞数  （開催時期の古い順）
    """
    db_path = _get_db_path()
    pe = _period_expr(interval)

    query = f"""
    SELECT
        {pe}         AS period,
        r.deck_type  AS deck_type,
        COUNT(r.id)  AS placement_count
    FROM results r
    JOIN events e ON r.event_id = e.id
    WHERE r.deck_type IS NOT NULL
    GROUP BY period, r.deck_type
    ORDER BY period ASC, placement_count DESC
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

    # --- 表示 ---
    print(f"{'Period':<10} | {'Deck Type':<25} | {'Placements':>10}")
    print("-" * 52)

    data_out = []
    for period, deck_type, count in rows:
        if not period:
            continue
        print(f"{period:<10} | {deck_type:<25} | {count:>10}")
        data_out.append({
            'period': period,
            'deck_type': deck_type,
            'placement_count': count,
        })

    if not data_out:
        print("No data found.")
        return

    # --- CSV 出力 ---
    if output_file:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data_out[0].keys())
            writer.writeheader()
            writer.writerows(data_out)
        print(f"\nData saved to {output_file}")


# ============================================================
# 2) カード採用トレンド（デッキ指定 or 全デッキ）
# ============================================================
def analyze_card_trend(deck_type: str | None, card_name: str, interval: str, output_file: str):
    """
    特定カードの採用状況を時系列で集計する。
    deck_type: デッキタイプ名。None の場合は全デッキを対象とする。
    interval: 'W' (週次), 'M' (月次)
    """
    db_path = _get_db_path()
    pe = _period_expr(interval)

    # サブクエリでデッキごとの対象カード枚数を事前に集計する（同名カードの複数バージョン対策）
    if deck_type:
        where_clause = "WHERE r.deck_type = ?"
        params = (card_name, deck_type)
    else:
        where_clause = "WHERE r.deck_type IS NOT NULL"
        params = (card_name,)

    query = f"""
    WITH deck_card_counts AS (
        SELECT 
            c.result_id, 
            SUM(c.quantity) as total_copies
        FROM deck_cards c 
        WHERE c.normalized_card_name = ?
        GROUP BY c.result_id
    )
    SELECT 
        {pe} as period,
        COUNT(r.id) as total_decks,
        CAST(SUM(CASE WHEN dc.total_copies IS NOT NULL AND dc.total_copies > 0 THEN 1 ELSE 0 END) AS INTEGER) as decks_with_card,
        CAST(SUM(IFNULL(dc.total_copies, 0)) AS INTEGER) as total_copies
    FROM results r
    JOIN events e ON r.event_id = e.id
    LEFT JOIN deck_card_counts dc ON r.id = dc.result_id
    {where_clause}
    GROUP BY period
    ORDER BY period
    """
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    scope = f"[{deck_type}]" if deck_type else "[全デッキ]"
    print(f"--- Analysis for {scope} using [{card_name}] ---")
    print(f"{'Period':<10} | {'Total Decks':<12} | {'With Card':<10} | {'Total Copies':<12} | {'Adoption Rate':<15} | {'Avg Copies':<10}")
    print("-" * 80)
    
    data_out = []
    for row in rows:
        period, total_decks, decks_with_card, total_copies = row
        if not period:
            continue
        adoption_rate = (decks_with_card / total_decks) * 100 if total_decks > 0 else 0
        avg_copies = total_copies / total_decks if total_decks > 0 else 0
        
        print(f"{period:<10} | {total_decks:<12} | {decks_with_card:<10} | {total_copies:<12} | {adoption_rate:>6.2f}%{'':<8} | {avg_copies:.2f}")
        
        data_out.append({
            'period': period,
            'total_decks': total_decks,
            'decks_with_card': decks_with_card,
            'total_copies': total_copies,
            'adoption_rate_pct': round(adoption_rate, 2),
            'avg_copies': round(avg_copies, 2)
        })

    if not data_out:
        print("No data found for the given criteria.")
        return

    if output_file:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data_out[0].keys())
            writer.writeheader()
            writer.writerows(data_out)
        print(f"Data saved to {output_file}")


# ============================================================
# 3) 全デッキ横断 カード採用率・平均採用枚数
# ============================================================
def analyze_card_adoption_all(deck_type: str | None = None, output_file: str | None = None):
    """
    全デッキ（またはデッキタイプ指定時はそのデッキ内）での
    各カードの採用率と平均採用枚数を集計する。

    出力: カード名, 採用率(%), 平均採用枚数  （採用率の高い順）
    """
    db_path = _get_db_path()

    # --- 対象デッキ総数 ---
    if deck_type:
        count_query = """
        SELECT COUNT(DISTINCT r.id)
        FROM results r
        JOIN deck_cards c ON c.result_id = r.id
        WHERE r.deck_type = ?
        """
        count_params = (deck_type,)
    else:
        count_query = """
        SELECT COUNT(DISTINCT r.id)
        FROM results r
        JOIN deck_cards c ON c.result_id = r.id
        WHERE r.deck_type IS NOT NULL
        """
        count_params = ()

    # --- カードごとの採用デッキ数と合計枚数 ---
    if deck_type:
        card_query = """
        SELECT
            c.normalized_card_name          AS card_name,
            COUNT(DISTINCT c.result_id)     AS decks_with_card,
            SUM(c.quantity)                 AS total_copies
        FROM deck_cards c
        JOIN results r ON r.id = c.result_id
        WHERE r.deck_type = ?
          AND c.normalized_card_name IS NOT NULL
        GROUP BY c.normalized_card_name
        """
        card_params = (deck_type,)
    else:
        card_query = """
        SELECT
            c.normalized_card_name          AS card_name,
            COUNT(DISTINCT c.result_id)     AS decks_with_card,
            SUM(c.quantity)                 AS total_copies
        FROM deck_cards c
        JOIN results r ON r.id = c.result_id
        WHERE r.deck_type IS NOT NULL
          AND c.normalized_card_name IS NOT NULL
        GROUP BY c.normalized_card_name
        """
        card_params = ()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(count_query, count_params)
        total_decks = cursor.fetchone()[0]

        cursor.execute(card_query, card_params)
        rows = cursor.fetchall()

    if total_decks == 0:
        print("No decks found.")
        return

    # --- 採用率計算 & ソート ---
    results_list = []
    for card_name, decks_with_card, total_copies in rows:
        adoption_rate = (decks_with_card / total_decks) * 100
        avg_copies = total_copies / decks_with_card  # 採用しているデッキでの平均
        results_list.append({
            'card_name': card_name,
            'adoption_rate_pct': round(adoption_rate, 2),
            'avg_copies': round(avg_copies, 2),
        })

    results_list.sort(key=lambda x: x['adoption_rate_pct'], reverse=True)

    # --- 表示 ---
    scope = f"[{deck_type}]" if deck_type else "全デッキ"
    print(f"--- カード採用率 ({scope}, 対象デッキ数: {total_decks}) ---")
    print(f"{'Card Name':<25} | {'Adoption %':>10} | {'Avg Copies':>10}")
    print("-" * 52)

    for r in results_list:
        print(f"{r['card_name']:<25} | {r['adoption_rate_pct']:>9.2f}% | {r['avg_copies']:>10.2f}")

    # --- CSV 出力 ---
    if output_file:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=results_list[0].keys())
            writer.writeheader()
            writer.writerows(results_list)
        print(f"\nData saved to {output_file}")


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trend analysis tools.")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- deck-trend サブコマンド ---
    p_deck = subparsers.add_parser("deck-trend", help="デッキタイプ別 入賞数の時系列推移")
    p_deck.add_argument("--interval", type=str, choices=['W', 'M'], default='M',
                        help="集計単位: W (週次) or M (月次, デフォルト)")
    p_deck.add_argument("--out", type=str, help="出力CSVファイルパス")

    # --- card サブコマンド ---
    p_card = subparsers.add_parser("card", help="カード採用トレンド（デッキ指定 or 全デッキ）")
    p_card.add_argument("--deck", type=str, default=None,
                        help="デッキタイプ名 (省略時は全デッキ対象, 例: 'リザードンex')")
    p_card.add_argument("--card", type=str, required=True, help="カード名 (例: 'ボスの指令')")
    p_card.add_argument("--interval", type=str, choices=['W', 'M'], default='W',
                        help="集計単位: W (週次, デフォルト) or M (月次)")
    p_card.add_argument("--out", type=str, help="出力CSVファイルパス")

    # --- card-adoption サブコマンド ---
    p_adopt = subparsers.add_parser("card-adoption", help="カード採用率・平均採用枚数（全デッキ横断）")
    p_adopt.add_argument("--deck", type=str, default=None,
                         help="デッキタイプで絞り込む場合に指定 (例: 'リザードンex')")
    p_adopt.add_argument("--out", type=str, help="出力CSVファイルパス")

    args = parser.parse_args()

    if args.command == "deck-trend":
        out = args.out or f"deck_type_trend_{args.interval}.csv"
        analyze_deck_type_trend(args.interval, out)

    elif args.command == "card":
        output_filename = args.out
        if not output_filename:
            safe_deck = "".join(c for c in (args.deck or "all_decks") if c.isalnum() or c in (' ', '_', '-')).replace(' ', '_')
            safe_card = "".join(c for c in args.card if c.isalnum() or c in (' ', '_', '-')).replace(' ', '_')
            output_filename = f"trend_{safe_deck}_{safe_card}_{args.interval}.csv"
        analyze_card_trend(args.deck, args.card, args.interval, output_filename)

    elif args.command == "card-adoption":
        out = args.out
        if not out:
            suffix = args.deck or "all"
            safe = "".join(c for c in suffix if c.isalnum() or c in (' ', '_', '-')).replace(' ', '_')
            out = f"card_adoption_{safe}.csv"
        analyze_card_adoption_all(deck_type=args.deck, output_file=out)

    else:
        parser.print_help()
