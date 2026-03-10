import tkinter as tk
from tkinter import ttk, messagebox, filedialog
try:
    from tkcalendar import Calendar
except ImportError:
    # tkcalendar is not installed, but it should be based on previous steps
    Calendar = None
import sqlite3
import csv
import os
import sys
import random
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib

# 日本語フォント対応
matplotlib.rcParams['font.family'] = ['Meiryo', 'Yu Gothic', 'MS Gothic', 'sans-serif']

def get_db_path():
    # PyInstaller (`.exe`) 実行時と通常の `.py` 実行時の両方に対応
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 探索順: 1. exeと同じ階層 -> 2. カレントディレクトリ -> 3. 一つ上の階層 (開発時 dist/ 内用)
    paths_to_check = [
        os.path.join(base_dir, "cityresu.db"),
        os.path.join(os.getcwd(), "cityresu.db"),
        os.path.join(os.path.dirname(base_dir), "cityresu.db")
    ]
    
    for p in paths_to_check:
        if os.path.exists(p):
            return p
            
    # 見つからない場合はデフォルトのパスを返す (GUI上でエラー通知される)
    return paths_to_check[0]

DB_PATH = get_db_path()

class AnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ポケカ デッキ・カード分析ツール")
        self.root.geometry("900x600")

        # --- 上部フレーム: 設定・入力部 ---
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        # 分析メニュー
        ttk.Label(top_frame, text="分析メニュー:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.analysis_var = tk.StringVar(value="1. デッキタイプ別の入賞数とシェア率")
        self.analysis_combo = ttk.Combobox(
            top_frame, 
            textvariable=self.analysis_var, 
            values=[
                "1. デッキタイプ別の入賞数とシェア率",
                "2. 特定デッキ内のカード採用率と平均採用枚数",
                "3. デッキタイプの時系列推移",
                "4. 特定デッキ内におけるカード採用状況の時系列推移"
            ],
            width=50,
            state="readonly"
        )
        self.analysis_combo.grid(row=0, column=1, columnspan=3, sticky=tk.W, pady=5, padx=5)
        self.analysis_combo.bind("<<ComboboxSelected>>", self.on_analysis_change)

        # デッキ名入力
        ttk.Label(top_frame, text="特定のデッキ名:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.deck_name_var = tk.StringVar()
        self.deck_name_entry = ttk.Entry(top_frame, textvariable=self.deck_name_var, width=30, state="disabled")
        self.deck_name_entry.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)

        # 時系列単位
        ttk.Label(top_frame, text="集計単位:").grid(row=1, column=2, sticky=tk.W, pady=5, padx=10)
        self.interval_var = tk.StringVar(value="日次 (%Y-%m-%d)")
        self.interval_combo = ttk.Combobox(
            top_frame, 
            textvariable=self.interval_var, 
            values=["日次 (%Y-%m-%d)", "週次 (%Y-%W)", "月次 (%Y-%m)"],
            width=15,
            state="disabled"
        )
        self.interval_combo.grid(row=1, column=3, sticky=tk.W, pady=5, padx=5)

        # 対象期間
        ttk.Label(top_frame, text="対象期間(開始):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.start_date_var = tk.StringVar()
        self.start_date_entry = ttk.Entry(top_frame, textvariable=self.start_date_var, width=15)
        self.start_date_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Button(top_frame, text="📅", width=3, command=lambda: self.open_calendar(self.start_date_var)).grid(row=2, column=1, sticky=tk.E, padx=(0, 10))

        ttk.Label(top_frame, text="対象期間(終了):").grid(row=2, column=2, sticky=tk.W, pady=5, padx=10)
        self.end_date_var = tk.StringVar()
        self.end_date_entry = ttk.Entry(top_frame, textvariable=self.end_date_var, width=15)
        self.end_date_entry.grid(row=2, column=3, sticky=tk.W, pady=5, padx=5)
        ttk.Button(top_frame, text="📅", width=3, command=lambda: self.open_calendar(self.end_date_var)).grid(row=2, column=3, sticky=tk.E, padx=(0, 10))

        # 順位フィルター
        ttk.Label(top_frame, text="順位(Top Cut):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.rank_filter_var = tk.StringVar(value="すべて")
        self.rank_filter_combo = ttk.Combobox(
            top_frame, 
            textvariable=self.rank_filter_var, 
            values=["すべて", "優勝のみ", "2位以上", "Top4以上", "Top8以上", "Top16以上"],
            width=15,
            state="readonly"
        )
        self.rank_filter_combo.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)

        # 実行ボタン & エクスポートボタン
        btn_frame = ttk.Frame(top_frame)
        btn_frame.grid(row=4, column=0, columnspan=4, sticky=tk.W, pady=10)
        
        self.run_btn = ttk.Button(btn_frame, text="分析実行", command=self.run_analysis)
        self.run_btn.pack(side=tk.LEFT, padx=5)
        
        self.export_btn = ttk.Button(btn_frame, text="CSV出力", command=self.export_csv, state="disabled")
        self.export_btn.pack(side=tk.LEFT, padx=5)

        # DB接続状況
        self.db_status_lbl = ttk.Label(btn_frame, text="", foreground="grey")
        self.db_status_lbl.pack(side=tk.LEFT, padx=20)
        self.check_db()

        # --- 中央フレーム: 結果表示 (Notebook) ---
        mid_frame = ttk.Frame(self.root, padding=10)
        mid_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(mid_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # タブ1: データ表
        self.tab_table = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_table, text="データ表")

        # Treeviewとスクロールバー
        columns = ()
        self.tree = ttk.Treeview(self.tab_table, columns=columns, show="headings")
        
        yscb = ttk.Scrollbar(self.tab_table, orient=tk.VERTICAL, command=self.tree.yview)
        xscb = ttk.Scrollbar(self.tab_table, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscb.set, xscrollcommand=xscb.set)
        
        yscb.pack(side=tk.RIGHT, fill=tk.Y)
        xscb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # ダブルクリック・ドリルダウンのためのイベントバインド
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # タブ2: グラフ表示
        self.tab_graph = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_graph, text="グラフ表示")
        
        # グラフ用のメイン領域（左右に分割）
        graph_main_frame = ttk.Frame(self.tab_graph)
        graph_main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左側: グラフ描画領域
        graph_canvas_frame = ttk.Frame(graph_main_frame)
        graph_canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Matplotlib用のFigureとCanvasを準備
        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_canvas_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # アノテーション（ツールチップ）の初期化
        self.annot = self.ax.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="white", alpha=0.9),
                            arrowprops=dict(arrowstyle="->"))
        self.annot.set_visible(False)
        self.canvas.mpl_connect("motion_notify_event", self.on_graph_hover)
        self.lines_dict = {}

        # 右側: 操作パネル領域
        graph_control_frame = ttk.Frame(graph_main_frame, width=200)
        graph_control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        
        ttk.Label(graph_control_frame, text="表示項目の選択:").pack(anchor=tk.W)
        
        # スクロールバー付きリストボックス
        list_frame = ttk.Frame(graph_control_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.label_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, exportselection=False)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.label_listbox.yview)
        self.label_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.label_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.label_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        
        btn_frame = ttk.Frame(graph_control_frame)
        btn_frame.pack(fill=tk.X)
        self.btn_show_all = ttk.Button(btn_frame, text="全て表示", command=self.show_all_lines)
        self.btn_show_all.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.btn_hide_all = ttk.Button(btn_frame, text="選択解除", command=self.hide_all_lines)
        self.btn_hide_all.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.current_data = []
        self.current_columns = []

    def open_calendar(self, target_var):
        top = tk.Toplevel(self.root)
        top.title("日付選択")
        cal = Calendar(top, selectmode='day', date_pattern='y-mm-dd')
        cal.pack(padx=10, pady=10)
        
        def set_date():
            target_var.set(cal.get_date())
            top.destroy()
            
        ttk.Button(top, text="選択", command=set_date).pack(pady=5)

    def on_graph_hover(self, event):
        if not self.lines_dict:
            return
        vis = self.annot.get_visible()
        if event.inaxes == self.ax:
            for label, line in self.lines_dict.items():
                if not line.get_visible():
                    continue
                cont, ind = line.contains(event)
                if cont:
                    self.update_annot(line, ind, label, event)
                    self.annot.set_visible(True)
                    self.canvas.draw_idle()
                    return
        if vis:
            self.annot.set_visible(False)
            self.canvas.draw_idle()

    def update_annot(self, line, ind, label, event):
        x, y = line.get_data()
        idx = ind["ind"][0]
        val_x = x[idx]
        val_y = y[idx]
        text = f"{label}\n期間: {val_x}\n値: {val_y}"
        self.annot.xy = (event.xdata, event.ydata)
        self.annot.set_text(text)

    def on_listbox_select(self, event):
        selected_indices = self.label_listbox.curselection()
        for i in range(self.label_listbox.size()):
            label = self.label_listbox.get(i)
            if i in selected_indices:
                self.lines_dict[label].set_visible(True)
            else:
                self.lines_dict[label].set_visible(False)
        self.ax.relim()
        self.canvas.draw_idle()

    def show_all_lines(self):
        self.label_listbox.selection_set(0, tk.END)
        for line in self.lines_dict.values():
            line.set_visible(True)
        self.canvas.draw_idle()

    def hide_all_lines(self):
        self.label_listbox.selection_clear(0, tk.END)
        for line in self.lines_dict.values():
            line.set_visible(False)
        self.canvas.draw_idle()

    def on_tree_double_click(self, event):
        selection = self.analysis_var.get()
        if selection.startswith("1"):
            item_id = self.tree.focus()
            if not item_id:
                return
            item_values = self.tree.item(item_id, "values")
            if item_values:
                deck_name = item_values[0] # デッキタイプ名
                # 分析メニューを2に変更
                self.analysis_combo.current(1) # "2. 特定デッキ内のカード採用率と平均採用枚数"
                self.on_analysis_change()
                self.deck_name_var.set(deck_name)
                # 自動実行
                self.run_analysis()
                # データ表タブを選択
                self.notebook.select(self.tab_table)

    def check_db(self):
        if os.path.exists(DB_PATH):
            self.db_status_lbl.config(text=f"DB接続OK: {os.path.basename(DB_PATH)}")
        else:
            self.db_status_lbl.config(text=f"DBが見つかりません: {DB_PATH}", foreground="red")

    def on_analysis_change(self, event=None):
        selection = self.analysis_var.get()
        if selection.startswith("1"):
            self.deck_name_var.set("") # クリア
            self.deck_name_entry.config(state="disabled")
            self.interval_combo.config(state="disabled")
        elif selection.startswith("2"):
            self.deck_name_entry.config(state="normal")
            self.interval_combo.config(state="disabled")
        elif selection.startswith("3"):
            self.deck_name_var.set("") # クリア
            self.deck_name_entry.config(state="disabled")
            self.interval_combo.config(state="readonly")
        elif selection.startswith("4"):
            self.deck_name_entry.config(state="normal")
            self.interval_combo.config(state="readonly")

    def get_period_format(self):
        val = self.interval_var.get()
        if "日次" in val:
            return "%Y-%m-%d"
        elif "月次" in val:
            return "%Y-%m"
        else:
            return "%Y-W%W"

    def get_rank_filter_condition(self, table_alias="r"):
        val = self.rank_filter_var.get()
        if val == "優勝のみ":
            return f" AND {table_alias}.rank IN ('1 位', '優勝')"
        elif val == "2位以上":
            return f" AND {table_alias}.rank IN ('1 位', '優勝', '2 位', '準優勝')"
        elif val == "Top4以上":
            return f" AND {table_alias}.rank IN ('1 位', '優勝', '2 位', '準優勝', '3 位')"
        elif val == "Top8以上":
            return f" AND {table_alias}.rank IN ('1 位', '優勝', '2 位', '準優勝', '3 位', '5 位', 'ベスト8')"
        elif val == "Top16以上":
            return f" AND {table_alias}.rank IN ('1 位', '優勝', '2 位', '準優勝', '3 位', '5 位', 'ベスト8', '9 位', 'ベスト16')"
        return ""

    def run_analysis(self):
        if not os.path.exists(DB_PATH):
            messagebox.showerror("エラー", f"データベースファイルが見つかりません: {DB_PATH}")
            return

        selection = self.analysis_var.get()
        deck_name = self.deck_name_var.get().strip()
        period_fmt = self.get_period_format()
        start_date = self.start_date_var.get().strip()
        end_date = self.end_date_var.get().strip()

        if ("2" in selection or "4" in selection) and not deck_name:
            messagebox.showwarning("警告", "「特定のデッキ名」を入力してください。")
            return

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                
                rank_cond = self.get_rank_filter_condition("r")
                
                if selection.startswith("1"):
                    date_filter = ""
                    params = []
                    if start_date:
                        date_filter += " AND e.event_date >= ?"
                        params.append(start_date)
                    if end_date:
                        date_filter += " AND e.event_date <= ?"
                        params.append(end_date)
                        
                    date_filter_sub = ""
                    params_sub = []
                    if start_date:
                        date_filter_sub += " AND e2.event_date >= ?"
                        params_sub.append(start_date)
                    if end_date:
                        date_filter_sub += " AND e2.event_date <= ?"
                        params_sub.append(end_date)

                    query = f"""
                    SELECT 
                        r.deck_type AS デッキタイプ名,
                        COUNT(r.id) AS 入賞数,
                        ROUND(CAST(COUNT(r.id) AS FLOAT) * 100 / (
                            SELECT COUNT(r2.id) FROM results r2
                            JOIN events e2 ON r2.event_id = e2.id
                            WHERE r2.deck_type IS NOT NULL {date_filter_sub} {self.get_rank_filter_condition('r2')}
                        ), 2) AS シェア率_パーセント
                    FROM results r
                    JOIN events e ON r.event_id = e.id
                    WHERE r.deck_type IS NOT NULL
                    {date_filter}
                    {rank_cond}
                    GROUP BY r.deck_type
                    ORDER BY 入賞数 DESC
                    """
                    cursor.execute(query, tuple(params_sub + params))
                
                elif selection.startswith("2"):
                    date_filter_sub = ""
                    params_sub = [deck_name]
                    if start_date:
                        date_filter_sub += " AND e.event_date >= ?"
                        params_sub.append(start_date)
                    if end_date:
                        date_filter_sub += " AND e.event_date <= ?"
                        params_sub.append(end_date)

                    date_filter = ""
                    params = [deck_name]
                    if start_date:
                        date_filter += " AND e.event_date >= ?"
                        params.append(start_date)
                    if end_date:
                        date_filter += " AND e.event_date <= ?"
                        params.append(end_date)

                    query = f"""
                    SELECT
                        c.normalized_card_name AS カード名,
                        ROUND(CAST(COUNT(DISTINCT c.result_id) AS FLOAT) * 100 / (
                            SELECT COUNT(r.id) FROM results r 
                            JOIN events e ON r.event_id = e.id
                            WHERE r.deck_type = ? {date_filter_sub} {self.get_rank_filter_condition('r')}
                        ), 2) AS 採用率_パーセント,
                        ROUND(CAST(SUM(c.quantity) AS FLOAT) / COUNT(DISTINCT c.result_id), 2) AS 平均採用枚数,
                        SUM(CASE WHEN c.quantity = 1 THEN 1 ELSE 0 END) AS "1枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 1 THEN 1 ELSE 0 END) AS FLOAT) * 100 / COUNT(DISTINCT c.result_id), 2) AS "1枚_割合(%)",
                        SUM(CASE WHEN c.quantity = 2 THEN 1 ELSE 0 END) AS "2枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 2 THEN 1 ELSE 0 END) AS FLOAT) * 100 / COUNT(DISTINCT c.result_id), 2) AS "2枚_割合(%)",
                        SUM(CASE WHEN c.quantity = 3 THEN 1 ELSE 0 END) AS "3枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 3 THEN 1 ELSE 0 END) AS FLOAT) * 100 / COUNT(DISTINCT c.result_id), 2) AS "3枚_割合(%)",
                        SUM(CASE WHEN c.quantity = 4 THEN 1 ELSE 0 END) AS "4枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 4 THEN 1 ELSE 0 END) AS FLOAT) * 100 / COUNT(DISTINCT c.result_id), 2) AS "4枚_割合(%)"
                    FROM deck_cards c
                    JOIN results r ON r.id = c.result_id
                    JOIN events e ON r.event_id = e.id
                    WHERE r.deck_type = ?
                      AND c.normalized_card_name IS NOT NULL
                    {date_filter}
                    {rank_cond}
                    GROUP BY c.normalized_card_name
                    ORDER BY 採用率_パーセント DESC
                    """
                    cursor.execute(query, tuple(params_sub + params))

                elif selection.startswith("3"):
                    date_filter = ""
                    params = []
                    if start_date:
                        date_filter += " AND e.event_date >= ?"
                        params.append(start_date)
                    if end_date:
                        date_filter += " AND e.event_date <= ?"
                        params.append(end_date)

                    query = f"""
                    SELECT 
                        strftime('{period_fmt}', e.event_date) AS 開催期間,
                        r.deck_type AS デッキタイプ名,
                        COUNT(r.id) AS 入賞数
                    FROM results r
                    JOIN events e ON r.event_id = e.id
                    WHERE r.deck_type IS NOT NULL
                    {date_filter}
                    {rank_cond}
                    GROUP BY 開催期間, デッキタイプ名
                    ORDER BY 開催期間 ASC
                    """
                    cursor.execute(query, tuple(params))

                elif selection.startswith("4"):
                    date_filter = ""
                    params_sub = [deck_name]
                    params = [deck_name]
                    
                    if start_date:
                        date_filter += " AND e.event_date >= ?"
                        params_sub.append(start_date)
                        params.append(start_date)
                    if end_date:
                        date_filter += " AND e.event_date <= ?"
                        params_sub.append(end_date)
                        params.append(end_date)

                    query = f"""
                    WITH DeckTotalPerPeriod AS (
                        SELECT 
                            strftime('{period_fmt}', e.event_date) AS period,
                            COUNT(r.id) AS total_decks
                        FROM results r
                        JOIN events e ON r.event_id = e.id
                        WHERE r.deck_type = ? {date_filter} {self.get_rank_filter_condition('r')}
                        GROUP BY period
                    )
                    SELECT 
                        strftime('{period_fmt}', e.event_date) AS 開催期間,
                        c.normalized_card_name AS カード名,
                        ROUND(CAST(COUNT(DISTINCT c.result_id) AS FLOAT) * 100 / p.total_decks, 2) AS 採用率_パーセント,
                        ROUND(CAST(SUM(c.quantity) AS FLOAT) / COUNT(DISTINCT c.result_id), 2) AS 平均採用枚数
                    FROM deck_cards c
                    JOIN results r ON r.id = c.result_id
                    JOIN events e ON r.event_id = e.id
                    JOIN DeckTotalPerPeriod p ON p.period = strftime('{period_fmt}', e.event_date)
                    WHERE r.deck_type = ?
                      AND c.normalized_card_name IS NOT NULL
                    {date_filter}
                    {rank_cond}
                    GROUP BY 
                        開催期間, 
                        カード名,
                        p.total_decks
                    ORDER BY 
                        開催期間 ASC
                    """
                    cursor.execute(query, tuple(params_sub + params))

                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                
                self.update_table(columns, rows)
                self.plot_graph(selection, columns, rows)
                self.export_btn.config(state="normal")
                messagebox.showinfo("完了", f"{len(rows)}件のデータを取得しました。")

        except Exception as e:
            messagebox.showerror("エラー", f"クエリ実行中にエラーが発生しました:\n{e}")

    def treeview_sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try:
            # 数値としてソートを試みる（% や カンマ を除去）
            l.sort(key=lambda t: float(t[0].replace('%', '').replace(',', '')), reverse=reverse)
        except ValueError:
            # 失敗した場合は文字列としてソート
            l.sort(key=lambda t: t[0] if t[0] else "", reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda _col=col: self.treeview_sort_column(_col, not reverse))

    def update_table(self, columns, rows):
        # 既存のデータをクリア
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.current_columns = columns
        self.current_data = rows

        # カラム設定
        self.tree["columns"] = columns
        for col in columns:
            self.tree.heading(col, text=col, command=lambda _col=col: self.treeview_sort_column(_col, False))
            # 文字列長に応じて大まかに幅調整
            self.tree.column(col, width=150, anchor=tk.W)

        # データ挿入
        for row in rows:
            self.tree.insert("", tk.END, values=row)

    def plot_graph(self, selection, columns, rows):
        self.ax.clear()
        self.lines_dict.clear()
        self.label_listbox.delete(0, tk.END)
        # 再描画時にAnnotを残すために再度追加、あるいは消去されないようにする
        self.annot = self.ax.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="white", alpha=0.9),
                            arrowprops=dict(arrowstyle="->"), zorder=10)
        self.annot.set_visible(False)
        
        if not rows:
            self.ax.text(0.5, 0.5, 'データがありません', ha='center', va='center', fontfamily='sans-serif')
            self.canvas.draw()
            return

        if selection.startswith("3"):
            periods = sorted(list(set([row[0] for row in rows])))
            decks = list(set([row[1] for row in rows]))
            
            # デッキの総入賞数でソート
            deck_totals = []
            for d in decks:
                total = sum([r[2] for r in rows if r[1] == d])
                deck_totals.append((d, total))
            deck_totals.sort(key=lambda x: x[1], reverse=True)
            top_decks = [x[0] for x in deck_totals]
            
            for i, deck in enumerate(top_decks):
                deck_counts = []
                for p in periods:
                    matched = [r[2] for r in rows if r[0] == p and r[1] == deck]
                    val = matched[0] if matched else 0
                    deck_counts.append(val)
                
                # 重なりを防ぐためのわずかなジッター(散らばり)を付与
                # 0以上のデータにのみノイズを加え、最小限の変動に抑える
                jitter = [val + random.uniform(-0.1, 0.1) if val > 0 else 0 for val in deck_counts]

                line, = self.ax.plot(periods, jitter, marker='o', label=deck, picker=True, alpha=0.7, linewidth=1.5)
                self.lines_dict[deck] = line
                self.label_listbox.insert(tk.END, deck)
                if i < 10:  # 初期状態では上位10件のみ表示
                    self.label_listbox.selection_set(tk.END)
                else:
                    line.set_visible(False)
            
            self.ax.set_title("デッキタイプの時系列推移")
            self.ax.set_xlabel("期間")
            self.ax.set_ylabel("入賞数 (重なり回避のためノイズ追加)")
            self.ax.tick_params(axis='x', rotation=45)
            # 凡例はリストボックスがあるので非表示に（または表示する場合は重複）
            # self.ax.legend(loc='upper left', bbox_to_anchor=(1, 1))
            self.fig.tight_layout()

        elif selection.startswith("4"):
            periods = sorted(list(set([row[0] for row in rows])))
            cards = list(set([row[1] for row in rows]))
            
            # 全てのカードを選択できるように変更（デフォルトはトップ10件のみ選択状態にする等でもよい）
            card_avg_rates = []
            for c in cards:
                rates = [r[2] for r in rows if r[1] == c]
                card_avg_rates.append((c, sum(rates)/len(rates)))
            card_avg_rates.sort(key=lambda x: x[1], reverse=True)
            top_cards = [x[0] for x in card_avg_rates]
                
            for i, card in enumerate(top_cards):
                rates = []
                for p in periods:
                    matched = [r[2] for r in rows if r[0] == p and r[1] == card]
                    val = matched[0] if matched else 0
                    rates.append(val)
                
                # 重なりを防ぐためのわずかなジッター(散らばり)を付与
                # 採用率(%)に対して目立たない程度のノイズを付与
                jitter = [val + random.uniform(-0.3, 0.3) if val > 0 else 0 for val in rates]

                line, = self.ax.plot(periods, jitter, marker='o', label=card, picker=True, alpha=0.7, linewidth=1.5)
                self.lines_dict[card] = line
                self.label_listbox.insert(tk.END, card)
                if i < 10:  # 初期状態では上位10件のみ表示
                    self.label_listbox.selection_set(tk.END)
                else:
                    line.set_visible(False)

            self.ax.set_title("カード採用率の時系列推移")
            self.ax.set_xlabel("期間")
            self.ax.set_ylabel("採用率 (%) (重なり回避のためノイズ追加)")
            self.ax.tick_params(axis='x', rotation=45)
            self.fig.tight_layout()

        else:
            self.ax.text(0.5, 0.5, '時系列分析(3, 4)選択時に\nグラフが表示されます。', ha='center', va='center')
        
        self.canvas.draw()

    def export_csv(self):
        if not self.current_data:
            messagebox.showwarning("警告", "出力するデータがありません。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="CSVとして保存"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(self.current_columns)
                writer.writerows(self.current_data)
            messagebox.showinfo("完了", "CSVファイルを出力しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"ファイル保存中にエラーが発生しました:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AnalyzerApp(root)
    # 初期状態UI更新
    app.on_analysis_change()
    root.mainloop()
