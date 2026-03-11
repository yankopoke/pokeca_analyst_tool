import json
from sqlalchemy.orm import joinedload
from models import get_session, Result, DeckCard, Event
import os

def generate_report():
    session = get_session()
    
    # 全ての結果と関連するカード、イベントデータを取得
    results = session.query(Result).options(
        joinedload(Result.deck_cards),
        joinedload(Result.event)
    ).order_by(Result.event_id.desc(), Result.rank).all()
    
    deck_data = []
    for r in results:
        pokemon_cards = [c.card_name for c in r.deck_cards if c.card_code]
        trainer_cards = [c.card_name for c in r.deck_cards if not c.card_code and "基本" not in c.card_name]
        
        deck_data.append({
            "id": r.id,
            "event_date": r.event.event_date,
            "shop_name": r.event.shop_name,
            "rank": r.rank,
            "player_name": r.player_name,
            "deck_type": r.deck_type or "未設定",
            "pokemon": pokemon_cards,
            "trainers": trainer_cards
        })

    # デッキタイプのリスト（ユニーク）を取得
    all_types = sorted(list(set(d["deck_type"] for d in deck_data)))

    # HTMLテンプレート (Vanilla JS + CSS)
    html_template = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>デッキ判定確認レポート</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #6366f1;
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --accent: #818cf8;
        }

        * { box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 2rem;
            line-height: 1.5;
        }

        h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 2.5rem;
            margin-bottom: 2rem;
            background: linear-gradient(to right, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
        }

        .controls {
            max-width: 1200px;
            margin: 0 auto 2rem;
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }

        input, select {
            padding: 0.75rem 1rem;
            border-radius: 0.5rem;
            border: 1px solid var(--border);
            background: var(--card-bg);
            color: var(--text);
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }

        input { flex: 2; min-width: 300px; }
        select { flex: 1; min-width: 200px; }

        input:focus, select:focus { border-color: var(--primary); }

        .stats {
            text-align: center;
            margin-bottom: 1rem;
            color: var(--text-muted);
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 1.5rem;
            max-width: 1400px;
            margin: 0 auto;
        }

        .deck-card {
            background: var(--card-bg);
            border-radius: 1rem;
            padding: 1.5rem;
            border: 1px solid var(--border);
            transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .deck-card:hover {
            transform: translateY(-4px);
            border-color: var(--accent);
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }

        .deck-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.75rem;
        }

        .deck-type {
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--accent);
        }

        .rank {
            background: #334155;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.875rem;
            font-weight: 600;
        }

        .meta {
            font-size: 0.875rem;
            color: var(--text-muted);
        }

        .card-list {
            margin-top: 0.5rem;
        }

        .section-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            font-weight: 600;
        }

        .pkm-tags, .tr-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
        }

        .tag {
            font-size: 0.75rem;
            background: #1e293b;
            border: 1px solid #475569;
            padding: 0.15rem 0.4rem;
            border-radius: 0.25rem;
        }

        .tag.match {
            background: rgba(99, 102, 241, 0.2);
            border-color: var(--accent);
        }

        [hidden] { display: none !important; }
    </style>
</head>
<body>
    <h1>Pokeca Deck Classification Report</h1>
    
    <div class="stats" id="stats">Total: 0 decks</div>

    <div class="controls">
        <select id="typeFilter">
            <option value="">-- 全てのデッキタイプ --</option>
            """ + "\n".join([f'<option value="{t}">{t}</option>' for t in all_types]) + """
        </select>
        <input type="text" id="search" placeholder="Filter by Player, or Cards...">
    </div>

    <div class="grid" id="deckGrid"></div>

    <script>
        const decks = """ + json.dumps(deck_data, ensure_ascii=False) + """;

        const grid = document.getElementById('deckGrid');
        const searchInput = document.getElementById('search');
        const typeFilter = document.getElementById('typeFilter');
        const statsEl = document.getElementById('stats');

        function renderDecks() {
            const filterText = searchInput.value.toLowerCase();
            const filterType = typeFilter.value;

            grid.innerHTML = '';
            let visibleCount = 0;

            decks.forEach(deck => {
                const searchContent = [
                    deck.player_name,
                    ...deck.pokemon,
                    ...deck.trainers
                ].join(' ').toLowerCase();

                const matchesType = !filterType || deck.deck_type === filterType;
                const matchesText = !filterText || searchContent.includes(filterText);

                if (matchesType && matchesText) {
                    visibleCount++;
                    const card = document.createElement('div');
                    card.className = 'deck-card';
                    card.innerHTML = `
                        <div class="deck-header">
                            <div class="deck-type">${deck.deck_type}</div>
                            <div class="rank">${deck.rank}</div>
                        </div>
                        <div class="meta">
                            ${deck.event_date} | ${deck.shop_name} | ${deck.player_name || 'Anonymous'}
                        </div>
                        <div class="card-list">
                            <div class="section-title">Pokémon</div>
                            <div class="pkm-tags">
                                ${deck.pokemon.map(p => `<span class="tag">${p}</span>`).join('')}
                            </div>
                        </div>
                        <div class="card-list">
                            <div class="section-title">Trainers (Major)</div>
                            <div class="tr-tags">
                                ${deck.trainers.slice(0, 8).map(t => `<span class="tag">${t}</span>`).join('')}
                                ${deck.trainers.length > 8 ? '<span class="tag">...</span>' : ''}
                            </div>
                        </div>
                    `;
                    grid.appendChild(card);
                }
            });

            statsEl.textContent = `Total: ${visibleCount} / ${decks.length} decks shown`;
        }

        searchInput.addEventListener('input', renderDecks);
        typeFilter.addEventListener('change', renderDecks);
        renderDecks();
    </script>
</body>
</html>
    """
    
    output_path = "deck_report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"Report generated: {os.path.abspath(output_path)}")
    session.close()

if __name__ == "__main__":
    generate_report()
