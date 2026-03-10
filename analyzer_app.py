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
from datetime import date
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

class Toast(tk.Toplevel):
    """画面右上に表示される自動消去型通知 (トースト)"""
    def __init__(self, parent, message, delay=2000):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        # スタイル設定
        frame = tk.Frame(self, bg="#4CAF50", padx=2, pady=2) # 縁取り
        frame.pack()
        lbl = tk.Label(frame, text=message, bg="#f9f9f9", fg="#333333", 
                       padx=15, pady=8, font=("Meiryo", 10))
        lbl.pack()
        
        # 位置計算 (親ウィンドウの右上)
        self.update_idletasks()
        parent.update_idletasks()
        
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        
        tw = self.winfo_width()
        
        margin = 20
        x = px + pw - tw - margin
        y = py + margin
        
        # 親ウィンドウの外に出ないように調整
        if x < px: x = px + margin
        
        self.geometry(f"+{x}+{y}")
        
        # フェードイン効果 (簡易)
        self.attributes("-alpha", 0.0)
        self._fade_in()
        
        # 指定時間後に自動消去
        self.after(delay, self._fade_out)

    def _fade_in(self):
        alpha = self.attributes("-alpha")
        if alpha < 1.0:
            self.attributes("-alpha", alpha + 0.1)
            self.after(20, self._fade_in)

    def _fade_out(self):
        alpha = self.attributes("-alpha")
        if alpha > 0.0:
            self.attributes("-alpha", alpha - 0.1)
            self.after(20, self._fade_out)
        else:
            self.destroy()

class AnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ポケカ デッキ・カード分析ツール")
        # 起動時にウィンドウを最大化（Windows環境）
        try:
            self.root.state('zoomed')
        except Exception:
            # 他のOSや非対応環境向けに大きめの初期サイズを設定
            self.root.geometry("1100x750")

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

        # デッキ名入力（コンボボックスに変更）
        ttk.Label(top_frame, text="特定のデッキ名:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.deck_name_var = tk.StringVar()
        self.deck_name_combo = ttk.Combobox(top_frame, textvariable=self.deck_name_var, width=28, state="disabled")
        self.deck_name_combo.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)

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
        self.end_date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
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

        # DB接続状況と初期データ読み込み
        self.db_status_lbl = ttk.Label(btn_frame, text="", foreground="grey")
        self.db_status_lbl.pack(side=tk.LEFT, padx=20)
        self.check_db()
        self.load_deck_names()

        # --- 中央フレーム: 結果表示 (Notebook) ---
        mid_frame = ttk.Frame(self.root, padding=10)
        mid_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(mid_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # タブ1: データ表 (Treeview用フレームと、ヒートマップ用Canvasフレームの切り替え)
        self.tab_table = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_table, text="データ表")

        # Treeview (通常の表用)
        self.tree_frame = ttk.Frame(self.tab_table)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ()
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings")
        
        yscb = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xscb = ttk.Scrollbar(self.tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscb.set, xscrollcommand=xscb.set)
        
        yscb.pack(side=tk.RIGHT, fill=tk.Y)
        xscb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # ダブルクリック・ドリルダウンのためのイベントバインド
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Canvas (ヒートマップ表用)
        self.heat_frame = ttk.Frame(self.tab_table)
        # 初期状態では非表示
        
        self.heat_canvas = tk.Canvas(self.heat_frame, bg="white")
        self.heat_vbar = ttk.Scrollbar(self.heat_frame, orient=tk.VERTICAL, command=self.heat_canvas.yview)
        self.heat_hbar = ttk.Scrollbar(self.heat_frame, orient=tk.HORIZONTAL, command=self.heat_canvas.xview)
        self.heat_canvas.configure(yscrollcommand=self.heat_vbar.set, xscrollcommand=self.heat_hbar.set)
        
        self.heat_vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.heat_hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.heat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.heat_inner_frame = ttk.Frame(self.heat_canvas)
        self.heat_window = self.heat_canvas.create_window((0, 0), window=self.heat_inner_frame, anchor="nw")
        self.heat_inner_frame.bind("<Configure>", self.on_heat_frame_configure)
        self.heat_canvas.bind("<Configure>", self.on_heat_canvas_configure)
        
        # マウスホイールによるスクロール対応
        self.heat_canvas.bind_all("<MouseWheel>", self.on_mousewheel)

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
        # 固定レイアウトを管理しやすくするため最初は None
        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_canvas_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # ウィンドウリサイズ時にグラフのレイアウトを自動調整するためのバインド
        # self.canvas.get_tk_widget().bind("<Configure>", lambda e: self.on_graph_resize())

        # アノテーション（ツールチップ）の初期化
        self.annot = self.ax.annotate("", xy=(0,0), xytext=(20,20), textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="white", alpha=0.9),
                            arrowprops=dict(arrowstyle="->"))
        self.annot.set_visible(False)
        self.canvas.mpl_connect("motion_notify_event", self.on_graph_hover)
        self.canvas.mpl_connect("button_press_event", self.on_graph_click)
        self.lines_dict = {}
        self.locked_lines_graph = set()
        self.locked_lines_legend = set()

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
        self.pie_wedges = []

        # タブ3: ヘルプ
        self.tab_help = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_help, text="ヘルプ")
        self._setup_help_tab()

    def on_heat_frame_configure(self, event):
        self.heat_canvas.configure(scrollregion=self.heat_canvas.bbox("all"))

    def on_heat_canvas_configure(self, event):
        # Canvasの幅に合わせて内部フレームの最小幅を設定
        if self.heat_inner_frame.winfo_reqwidth() < event.width:
            self.heat_canvas.itemconfig(self.heat_window, width=event.width)

    def on_mousewheel(self, event):
        # 現在のタブがデータ表かつヒートマップが表示されている場合のみスクロール
        if self.notebook.select() == str(self.tab_table) and self.heat_frame.winfo_ismapped():
            self.heat_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def on_graph_resize(self):
        """リサイズ時に呼び出され、グラフのレイアウトを最適化する"""
        try:
            # 描画保留中のタスクを処理して正確なサイズを取得
            self.root.update_idletasks()
            
            # ウィンドウサイズに合わせてFigureのインチサイズを調整
            w = self.canvas.get_tk_widget().winfo_width()
            h = self.canvas.get_tk_widget().winfo_height()
            
            # サイズが極端に小さい場合はスキップ
            if w <= 100 or h <= 100:
                return

            # DPIを考慮してインチサイズを再計算
            self.fig.set_size_inches(w / self.fig.dpi, h / self.fig.dpi)
            
            # 汎用的なレイアウト調整
            self.refresh_layout()
            
            # idle中ではなく強制的に描画してレスポンスを向上（ただし頻度を抑える必要があるかもしれない）
            self.canvas.draw_idle()
        except Exception:
            pass

    def refresh_layout(self):
        """グラフと凡例のバランスを調整し、見切れを防ぐ"""
        has_legend = bool(self.ax.get_legend())
        
        # tight_layout は円グラフのリサイズ時に誤作動を起こしやすいため、
        # subplots_adjust で余白比率を固定してレスポンシブ対応させます。
        if has_legend:
            # 凡例がある場合: 右側に25%のスペースを空け、ラベル用に左と下を広げる
            self.fig.subplots_adjust(left=0.10, right=0.75, top=0.90, bottom=0.20)
        else:
            # 凡例がない場合: ラベル用に左と下を広げる
            self.fig.subplots_adjust(left=0.10, right=0.90, top=0.90, bottom=0.20)

    def _setup_help_tab(self):
        """ヘルプタブの内容設定"""
        help_text = tk.Text(self.tab_help, wrap=tk.WORD, font=("Meiryo", 10), padx=20, pady=20)
        help_text.pack(fill=tk.BOTH, expand=True)
        
        content = """【ポケカ 分析ツール 使い方ガイド】

■ 分析メニューの概要
1. デッキタイプ別の入賞数とシェア率
   - 指定期間内の全デッキの入賞数と割合を集計し、表と円グラフで表示します。
   - 「データ表」の行をダブルクリックすると、そのデッキのカード構成分析（メニュー2）へジャンプします。

2. 特定デッキ内のカード採用率と平均採用枚数
   - 選択したデッキタイプに、どのカードが何枚採用されているかを詳しく分析します。
   - 1枚〜4枚の採用枚数ごとの割合も表示されます。

3. デッキタイプの時系列推移
   - デッキタイプの入賞数の変化を、日次・週次・月次の単位で折れ線グラフにします。
   - どのデッキがいつ流行ったのか（メタゲームの変遷）を確認できます。

4. 特定デッキ内におけるカード採用状況の時系列推移
   - 選択したデッキに含まれるカードの「平均採用枚数」が、時系列でどう変化したかをグラフ化します。

■ グラフの操作方法
・ホバー（マウスを合わせる）: 
  データ点や円グラフの扇形に合わせると、詳細な数値がツールチップで表示されます。
・クリック: 
  グラフの線や扇形、または凡例の文字をクリックすると、その項目を「強調表示（ロック）」します。
  もう一度クリックすると解除、背景をクリックすると全解除されます。
・右側のリストボックス:
  グラフに表示したい項目だけをチェック（選択）して絞り込むことができます。
・凡例の自動調整:
  項目が多い場合、凡例は自動的に2列表示やフォントサイズの縮小を行い、視認性を維持します。

■ 便利な機能
・トースト通知: 処理が完了した際、画面右上にメッセージが表示されます。
・CSV出力: 分析結果をExcel等で読み込めるCSV形式で保存できます。
・カレンダーUI: 📅ボタンから直感的に日付を選択できます。
"""
        help_text.insert(tk.END, content)
        help_text.config(state=tk.DISABLED) # 読み取り専用

    def open_calendar(self, target_var):
        top = tk.Toplevel(self.root)
        top.title("日付選択")
        cal = Calendar(top, selectmode='day', date_pattern='y-mm-dd')
        cal.pack(padx=10, pady=10)
        
        def set_date():
            target_var.set(cal.get_date())
            top.destroy()
            
        ttk.Button(top, text="選択", command=set_date).pack(pady=5)

    def on_graph_click(self, event):
        if not self.lines_dict and not getattr(self, 'pie_wedges', []):
            return
            
        if not hasattr(self, 'locked_lines_graph'):
            self.locked_lines_graph = set()
        if not hasattr(self, 'locked_lines_legend'):
            self.locked_lines_legend = set()

        clicked_label = None
        is_legend_click = False

        leg = self.ax.get_legend()
        if leg and hasattr(self, 'map_label_to_legline'):
            leg_cont, _ = leg.contains(event)
            if leg_cont:
                for label, (legline, legtext) in self.map_label_to_legline.items():
                    if legline.contains(event)[0] or legtext.contains(event)[0]:
                        clicked_label = label
                        is_legend_click = True
                        break
        
        # Clicked on axes lines
        if not clicked_label and event.inaxes == self.ax:
            for label, line in self.lines_dict.items():
                if not line.get_visible(): continue
                cont, _ = line.contains(event)
                if cont:
                    clicked_label = label
                    break
            
            # Clicked on pie wedges
            if not clicked_label and hasattr(self, 'pie_wedges'):
                for w in self.pie_wedges:
                    cont, _ = w.contains(event)
                    if cont:
                        clicked_label = w.get_label()
                        break

        if clicked_label:
            if is_legend_click:
                if clicked_label in self.locked_lines_legend:
                    self.locked_lines_legend.remove(clicked_label)
                else:
                    self.locked_lines_legend.add(clicked_label)
            else:
                if clicked_label in self.locked_lines_graph:
                    self.locked_lines_graph.remove(clicked_label)
                else:
                    self.locked_lines_graph.add(clicked_label)
            self.update_graph_styles()
        elif event.inaxes == self.ax:
            # Clicked on background, clear locks
            if self.locked_lines_graph or self.locked_lines_legend:
                self.locked_lines_graph.clear()
                self.locked_lines_legend.clear()
                self.update_graph_styles()

    def update_graph_styles(self, hovered_label=None):
        if not hasattr(self, 'locked_lines_graph'): self.locked_lines_graph = set()
        if not hasattr(self, 'locked_lines_legend'): self.locked_lines_legend = set()
            
        any_locked = bool(self.locked_lines_graph | self.locked_lines_legend)
        needs_redraw = False
        
        # Line graphs
        for label, l in self.lines_dict.items():
            if not l.get_visible(): continue
            is_graph_locked = label in self.locked_lines_graph
            is_legend_locked = label in self.locked_lines_legend
            is_hovered = (label == hovered_label)
            
            if is_hovered or is_graph_locked:
                target_alpha = 1.0
                target_lw = 3.0
                target_z = 5
            elif is_legend_locked:
                target_alpha = 1.0
                target_lw = 1.5
                target_z = 1
            elif any_locked or hovered_label:
                target_alpha = 0.2
                target_lw = 1.0
                target_z = 1
            else:
                target_alpha = 0.7
                target_lw = 1.5
                target_z = 1
                
            if l.get_alpha() != target_alpha or l.get_linewidth() != target_lw:
                l.set_alpha(target_alpha)
                l.set_linewidth(target_lw)
                l.set_zorder(target_z)
                needs_redraw = True
                
        # Pie charts
        if hasattr(self, 'pie_wedges') and self.pie_wedges:
            for w in self.pie_wedges:
                if not getattr(w, 'get_visible', lambda: True)(): continue
                label = w.get_label()
                is_graph_locked = label in self.locked_lines_graph
                is_legend_locked = label in self.locked_lines_legend
                is_hovered = (label == hovered_label)
                
                if is_hovered or is_graph_locked or is_legend_locked:
                    target_alpha = 1.0
                elif any_locked or hovered_label:
                    target_alpha = 0.3
                else:
                    target_alpha = 0.8
                    
                if w.get_alpha() != target_alpha:
                    w.set_alpha(target_alpha)
                    needs_redraw = True
                    
        # Legends text bolding
        if hasattr(self, 'map_label_to_legline'):
            for lbl, (legline, legtext) in self.map_label_to_legline.items():
                target_weight = "bold" if (lbl in self.locked_lines_graph or lbl in self.locked_lines_legend) else "normal"
                if legtext.get_weight() != target_weight:
                    legtext.set_weight(target_weight)
                    needs_redraw = True
                
        if needs_redraw:
            self.canvas.draw_idle()

    def on_graph_hover(self, event):
        if not self.lines_dict and not getattr(self, 'pie_wedges', []):
            return
            
        hovered_label = None
        
        leg = self.ax.get_legend()
        if leg and hasattr(self, 'map_label_to_legline'):
            leg_cont, _ = leg.contains(event)
            if leg_cont:
                for label, (legline, legtext) in self.map_label_to_legline.items():
                    if legline.contains(event)[0] or legtext.contains(event)[0]:
                        hovered_label = label
                        break
                        
                if hovered_label:
                    self.update_graph_styles(hovered_label)
                    if self.annot.get_visible():
                        self.annot.set_visible(False)
                    return

        vis = self.annot.get_visible()
        annot_needs_update = False
        
        if event.inaxes == self.ax:
            for label, line in self.lines_dict.items():
                if not line.get_visible(): continue
                cont, ind = line.contains(event)
                if cont:
                    self.update_annot(line, ind, label, event)
                    hovered_label = label
                    annot_needs_update = True
                    break
        
            if not hovered_label and hasattr(self, 'pie_wedges') and self.pie_wedges:
                for w in self.pie_wedges:
                    cont, _ = w.contains(event)
                    if cont:
                        label = w.get_label()
                        if hasattr(self, 'pie_data_dict') and label in self.pie_data_dict:
                            count, share = self.pie_data_dict[label]
                            text = f"{label}\n入賞数: {count}\nシェア率: {share}%"
                            self.annot.xy = (event.xdata, event.ydata)
                            self.annot.set_text(text)
                            hovered_label = label
                            annot_needs_update = True
                            break

        if annot_needs_update:
            self.annot.set_visible(True)
        else:
            if vis:
                self.annot.set_visible(False)

        self.update_graph_styles(hovered_label)

    def update_annot(self, line, ind, label, event):
        x, y = line.get_data()
        idx = ind["ind"][0]
        val_x = x[idx]
        
        if hasattr(line, 'orig_y'):
            val_disp = line.orig_y[idx]
            if isinstance(val_disp, float):
                val_disp = f"{val_disp:.2f}"
            else:
                val_disp = str(val_disp)
        else:
            val_disp = f"{y[idx]:.2f}"
            
        text = f"{label}\n期間: {val_x}\n値: {val_disp}"
        self.annot.xy = (event.xdata, event.ydata)
        self.annot.set_text(text)

    def update_legend(self):
        leg = self.ax.get_legend()
        if leg:
            leg.remove()
        
        handles, labels = self.ax.get_legend_handles_labels()
        visible_handles = [h for h in handles if h.get_visible()]
        visible_labels = [l for h, l in zip(handles, labels) if h.get_visible()]
        
        if not visible_handles:
            return

        num_items = len(visible_handles)
        
        # 凡例が多すぎる場合はグラフ内には上位15件のみ表示（リストボックスで全件制御可能）
        display_handles = visible_handles
        display_labels = visible_labels
        if num_items > 20:
            display_handles = visible_handles[:20]
            display_labels = [f"{l[:10]}..." if len(l) > 10 else l for l in visible_labels[:20]]
            # 最後に「他...」を追加
            display_labels[-1] = "他..."

        # 項目数に応じてフォントサイズ調整
        fontsize = 8 if num_items > 10 else 9

        leg = self.ax.legend(display_handles, display_labels, loc='upper left', bbox_to_anchor=(1.02, 1), 
                             fontsize=fontsize, borderaxespad=0.)
        
        self.map_legend_to_ax = {}
        self.map_label_to_legline = {}
        
        for legline, legtext, origline in zip(leg.get_lines(), leg.get_texts(), visible_handles):
            legline.set_alpha(1.0)
            legtext.set_alpha(1.0)
            
            self.map_legend_to_ax[legline] = origline
            self.map_legend_to_ax[legtext] = origline
            self.map_label_to_legline[origline.get_label()] = (legline, legtext)

    def _build_pie_legend(self):
        """円グラフ用の凡例と強調表示の紐付け"""
        leg = self.ax.get_legend()
        if leg:
            leg.remove()
            
        # 可視状態のウェッジのみ取得
        visible_wedges = [w for w in self.pie_wedges if w.get_visible()]
        if not visible_wedges:
            return

        num_items = len(visible_wedges)
        if num_items > 30:
            ncol = 3
            fontsize = 6
        elif num_items > 15:
            ncol = 2
            fontsize = 8
        else:
            ncol = 1
            fontsize = 9
        
        leg = self.ax.legend(visible_wedges, [w.get_label() for w in visible_wedges], 
                             title="デッキタイプ", loc="upper left", bbox_to_anchor=(1.02, 1),
                             fontsize=fontsize, borderaxespad=0., ncol=ncol)
        
        self.map_label_to_legline = {}
        # pieの凡例は patches がハンドルになる
        for legline, legtext, wedge in zip(leg.get_patches(), leg.get_texts(), visible_wedges):
            legline.set_alpha(1.0)
            legtext.set_alpha(1.0)
            self.map_label_to_legline[wedge.get_label()] = (legline, legtext)

        # インチサイズの同期とレイアウト適用
        self.refresh_layout()
        self.canvas.draw_idle()

    def sync_legend_alphas(self):
        if not hasattr(self, 'map_label_to_legline'):
            return
        for label, (legline, legtext) in self.map_label_to_legline.items():
            visible = True
            if label in self.lines_dict:
                visible = self.lines_dict[label].get_visible()
            elif hasattr(self, 'pie_wedges'):
                for wedge in self.pie_wedges:
                    if wedge.get_label() == label:
                        visible = wedge.get_visible()
                        break
            
            alpha_val = 1.0 if visible else 0.2
            legline.set_alpha(alpha_val)
            legtext.set_alpha(alpha_val)

    def on_listbox_select(self, event):
        selected_indices = self.label_listbox.curselection()
        for i in range(self.label_listbox.size()):
            label = self.label_listbox.get(i)
            if label in self.lines_dict:
                if i in selected_indices:
                    self.lines_dict[label].set_visible(True)
                else:
                    self.lines_dict[label].set_visible(False)
            elif hasattr(self, 'pie_wedges'):
                # Pie chart case: toggle visible for wedges
                for wedge in self.pie_wedges:
                    if wedge.get_label() == label:
                        if i in selected_indices:
                            wedge.set_visible(True)
                        else:
                            wedge.set_visible(False)
        self.ax.relim()
        
        selection = self.analysis_var.get()
        if selection.startswith("1"):
            self.sync_legend_alphas()
        else:
            self.update_legend()
            
        self.canvas.draw_idle()

    def show_all_lines(self):
        self.label_listbox.selection_set(0, tk.END)
        for line in self.lines_dict.values():
            line.set_visible(True)
        if hasattr(self, 'pie_wedges'):
            for wedge in self.pie_wedges:
                wedge.set_visible(True)
                
        selection = self.analysis_var.get()
        if selection.startswith("1"):
            self.sync_legend_alphas()
        else:
            self.update_legend()
            
        self.canvas.draw_idle()

    def hide_all_lines(self):
        self.label_listbox.selection_clear(0, tk.END)
        for line in self.lines_dict.values():
            line.set_visible(False)
        if hasattr(self, 'pie_wedges'):
            for wedge in self.pie_wedges:
                wedge.set_visible(False)
                
        selection = self.analysis_var.get()
        if selection.startswith("1"):
            self.sync_legend_alphas()
        else:
            self.update_legend()
            
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

    def load_deck_names(self):
        if not os.path.exists(DB_PATH):
            return
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT deck_type FROM results WHERE deck_type IS NOT NULL AND deck_type != '' ORDER BY deck_type")
                decks = [row[0] for row in cursor.fetchall()]
                self.deck_name_combo['values'] = decks
        except Exception:
            pass

    def on_analysis_change(self, event=None):
        selection = self.analysis_var.get()
        if selection.startswith("1"):
            self.deck_name_var.set("") # クリア
            self.deck_name_combo.config(state="disabled")
            self.interval_combo.config(state="disabled")
        elif selection.startswith("2"):
            self.deck_name_combo.config(state="readonly")
            self.interval_combo.config(state="disabled")
        elif selection.startswith("3"):
            self.deck_name_var.set("") # クリア
            self.deck_name_combo.config(state="disabled")
            self.interval_combo.config(state="readonly")
        elif selection.startswith("4"):
            self.deck_name_combo.config(state="readonly")
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
                        ROUND(CAST(COUNT(r.id) AS FLOAT) * 100.0 / (
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
                        ROUND(CAST(COUNT(DISTINCT c.result_id) AS FLOAT) * 100.0 / (
                            SELECT COUNT(r.id) FROM results r 
                            JOIN events e ON r.event_id = e.id
                            WHERE r.deck_type = ? {date_filter_sub} {self.get_rank_filter_condition('r')}
                        ), 2) AS 採用率_パーセント,
                        ROUND(CAST(SUM(c.quantity) AS FLOAT) / COUNT(DISTINCT c.result_id), 2) AS 平均採用枚数,
                        SUM(CASE WHEN c.quantity = 1 THEN 1 ELSE 0 END) AS "1枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 1 THEN 1 ELSE 0 END) AS FLOAT) * 100.0 / COUNT(DISTINCT c.result_id), 2) AS "1枚_割合(%)",
                        SUM(CASE WHEN c.quantity = 2 THEN 1 ELSE 0 END) AS "2枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 2 THEN 1 ELSE 0 END) AS FLOAT) * 100.0 / COUNT(DISTINCT c.result_id), 2) AS "2枚_割合(%)",
                        SUM(CASE WHEN c.quantity = 3 THEN 1 ELSE 0 END) AS "3枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 3 THEN 1 ELSE 0 END) AS FLOAT) * 100.0 / COUNT(DISTINCT c.result_id), 2) AS "3枚_割合(%)",
                        SUM(CASE WHEN c.quantity = 4 THEN 1 ELSE 0 END) AS "4枚",
                        ROUND(CAST(SUM(CASE WHEN c.quantity = 4 THEN 1 ELSE 0 END) AS FLOAT) * 100.0 / COUNT(DISTINCT c.result_id), 2) AS "4枚_割合(%)"
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
                        WHERE r.deck_type = ? {date_filter} {rank_cond}
                        GROUP BY period
                    )
                    SELECT 
                        strftime('{period_fmt}', e.event_date) AS 開催期間,
                        c.normalized_card_name AS カード名,
                        ROUND(CAST(COUNT(DISTINCT c.result_id) AS FLOAT) * 100.0 / p.total_decks, 2) AS 採用率_パーセント,
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
                
                if selection.startswith("4"):
                    # Treeviewを隠してCanvas（ヒートマップ）を表示
                    self.tree_frame.pack_forget()
                    self.heat_frame.pack(fill=tk.BOTH, expand=True)

                    # 表表示用にクロス集計（ピボット）を作成
                    raw_rows = rows
                    periods = sorted(list(set([r[0] for r in raw_rows])))
                    card_data = {}
                    for row in raw_rows:
                        period, card, rate, avg = row
                        if card not in card_data:
                            card_data[card] = {}
                        card_data[card][period] = (rate, avg)

                    table_columns = ["カード名"] + periods
                    
                    # ソート設定（全期間の平均採用率を基準に降順ソート）
                    def sort_key(card):
                        rates = [data[0] for data in card_data[card].values()]
                        return sum(rates) / len(rates) if rates else 0

                    sorted_cards = sorted(card_data.keys(), key=sort_key, reverse=True)

                    # 内部フレームの子ウィジェットを全て削除
                    for widget in self.heat_inner_frame.winfo_children():
                        widget.destroy()

                    # ヘッダー描画
                    for col_idx, col_name in enumerate(table_columns):
                        lbl = tk.Label(self.heat_inner_frame, text=col_name, bg="#f0f0f0", relief=tk.RIDGE, bd=1, padx=5, pady=5)
                        lbl.grid(row=0, column=col_idx, sticky="nsew")
                        # 列の幅を定義
                        if col_idx == 0:
                            self.heat_inner_frame.columnconfigure(col_idx, minsize=180) # カード名
                        else:
                            self.heat_inner_frame.columnconfigure(col_idx, minsize=100) # 日付

                    self.current_columns = table_columns
                    self.current_data = [] # 生データ保存用(CSV出力用)

                    # データ行描画
                    for row_idx, card in enumerate(sorted_cards, start=1):
                        row_data_csv = [card]
                        
                        # カード名セル
                        lbl = tk.Label(self.heat_inner_frame, text=card, bg="white", relief=tk.RIDGE, bd=1, padx=5, pady=5, anchor="w")
                        lbl.grid(row=row_idx, column=0, sticky="nsew")
                        
                        for col_idx, p in enumerate(periods, start=1):
                            if p in card_data[card]:
                                rate, avg = card_data[card][p]
                                avg_str = f"{int(avg)}" if avg.is_integer() else f"{avg:.1f}"
                                text = f"{avg_str} ({int(rate)}%)"
                                row_data_csv.append(text)
                                
                                # セルごとの色計算（平均採用枚数ベース: 0〜4の5段階）
                                # 四捨五入ではなく、小数点切り捨てで「1枚台」「2枚台」といった基準で色分けする
                                avg_floor = int(avg)
                                
                                if avg_floor == 0:
                                    bg_color = "#ffffff" # 白
                                    fg_color = "black"
                                elif avg_floor == 1:
                                    bg_color = "#e6f2ff" # 極薄い青
                                    fg_color = "black"
                                elif avg_floor == 2:
                                    bg_color = "#b3d9ff" # 薄い青
                                    fg_color = "black"
                                elif avg_floor == 3:
                                    bg_color = "#4d94ff" # 青
                                    fg_color = "white"
                                else: # 4以上
                                    bg_color = "#0047b3" # 濃い青
                                    fg_color = "white"
                                
                                cell_lbl = tk.Label(self.heat_inner_frame, text=text, bg=bg_color, fg=fg_color, relief=tk.RIDGE, bd=1)
                                cell_lbl.grid(row=row_idx, column=col_idx, sticky="nsew")
                            else:
                                row_data_csv.append("")
                                cell_lbl = tk.Label(self.heat_inner_frame, text="", bg="white", relief=tk.RIDGE, bd=1)
                                cell_lbl.grid(row=row_idx, column=col_idx, sticky="nsew")
                                
                        self.current_data.append(row_data_csv)

                    self.plot_graph(selection, columns, raw_rows, is_raw=True)
                else:
                    # Treeviewを表示してCanvas（ヒートマップ）を隠す
                    self.heat_frame.pack_forget()
                    self.tree_frame.pack(fill=tk.BOTH, expand=True)
                    self.update_table(columns, rows)
                    self.plot_graph(selection, columns, rows)

                self.export_btn.config(state="normal")
                Toast(self.root, "データの取得・集計が完了しました。")

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

    def plot_graph(self, selection, columns, rows, is_raw=False):
        # 現在のウィジェットサイズに合わせてFigureサイズを同期（リサイズイベント削除の補填）
        w = self.canvas.get_tk_widget().winfo_width()
        h = self.canvas.get_tk_widget().winfo_height()
        if w > 100 and h > 100:
            self.fig.set_size_inches(w / self.fig.dpi, h / self.fig.dpi)

        self.ax.clear()
        self.lines_dict.clear()
        if hasattr(self, 'locked_lines_graph'):
            self.locked_lines_graph.clear()
        if hasattr(self, 'locked_lines_legend'):
            self.locked_lines_legend.clear()
        self.pie_wedges = []
        self.pie_data_dict = {}
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

        if selection.startswith("1"):
            # デッキタイプ別のシェア率を円グラフで表示
            # columns: [デッキタイプ名, 入賞数, シェア率_パーセント]
            data = sorted(rows, key=lambda x: x[2], reverse=True)
            
            top_n = 12
            plot_data = data[:top_n]
            others = data[top_n:]
            
            labels = []
            sizes = []
            tooltip_data = {}
            
            for item in plot_data:
                name, count, share = item
                labels.append(name)
                sizes.append(share)
                tooltip_data[name] = (count, share)
            
            if others:
                others_count = sum([x[1] for x in others])
                others_share = sum([x[2] for x in others])
                labels.append("その他")
                sizes.append(others_share)
                tooltip_data["その他"] = (others_count, round(others_share, 2))

            self.pie_data_dict = tooltip_data
            
            # 円グラフ描画
            wedges, texts = self.ax.pie(sizes, labels=None, startangle=90, counterclock=False, 
                                        wedgeprops={'alpha': 0.8, 'edgecolor': 'white'})
            
            # 【追加】明示的にアスペクト比を等しくし、リサイズ時も真円を保つ
            self.ax.axis('equal')
            
            self.pie_wedges = wedges
            for i, wedge in enumerate(wedges):
                lbl = f"{labels[i]} ({sizes[i]:.1f}%)"
                wedge.set_label(lbl)
                wedge.set_picker(True)
                # pie_data_dict のキーも統一ラベルで登録
                if labels[i] in tooltip_data:
                    self.pie_data_dict[lbl] = tooltip_data[labels[i]]
            
            self.ax.set_title("デッキタイプ別のシェア率")
            
            # リストボックスに反映（全件選択）
            for w in wedges:
                self.label_listbox.insert(tk.END, w.get_label())
                self.label_listbox.selection_set(tk.END)
            
            # 他グラフと統一の凡例描画（クリック・ホバー強調対応）
            self._build_pie_legend()

        elif selection.startswith("3"):
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
                line.orig_y = deck_counts
                self.lines_dict[deck] = line
                self.label_listbox.insert(tk.END, deck)
                if i < 10:  # 初期状態では上位10件のみ表示
                    self.label_listbox.selection_set(tk.END)
                else:
                    line.set_visible(False)
            
            self.ax.set_title("デッキタイプの時系列推移")
            self.ax.set_xlabel("期間")
            self.ax.set_ylabel("入賞数")
            self.ax.tick_params(axis='x', rotation=45)
            
            # 「ノイズ追加」の注釈を小さく右下に表示
            self.ax.text(1.0, -0.15, "*重なり回避のためノイズ追加", transform=self.ax.transAxes, 
                         ha='right', fontsize=7, color='grey')
            
            # X軸のラベルが多すぎる場合に間引く
            import matplotlib.ticker as ticker
            self.ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=15))
            
            self.update_legend()

        elif selection.startswith("4"):
            # is_raw=Trueの場合、rowsは [開催期間, カード名, 採用率, 平均採用枚数]
            periods = sorted(list(set([row[0] for row in rows])))
            cards = list(set([row[1] for row in rows]))
            
            # 各カードのグラフ表示順（凡例や初期選択のため）、平均採用枚数の全期間平均でソート
            card_avg_counts = []
            for c in cards:
                counts = [r[3] for r in rows if r[1] == c] # 3: 平均採用枚数
                card_avg_counts.append((c, sum(counts)/len(counts) if counts else 0))
            card_avg_counts.sort(key=lambda x: x[1], reverse=True)
            top_cards = [x[0] for x in card_avg_counts]
                
            for i, card in enumerate(top_cards):
                values = []
                for p in periods:
                    matched = [r[3] for r in rows if r[0] == p and r[1] == card] # 3: 平均採用枚数
                    val = matched[0] if matched else 0
                    values.append(val)
                
                # 枚数に対するジッターは小さめに (0.05程度)
                jitter = [val + random.uniform(-0.05, 0.05) if val > 0 else 0 for val in values]

                line, = self.ax.plot(periods, jitter, marker='o', label=card, picker=True, alpha=0.7, linewidth=1.5)
                line.orig_y = values
                self.lines_dict[card] = line
                self.label_listbox.insert(tk.END, card)
                if i < 10:  # 初期状態では上位10件のみ表示
                    self.label_listbox.selection_set(tk.END)
                else:
                    line.set_visible(False)

            self.ax.set_title("カード平均採用枚数の時系列推移")
            self.ax.set_xlabel("期間")
            self.ax.set_ylabel("平均採用枚数")
            self.ax.tick_params(axis='x', rotation=45)

            self.ax.text(1.0, -0.15, "*重なり回避のためノイズ追加", transform=self.ax.transAxes, 
                         ha='right', fontsize=7, color='grey')
            
            # X軸のラベルが多すぎる場合に間引く
            import matplotlib.ticker as ticker
            self.ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=15))
            
            self.update_legend()

        else:
            self.ax.text(0.5, 0.5, '時系列分析(3, 4)選択時に\nグラフが表示されます。', ha='center', va='center')
        
        # グラフを描画するタイミングでレイアウトを整える
        self.refresh_layout()
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
            Toast(self.root, "CSVファイルを出力しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"ファイル保存中にエラーが発生しました:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AnalyzerApp(root)
    # 初期状態UI更新
    app.on_analysis_change()
    root.mainloop()
