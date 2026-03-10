import sqlite3
import pandas as pd

DB_PATH = "c:\\Users\\naga4\\cityresu_scrape\\cityresu.db"

def investigate():
    conn = sqlite3.connect(DB_PATH)
    
    # ユーザーの画像と同じ条件でクエリを実行する
    # ドラパルトex, Top16以上, 2026-02-23 〜 2026-03-02
    
    query = """
    WITH DeckTotalPerPeriod AS (
        SELECT 
            strftime('%Y-%W', e.event_date) AS period,
            COUNT(r.id) AS total_decks
        FROM results r
        JOIN events e ON r.event_id = e.id
        WHERE r.deck_type = 'ドラパルトex' 
          AND e.event_date >= '2026-02-23' 
          AND e.event_date <= '2026-03-02'
          AND r.rank IN ('1 位', '優勝', '2 位', '準優勝', '3 位', '5 位', 'ベスト8', '9 位', 'ベスト16')
        GROUP BY period
    )
    SELECT 
        strftime('%Y-%W', e.event_date) AS 開催期間,
        c.normalized_card_name AS カード名,
        COUNT(DISTINCT c.result_id) AS 採用デッキ数,
        p.total_decks AS 総デッキ数(Top16以上),
        ROUND(CAST(COUNT(DISTINCT c.result_id) AS FLOAT) * 100.0 / p.total_decks, 2) AS 採用率_パーセント,
        SUM(c.quantity) AS 総採用枚数,
        ROUND(CAST(SUM(c.quantity) AS FLOAT) / COUNT(DISTINCT c.result_id), 2) AS 平均採用枚数
    FROM deck_cards c
    JOIN results r ON r.id = c.result_id
    JOIN events e ON r.event_id = e.id
    JOIN DeckTotalPerPeriod p ON p.period = strftime('%Y-%W', e.event_date)
    WHERE r.deck_type = 'ドラパルトex'
      AND c.normalized_card_name LIKE '%オーガポン いどのめんex%'
      AND e.event_date >= '2026-02-23'
      AND e.event_date <= '2026-03-02'
      AND r.rank IN ('1 位', '優勝', '2 位', '準優勝', '3 位', '5 位', 'ベスト8', '9 位', 'ベスト16')
    GROUP BY 
        開催期間, 
        カード名,
        p.total_decks
    ORDER BY 
        開催期間 ASC;
    """
    
    df = pd.read_sql_query(query, conn)
    print(df.to_string())
    conn.close()

if __name__ == "__main__":
    investigate()
