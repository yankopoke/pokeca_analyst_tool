"""
ポケモンカード シティリーグ データベースモデル

テーブル構成:
  events     - 大会情報 (開催日, 店舗, 都道府県, 定員)
  results    - 上位8名の結果 (順位, プレイヤー名)
  deck_cards - デッキ内カード詳細 (カード名, カード番号, 枚数)
"""

from sqlalchemy import create_engine, Column, Integer, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config import DATABASE_URL

Base = declarative_base()


class Event(Base):
    """大会情報"""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_holding_id = Column(Integer, unique=True, nullable=False)  # 内部参照用
    event_date = Column(Text, nullable=False)       # 開催日 (YYYY-MM-DD)
    shop_name = Column(Text)                         # 開催店舗名
    prefecture = Column(Text)                        # 都道府県
    capacity = Column(Integer)                       # 定員

    results = relationship("Result", back_populates="event", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Event {self.event_date} {self.shop_name}>"


class Result(Base):
    """大会上位8名の結果"""
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    rank = Column(Text, nullable=False)             # 順位 (優勝, 準優勝, ベスト4, ベスト8)
    player_name = Column(Text)                       # プレイヤー名
    deck_type = Column(Text, nullable=True)          # AIが判定した、またはユーザーが登録したデッキ名

    event = relationship("Event", back_populates="results")
    deck_cards = relationship("DeckCard", back_populates="result", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Result {self.rank} {self.player_name}>"


class DeckCard(Base):
    """デッキ内カード"""
    __tablename__ = "deck_cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, ForeignKey("results.id"), nullable=False)
    card_name = Column(Text, nullable=False)          # カード名
    normalized_card_name = Column(Text, nullable=True) # 名寄せ後のカード名
    card_code = Column(Text)                           # カード番号 (例: SV8a 051/080)
    quantity = Column(Integer, nullable=False)          # 枚数

    result = relationship("Result", back_populates="deck_cards")

    def __repr__(self):
        return f"<DeckCard {self.card_name} x{self.quantity}>"


# === DB初期化 ===
engine = create_engine(DATABASE_URL, echo=False)


def init_db():
    """テーブルを作成"""
    Base.metadata.create_all(engine)


def get_session():
    """DBセッションを取得"""
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    init_db()
    print("データベースを初期化しました:", DATABASE_URL)
