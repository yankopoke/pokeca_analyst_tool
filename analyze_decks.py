"""
デッキ自動判別スクリプト (ルールベース)

このスクリプトはデータベースのデッキリスト(60枚)を取得し、
deck_rules.json の定義に従ってデッキのアーキタイプ名（主軸となるポケモンの名前など）
を自動判別してデータベースに保存します。
"""

import os
import sys
import json
import argparse
import logging
import time

from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from models import Result, DeckCard, get_session

# ロギング設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def load_rules():
    """ルールの定義をJSONファイルから読み込む"""
    rule_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deck_rules.json")
    try:
        with open(rule_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        return rules
    except FileNotFoundError:
        logger.error(f"ルールファイルが見つかりません: {rule_path}")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"ルールファイルのJSON形式が不正です: {rule_path}")
        sys.exit(1)

def get_unclassified_results(session, limit=None, overwrite_all=False):
    """判定対象のResultを取得"""
    # まずデッキカードを持つ結果IDを取得
    results_with_cards = session.query(DeckCard.result_id).distinct().subquery()
    
    # 対象のResultを取得
    query = session.query(Result).options(joinedload(Result.deck_cards)).filter(
        Result.id.in_(results_with_cards)
    )
    
    if not overwrite_all:
        query = query.filter(
            or_(
                Result.deck_type.is_(None),
                Result.deck_type == '',
                Result.deck_type == '不明'
                # 既にAI判定済みのものはスキップする
            )
        )
    
    if limit:
        query = query.limit(limit)
        
    return query.all()

def determine_deck_type(card_names_in_deck, rules):
    """デッキに含まれるカード名リストからデッキタイプを判定する"""
    for rule in rules:
        deck_name = rule["name"]
        required_cards = rule["required_cards"]
        
        # required_cards のすべてのカードがデッキに含まれているかチェック
        match = True
        for req in required_cards:
            if req not in card_names_in_deck:
                match = False
                break
                
        if match:
            return deck_name
            
    return "その他"

def analyze_and_update_decks(limit=None, overwrite_all=False):
    """デッキを分析してDBを更新する"""
    rules = load_rules()
    session = get_session()
    
    results = get_unclassified_results(session, limit=limit, overwrite_all=overwrite_all)
    if not results:
        logger.info("判定対象のデッキはありませんでした。")
        session.close()
        return

    logger.info(f"対象のデッキ {len(results)} 件を分析します...")

    updated_count = 0
    for i, result in enumerate(results):
        if not result.deck_cards:
            continue
            
        # デッキに含まれるユニークなカード名の集合を作成
        card_names_in_deck = {card.card_name for card in result.deck_cards}
        
        try:
            deck_type_name = determine_deck_type(card_names_in_deck, rules)
            
            logger.info(f"[{i+1}/{len(results)}] イベントID:{result.event_id} 順位:{result.rank} "
                        f"判定結果: 【{deck_type_name}】 (前回: {result.deck_type})")
            
            # DB更新
            result.deck_type = deck_type_name
            updated_count += 1
            
            # 一定件数ごとにコミットしてメモリを節約
            if updated_count % 100 == 0:
                session.commit()
            
        except Exception as e:
            logger.error(f"  分析中にエラーが発生しました: {e}")
            session.rollback()

    session.commit()
    session.close()
    logger.info(f"分析が完了しました。{updated_count} 件更新されました。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ルールベースを用いたデッキタイプ自動判別ツール")
    parser.add_argument("--limit", type=int, default=None, help="1度に分析する最大件数 (デフォルト: 全件)")
    parser.add_argument("--all", action="store_true", help="すでに判定済みのデッキを含めて全てのデッキを再判定する")
    args = parser.parse_args()
    
    analyze_and_update_decks(limit=args.limit, overwrite_all=args.all)

