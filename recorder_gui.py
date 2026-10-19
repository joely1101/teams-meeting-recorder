"""
Teams 會議雙向錄音與 AI 語音轉文字工具 (橫向寬螢幕專業版)
功能：
1. 雙向錄音 (揚聲器對方聲音 + 麥克風自己聲音) 混音轉高品質 MP3
2. 雲端 AI 語音轉文字 (時間軸 + 人物說話者識別 + 自動生成會議摘要與待辦清單)
3. 自動將轉譯結果分存為【會議摘要】與【逐字稿】二個檔案
"""

import os
import sys
import time
import datetime
import threading
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# 設置 Windows 高 DPI 認知
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from audio_engine import AudioEngine
import transcriber

class TeamsRecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Teams 會議雙向錄音 ＆ AI 語音轉文字 (揚聲器+麥克風混音 / 時間軸+人物識別)")
        # 橫向電腦寬螢幕預設尺寸
        self.root.geometry("1280x780")
        self.root.minsize(1120, 680)

        # 讀取本地設定
        self.cfg = transcriber.load_config()
        self.save_key_local = self.cfg.get("save_key_local", bool(self.cfg.get("gemini_api_key", "")))
        self.cfg["save_key_local"] = self.save_key_local

        # 初始化音訊引擎
        self.engine = AudioEngine()
        self.is_recording = False
        self.is_processing = False
        self.is_transcribing = False
        self.start_record_timestamp = 0
        self.last_saved_mp3 = None
        self.last_stt_result = None

        # 設備列表快取
        self.spk_devices = []
        self.mic_devices = []

        self._apply_style()
        self._build_ui()
        self._refresh_device_list()
        self._schedule_meter_update()

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        self.bg_color = "#f4f6f9"
        self.card_bg = "#ffffff"
        self.accent_color = "#1f6feb"
        self.text_color = "#24292f"
        
        self.root.configure(bg=self.bg_color)
        
        style.configure(".", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 9))
        style.configure("Card.TFrame", background=self.card_bg, relief="groove")
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), background=self.card_bg)
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"), background=self.card_bg, foreground="#24292f")
        style.configure("Dim.TLabel", font=("Segoe UI", 8), foreground="#555555", background=self.card_bg)

    def _build_ui(self):
        # 頂部 Header Bar
        top_bar = tk.Frame(self.root, bg="#24292f", height=42, padx=16)
        top_bar.pack(fill="x")

        top_title = tk.Label(top_bar, text="🎙️ Teams 會議雙向錄音 ＆ AI 語音轉文字", font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#24292f")
        top_title.pack(side="left", pady=8)

        top_sub = tk.Label(top_bar, text="喇叭/麥克風雙軌混音  •  Gemini 3.8 Flash AI 時間軸＋角色識別  •  自動分存摘要與逐字稿", font=("Segoe UI", 9), fg="#8b949e", bg="#24292f")
        top_sub.pack(side="left", padx=15, pady=8)

        # 主體雙欄容器 (左右分割，充分發揮橫向寬螢幕優勢)
        main_container = ttk.Frame(self.root, padding=12)
        main_container.pack(fill="both", expand=True)

        # 左右等高網格佈局
        main_container.columnconfigure(0, weight=45) # 左欄 45%
        main_container.columnconfigure(1, weight=55) # 右欄 55%
        main_container.rowconfigure(0, weight=1)

        # ==========================================================
        # ◀ 左側欄：會議雙向錄音控制中心
        # ==========================================================
        left_panel = ttk.Frame(main_container, style="Card.TFrame", padding=14)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        # 標題列 + 重新整理按鈕
        dev_title_frame = ttk.Frame(left_panel, style="Card.TFrame")
        dev_title_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(dev_title_frame, text="🎙️ 會議雙向錄音控制", style="Section.TLabel").pack(side="left")
        self.refresh_btn = ttk.Button(dev_title_frame, text="🔄 重新整理設備", command=self._refresh_device_list)
        self.refresh_btn.pack(side="right")

        # 1. 揚聲器 (Loopback)
        spk_frame = ttk.Frame(left_panel, style="Card.TFrame")
        spk_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(spk_frame, text="🔊 揚聲器 / 喇叭（會議中對方的聲音）：", font=("Segoe UI", 9, "bold"), background=self.card_bg).pack(anchor="w")
        self.spk_combobox = ttk.Combobox(spk_frame, state="readonly", font=("Segoe UI", 9))
        self.spk_combobox.pack(fill="x", pady=(2, 4))
        
        spk_ctrl = ttk.Frame(spk_frame, style="Card.TFrame")
        spk_ctrl.pack(fill="x")
        ttk.Label(spk_ctrl, text="音量增益：", style="Dim.TLabel").pack(side="left")
        self.spk_gain_var = tk.DoubleVar(value=1.0)
        self.spk_gain_slider = ttk.Scale(spk_ctrl, from_=0.0, to=2.0, variable=self.spk_gain_var, orient="horizontal", length=130)
        self.spk_gain_slider.pack(side="left", padx=4)
        self.spk_gain_lbl = ttk.Label(spk_ctrl, text="100%", style="Dim.TLabel", width=4)
        self.spk_gain_lbl.pack(side="left")
        self.spk_gain_slider.configure(command=lambda v: self.spk_gain_lbl.configure(text=f"{int(float(v)*100)}%"))

        ttk.Label(spk_ctrl, text="動態：", style="Dim.TLabel").pack(side="left", padx=(10, 2))
        self.spk_meter = tk.Canvas(spk_ctrl, width=110, height=10, bg="#e1e4e8", highlightthickness=0)
        self.spk_meter.pack(side="left")

        ttk.Separator(left_panel, orient="horizontal").pack(fill="x", pady=8)

        # 2. 麥克風
        mic_frame = ttk.Frame(left_panel, style="Card.TFrame")
        mic_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(mic_frame, text="🎤 麥克風（自己說話的聲音）：", font=("Segoe UI", 9, "bold"), background=self.card_bg).pack(anchor="w")
        self.mic_combobox = ttk.Combobox(mic_frame, state="readonly", font=("Segoe UI", 9))
        self.mic_combobox.pack(fill="x", pady=(2, 4))

        mic_ctrl = ttk.Frame(mic_frame, style="Card.TFrame")
        mic_ctrl.pack(fill="x")
        ttk.Label(mic_ctrl, text="音量增益：", style="Dim.TLabel").pack(side="left")
        self.mic_gain_var = tk.DoubleVar(value=1.2)
        self.mic_gain_slider = ttk.Scale(mic_ctrl, from_=0.0, to=2.5, variable=self.mic_gain_var, orient="horizontal", length=130)
        self.mic_gain_slider.pack(side="left", padx=4)
        self.mic_gain_lbl = ttk.Label(mic_ctrl, text="120%", style="Dim.TLabel", width=4)
        self.mic_gain_lbl.pack(side="left")
        self.mic_gain_slider.configure(command=lambda v: self.mic_gain_lbl.configure(text=f"{int(float(v)*100)}%"))

        ttk.Label(mic_ctrl, text="動態：", style="Dim.TLabel").pack(side="left", padx=(10, 2))
        self.mic_meter = tk.Canvas(mic_ctrl, width=110, height=10, bg="#e1e4e8", highlightthickness=0)
        self.mic_meter.pack(side="left")

        ttk.Separator(left_panel, orient="horizontal").pack(fill="x", pady=8)

        # 3. 儲存路徑
        save_box = ttk.Frame(left_panel, style="Card.TFrame")
        save_box.pack(fill="x", pady=(0, 6))
        ttk.Label(save_box, text="📁 MP3 儲存路徑：", font=("Segoe UI", 9, "bold"), background=self.card_bg).pack(anchor="w")
        
        path_input_box = ttk.Frame(save_box, style="Card.TFrame")
        path_input_box.pack(fill="x", pady=(2, 0))
        self.save_path_var = tk.StringVar()
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        self._generate_default_filename(base_dir)
        self.save_entry = ttk.Entry(path_input_box, textvariable=self.save_path_var, font=("Segoe UI", 9))
        self.save_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.browse_btn = ttk.Button(path_input_box, text="瀏覽...", command=self._browse_save_path)
        self.browse_btn.pack(side="right")

        # 4. 控制按鈕與計時器 (醒目的大區域)
        action_card = tk.Frame(left_panel, bg="#f8f9fa", bd=1, relief="solid", padx=10, pady=12)
        action_card.pack(fill="x", pady=(10, 6))

        self.timer_lbl = tk.Label(action_card, text="00:00:00", font=("Consolas", 26, "bold"), fg="#24292f", bg="#f8f9fa")
        self.timer_lbl.pack(anchor="center", pady=(0, 8))

        btn_row = tk.Frame(action_card, bg="#f8f9fa")
        btn_row.pack(anchor="center", pady=(0, 4))

        self.record_btn = tk.Button(
            btn_row,
            text="🔴 開始錄音",
            font=("Segoe UI", 11, "bold"),
            bg="#d73a49",
            fg="#ffffff",
            activebackground="#cb2431",
            activeforeground="#ffffff",
            relief="flat",
            padx=24,
            pady=8,
            cursor="hand2",
            command=self._toggle_recording
        )
        self.record_btn.pack(side="left", padx=6)

        self.open_folder_btn = ttk.Button(btn_row, text="📁 開啟檔案目錄", command=self._open_output_folder, state="disabled")
        self.open_folder_btn.pack(side="left", padx=6)

        self.rec_progress_bar = ttk.Progressbar(left_panel, orient="horizontal", mode="determinate")
        self.rec_progress_bar.pack(fill="x", pady=(8, 2))
        self.rec_status_lbl = ttk.Label(left_panel, text="就緒。選擇設備後點擊「開始錄音」即可同時錄製揚聲器與麥克風。", style="Dim.TLabel")
        self.rec_status_lbl.pack(anchor="w")


        # ==========================================================
        # ▶ 右側欄：AI 會議語音轉文字工作台 (Gemini 雲端轉錄)
        # ==========================================================
        right_panel = ttk.Frame(main_container, style="Card.TFrame", padding=14)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # 標題列
        stt_title_frame = ttk.Frame(right_panel, style="Card.TFrame")
        stt_title_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(stt_title_frame, text="📝 AI 語音轉文字工作台", style="Section.TLabel").pack(side="left")
        ttk.Label(stt_title_frame, text="（含時間軸 ＋ 說話者識別 ＋ 會議重點摘要）", style="Dim.TLabel").pack(side="left", padx=6)

        # 1. 選取錄音檔
        stt_file_frame = ttk.Frame(right_panel, style="Card.TFrame")
        stt_file_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(stt_file_frame, text="選取錄音檔：", font=("Segoe UI", 9, "bold"), background=self.card_bg).pack(anchor="w")
        
        stt_file_input_box = ttk.Frame(stt_file_frame, style="Card.TFrame")
        stt_file_input_box.pack(fill="x", pady=(2, 0))
        self.stt_file_var = tk.StringVar(value=self.save_path_var.get())
        self.stt_file_entry = ttk.Entry(stt_file_input_box, textvariable=self.stt_file_var, font=("Segoe UI", 9))
        self.stt_file_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.stt_browse_btn = ttk.Button(stt_file_input_box, text="📂 選擇檔案...", command=self._browse_stt_file)
        self.stt_browse_btn.pack(side="right")

        # 2. Google Gemini API 設定
        api_frame = ttk.Frame(right_panel, style="Card.TFrame")
        api_frame.pack(fill="x", pady=(0, 6))

        api_header = ttk.Frame(api_frame, style="Card.TFrame")
        api_header.pack(fill="x", pady=(0, 2))
        ttk.Label(api_header, text="🔑 Google Gemini API Key：", font=("Segoe UI", 9, "bold"), background=self.card_bg).pack(side="left")
        self.guide_btn = ttk.Button(api_header, text="❓ 如何免費取得 API Key？ (超簡易教學)", command=self._show_api_key_guide)
        self.guide_btn.pack(side="right")

        api_input_row = ttk.Frame(api_frame, style="Card.TFrame")
        api_input_row.pack(fill="x", pady=(2, 2))
        initial_key = self.cfg.get("gemini_api_key", "") if self.save_key_local else ""
        self.api_key_var = tk.StringVar(value=initial_key)
        self.api_key_entry = ttk.Entry(api_input_row, textvariable=self.api_key_var, show="*", font=("Segoe UI", 9))
        self.api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.show_key_var = tk.BooleanVar(value=False)
        def _toggle_key_vis():
            self.api_key_entry.configure(show="" if self.show_key_var.get() else "*")
        ttk.Checkbutton(api_input_row, text="顯示", variable=self.show_key_var, command=_toggle_key_vis).pack(side="right")

        # 勾選是否把 API Key 存在 local
        api_opt_row = ttk.Frame(api_frame, style="Card.TFrame")
        api_opt_row.pack(fill="x", pady=(2, 2))

        self.save_key_var = tk.BooleanVar(value=self.save_key_local)
        self.save_key_cb = ttk.Checkbutton(
            api_opt_row,
            text="💾 將 API Key 儲存在本機（勾選後每次開啟程式會自動載入）",
            variable=self.save_key_var,
            command=self._on_toggle_save_key
        )
        self.save_key_cb.pack(side="left")

        # 監聽 API Key 輸入變更，若已勾選儲存則自動同步寫入本地設定
        def _on_key_changed(*args):
            if self.save_key_var.get():
                self.cfg["save_key_local"] = True
                self.cfg["gemini_api_key"] = self.api_key_var.get().strip()
                transcriber.save_config(self.cfg)
        self.api_key_var.trace_add("write", _on_key_changed)

        self.summarize_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            api_frame,
            text="自動產出並分存二個檔案：【會議重點摘要】與【詳細逐字稿】",
            variable=self.summarize_var
        ).pack(anchor="w", pady=(2, 0))

        # 3. 轉錄觸發按鈕與進度
        stt_action_row = ttk.Frame(right_panel, style="Card.TFrame")
        stt_action_row.pack(fill="x", pady=(6, 4))

        self.transcribe_btn = tk.Button(
            stt_action_row,
            text="🚀 開始轉錄語音為文字 (自動產生摘要＋逐字稿)",
            font=("Segoe UI", 10, "bold"),
            bg="#2da44e",
            fg="#ffffff",
            activebackground="#2c974b",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=6,
            cursor="hand2",
            command=self._start_transcription
        )
        self.transcribe_btn.pack(side="left")

        self.stt_progress_bar = ttk.Progressbar(right_panel, orient="horizontal", mode="determinate")
        self.stt_progress_bar.pack(fill="x", pady=(4, 2))
        self.stt_status_lbl = ttk.Label(right_panel, text="就緒。選擇音訊檔後點擊開始轉錄。", style="Dim.TLabel")
        self.stt_status_lbl.pack(anchor="w")

        # 4. 雙分頁展示區 (會議摘要 ＋ 詳細逐字稿)
        self.stt_notebook = ttk.Notebook(right_panel)
        self.stt_notebook.pack(fill="both", expand=True, pady=(6, 6))

        # 分頁 1: 會議摘要
        summary_tab = ttk.Frame(self.stt_notebook, padding=2)
        self.stt_notebook.add(summary_tab, text="  📊 會議重點摘要 (Summary)  ")
        self.summary_text = scrolledtext.ScrolledText(summary_tab, font=("Segoe UI", 10), wrap="word")
        self.summary_text.pack(fill="both", expand=True)

        # 分頁 2: 詳細逐字稿
        transcript_tab = ttk.Frame(self.stt_notebook, padding=2)
        self.stt_notebook.add(transcript_tab, text="  📝 詳細會議逐字稿 (Transcript)  ")
        self.transcript_text = scrolledtext.ScrolledText(transcript_tab, font=("Segoe UI", 10), wrap="word")
        self.transcript_text.pack(fill="both", expand=True)

        # 底部快捷按鈕
        stt_tools_frame = ttk.Frame(right_panel, style="Card.TFrame")
        stt_tools_frame.pack(fill="x")
        ttk.Button(stt_tools_frame, text="📋 複製當前頁", command=self._copy_current_tab_text).pack(side="left", padx=(0, 4))
        ttk.Button(stt_tools_frame, text="💾 另存摘要檔", command=self._export_summary_txt).pack(side="left", padx=4)
        ttk.Button(stt_tools_frame, text="💾 另存逐字稿", command=self._export_transcript_txt).pack(side="left", padx=4)
        ttk.Button(stt_tools_frame, text="💾 匯出 SRT", command=self._export_srt).pack(side="left", padx=4)
        self.stt_open_dir_btn = ttk.Button(stt_tools_frame, text="📁 開啟檔案目錄", command=self._open_stt_folder)
        self.stt_open_dir_btn.pack(side="left", padx=4)
        ttk.Button(stt_tools_frame, text="🧹 清空內容", command=self._clear_stt_texts).pack(side="right")

    def _show_api_key_guide(self):
        """跳出圖文教學視窗，極度簡單地引導使用者免費取得 Google API Key"""
        guide_win = tk.Toplevel(self.root)
        guide_win.title("如何免費取得 Google Gemini API Key？")
        guide_win.geometry("640x520")
        guide_win.minsize(560, 460)
        guide_win.configure(bg="#ffffff")
        guide_win.grab_set()

        frame = ttk.Frame(guide_win, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="🔑 只要 3 步驟，完全免費取得 Google API Key！", font=("Segoe UI", 13, "bold"), foreground="#1f6feb").pack(anchor="w", pady=(0, 6))
        ttk.Label(frame, text="Google 每日提供充裕的免費額度，日常會議轉錄完全不需要付費。", font=("Segoe UI", 9), foreground="#555555").pack(anchor="w", pady=(0, 14))

        steps_box = tk.LabelFrame(frame, text=" 超直覺 3 步驟教學 ", font=("Segoe UI", 10, "bold"), padx=14, pady=12, bg="#ffffff")
        steps_box.pack(fill="both", expand=True, pady=(0, 14))

        step1 = "🔹 步驟 1：開啟官方網站並登入\n點擊下方藍色按鈕前往 Google AI Studio 網站，使用您平常的 Google (Gmail) 帳號登入。"
        ttk.Label(steps_box, text=step1, font=("Segoe UI", 9), justify="left", background="#ffffff", wraplength=560).pack(anchor="w", pady=4)

        step2 = "🔹 步驟 2：點選「Create API key」按鈕\n進入頁面後，點擊「Create API key」按鈕。\n（若第一次進入跳出服務條款，勾選同意即可；接著選擇「Create API key in new project」）。"
        ttk.Label(steps_box, text=step2, font=("Segoe UI", 9), justify="left", background="#ffffff", wraplength=560).pack(anchor="w", pady=4)

        step3 = "🔹 步驟 3：複製金鑰並貼回本軟體\n畫面會彈出一長串專屬金鑰（例如以 AIzaSy... 開頭），點擊旁邊的「Copy」按鈕，回到本軟體的輸入框貼上即可！"
        ttk.Label(steps_box, text=step3, font=("Segoe UI", 9), justify="left", background="#ffffff", wraplength=560).pack(anchor="w", pady=4)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(0, 8))

        def open_url():
            webbrowser.open("https://aistudio.google.com/app/apikey")

        open_web_btn = tk.Button(
            btn_frame,
            text="🌐 點我立即開啟 Google AI Studio 網站 (https://aistudio.google.com/app/apikey)",
            font=("Segoe UI", 10, "bold"),
            bg="#1f6feb",
            fg="#ffffff",
            activebackground="#1a56db",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            command=open_url
        )
        open_web_btn.pack(fill="x")

        close_btn = ttk.Button(frame, text="關閉教學", command=guide_win.destroy)
        close_btn.pack(side="right")

    def _on_toggle_save_key(self):
        """當使用者勾選或取消勾選「將 API Key 儲存在本機」時觸發"""
        is_save = self.save_key_var.get()
        self.cfg["save_key_local"] = is_save
        if is_save:
            curr_key = self.api_key_var.get().strip()
            if curr_key:
                self.cfg["gemini_api_key"] = curr_key
            else:
                # 若輸入框為空，但設定檔已有儲存過的 Key，自動載入
                saved_key = self.cfg.get("gemini_api_key", "")
                if saved_key:
                    self.api_key_var.set(saved_key)
        else:
            # 使用者取消勾選：清空本地設定檔中的 Key 以維護安全性
            self.cfg["gemini_api_key"] = ""
        transcriber.save_config(self.cfg)

    def _generate_default_filename(self, target_dir):
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Teams會議錄音_{now_str}.mp3"
        full_path = os.path.join(target_dir, filename)
        self.save_path_var.set(full_path)

    def _browse_save_path(self):
        curr_path = self.save_path_var.get()
        init_dir = os.path.dirname(curr_path) if curr_path else os.getcwd()
        init_file = os.path.basename(curr_path) if curr_path else "Teams會議錄音.mp3"
        file_selected = filedialog.asksaveasfilename(
            title="選擇 MP3 儲存位置",
            initialdir=init_dir,
            initialfile=init_file,
            defaultextension=".mp3",
            filetypes=[("MP3 音訊檔案", "*.mp3"), ("所有檔案", "*.*")]
        )
        if file_selected:
            self.save_path_var.set(file_selected)

    def _browse_stt_file(self):
        f = filedialog.askopenfilename(
            title="選擇要轉錄的音訊檔案",
            filetypes=[
                ("音訊檔案 (*.mp3;*.wav;*.m4a;*.aac;*.flac)", "*.mp3;*.wav;*.m4a;*.aac;*.flac"),
                ("所有檔案 (*.*)", "*.*")
            ]
        )
        if f:
            self.stt_file_var.set(f)

    def _refresh_device_list(self):
        self.spk_devices, self.mic_devices = self.engine.get_devices()

        # 1. 揚聲器設備選單 (首項為 None / 不錄音)
        spk_names = ["🚫 [不錄揚聲器 / 關閉] (None)"]
        for dev in self.spk_devices:
            spk_names.append(f"{dev['name']} ({dev['channels']} 聲道, {dev['rate']} Hz)")
        
        self.spk_combobox["values"] = spk_names
        # 預設選取第一個有效揚聲器 (index 1)，若無設備則選 None (index 0)
        if len(self.spk_devices) > 0:
            self.spk_combobox.current(1)
        else:
            self.spk_combobox.current(0)

        # 2. 麥克風設備選單 (首項為 None / 不錄音)
        mic_names = ["🚫 [不錄麥克風 / 關閉] (None)"]
        for dev in self.mic_devices:
            mic_names.append(f"{dev['name']} ({dev['channels']} 聲道, {dev['rate']} Hz)")

        self.mic_combobox["values"] = mic_names
        # 預設選取第一個有效麥克風 (index 1)，若無設備則選 None (index 0)
        if len(self.mic_devices) > 0:
            self.mic_combobox.current(1)
        else:
            self.mic_combobox.current(0)

    def _toggle_recording(self):
        if self.is_processing or self.is_transcribing:
            return

        if not self.is_recording:
            spk_idx = self.spk_combobox.current()
            # index 0 為 None，大於 0 時對應 self.spk_devices[spk_idx - 1]
            selected_spk = self.spk_devices[spk_idx - 1] if (spk_idx > 0 and (spk_idx - 1) < len(self.spk_devices)) else None

            mic_idx = self.mic_combobox.current()
            selected_mic = self.mic_devices[mic_idx - 1] if (mic_idx > 0 and (mic_idx - 1) < len(self.mic_devices)) else None

            if not selected_spk and not selected_mic:
                messagebox.showwarning(
                    "無法開始錄音",
                    "揚聲器與麥克風都被設定為 [不錄此裝置 / 關閉] (None)！\n\n請至少選擇一個要錄音的裝置。"
                )
                return

            out_path = self.save_path_var.get().strip()
            if not out_path:
                messagebox.showwarning("提示", "請指定有效的 MP3 儲存路徑！")
                return

            success, msg = self.engine.start_recording(selected_spk, selected_mic)
            if not success:
                messagebox.showerror("錄音啟動失敗", msg)
                return

            self.is_recording = True
            self.start_record_timestamp = time.time()
            self.record_btn.configure(text="⏹️ 停止錄音並儲存 MP3", bg="#24292f", activebackground="#444d56")
            self.rec_status_lbl.configure(text="🔴 錄音進行中... 會議結束後請點擊「停止錄音並儲存 MP3」", foreground="#d73a49")
            self.refresh_btn.configure(state="disabled")
            self.spk_combobox.configure(state="disabled")
            self.mic_combobox.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.open_folder_btn.configure(state="disabled")
            self.rec_progress_bar["value"] = 0

            self._update_timer()
        else:
            self.is_recording = False
            self.is_processing = True
            self.record_btn.configure(text="⏳ 混音與轉檔中...", state="disabled", bg="#6a737d")
            self.rec_status_lbl.configure(text="正在停止錄音串流並處理音訊...", foreground="#0366d6")

            threading.Thread(target=self._process_export_thread, daemon=True).start()

    def _update_timer(self):
        if self.is_recording:
            elapsed = int(time.time() - self.start_record_timestamp)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            self.timer_lbl.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(500, self._update_timer)

    def _process_export_thread(self):
        try:
            self.engine.stop_recording()

            out_path = self.save_path_var.get().strip()
            spk_gain = self.spk_gain_var.get()
            mic_gain = self.mic_gain_var.get()

            def progress_cb(pct, text):
                def update_ui():
                    self.rec_progress_bar["value"] = int(pct * 100)
                    self.rec_status_lbl.configure(text=f"[{int(pct * 100)}%] {text}", foreground="#0366d6")
                self.root.after(0, update_ui)

            final_file = self.engine.mix_and_export_mp3(
                out_path,
                spk_gain=spk_gain,
                mic_gain=mic_gain,
                bitrate=192,
                progress_cb=progress_cb
            )

            self.last_saved_mp3 = final_file

            def on_success():
                self.rec_progress_bar["value"] = 100
                self.rec_status_lbl.configure(text=f"✅ 錄音混音完成！已儲存至：{os.path.basename(final_file)}", foreground="#28a745")
                self.open_folder_btn.configure(state="normal")
                self.record_btn.configure(text="🔴 開始錄音", state="normal", bg="#d73a49")
                self.refresh_btn.configure(state="normal")
                self.spk_combobox.configure(state="readonly")
                self.mic_combobox.configure(state="readonly")
                self.browse_btn.configure(state="normal")

                # 【貼心功能】自動填入右側語音轉文字檔案路徑！
                self.stt_file_var.set(final_file)

                # 生成下一次預設檔名
                default_dir = os.path.dirname(final_file)
                self._generate_default_filename(default_dir)
                messagebox.showinfo("完成", f"會議錄音已成功混音儲存！\n\n檔案路徑：\n{final_file}\n\n已自動為您帶入右側的語音轉文字區域，可直接點擊「開始轉錄」產生逐字稿。")

            self.root.after(0, on_success)

        except Exception as e:
            def on_error(err=str(e)):
                self.rec_status_lbl.configure(text=f"❌ 混音失敗：{err}", foreground="#cb2431")
                self.record_btn.configure(text="🔴 開始錄音", state="normal", bg="#d73a49")
                self.refresh_btn.configure(state="normal")
                self.spk_combobox.configure(state="readonly")
                self.mic_combobox.configure(state="readonly")
                self.browse_btn.configure(state="normal")
                messagebox.showerror("轉檔錯誤", f"處理音訊時發生錯誤：\n{err}")
            self.root.after(0, on_error)
        finally:
            self.is_processing = False

    def _open_output_folder(self):
        target = self.last_saved_mp3 or self.save_path_var.get()
        if os.path.exists(target):
            subprocess.Popen(f'explorer /select,"{os.path.abspath(target)}"')
        else:
            folder = os.path.dirname(os.path.abspath(target))
            if os.path.exists(folder):
                subprocess.Popen(f'explorer "{folder}"')

    # ==========================================================
    # 5. 語音轉文字邏輯處理 (純雲端 Gemini AI 轉錄)
    # ==========================================================
    def _start_transcription(self):
        if self.is_transcribing:
            return

        audio_file = self.stt_file_var.get().strip()
        if not audio_file or not os.path.exists(audio_file):
            messagebox.showwarning("提示", "請先選擇有效的音訊檔案！")
            return

        api_key = self.api_key_var.get().strip()
        if not api_key:
            if messagebox.askyesno(
                "缺少 API Key",
                "使用 AI 語音轉文字需要填寫 Google Gemini API Key。\n\n是否立即查看「超簡易免費取得教學」？"
            ):
                self._show_api_key_guide()
            return

        if self.save_key_var.get():
            self.cfg["save_key_local"] = True
            self.cfg["gemini_api_key"] = api_key
        else:
            self.cfg["save_key_local"] = False
            self.cfg["gemini_api_key"] = ""
        transcriber.save_config(self.cfg)

        self.is_transcribing = True
        self.transcribe_btn.configure(text="⏳ 雲端 AI 轉錄進行中...", state="disabled", bg="#6a737d")
        self.stt_progress_bar["value"] = 5
        self.stt_status_lbl.configure(text="正在啟動轉錄作業...", foreground="#0366d6")

        threading.Thread(target=self._run_transcription_worker, daemon=True).start()

    def _run_transcription_worker(self):
        audio_file = self.stt_file_var.get().strip()
        api_key = self.api_key_var.get().strip()
        summarize = self.summarize_var.get()

        def progress_cb(pct, text):
            def update():
                self.stt_progress_bar["value"] = int(pct * 100)
                self.stt_status_lbl.configure(text=f"[{int(pct * 100)}%] {text}", foreground="#0366d6")
            self.root.after(0, update)

        try:
            result = transcriber.transcribe_cloud_gemini(
                audio_file,
                api_key=api_key,
                summarize=summarize,
                progress_cb=progress_cb
            )

            def on_success(res_dict=result):
                self.stt_progress_bar["value"] = 100
                self.stt_status_lbl.configure(text="✅ 轉錄完成！已自動產出摘要與逐字稿二個檔案。", foreground="#28a745")
                self.transcribe_btn.configure(text="🚀 開始轉錄語音為文字 (自動產生摘要＋逐字稿)", state="normal", bg="#2da44e")
                self.last_stt_result = res_dict

                # 填入文字框
                self.summary_text.delete("1.0", "end")
                if res_dict.get("summary"):
                    self.summary_text.insert("end", res_dict["summary"])
                    self.stt_notebook.select(0)
                else:
                    self.summary_text.insert("end", "（此轉錄模式未生成摘要，或未勾選自動摘要）")
                    self.stt_notebook.select(1)

                self.transcript_text.delete("1.0", "end")
                self.transcript_text.insert("end", res_dict.get("transcript", ""))

                msg_lines = ["轉錄已順利完成！", "", "已自動為您在錄音檔同目錄下建立二個檔案："]
                if res_dict.get("summary_file"):
                    msg_lines.append(f"📊 會議摘要：{os.path.basename(res_dict['summary_file'])}")
                if res_dict.get("transcript_file"):
                    msg_lines.append(f"📝 詳細逐字稿：{os.path.basename(res_dict['transcript_file'])}")
                msg_lines.append("")
                msg_lines.append("您可直接在右側分頁預覽，或點擊「開啟檔案目錄」查看這二個檔案。")

                messagebox.showinfo("轉錄成功", "\n".join(msg_lines))

            self.root.after(0, on_success)

        except Exception as e:
            def on_error(err=str(e)):
                self.stt_status_lbl.configure(text=f"❌ 轉錄失敗：{err}", foreground="#cb2431")
                self.transcribe_btn.configure(text="🚀 開始轉錄語音為文字 (自動產生摘要＋逐字稿)", state="normal", bg="#2da44e")
                messagebox.showerror("轉錄失敗", f"執行語音轉文字時發生錯誤：\n\n{err}")
            self.root.after(0, on_error)
        finally:
            self.is_transcribing = False

    def _copy_current_tab_text(self):
        curr_tab = self.stt_notebook.index(self.stt_notebook.select())
        txt = self.summary_text.get("1.0", "end").strip() if curr_tab == 0 else self.transcript_text.get("1.0", "end").strip()
        if not txt:
            messagebox.showinfo("提示", "目前分頁沒有文字內容可供複製！")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(txt)
        tab_name = "會議摘要" if curr_tab == 0 else "逐字稿"
        messagebox.showinfo("已複製", f"【{tab_name}】內容已成功複製至剪貼簿！")

    def _export_summary_txt(self):
        txt = self.summary_text.get("1.0", "end").strip()
        if not txt or "未生成摘要" in txt:
            messagebox.showinfo("提示", "目前沒有會議摘要可供匯出！")
            return
        init_file = "會議重點摘要_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
        path = filedialog.asksaveasfilename(
            title="儲存會議摘要檔案",
            initialfile=init_file,
            defaultextension=".txt",
            filetypes=[("文字檔案 (*.txt)", "*.txt"), ("所有檔案", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
            messagebox.showinfo("匯出成功", f"會議摘要已儲存至：\n{path}")

    def _export_transcript_txt(self):
        txt = self.transcript_text.get("1.0", "end").strip()
        if not txt:
            messagebox.showinfo("提示", "目前沒有逐字稿可供匯出！")
            return
        init_file = "會議逐字稿_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
        path = filedialog.asksaveasfilename(
            title="儲存會議逐字稿檔案",
            initialfile=init_file,
            defaultextension=".txt",
            filetypes=[("文字檔案 (*.txt)", "*.txt"), ("所有檔案", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
            messagebox.showinfo("匯出成功", f"會議逐字稿已儲存至：\n{path}")

    def _export_srt(self):
        txt = self.transcript_text.get("1.0", "end").strip()
        if not txt:
            messagebox.showinfo("提示", "目前沒有逐字稿可供匯出為 SRT 字幕！")
            return
        init_file = "會議字幕_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".srt"
        path = filedialog.asksaveasfilename(
            title="儲存為 SRT 字幕檔",
            initialfile=init_file,
            defaultextension=".srt",
            filetypes=[("SRT 字幕檔案 (*.srt)", "*.srt"), ("所有檔案", "*.*")]
        )
        if path:
            lines = txt.splitlines()
            srt_entries = []
            idx = 1
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and "]" in line:
                    parts = line.split("]", 1)
                    ts_str = parts[0].strip("[")
                    content = parts[1].strip()
                    ts_parts = ts_str.split(":")
                    if len(ts_parts) == 2:
                        h = 0
                        m = int(ts_parts[0])
                        s = int(ts_parts[1])
                    elif len(ts_parts) == 3:
                        h = int(ts_parts[0])
                        m = int(ts_parts[1])
                        s = int(ts_parts[2])
                    else:
                        continue
                    start_sec = h * 3600 + m * 60 + s
                    end_sec = start_sec + 3
                    
                    def to_srt_time(sec):
                        h = sec // 3600
                        m = (sec % 3600) // 60
                        s = sec % 60
                        return f"{h:02d}:{m:02d}:{s:02d},000"

                    srt_entries.append(f"{idx}\n{to_srt_time(start_sec)} --> {to_srt_time(end_sec)}\n{content}\n")
                    idx += 1

            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_entries))
            messagebox.showinfo("匯出成功", f"SRT 字幕檔案已儲存至：\n{path}")

    def _open_stt_folder(self):
        target_file = None
        if hasattr(self, "last_stt_result") and self.last_stt_result:
            target_file = self.last_stt_result.get("transcript_file") or self.last_stt_result.get("summary_file")
        if not target_file:
            target_file = self.stt_file_var.get().strip()

        if target_file and os.path.exists(target_file):
            subprocess.Popen(f'explorer /select,"{os.path.abspath(target_file)}"')
        else:
            folder = os.path.dirname(os.path.abspath(target_file)) if target_file else os.getcwd()
            subprocess.Popen(f'explorer "{folder}"')

    def _clear_stt_texts(self):
        self.summary_text.delete("1.0", "end")
        self.transcript_text.delete("1.0", "end")

    def _schedule_meter_update(self):
        spk_val = self.engine.spk_level if self.is_recording else 0.0
        mic_val = self.engine.mic_level if self.is_recording else 0.0

        self._draw_meter(self.spk_meter, spk_val)
        self._draw_meter(self.mic_meter, mic_val)

        self.root.after(50, self._schedule_meter_update)

    def _draw_meter(self, canvas, val):
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1:
            w = 110
        if h <= 1:
            h = 10

        fill_w = int(w * max(0.0, min(1.0, val)))
        if fill_w > 0:
            color = "#28a745"
            if val > 0.75:
                color = "#dc3545"
            elif val > 0.5:
                color = "#ffc107"
            canvas.create_rectangle(0, 0, fill_w, h, fill=color, outline="")

    def on_closing(self):
        if self.is_recording:
            if not messagebox.askyesno("正在錄音中", "錄音進行中，確定要離開嗎？"):
                return
        self.engine.cleanup()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = TeamsRecorderApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
