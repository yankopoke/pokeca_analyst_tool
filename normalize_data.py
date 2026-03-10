import re
import sqlite3
import logging
from config import DATABASE_URL
from models import get_session, Result, DeckCard

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def add_normalization_columns():
    """DBに名寄せ用のカラムを追加する"""
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # deck_cardsテーブルにnormalized_card_nameを追加
        try:
            cursor.execute("ALTER TABLE deck_cards ADD COLUMN normalized_card_name TEXT;")
            logger.info("Added normalized_card_name column to deck_cards table.")
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                logger.info("Column normalized_card_name already exists.")
            else:
                logger.error(f"Error adding normalized_card_name: {e}")
        
        conn.commit()

def normalize_card_name(name: str) -> str:
    """
    カード名の名寄せルール
    - "ボスの指令(サカキ)" -> "ボスの指令"
    - "博士の研究（オーキド博士）" -> "博士の研究"
    """
    if not name:
        return name
    # 括弧以降を削除
    name = re.sub(r'[\(（].*?[\)）]', '', name).strip()
    return name

def run_normalization():
    """データベース内の全データを正規化して更新する"""
    session = get_session()
    
    logger.info("Start normalizing card names...")
    deck_cards = session.query(DeckCard).all()
    normalized_card_count = 0
    for dc in deck_cards:
        if dc.card_name:
            new_name = normalize_card_name(dc.card_name)
            if dc.normalized_card_name != new_name:
                dc.normalized_card_name = new_name
                normalized_card_count += 1
                
    logger.info(f"Committing changes... (Cards updated: {normalized_card_count})")
    session.commit()
    session.close()
    logger.info("Normalization completed.")

if __name__ == "__main__":
    add_normalization_columns()
    run_normalization()
