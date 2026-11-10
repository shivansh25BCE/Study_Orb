import sys
import random
import math
import os
import sqlite3
import calendar
from datetime import datetime, timedelta
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, QTime, QPoint, QVariantAnimation, QRectF, QUrl, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QIcon, QGuiApplication, QPolygon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QSoundEffect

class LofiOrb(QWidget):
    def __init__(self):
        super().__init__()
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.size = 350
        self.mini_size = 140
        self.current_window_size = self.size
        self.setFixedSize(self.current_window_size, self.current_window_size)
        self.window_opacity = 1.0
        
        self.seasons = ["MONSOON", "AUTUMN", "WINTER", "SPRING", "SUMMER"]
        self.current_season_idx = 0
        
        self.sound_files = {
            "MONSOON": "sounds/monsoon.mp3", "AUTUMN": "sounds/autumn.mp3",
            "WINTER": "sounds/winter.mp3", "SPRING": "sounds/spring.mp3", "SUMMER": "sounds/summer.mp3"
        }
        
        # Timer & Tracking Variables
        self.total_pomo_time = 25 * 60
        self.pomo_time_left = self.total_pomo_time
        self.is_pomo_running = False
        self.is_focus_mode = True
        self.is_mini_mode = False
        self.drag_pos = QPoint()
        
        # View State
        self.current_view = "TIMER"
        self.slide_offset = 0.0
        
        # Dual-Level Garden Data
        self.garden_date = self.get_current_logical_date()
        self.garden_tab = "D"
        self.active_dates = []
        self.active_minutes = []
        self.in_basement = False
        self.basement_offset = 0.0
        
        self.init_db()
        
        # Animations
        self.focus_anim = QVariantAnimation(self)
        self.focus_anim.setDuration(500)
        self.focus_anim.valueChanged.connect(self.animate_focus)

        self.window_anim = QVariantAnimation(self)
        self.window_anim.setDuration(400)
        self.window_anim.valueChanged.connect(self.animate_window_size)
        
        self.slide_anim = QVariantAnimation(self)
        self.slide_anim.setDuration(400)
        self.slide_anim.valueChanged.connect(self.animate_slide)

        self.basement_anim = QVariantAnimation(self)
        self.basement_anim.setDuration(400)
        self.basement_anim.valueChanged.connect(self.animate_basement)

        # Audio Engine
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.current_volume = 0.4
        self.audio_output.setVolume(self.current_volume)
        self.is_audio_muted = False
        self.player.mediaStatusChanged.connect(self.check_audio_loop)

        self.particles = []
        self.reset_particles()
        
        self.init_ui()
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        
        self.particle_timer = QTimer(self)
        self.particle_timer.timeout.connect(self.update_particles)
        self.particle_timer.start(30) 
        
        self.play_season_audio()
        
        # Initialize the BoomBot
        self.bot = BoomBot(self)
        self.bot.current_season = self.seasons[self.current_season_idx] # <--- ADD THIS LINE
        self.bot.show()
        self.pinned_snips = []
        self.snip_overlay = None

    # --- DATABASE LOGIC ---
    def get_current_logical_date(self):
        now = datetime.now()
        if now.hour < 4: now -= timedelta(days=1)
        return now.date()

    def init_db(self):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.db_path = os.path.join(base_dir, "zen_garden.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute("CREATE TABLE IF NOT EXISTS daily_focus (date TEXT PRIMARY KEY, minutes INTEGER)")
        self.conn.commit()

    def add_focus_minutes(self, minutes):
        if minutes <= 0: return
        date_str = self.get_current_logical_date().strftime("%Y-%m-%d")
        self.cursor.execute("SELECT minutes FROM daily_focus WHERE date = ?", (date_str,))
        row = self.cursor.fetchone()
        if row: 
            self.cursor.execute("UPDATE daily_focus SET minutes = minutes + ? WHERE date = ?", (minutes, date_str))
        else: 
            self.cursor.execute("INSERT INTO daily_focus (date, minutes) VALUES (?, ?)", (date_str, minutes))
        self.conn.commit()
        
    def get_minutes_for_date(self, target_date):
        date_str = target_date.strftime("%Y-%m-%d")
        self.cursor.execute("SELECT minutes FROM daily_focus WHERE date = ?", (date_str,))
        row = self.cursor.fetchone()
        return row[0] if row else 0

    # --- UI SETUP ---
    def init_ui(self):
        self.analytics_container = QWidget(self)
        self.analytics_container.setFixedSize(self.size, self.size)
        self.analytics_container.move(-self.size, 0)
        
        self.timer_container = QWidget(self)
        self.timer_container.setFixedSize(self.size, self.size)
        self.timer_container.move(0, 0)
        
        self.garden_container = QWidget(self)
        self.garden_container.setFixedSize(self.size, self.size)
        self.garden_container.move(self.size, 0)
        
        self.basement_container = QWidget(self)
        self.basement_container.setFixedSize(self.size, self.size)
        self.basement_container.move(self.size, self.size)
        
        self.setup_analytics_ui()
        self.setup_timer_ui()
        self.setup_garden_ui()
        
        self.nav_left = self.create_main_nav_btn("<", 10, self.on_nav_left_clicked)
        self.nav_right = self.create_main_nav_btn(">", self.size - 30, self.on_nav_right_clicked)

    def create_main_nav_btn(self, text, x_pos, callback):
        btn = QPushButton(text, self)
        btn.setGeometry(x_pos, self.size // 2 - 15, 20, 30)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("background: transparent; color: #a9b1d6; font-size: 16px; font-weight: bold; border: none;")
        btn.clicked.connect(callback)
        return btn

    def on_nav_left_clicked(self):
        if self.current_view == "TIMER": self.switch_view("ANALYTICS")
        elif self.current_view == "GARDEN": self.switch_view("TIMER")

    def on_nav_right_clicked(self):
        if self.current_view == "TIMER": self.switch_view("GARDEN")
        elif self.current_view == "ANALYTICS": self.switch_view("TIMER")

    def setup_analytics_ui(self):
        layout = QVBoxLayout(self.analytics_container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("BAMBOO FOREST")
        title.setStyleSheet("color: #a9b1d6; font-size: 13px; font-weight: bold; letter-spacing: 3px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        stats_lbl = QLabel("PAST 7 DAYS")
        stats_lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        stats_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(stats_lbl)
        
        layout.addStretch()

    def setup_timer_ui(self):
        layout = QVBoxLayout(self.timer_container)
        layout.setContentsMargins(50, 40, 50, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QLabel("MIDNIGHT ORB")
        self.title_lbl.setStyleSheet("color: #a9b1d6; font-size: 11px; font-weight: bold; letter-spacing: 2px;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_lbl)
        layout.addSpacing(10)

        self.clock_lbl = QLabel("00:00")
        self.clock_lbl.setStyleSheet("color: #ffb347; font-size: 50px; font-weight: bold; font-family: 'Consolas';")
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.clock_lbl)
        layout.addSpacing(10)

        self.pomo_status = QLabel("FOCUS")
        self.pomo_status.setStyleSheet("color: #ff6b6b; font-size: 13px; font-weight: bold; letter-spacing: 4px;")
        self.pomo_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.pomo_status)
        
        self.pomo_lbl = QLabel("25:00")
        self.pomo_lbl.setStyleSheet("color: #ff6b6b; font-size: 32px; font-weight: bold; font-family: 'Consolas';")
        self.pomo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.pomo_lbl)

        self.mini_season_btn = QPushButton(f"✦ {self.seasons[self.current_season_idx][:3]} ✦")
        self.mini_season_btn.setStyleSheet("background: transparent; color: #a9b1d6; border: none; font-size: 10px; font-weight: bold; letter-spacing: 2px;")
        self.mini_season_btn.clicked.connect(self.cycle_season)
        self.mini_season_btn.hide()
        layout.addWidget(self.mini_season_btn)

        self.time_adjust_widget = QWidget()
        ta_layout = QHBoxLayout(self.time_adjust_widget)
        ta_layout.setContentsMargins(0, 0, 0, 0)
        ta_layout.addWidget(self.create_button("- 5m", lambda: self.adjust_time(-5)))
        ta_layout.addWidget(self.create_button("+ 5m", lambda: self.adjust_time(5)))
        layout.addWidget(self.time_adjust_widget)
        layout.addSpacing(5)

        self.pomo_btn_widget = QWidget()
        pb_layout = QHBoxLayout(self.pomo_btn_widget)
        pb_layout.setContentsMargins(0, 0, 0, 0)
        self.start_btn = self.create_button("START", self.toggle_pomo)
        self.reset_btn = self.create_button("SAVE && QUIT", self.reset_pomo)
        pb_layout.addWidget(self.start_btn)
        pb_layout.addWidget(self.reset_btn)
        layout.addWidget(self.pomo_btn_widget)
        layout.addSpacing(5)

        self.util_widget = QWidget()
        u_layout = QHBoxLayout(self.util_widget)
        u_layout.setContentsMargins(0, 0, 0, 0)
        self.season_btn = self.create_button(f"S: {self.seasons[self.current_season_idx]}", self.cycle_season)
        self.audio_btn = self.create_button("🎵 ON", self.toggle_audio)
        self.snip_btn = self.create_button("📌 SNIP", self.start_snip)
        self.close_btn = self.create_button("CLOSE", self.close)
        u_layout.addWidget(self.season_btn)
        u_layout.addWidget(self.audio_btn)
        u_layout.addWidget(self.snip_btn)
        u_layout.addWidget(self.close_btn)
        layout.addWidget(self.util_widget)

    def setup_garden_ui(self):
        layout = QVBoxLayout(self.garden_container)
        layout.setContentsMargins(20, 25, 20, 25)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        tabs_widget = QWidget()
        tabs_layout = QHBoxLayout(tabs_widget)
        tabs_layout.setContentsMargins(0,0,0,0)
        tabs_layout.setSpacing(10)
        
        self.tab_btns = {}
        for tab in ["D", "W", "M", "Y"]:
            btn = QPushButton(tab)
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, t=tab: self.set_garden_tab(t))
            self.tab_btns[tab] = btn
            tabs_layout.addWidget(btn)
        layout.addWidget(tabs_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(5)

        picker_widget = QWidget()
        picker_layout = QHBoxLayout(picker_widget)
        picker_layout.setContentsMargins(0,0,0,0)
        prev_btn = self.create_picker_arrow("◄", lambda: self.shift_garden_date(-1))
        self.date_lbl = QLabel("")
        self.date_lbl.setStyleSheet("color: #ffb347; font-size: 13px; font-weight: bold; font-family: 'Consolas';")
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        next_btn = self.create_picker_arrow("►", lambda: self.shift_garden_date(1))
        picker_layout.addWidget(prev_btn)
        picker_layout.addWidget(self.date_lbl)
        picker_layout.addWidget(next_btn)
        layout.addWidget(picker_widget)
        
        layout.addStretch()
        
        self.garden_stats_lbl = QLabel("")
        self.garden_stats_lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        self.garden_stats_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.garden_stats_lbl)
        
        self.overflow_btn = QPushButton("▼ EXPLORE ROOTS ▼")
        self.overflow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overflow_btn.setStyleSheet("background: transparent; color: #ffb347; font-size: 11px; font-weight: bold; letter-spacing: 2px; border: none;")
        self.overflow_btn.clicked.connect(lambda: self.toggle_basement())
        layout.addWidget(self.overflow_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        b_layout = QVBoxLayout(self.basement_container)
        b_layout.setContentsMargins(20, 30, 20, 30)
        
        self.return_btn = QPushButton("▲ BACK TO SHELVES ▲")
        self.return_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.return_btn.setStyleSheet("background: transparent; color: #a9b1d6; font-size: 11px; font-weight: bold; letter-spacing: 2px; border: none;")
        self.return_btn.clicked.connect(lambda: self.toggle_basement())
        b_layout.addWidget(self.return_btn, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        b_layout.addStretch()
        
        self.basement_stats_lbl = QLabel("")
        self.basement_stats_lbl.setStyleSheet("color: #ffb347; font-size: 13px; font-weight: bold; font-family: 'Consolas'; letter-spacing: 1px;")
        self.basement_stats_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_layout.addWidget(self.basement_stats_lbl)
        
        self.update_garden_data()

    def create_picker_arrow(self, text, callback):
        btn = QPushButton(text)
        btn.setFixedSize(20, 20)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("background: transparent; color: #a9b1d6; font-size: 14px; font-weight: bold; border: none;")
        btn.clicked.connect(callback)
        return btn

    def create_button(self, text, callback):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { background-color: rgba(42, 42, 53, 200); color: #a9b1d6; border: 2px solid #444; border-radius: 12px; padding: 6px 0px; font-family: 'Consolas'; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: rgba(63, 63, 78, 255); border: 2px solid #ffb347; color: #ffb347; }
        """)
        btn.clicked.connect(callback)
        return btn

    # --- GARDEN NAVIGATION & DATA ---
    def set_garden_tab(self, tab_id):
        self.garden_tab = tab_id
        self.update_garden_data()

    def shift_garden_date(self, delta):
        if self.garden_tab == "D":
            new_date = self.garden_date + timedelta(days=delta)
            if new_date.month != self.garden_date.month:
                _, last_day = calendar.monthrange(self.garden_date.year, self.garden_date.month)
                self.garden_date = self.garden_date.replace(day=1 if delta > 0 else last_day)
            else:
                self.garden_date = new_date
        elif self.garden_tab == "W":
            new_date = self.garden_date + timedelta(days=delta * 7)
            if new_date.month != self.garden_date.month:
                _, last_day = calendar.monthrange(self.garden_date.year, self.garden_date.month)
                self.garden_date = self.garden_date.replace(day=1 if delta > 0 else last_day)
            else:
                self.garden_date = new_date
        elif self.garden_tab == "M":
            m = self.garden_date.month - 1 + delta
            y = self.garden_date.year + m // 12
            self.garden_date = self.garden_date.replace(year=y, month=m % 12 + 1, day=1)
        elif self.garden_tab == "Y":
            self.garden_date = self.garden_date.replace(year=self.garden_date.year + delta)
        self.update_garden_data()

    def update_garden_data(self):
        d = self.garden_date
        if self.garden_tab == "D":
            self.active_dates = [d]
            self.date_lbl.setText(d.strftime("%b %d, %Y").upper())
        elif self.garden_tab == "W":
            start = d - timedelta(days=d.weekday())
            end = start + timedelta(days=6)
            self.active_dates = [start + timedelta(days=i) for i in range(7)]
            if start.month == end.month:
                self.date_lbl.setText(f"{start.strftime('%b %d')}-{end.strftime('%d')}, {start.year}".upper())
            else:
                self.date_lbl.setText(f"{start.strftime('%b %d')}-{end.strftime('%b %d')}, {start.year}".upper())
        elif self.garden_tab == "M":
            _, days = calendar.monthrange(d.year, d.month)
            self.active_dates = [d.replace(day=i+1) for i in range(days)]
            self.date_lbl.setText(d.strftime("%B %Y").upper())
        elif self.garden_tab == "Y":
            start = d.replace(month=1, day=1)
            days = 366 if calendar.isleap(d.year) else 365
            self.active_dates = [start + timedelta(days=i) for i in range(days)]
            self.date_lbl.setText(f"{d.year}")
            
        self.active_minutes = [self.get_minutes_for_date(date) for date in self.active_dates]
        
        for tab_name, btn in self.tab_btns.items():
            if tab_name == self.garden_tab:
                btn.setStyleSheet("background-color: #ffb347; color: #1d110d; font-weight: bold; border-radius: 4px;")
            else:
                btn.setStyleSheet("background-color: rgba(255, 255, 255, 30); color: #a9b1d6; font-weight: bold; border-radius: 4px;")
                
        total_pots = max(1, math.ceil(self.active_minutes[0] / 100)) if self.garden_tab == "D" and self.active_minutes[0] > 0 else len(self.active_dates)
        if total_pots > 12:
            self.overflow_btn.show()
        else:
            self.overflow_btn.hide()
            if self.in_basement:
                self.in_basement = False
                self.basement_anim.stop()
                self.basement_offset = 0.0
                
        t_mins = sum(self.active_minutes)
        t_lotuses = sum(m // 100 for m in self.active_minutes)
        self.garden_stats_lbl.setText(f"FOCUS: {t_mins} MINS")
        self.basement_stats_lbl.setText(f"{t_mins} TOTAL MINUTES\n{t_lotuses} GOLDEN LOTUSES")
        self.update()

    # --- ANIMATIONS (Slide & Basement) ---
    def switch_view(self, target_view):
        if self.current_view == target_view or self.is_mini_mode: return
        
        if self.current_view == "GARDEN" and target_view == "TIMER" and self.in_basement:
            self.toggle_basement()
            
        self.current_view = target_view
        self.slide_anim.stop()
        
        target_val = {"ANALYTICS": -1.0, "TIMER": 0.0, "GARDEN": 1.0}[target_view]
        current_val = self.slide_offset / self.size
        
        self.slide_anim.setStartValue(current_val)
        self.slide_anim.setEndValue(target_val)
        
        if target_view == "TIMER":
            self.nav_left.show()
            self.nav_right.show()
        elif target_view == "GARDEN":
            self.nav_left.show()
            self.nav_right.hide()
            self.update_garden_data()
        elif target_view == "ANALYTICS":
            self.nav_left.hide()
            self.nav_right.show()
            
        self.slide_anim.start()

    def animate_slide(self, val):
        self.slide_offset = float(val) * self.size
        self.timer_container.move(int(-self.slide_offset), 0)
        self.garden_container.move(int(self.size - self.slide_offset), int(-self.basement_offset))
        self.basement_container.move(int(self.size - self.slide_offset), int(self.size - self.basement_offset))
        self.analytics_container.move(int(-self.size - self.slide_offset), 0)
        self.update()

    def toggle_basement(self):
        self.in_basement = not self.in_basement
        self.basement_anim.stop()
        self.basement_anim.setStartValue(self.basement_offset)
        self.basement_anim.setEndValue(float(self.size) if self.in_basement else 0.0)
        self.basement_anim.start()

    def animate_basement(self, val):
        self.basement_offset = float(val)
        self.garden_container.move(int(self.size - self.slide_offset), int(-self.basement_offset))
        self.basement_container.move(int(self.size - self.slide_offset), int(self.size - self.basement_offset))
        self.update()

    # --- CORE TIMER LOGIC ---
    def adjust_time(self, minutes):
        new_time = self.total_pomo_time + (minutes * 60)
        if new_time >= 60: 
            self.total_pomo_time = new_time
            self.pomo_time_left = self.total_pomo_time
            self.update_pomo_label()

    def update_pomo_label(self):
        m = self.pomo_time_left // 60
        s = self.pomo_time_left % 60
        self.pomo_lbl.setText(f"{m:02d}:{s:02d}")

    def update_clock(self):
        self.clock_lbl.setText(QTime.currentTime().toString("HH:mm"))
        if self.is_pomo_running:
            if self.pomo_time_left > 0:
                self.pomo_time_left -= 1
                self.update_pomo_label()
                
                # 5-minute warning trigger
                if self.is_focus_mode and self.pomo_time_left == 5 * 60:
                    self.bot.speak("5 mins left! òwó")
            else:
                try:
                    self.is_pomo_running = False
                    if self.is_focus_mode:
                        self.add_focus_minutes(int(self.total_pomo_time // 60))
                        self.update_garden_data() 
                        
                    if self.is_mini_mode: self.toggle_mini_mode()
                    self.is_focus_mode = not self.is_focus_mode
                    self.total_pomo_time = 25 * 60 if self.is_focus_mode else 5 * 60
                    self.pomo_time_left = self.total_pomo_time
                    
                    if not self.is_focus_mode:
                        self.pomo_status.setText("REST")
                        self.pomo_status.setStyleSheet("color: #10b981; font-size: 24px; font-weight: bold; letter-spacing: 4px;")
                        self.bot.is_focusing = False # Update bot eye to green
                    else:
                        self.bot.is_focusing = True
                    
                    self.start_btn.setText("START")
                    self.update_pomo_label()
                    self.trigger_focus_animation()
                except Exception as e:
                    print(f"CRASH PREVENTED in update_clock: {e}")
                    
            self.update()
    
    def toggle_pomo(self, *args):
        self.is_pomo_running = not self.is_pomo_running
        self.start_btn.setText("PAUSE" if self.is_pomo_running else "START")
        
        if not self.is_pomo_running:
            self.bot.speak("Paused zZz...")
        elif self.is_focus_mode:
            self.bot.speak("Let's go! òwó")
            
        self.trigger_focus_animation()

    def reset_pomo(self, *args):
        try:
            if self.is_focus_mode:
                elapsed_seconds = self.total_pomo_time - self.pomo_time_left
                minutes_to_save = int(round(elapsed_seconds / 60.0)) 
                if minutes_to_save > 0:
                    self.add_focus_minutes(minutes_to_save)
                    self.update_garden_data() 
                    self.repaint() 
                    
            self.is_pomo_running = False
            self.is_focus_mode = True
            self.total_pomo_time = 25 * 60
            self.pomo_time_left = self.total_pomo_time
            self.start_btn.setText("START")
            self.pomo_status.setText("FOCUS")
            self.pomo_status.setStyleSheet("color: #ff6b6b; font-size: 24px; font-weight: bold; letter-spacing: 4px;")
            self.bot.is_focusing = True # Reset bot eye to red
            self.update_pomo_label()
            self.trigger_focus_animation()
            self.update()
        except Exception as e:
            print(f"CRASH PREVENTED in reset_pomo: {e}")

    # --- DRAWING THE GARDENS ---
    def draw_garden_shelves(self, painter):
        if self.garden_tab == "D":
            mins = self.active_minutes[0]
            num_pots = max(1, math.ceil(mins / 100)) if mins > 0 else 1
            if num_pots <= 4: shelf_ys = [220]
            elif num_pots <= 8: shelf_ys = [150, 240]
            else: shelf_ys = [120, 190, 260]
        elif self.garden_tab == "W":
            shelf_ys = [150, 240]
        else:
            shelf_ys = [120, 190, 260]
            
        for y in shelf_ys:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(139, 90, 43))) 
            painter.drawRect(40, y, 270, 8)
            painter.setBrush(QBrush(QColor(101, 67, 33))) 
            painter.drawRect(40, y + 8, 270, 4)

    def draw_garden_pots(self, painter):
        today = self.get_current_logical_date()
        spacing = 65
        if self.garden_tab == "D":
            mins = self.active_minutes[0]
            num_pots = max(1, math.ceil(mins / 100)) if mins > 0 else 1
            shelf_ys = [220] if num_pots <= 4 else [150, 240] if num_pots <= 8 else [120, 190, 260]
            for i in range(min(12, num_pots)):
                row, col = i // 4, i % 4
                pots_in_row = min(4, num_pots - row * 4)
                start_x = self.size // 2 - ((pots_in_row - 1) * spacing) / 2
                pot_mins = max(0, min(100, mins - (i * 100)))
                self.draw_potted_plant(painter, int(start_x + (col * spacing)), shelf_ys[row], min(4, pot_mins // 25), self.active_dates[0] == today)
        elif self.garden_tab == "W":
            shelf_ys = [150, 240]
            for i in range(7):
                row = 0 if i < 4 else 1
                col = i if row == 0 else i - 4
                pots_in_row = 4 if row == 0 else 3
                start_x = self.size // 2 - ((pots_in_row - 1) * spacing) / 2
                mins = self.active_minutes[i]
                self.draw_potted_plant(painter, int(start_x + (col * spacing)), shelf_ys[row], min(4, mins // 25) if mins > 0 else 0, self.active_dates[i] == today)
        else: 
            shelf_ys = [120, 190, 260]
            earned_days = [(d, m) for d, m in zip(self.active_dates, self.active_minutes) if m > 0]
            for i in range(min(12, len(earned_days))):
                row, col = i // 4, i % 4
                start_x = self.size // 2 - (1.5 * spacing)
                date_obj, mins = earned_days[i]
                self.draw_potted_plant(painter, int(start_x + (col * spacing)), shelf_ys[row], min(4, mins // 25), date_obj == today)

    def draw_potted_plant(self, painter, x, y, level, is_today):
        painter.save()
        painter.translate(x, y)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(204, 102, 51)))
        
        pot_path = QPainterPath()
        pot_path.moveTo(-11, -5)
        pot_path.lineTo(11, -5)
        pot_path.lineTo(7, 5)
        pot_path.lineTo(-7, 5)
        painter.drawPath(pot_path)
        
        painter.drawRect(-13, -9, 26, 4)
        painter.setBrush(QBrush(QColor(50, 30, 15)))
        painter.drawEllipse(-10, -10, 20, 4)

        if level > 0:
            pen = QPen(QColor(139, 195, 74, 230))
            pen.setWidth(2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            stem_height = int(min(25, 5 + (level * 5)))
            painter.drawLine(0, -10, 0, -10 - stem_height)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(168, 228, 160, 240)))
            if level >= 1: painter.drawEllipse(2, -18, 5, 3)
            if level >= 2: painter.drawEllipse(-7, -24, 5, 3)
            if level >= 3: painter.drawEllipse(2, -30, 5, 3)
            
            if level >= 4:
                flowers = ["🌸", "🌻", "🌺", "🌷", "🪷"]
                flower_idx = (abs(int(x)) * 37 + abs(int(y)) * 13) % len(flowers)
                flower = flowers[flower_idx]  
                font = painter.font()
                font.setPointSize(16) 
                painter.setFont(font)
                painter.setPen(QColor(255, 255, 255))
                rect = QRectF(-20, -10 - stem_height - 25, 40, 40)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, flower)

        if is_today:
            painter.setPen(QPen(QColor(255, 255, 255, 150), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(-16, -14, 32, 22)
        painter.restore()

    def draw_ancient_tree(self, painter, total_mins):
        center = self.size / 2
        bottom = self.size - 60 
        scale = min(1.0, total_mins / 3000.0) 
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(60, 40, 20)))
        trunk_w = 6 + (24 * scale)
        height = 40 + (120 * scale)
        
        path = QPainterPath()
        path.moveTo(center - trunk_w - 20*scale, bottom)
        path.quadTo(center - trunk_w, bottom - 10, center - trunk_w, bottom - height/2)
        path.lineTo(center + trunk_w, bottom - height/2)
        path.quadTo(center + trunk_w, bottom - 10, center + trunk_w + 20*scale, bottom)
        painter.drawPath(path)
        
        if total_mins > 0:
            canopy_sz = 40 + (140 * scale)
            if total_mins >= 100:
                painter.setBrush(QBrush(QColor(255, 179, 71, 30)))
                painter.drawEllipse(int(center - canopy_sz), int(bottom - height - canopy_sz), int(canopy_sz*2), int(canopy_sz*2))
            leaf_color = QColor(255, 179, 71, 220) if total_mins >= 100 else QColor(139, 195, 74, 220)
            painter.setBrush(QBrush(leaf_color))
            painter.drawEllipse(int(center - canopy_sz/2), int(bottom - height - canopy_sz/2), int(canopy_sz), int(canopy_sz))
            if total_mins >= 100:
                painter.setBrush(QBrush(QColor(255, 200, 100, 255)))
                painter.drawEllipse(int(center - canopy_sz/3), int(bottom - height - canopy_sz/3), int(canopy_sz*0.66), int(canopy_sz*0.66))

    # --- DRAWING THE BAMBOO CHART ---
    def draw_bamboo_chart(self, painter):
        today = self.get_current_logical_date()
        dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
        minutes = [self.get_minutes_for_date(d) for d in dates]
        
        max_mins = max(100, max(minutes)) if minutes else 100
        bottom_y = self.size - 70
        chart_h = 160
        spacing = 35
        start_x = self.size // 2 - (3 * spacing)
        
        for i, mins in enumerate(minutes):
            x = start_x + (i * spacing)
            day_str = dates[i].strftime("%a")[0]
            painter.setPen(QColor(169, 177, 214))
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(int(x - 10), int(bottom_y + 15), 20, 20, Qt.AlignmentFlag.AlignCenter, day_str)
            
            if mins == 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(50, 60, 50)))
                painter.drawRect(int(x - 5), int(bottom_y - 4), 10, 4)
                continue
                
            bar_h = int((mins / max_mins) * chart_h)
            if mins >= 100:
                base_color = QColor(218, 165, 32)
                highlight = QColor(255, 200, 100)
                shadow = QColor(160, 120, 20)
            else:
                base_color = QColor(76, 175, 80)
                highlight = QColor(129, 199, 132)
                shadow = QColor(56, 142, 60)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(shadow))
            painter.drawRect(int(x - 6), int(bottom_y - bar_h), 12, bar_h)
            painter.setBrush(QBrush(base_color))
            painter.drawRect(int(x - 4), int(bottom_y - bar_h), 8, bar_h)
            painter.setBrush(QBrush(highlight))
            painter.drawRect(int(x - 4), int(bottom_y - bar_h), 2, bar_h)
            
            painter.setPen(QPen(shadow, 2))
            num_segments = max(1, bar_h // 25)
            for s in range(1, num_segments + 1):
                seg_y = int(bottom_y - (s * 25))
                if seg_y > bottom_y - bar_h + 5:
                    painter.drawLine(int(x - 7), seg_y, int(x + 7), seg_y)
                    
            hours_str = f"{mins / 60.0:.1f}h"
            painter.setPen(QColor(255, 255, 255, 200))
            font.setPointSize(8)
            font.setBold(False)
            painter.setFont(font)
            painter.drawText(int(x - 20), int(bottom_y - bar_h - 22), 40, 15, Qt.AlignmentFlag.AlignCenter, hours_str)

    # --- CORE PAINT EVENT ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        season = self.seasons[self.current_season_idx]
        hour = QTime.currentTime().hour()
        if season == "MONSOON": base = QColor(15, 17, 26)
        elif season == "AUTUMN": base = QColor(26, 15, 12)
        elif season == "WINTER": base = QColor(12, 16, 24)
        elif season == "SPRING": base = QColor(24, 15, 20)
        elif season == "SUMMER": base = QColor(10, 20, 15)
        
        r, g, b = base.red(), base.green(), base.blue()
        if 6 <= hour < 16: r, g, b = int(r * 1.1), int(g * 1.1), b
        elif 16 <= hour < 19: r, g, b = int(r * 1.4), int(g * 1.1), int(b * 0.9)
        elif 19 <= hour <= 23 or 0 <= hour < 5: r, g, b = int(r * 0.7), int(g * 0.7), int(b * 1.3)
        else: r, g, b = int(r * 0.9), g, int(b * 1.2)

        painter.save()
        painter.translate(-int(self.slide_offset), 0)
        painter.setBrush(QBrush(QColor(min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)), 240)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.current_window_size, self.current_window_size)

        if self.is_pomo_running:
            ring_color = QColor("#ff6b6b") if self.is_focus_mode else QColor("#10b981")
            pen = QPen(ring_color)
            pen.setWidth(4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            margin = 6
            rect = QRectF(margin, margin, self.current_window_size - margin*2, self.current_window_size - margin*2)
            progress = self.pomo_time_left / self.total_pomo_time
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * progress))

        painter.save()
        scale = self.current_window_size / self.size
        painter.scale(scale, scale)
        clip_path = QPainterPath()
        clip_path.addEllipse(0.0, 0.0, float(self.size), float(self.size))
        painter.setClipPath(clip_path)

        for p in self.particles:
            painter.setBrush(QBrush(p['color']))
            if p['type'] == 'line':
                pen = QPen(p['color'])
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(int(p['x']), int(p['y']), int(p['x'] + p['sx']*2), int(p['y'] + p['len']))
            elif p['type'] == 'ellipse' or p['type'] == 'glow':
                painter.setPen(Qt.PenStyle.NoPen)
                sway = math.sin(p['angle']) * 15 if p.get('sway_speed') else 0
                if p['type'] == 'glow':
                    glow = QColor(p['color'])
                    glow.setAlpha(40)
                    painter.setBrush(QBrush(glow))
                    painter.drawEllipse(int(p['x'] + sway - 2), int(p['y'] - 2), p['w'] + 4, p['h'] + 4)
                    painter.setBrush(QBrush(p['color']))
                painter.drawEllipse(int(p['x'] + sway), int(p['y']), p['w'], p['h'])
                
        painter.restore()
        painter.restore()

        if self.slide_offset > 0:
            painter.save()
            painter.translate(int(self.size - self.slide_offset), int(-self.basement_offset))
            painter.setBrush(QBrush(QColor(62, 39, 35))) 
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, self.size, self.size)
            self.draw_garden_shelves(painter)
            self.draw_garden_pots(painter)
            painter.restore()

            if self.basement_offset > 0:
                painter.save()
                painter.translate(int(self.size - self.slide_offset), int(self.size - self.basement_offset))
                painter.setBrush(QBrush(QColor(29, 17, 13)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(0, 0, self.size, self.size)
                t_mins = sum(self.active_minutes)
                self.draw_ancient_tree(painter, t_mins)
                painter.restore()

        if self.slide_offset < 0:
            painter.save()
            painter.translate(int(-self.size - self.slide_offset), 0)
            painter.setBrush(QBrush(QColor(15, 25, 20))) 
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, self.size, self.size)
            self.draw_bamboo_chart(painter)
            painter.restore()

    # --- OTHER UI & EVENT HANDLERS ---
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            self.window_opacity = min(1.0, max(0.2, self.window_opacity + (0.05 if delta > 0 else -0.05)))
            self.setWindowOpacity(self.window_opacity)
            self.show_status_feedback(f"OPACITY {int(self.window_opacity * 100)}%")
        else:
            self.current_volume = min(1.0, max(0.0, self.current_volume + (0.05 if delta > 0 else -0.05)))
            self.audio_output.setVolume(self.current_volume)
            self.show_status_feedback(f"VOL {int(self.current_volume * 100)}%")
            if self.current_volume > 0 and self.is_audio_muted: self.toggle_audio()

    def show_status_feedback(self, text):
        if self.current_view != "TIMER": return 
        self.pomo_status.setText(text)
        self.pomo_status.setStyleSheet("color: #ffb347; font-size: 13px; font-weight: bold; letter-spacing: 2px;")
        QTimer.singleShot(1200, self.restore_status)

    def restore_status(self):
        status_text = "FOCUS" if self.is_focus_mode else "REST"
        color = "#ff6b6b" if self.is_focus_mode else "#10b981"
        font_sz = 24 if self.focus_anim.currentValue() == 1.0 else 13
        if self.is_mini_mode: font_sz = 10
        self.pomo_status.setText(status_text)
        self.pomo_status.setStyleSheet(f"color: {color}; font-size: {font_sz}px; font-weight: bold; letter-spacing: 4px;")

    def trigger_focus_animation(self):
        self.focus_anim.stop()
        # Hide clutter whenever the timer is actively running (Focus OR Rest)
        if self.is_pomo_running:
            self.focus_anim.setStartValue(0.0)
            self.focus_anim.setEndValue(1.0)
            self.time_adjust_widget.hide()
            self.util_widget.hide()
            self.nav_right.hide()
            self.nav_left.hide()
            
            # Sync the bot's state with the current mode
            self.bot.is_focusing = self.is_focus_mode
            self.bot.show()
        else:
            self.focus_anim.setStartValue(1.0)
            self.focus_anim.setEndValue(0.0)
            
            # Only restore full UI buttons if we are NOT in mini mode
            if not self.is_mini_mode:
                self.time_adjust_widget.show()
                self.util_widget.show()
                if self.current_view == "TIMER": 
                    self.nav_right.show()
                    self.nav_left.show()
        self.focus_anim.start()

    def animate_focus(self, val):
        val = float(val)
        color = "#ff6b6b" if self.is_focus_mode else "#10b981"
        self.pomo_lbl.setStyleSheet(f"color: {color}; font-size: {int(32 + (48 * val))}px; font-weight: bold; font-family: 'Consolas';")
        self.pomo_status.setStyleSheet(f"color: {color}; font-size: {int(13 + (11 * val))}px; font-weight: bold; letter-spacing: 4px;")
        
        clock_sz = int(50 - (38 * val)) 
        if clock_sz <= 15:
            self.clock_lbl.hide()
            self.title_lbl.hide()
        else:
            self.clock_lbl.show()
            self.title_lbl.show()
            self.clock_lbl.setStyleSheet(f"color: rgba(255, 179, 71, {int(255 * (1-val))}); font-size: {clock_sz}px; font-weight: bold; font-family: 'Consolas';")
            self.title_lbl.setStyleSheet(f"color: rgba(169, 177, 214, {int(255 * (1-val))}); font-size: {max(1, int(11 - (10 * val)))}px; font-weight: bold; letter-spacing: 2px;")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_pomo_running and self.current_view == "TIMER": 
            self.toggle_mini_mode()

    def toggle_mini_mode(self):
        self.is_mini_mode = not self.is_mini_mode
        self.window_anim.stop()
        self.window_anim.setStartValue(self.current_window_size)
        
        if self.is_mini_mode:
            self.window_anim.setEndValue(self.mini_size)
            self.pomo_btn_widget.hide()
            self.time_adjust_widget.hide()
            self.util_widget.hide()
            self.nav_right.hide()
            self.nav_left.hide()
            self.mini_season_btn.setText(f"✦ {self.seasons[self.current_season_idx][:3]} ✦")
            self.mini_season_btn.show()
        else:
            self.window_anim.setEndValue(self.size)
            self.pomo_btn_widget.show()
            self.mini_season_btn.hide()
            if not self.is_pomo_running:
                self.time_adjust_widget.show()
                self.util_widget.show()
                if self.current_view == "TIMER":
                    self.nav_right.show()
                    self.nav_left.show()
        self.window_anim.start()

    def animate_window_size(self, val):
        val = float(val)
        delta = self.current_window_size - int(val)
        self.move(self.x() + delta // 2, self.y() + delta // 2)
        
        self.current_window_size = int(val)
        self.setFixedSize(self.current_window_size, self.current_window_size)
        
        self.timer_container.setFixedSize(self.current_window_size, self.current_window_size)
        self.garden_container.setFixedSize(self.current_window_size, self.current_window_size)
        self.basement_container.setFixedSize(self.current_window_size, self.current_window_size)
        self.analytics_container.setFixedSize(self.current_window_size, self.current_window_size)
        
        progress = (val - self.mini_size) / (self.size - self.mini_size) 
        m = int(10 + (30 * progress)) 
        self.timer_container.layout().setContentsMargins(m, m, m, m)
        self.timer_container.layout().setSpacing(int(10 * progress))
        
        color = "#ff6b6b" if self.is_focus_mode else "#10b981"
        self.pomo_lbl.setStyleSheet(f"color: {color}; font-size: {int(24 + (56 * progress))}px; font-weight: bold; font-family: 'Consolas';")
        self.pomo_status.setStyleSheet(f"color: {color}; font-size: {int(10 + (14 * progress))}px; font-weight: bold; letter-spacing: 2px;")
        self.update()

    def reset_particles(self):
        self.particles.clear()
        for _ in range(80): self.spawn_particle(init_random_y=True)

    def spawn_particle(self, init_random_y=False):
        season = self.seasons[self.current_season_idx]
        p = { 'x': random.randint(0, self.size), 'y': random.randint(0, self.size) if init_random_y else -20, 'angle': random.uniform(0, math.pi * 2) }

        if season == "MONSOON": p.update({'type': 'line', 'color': QColor(174, 194, 224, 150), 'sy': random.uniform(12.0, 20.0), 'sx': random.uniform(-2.0, -1.0), 'len': random.randint(10, 25)})
        elif season == "AUTUMN": p.update({'type': 'ellipse', 'color': QColor(*random.choice([(212, 91, 18), (235, 140, 52), (194, 69, 14)]), random.randint(180, 255)), 'sy': random.uniform(1.5, 3.0), 'sx': random.uniform(-1.0, 1.0), 'w': random.randint(6, 10), 'h': random.randint(4, 7), 'sway_speed': random.uniform(0.02, 0.05)})
        elif season == "WINTER": p.update({'type': 'ellipse', 'color': QColor(255, 255, 255, random.randint(150, 255)), 'sy': random.uniform(0.5, 2.0), 'sx': random.uniform(-0.5, 0.5), 'w': random.randint(3, 7), 'h': random.randint(3, 7), 'sway_speed': random.uniform(0.01, 0.03)})
        elif season == "SPRING": p.update({'type': 'ellipse', 'color': QColor(255, 183, 197, random.randint(180, 255)), 'sy': random.uniform(1.0, 2.5), 'sx': random.uniform(1.5, 3.0), 'w': random.randint(5, 8), 'h': random.randint(3, 5), 'sway_speed': random.uniform(0.03, 0.06)})
        elif season == "SUMMER": p.update({'type': 'glow', 'color': QColor(204, 255, 51, random.randint(100, 220)), 'y': random.randint(0, self.size) if init_random_y else self.size + 20, 'sy': random.uniform(-0.3, -1.2), 'sx': random.uniform(-0.5, 0.5), 'w': random.randint(2, 5), 'h': random.randint(2, 5), 'sway_speed': random.uniform(0.02, 0.04)})
        self.particles.append(p)

    def update_particles(self):
        season = self.seasons[self.current_season_idx]
        for i in range(len(self.particles) - 1, -1, -1):
            p = self.particles[i]
            p['x'] += p['sx']
            p['y'] += p['sy']
            if 'angle' in p: p['angle'] += p.get('sway_speed', 0)
            
            if (season == "SUMMER" and p['y'] < -20) or (season != "SUMMER" and p['y'] > self.size + 20) or p['x'] < -50 or p['x'] > self.size + 50:
                self.particles.pop(i)
                self.spawn_particle()
        self.update() 

    def cycle_season(self):
        self.current_season_idx = (self.current_season_idx + 1) % len(self.seasons)
        self.season_btn.setText(f"S: {self.seasons[self.current_season_idx]}")
        self.mini_season_btn.setText(f"✦ {self.seasons[self.current_season_idx][:3]} ✦")
        
        # Syncs the bot's particles
        self.bot.current_season = self.seasons[self.current_season_idx] 
        
        self.reset_particles()
        
        # These two lines were missing!
        self.play_season_audio() 
        self.update()

    def play_season_audio(self):
        if self.is_audio_muted: return
        season = self.seasons[self.current_season_idx]
        base_dir = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, self.sound_files.get(season, ""))
        if os.path.exists(file_path):
            self.player.setSource(QUrl.fromLocalFile(file_path))
            self.player.play()
        else: self.player.stop()

    def toggle_audio(self):
        self.is_audio_muted = not self.is_audio_muted
        if self.is_audio_muted:
            self.player.pause()
            self.audio_btn.setText("🎵 OFF")
            self.audio_btn.setStyleSheet(self.audio_btn.styleSheet().replace("color: #a9b1d6;", "color: #666;"))
        else:
            self.play_season_audio()
            self.audio_btn.setText("🎵 ON")
            self.audio_btn.setStyleSheet(self.audio_btn.styleSheet().replace("color: #666;", "color: #a9b1d6;"))

    def check_audio_loop(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def start_snip(self):
        self.snip_overlay = SnipOverlay(self)        

    def closeEvent(self, event):
        for pin in self.pinned_snips[:]:
            pin.close()
        self.player.stop()
        self.clock_timer.stop()
        self.particle_timer.stop()
        self.bot.hide()
        self.conn.close()
        QApplication.quit()
        event.accept()


from PyQt6.QtCore import QRect, QSize

class PinnedSnip(QWidget):
    def __init__(self, pixmap, pos, dpr=1.0, parent_orb=None):
        super().__init__()
        self.parent_orb = parent_orb
        self.original_pixmap = pixmap
        self.dpr = dpr
        self.scale_factor = 1.0
        self.opacity_val = 1.0
        self.drag_pos = QPoint()
        self.border_pad = 4

        # Base logical size so it matches the exact screen size you selected
        self.base_w = int(self.original_pixmap.width() / self.dpr)
        self.base_h = int(self.original_pixmap.height() / self.dpr)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.update_dimensions()
        self.move(pos.x() - self.border_pad, pos.y() - self.border_pad)
        self.show()

    def update_dimensions(self):
        logical_w = max(40, int(self.base_w * self.scale_factor))
        logical_h = max(25, int(self.base_h * self.scale_factor))
        
        # Scale using physical pixels so high-DPI text stays razor sharp
        target_px_w = int(logical_w * self.dpr)
        target_px_h = int(logical_h * self.dpr)
        
        self.scaled_pixmap = self.original_pixmap.scaled(
            QSize(target_px_w, target_px_h),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.scaled_pixmap.setDevicePixelRatio(self.dpr)
        
        actual_logical_w = int(self.scaled_pixmap.width() / self.dpr)
        actual_logical_h = int(self.scaled_pixmap.height() / self.dpr)

        self.setFixedSize(
            actual_logical_w + self.border_pad * 2,
            actual_logical_h + self.border_pad * 2
        )
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(QColor(20, 20, 25, 230)))
        painter.setPen(QPen(QColor(136, 163, 140), 2))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 6, 6)

        painter.drawPixmap(self.border_pad, self.border_pad, self.scaled_pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()
        elif event.button() == Qt.MouseButton.RightButton:
            if self.parent_orb and self in self.parent_orb.pinned_snips:
                self.parent_orb.pinned_snips.remove(self)
            self.close()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            self.opacity_val = min(1.0, max(0.2, self.opacity_val + (0.08 if delta > 0 else -0.08)))
            self.setWindowOpacity(self.opacity_val)
        else:
            self.scale_factor = min(3.0, max(0.5, self.scale_factor + (0.1 if delta > 0 else -0.1)))
            self.update_dimensions()


class SnipOverlay(QWidget):
    def __init__(self, parent_orb):
        super().__init__()
        self.parent_orb = parent_orb
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.is_selecting = False

        screen = QGuiApplication.primaryScreen()
        self.full_pixmap = screen.grabWindow(0)
        self.dpr = self.full_pixmap.devicePixelRatio()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.full_pixmap)

        # Dim the entire screen
        painter.fillRect(self.rect(), QColor(10, 10, 15, 140))

        if self.is_selecting:
            sel_rect = QRect(self.start_pos, self.end_pos).normalized()
            if sel_rect.width() > 2 and sel_rect.height() > 2:
                # Scale source rectangle by Windows DPI ratio so it fills the entire box
                src_rect = QRect(
                    int(sel_rect.x() * self.dpr),
                    int(sel_rect.y() * self.dpr),
                    int(sel_rect.width() * self.dpr),
                    int(sel_rect.height() * self.dpr)
                )
                painter.drawPixmap(sel_rect, self.full_pixmap, src_rect)
                painter.setPen(QPen(QColor("#ffb347"), 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(sel_rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.position().toPoint()
            self.end_pos = self.start_pos
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.close()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            sel_rect = QRect(self.start_pos, self.end_pos).normalized()
            self.close()

            if sel_rect.width() > 15 and sel_rect.height() > 15:
                src_rect = QRect(
                    int(sel_rect.x() * self.dpr),
                    int(sel_rect.y() * self.dpr),
                    int(sel_rect.width() * self.dpr),
                    int(sel_rect.height() * self.dpr)
                )
                cropped = self.full_pixmap.copy(src_rect)
                pin = PinnedSnip(cropped, sel_rect.topLeft(), self.dpr, self.parent_orb)
                self.parent_orb.pinned_snips.append(pin)
                self.parent_orb.bot.speak("Pinned! òwó")
                self.parent_orb.bot.sfx_pet.play()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

class SpeechBubble(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(120, 50)
        
        self.text = ""
        self.hide_timer = QTimer(self)
        self.hide_timer.timeout.connect(self.hide)
        
    def show_message(self, text, x, y):
        self.text = text
        self.move(x, y)
        self.show()
        self.hide_timer.start(3000) 
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw the bubble box
        painter.setPen(QPen(QColor(136, 163, 140), 2)) 
        painter.setBrush(QBrush(QColor(20, 20, 25, 240)))
        painter.drawRoundedRect(2, 2, 116, 35, 8, 8)
        
        # Draw the little tail pointing down to the bot
        path = QPainterPath()
        path.moveTo(50, 37)
        path.lineTo(60, 47)
        path.lineTo(70, 37)
        painter.setBrush(QBrush(QColor(20, 20, 25, 240)))
        painter.drawPath(path)
        
        # Draw the text
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(2, 2, 116, 35, Qt.AlignmentFlag.AlignCenter, self.text)

class BoomBot(QWidget):
    def __init__(self, parent_orb=None):
        super().__init__()
        self.parent_orb = parent_orb
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(120, 140) 
        
        screen_geom = QGuiApplication.primaryScreen().availableGeometry()
        self.screen_w = screen_geom.width()
        self.ground_y = screen_geom.height() - self.height()
        
        self.x_pos = self.screen_w - self.width() - 20 
        self.move(self.x_pos, self.ground_y)
        
        self.is_focusing = True
        self.is_petted = False 
        self.is_dragging = False 
        
        self.blink_counter = 0
        self.tick_counter = 0 
        self.pause_ticks = 0
        self.glitch_x = 0
        self.glitch_y = 0
        self.bob_y = 0
        self.flicker_alpha = 255

        # Gravity & Walking Physics
        self.vy = 0.0
        self.gravity = 1.2
        self.bounce_damping = -0.45
        self.is_airborne = False
        self.squish_frames = 0
        
        self.walk_dir = 0      # -1 = left, 0 = paused/sipping tea, 1 = right
        self.walk_timer = 0    # Ticks remaining in current walk/pause state
        self.walk_speed = 1.5
        
        self.current_season = "MONSOON"
        self.energy_particles = []
        
        # Right-click cycle when pristine
        self.idle_props = ["KATANA", "TEA", "GRASS", "NONE"]
        self.current_prop_idx = 0
        
        self.bubble = SpeechBubble()
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.sfx_pet = QSoundEffect()
        self.sfx_pet.setSource(QUrl.fromLocalFile(os.path.join(base_dir, "sounds", "petting.wav")))
        self.sfx_pet.setVolume(0.4)
        
        self.sfx_panic = QSoundEffect()
        self.sfx_panic.setSource(QUrl.fromLocalFile(os.path.join(base_dir, "sounds", "panic.wav")))
        self.sfx_panic.setVolume(0.4)
        
        self.roam_timer = QTimer(self)
        self.roam_timer.timeout.connect(self.update_physics)
        self.roam_timer.start(30)

    def speak(self, text):
        bx = self.x() + (self.width() // 2) - (self.bubble.width() // 2)
        by = self.y() - self.bubble.height() + 5
        self.bubble.show_message(text, bx, by)

    def update_physics(self):
        import random
        import math
        
        self.tick_counter += 1
        self.bob_y = int(math.sin(self.tick_counter * 0.15) * 2)
        
        if self.squish_frames > 0:
            self.squish_frames -= 1
            
        self.blink_counter += 1
        if self.blink_counter > 100:
            self.blink_counter = 0
            
        if random.random() < 0.15:
            self.glitch_x = random.randint(-4, 4)
            self.glitch_y = random.randint(-3, 3)
            self.flicker_alpha = random.randint(50, 150)
        else:
            self.glitch_x = 0
            self.glitch_y = 0
            self.flicker_alpha = 255

        # --- 1. GRAVITY & BOUNCE PHYSICS ---
        if not self.is_dragging:
            curr_x = self.x()
            curr_y = self.y()
            
            # Keep within horizontal screen bounds
            curr_x = max(10, min(self.screen_w - self.width() - 10, curr_x))
            
            if curr_y < self.ground_y or abs(self.vy) > 0.1:
                self.is_airborne = True
                self.vy += self.gravity
                new_y = int(curr_y + self.vy)
                
                # Floor Collision
                if new_y >= self.ground_y:
                    new_y = self.ground_y
                    if self.vy > 10.0:
                        self.squish_frames = 6
                        self.speak("Oof! >_<")
                    
                    if abs(self.vy) > 3.5:
                        self.vy *= self.bounce_damping
                    else:
                        self.vy = 0.0
                        self.is_airborne = False
                        
                self.move(curr_x, new_y)
            else:
                self.is_airborne = False
                self.vy = 0.0

        # --- 2. REST MODE AUTONOMOUS STROLLING ---
        is_running = self.parent_orb.is_pomo_running if self.parent_orb else False
        is_pristine = (self.parent_orb.pomo_time_left == self.parent_orb.total_pomo_time) if self.parent_orb else True

        if not self.is_focusing and not self.is_dragging and not self.is_airborne and not self.is_petted:
            self.walk_timer -= 1
            if self.walk_timer <= 0:
                # 50% chance to pause and sip tea, 50% chance to stroll left or right
                self.walk_dir = random.choice([-1, 0, 0, 1])
                self.walk_timer = random.randint(50, 140)
                if self.walk_dir == 0 and random.random() < 0.35:
                    self.speak("*sips tea* U_U")
                    
            if self.walk_dir != 0:
                next_x = int(self.x() + (self.walk_dir * self.walk_speed))
                # Turn around at screen edges
                if next_x <= 20:
                    next_x = 20
                    self.walk_dir = 1
                elif next_x >= self.screen_w - self.width() - 20:
                    next_x = self.screen_w - self.width() - 20
                    self.walk_dir = -1
                    
                self.move(next_x, self.y())
                if self.bubble.isVisible():
                    bx = self.x() + (self.width() // 2) - (self.bubble.width() // 2)
                    by = self.y() - self.bubble.height() + 5
                    self.bubble.move(bx, by)
        else:
            self.walk_dir = 0

        # --- 3. PAUSE TRACKER & SEASONAL PARTICLES ---
        if not is_running and not is_pristine:
            self.pause_ticks += 1
        else:
            self.pause_ticks = 0

        if self.is_focusing and is_running:
            if random.random() < 0.25:
                p = {
                    'x': random.randint(5, 115),
                    'angle': random.uniform(0, math.pi * 2),
                    'is_foreground': random.choice([True, False])
                }
                
                if self.current_season == "MONSOON": 
                    p.update({'y': -10, 'type': 'line', 'color': QColor(174, 194, 224, 150), 'sy': random.uniform(10.0, 18.0), 'sx': random.uniform(-2.0, -1.0), 'len': random.randint(10, 25)})
                elif self.current_season == "AUTUMN": 
                    p.update({'y': -10, 'type': 'ellipse', 'color': QColor(*random.choice([(212, 91, 18), (235, 140, 52), (194, 69, 14)]), random.randint(180, 255)), 'sy': random.uniform(1.5, 3.0), 'sx': random.uniform(-1.0, 1.0), 'size': random.randint(4, 7), 'sway': random.uniform(0.02, 0.05)})
                elif self.current_season == "WINTER": 
                    p.update({'y': -10, 'type': 'ellipse', 'color': QColor(255, 255, 255, random.randint(150, 255)), 'sy': random.uniform(0.5, 2.0), 'sx': random.uniform(-0.5, 0.5), 'size': random.randint(3, 6), 'sway': random.uniform(0.01, 0.03)})
                elif self.current_season == "SPRING": 
                    p.update({'y': -10, 'type': 'ellipse', 'color': QColor(255, 183, 197, random.randint(180, 255)), 'sy': random.uniform(1.0, 2.5), 'sx': random.uniform(1.5, 3.0), 'size': random.randint(4, 7), 'sway': random.uniform(0.03, 0.06)})
                elif self.current_season == "SUMMER": 
                    p.update({'y': self.height() + 10, 'type': 'glow', 'color': QColor(204, 255, 51, random.randint(100, 220)), 'sy': random.uniform(-0.5, -1.5), 'sx': random.uniform(-0.5, 0.5), 'size': random.randint(2, 4), 'sway': random.uniform(0.02, 0.04)})

                self.energy_particles.append(p)
                
        for p in self.energy_particles[:]:
            p['x'] += p['sx']
            p['y'] += p['sy']
            if 'angle' in p: p['angle'] += p.get('sway', 0)
            
            if p['y'] > self.height() + 20 or p['y'] < -20 or p['x'] < -30 or p['x'] > self.width() + 30:
                self.energy_particles.remove(p)
            
        self.update()
    def enterEvent(self, event):
        if not self.is_dragging:
            self.is_petted = True
            self.speak("Hello! >w<")
            self.sfx_pet.play()
            self.update()

    def leaveEvent(self, event):
        self.is_petted = False
        self.update()

    def mousePressEvent(self, event):
        # Shift + Left-Click OR Middle-Click on BoomBot triggers Screen Snip
        if (event.button() == Qt.MouseButton.MiddleButton or 
           (event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.ShiftModifier)):
            if self.parent_orb:
                self.parent_orb.start_snip()
            return

        if event.button() == Qt.MouseButton.LeftButton: 
            self.drag_pos = event.globalPosition().toPoint()
            self.is_dragging = True
            self.vy = 0.0
            self.is_airborne = False
            self.speak("Put me down!!")
            self.sfx_panic.play()
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            is_running = self.parent_orb.is_pomo_running if self.parent_orb else False
            is_pristine = (self.parent_orb.pomo_time_left == self.parent_orb.total_pomo_time) if self.parent_orb else True
            
            if not is_running and is_pristine:
                self.current_prop_idx = (self.current_prop_idx + 1) % len(self.idle_props)
                self.speak("*Equipped*")
                self.sfx_pet.play()
                self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()
            
            if self.bubble.isVisible():
                bx = self.x() + (self.width() // 2) - (self.bubble.width() // 2)
                by = self.y() - self.bubble.height() + 5
                self.bubble.move(bx, by)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            if self.y() < self.ground_y - 10:
                self.is_airborne = True
                self.speak("Waaaaah!!")
            else:
                self.speak("Phew... UwU")
            self.update()

    def draw_bot_particle(self, painter, p):
        import math
        painter.setBrush(QBrush(p['color']))
        if p['type'] == 'line':
            pen = QPen(p['color'])
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(int(p['x']), int(p['y']), int(p['x'] + p['sx']*2), int(p['y'] + p['len']))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            sway = math.sin(p.get('angle', 0)) * 10 if p.get('sway') else 0
            if p['type'] == 'glow':
                glow = QColor(p['color'])
                glow.setAlpha(40)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(int(p['x'] + sway - 2), int(p['y'] - 2), p['size'] + 4, p['size'] + 4)
                painter.setBrush(QBrush(p['color']))
            painter.drawEllipse(int(p['x'] + sway), int(p['y']), p['size'], p['size'])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_running = self.parent_orb.is_pomo_running if self.parent_orb else False
        is_pristine = (self.parent_orb.pomo_time_left == self.parent_orb.total_pomo_time) if self.parent_orb else True
        
        # --- LAYER 1: BACKGROUND AURA & PARTICLES ---
        if self.is_focusing and is_running:
            if self.current_season == "MONSOON": aura_glow = QColor(174, 194, 224, 40)
            elif self.current_season == "AUTUMN": aura_glow = QColor(235, 140, 52, 40)
            elif self.current_season == "WINTER": aura_glow = QColor(255, 255, 255, 40)
            elif self.current_season == "SPRING": aura_glow = QColor(255, 183, 197, 40)
            elif self.current_season == "SUMMER": aura_glow = QColor(204, 255, 51, 40)
            else: aura_glow = QColor(255, 107, 107, 40)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(aura_glow))
            painter.drawEllipse(10, 30, 100, 100)
            
        for p in self.energy_particles:
            if not p['is_foreground']:
                self.draw_bot_particle(painter, p)
        
        # --- LAYER 2: THE BOT ---
        painter.save()
        painter.translate(15, 40)
        
        # Apply landing squish transform anchored to the bottom of the feet (y=72)
        if self.squish_frames > 0:
            painter.translate(45, 72)
            painter.scale(1.18, 0.82)
            painter.translate(-45, -72)
        
        # Alternating foot steps when strolling in Rest mode
        import math
        if self.walk_dir != 0 and not self.is_airborne:
            left_step = int(max(0, math.sin(self.tick_counter * 0.4) * 5))
            right_step = int(max(0, math.sin(self.tick_counter * 0.4 + math.pi) * 5))
        else:
            left_step, right_step = 0, 0
            
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 30, 35)))
        painter.drawRoundedRect(15, 54 - left_step, 18, 18, 4, 4)
        painter.drawRoundedRect(57, 54 - right_step, 18, 18, 4, 4)
        
        painter.setBrush(QBrush(QColor(136, 163, 140)))
        painter.drawRoundedRect(9, 12, 72, 48, 12, 12)
        
        # Dynamic Expression and Color Logic
        if self.is_dragging or self.is_airborne:
            expr, base_color, screen_bg = "O_O", QColor(255, 255, 255), QColor(200, 80, 0)
        elif self.squish_frames > 0:
            expr, base_color, screen_bg = ">_<", QColor(255, 183, 197), QColor(10, 10, 15)
        elif self.is_petted:
            expr, base_color, screen_bg = ">w<", QColor(255, 183, 197), QColor(10, 10, 15)
        elif not is_running and not is_pristine and self.pause_ticks > 2000:
            expr, base_color, screen_bg = "zZz", QColor(113, 175, 71), QColor(10, 10, 15)
        elif not self.is_focusing:
            expr = "-w-" if self.blink_counter > 95 else "U_U"
            base_color, screen_bg = QColor(16, 185, 129), QColor(10, 10, 15)
        else:
            expr = "-w-" if self.blink_counter > 95 else "òwó"
            base_color, screen_bg = QColor(255, 107, 107), QColor(10, 10, 15)

        base_color.setAlpha(self.flicker_alpha)
        painter.setBrush(QBrush(screen_bg))
        painter.drawRoundedRect(16, 18, 57, 36, 7, 7)

        font = painter.font()
        font.setFamily("Consolas")
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        
        painter.save()
        painter.translate(0, self.bob_y)
        if self.glitch_x != 0:
            painter.setPen(QColor(255, 255, 255, 80))
            painter.drawText(16 + self.glitch_x, 18 + self.glitch_y, 57, 36, Qt.AlignmentFlag.AlignCenter, expr)
        painter.setPen(base_color)
        painter.drawText(16, 18, 57, 36, Qt.AlignmentFlag.AlignCenter, expr)
        painter.restore()
        
        # --- PROPS ---
        painter.save()
        painter.translate(0, self.bob_y) 
        
        if is_running and self.is_focusing:
            active_prop = "KATANA"
        elif not self.is_focusing:
            active_prop = "TEA"
        elif not is_running and not is_pristine and self.pause_ticks > 2000:
            active_prop = "GRASS"
        elif not is_running and is_pristine:
            active_prop = self.idle_props[self.current_prop_idx]
        else:
            active_prop = "KATANA"
            
        painter.setPen(Qt.PenStyle.NoPen)
        px, py = 45, 12
        
        if active_prop == "KATANA":
            from PyQt6.QtCore import QPoint
            from PyQt6.QtGui import QPolygon
            k_px, k_py = 35, 12
            painter.setBrush(QBrush(QColor(200, 200, 205)))
            painter.drawRect(k_px - 10, k_py - 5, 75, 4)
            painter.setBrush(QBrush(QColor(40, 40, 45)))
            painter.drawRect(k_px - 40, k_py - 5, 30, 4)
            painter.setBrush(QBrush(QColor(130, 130, 135)))
            for hx in range(k_px - 36, k_px - 12, 6):
                diamond = QPolygon([
                    QPoint(hx, k_py - 5), QPoint(hx + 2, k_py - 3), QPoint(hx, k_py - 1), QPoint(hx - 2, k_py - 3)
                ])
                painter.drawPolygon(diamond)
            painter.setBrush(QBrush(QColor(218, 165, 32)))
            painter.drawRect(k_px - 12, k_py - 9, 3, 12)
            painter.drawRect(k_px - 42, k_py - 5, 2, 4)
            
        elif active_prop == "TEA":
            cup_x, cup_y = px - 10, py - 10
            import math
            steam_y = (self.tick_counter % 60) * 0.3
            steam_alpha = max(0, 200 - int((steam_y / 18.0) * 200))
            painter.setPen(QPen(QColor(255, 255, 255, steam_alpha), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            steam_offset = math.sin(self.tick_counter * 0.1) * 3
            painter.drawArc(int(cup_x + 6 + steam_offset), int(cup_y - 5 - steam_y), 8, 10, 90 * 16, 180 * 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(240, 235, 225)))
            painter.drawRoundedRect(cup_x, cup_y, 20, 14, 3, 3)
            painter.setBrush(QBrush(QColor(40, 20, 10)))
            painter.drawEllipse(cup_x + 2, cup_y - 2, 16, 4)
            
        elif active_prop == "GRASS":
            painter.setBrush(QBrush(QColor(101, 67, 33)))
            painter.drawRect(px - 10, py - 18, 20, 18)
            painter.setBrush(QBrush(QColor(113, 175, 71))) 
            painter.drawRect(px - 10, py - 18, 20, 6)
            painter.drawRect(px - 10, py - 12, 4, 3) 
            painter.drawRect(px + 4, py - 12, 5, 4)
            
        painter.restore() 
        painter.restore() 

        # --- LAYER 3: FOREGROUND PARTICLES ---
        for p in self.energy_particles:
            if p['is_foreground']:
                self.draw_bot_particle(painter, p)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    if os.path.exists("icon.ico"): app.setWindowIcon(QIcon("icon.ico"))
    widget = LofiOrb()
    widget.show()
    sys.exit(app.exec())