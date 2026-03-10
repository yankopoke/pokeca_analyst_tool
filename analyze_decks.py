"""
デッキ自動判別スクリプト (AI: OpenAI 使用)

このスクリプトはデータベース内のdeck_typeが空のデッキリスト(60枚)を取得し、
OpenAIのAPI (gpt-5-mini) を使ってそのデッキのアーキタイプ名（主軸となるポケモンの名前など）
を自動判別してデータベースに保存します。

実行前に .env ファイルに `OPENAI_API_KEY` を設定するか、環境変数として設定してください。
"""

import os
import sys
import argparse
import logging
import time

try:
    from openai import OpenAI
    from dotenv import load_dotenv
except ImportError:
    print("openai または python-dotenv ライブラリがインストールされていません。")
    print("pip install openai python-dotenv を実行してください。")
    sys.exit(1)

from sqlalchemy.orm import joinedload
from models import Result, DeckCard, get_session

# .envファイルから環境変数を読み込む
load_dotenv()

# ロギング設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# プロンプト設定
SYSTEM_PROMPT = """
あなたはポケモンカードゲーム(ポケカ)の熟練プレイヤー・アナリストです。
提供された60枚のデッキリスト（カード名と枚数）を見て、このデッキのアーキタイプ（デッキタイプ）名を最も簡潔に1単語、または短い熟語で回答してください。

回答のルール：
1. 主力となるポケモン（アタッカーやエンジン）の名前を中心に答えること。必ず日本語（カタカナなど）で表記すること。
   例: 「リザードンex」「ドラパルトex」「ルギアVSTAR」「タケルライコex」「サーナイトex」「ロストギラティナ」「カビゴンLO」
2. 余計な説明、「〜デッキです」「デッキタイプは〜です」といった文章は一切含めず、純粋なデッキ名のみを出力すること。
3. もし判別が難しい場合は、「分類不能」と出力すること。
"""

def setup_openai():
    """OpenAI APIのセットアップ"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("環境変数 'OPENAI_API_KEY' が設定されていません。")
        sys.exit(1)
        
    client = OpenAI(api_key=api_key)
    return client

def get_unclassified_results(session, limit=None):
    """deck_typeがNULLで、かつカードデータが存在する結果を取得"""
    # まずデッキカードを持つ結果IDを取得
    results_with_cards = session.query(DeckCard.result_id).distinct().subquery()
    
    # 対象のResultを取得
    query = session.query(Result).options(joinedload(Result.deck_cards)).filter(
        Result.deck_type.is_(None),
        Result.id.in_(results_with_cards)
    )
    
    if limit:
        query = query.limit(limit)
        
    return query.all()

def build_deck_text(deck_cards):
    """AIに渡すためのデッキリスト文字列を作成（トークン節約のためポケモンのみ抽出）"""
    text = "【デッキリスト(ポケモンのみ)】\n"
    for card in deck_cards:
        # パース時に「カード番号」が取得できているものは「ポケモンカード」に該当する
        if card.card_code:
            text += f"- {card.card_name} x{card.quantity}\n"
    return text

def analyze_and_update_decks(limit=10):
    """デッキを分析してDBを更新する"""
    client = setup_openai()
    session = get_session()
    
    results = get_unclassified_results(session, limit=limit)
    if not results:
        logger.info("未分類のデッキはありませんでした。")
        session.close()
        return

    logger.info(f"未分類のデッキ {len(results)} 件を分析します...")

    for i, result in enumerate(results):
        if not result.deck_cards:
            continue
            
        deck_text = build_deck_text(result.deck_cards)
        
        try:
            logger.info(f"[{i+1}/{len(results)}] イベントID:{result.event_id} 順位:{result.rank} のデッキを分析中...")
            
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": deck_text}
                ]
            )
            
            deck_type_name = response.choices[0].message.content.strip()
            # AIが余計な改行や記号を含めた場合のサニタイズ
            deck_type_name = deck_type_name.replace("デッキ", "").replace("です", "").strip()
            if not deck_type_name:
                deck_type_name = "不明"
                
            logger.info(f"  → 判定結果: 【{deck_type_name}】")
            
            # DB更新
            result.deck_type = deck_type_name
            session.commit()
            
            # レートリミット対策
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"  分析中にエラーが発生しました: {e}")
            session.rollback()

    session.close()
    logger.info("分析が完了しました。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIを用いたデッキタイプ自動判別ツール")
    parser.add_argument("--limit", type=int, default=10, help="1度に分析する最大件数 (デフォルト: 10)")
    parser.add_argument("--all", action="store_true", help="未分類の全てのデッキを分析する")
    args = parser.parse_args()
    
    limit = None if args.all else args.limit
    analyze_and_update_decks(limit=limit)
