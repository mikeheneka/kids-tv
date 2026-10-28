#!/usr/bin/env python3
"""
Kids TV - Simple HDHomeRun TV Player for Raspberry Pi
Designed to be simple, colorful, and easy to use for children.
"""

import sys
import os
import json
import socket
import time
import subprocess
import urllib.request
import urllib.error
from threading import Thread

# Force XCB (Xwayland) so mpv can embed cleanly into Qt widgets on Wayfire/Wayland
os.environ["QT_QPA_PLATFORM"] = "xcb"

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame, QSlider, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent
from PyQt5.QtGui import QFont, QIcon, QCursor
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.expanduser("~/.config/kids-tv")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
CACHE_FILE = os.path.join(CONFIG_DIR, "channels.json")
FAVORITES_FILE = os.path.join(CONFIG_DIR, "favorites.json")
ICON_PATH = os.path.join(APP_DIR, "icon.png")
SOCKET_PATH = f"/tmp/kids_tv_mpv_{os.getpid()}.sock"
SINGLE_INSTANCE_SERVER_NAME = f"kids_tv_single_instance_{os.getuid()}"

DEFAULT_HDHOMERUN_HOST = "hdhomerun.local"

# Channels confirmed to have active broadcast signal from the antenna
KNOWN_ACTIVE_CHANNELS = [
    "9.1", "3.2", "9.2", "9.3", "9.4",
    "56.1", "56.2", "56.3", "56.4", "56.5",
    "56.6", "56.7", "56.8", "56.9"
]


class LineupFetcher(QObject):
    lineup_ready = pyqtSignal(list, str)
    status_update = pyqtSignal(str)

    def __init__(self, fallback_ip=DEFAULT_HDHOMERUN_HOST):
        super().__init__()
        self.fallback_ip = fallback_ip

    def run(self):
        hd_ip = self.discover_ip()
        lineup = self.fetch_lineup(hd_ip)
        if not lineup and hd_ip != self.fallback_ip:
            lineup = self.fetch_lineup(self.fallback_ip)
            if lineup:
                hd_ip = self.fallback_ip

        if lineup:
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(CACHE_FILE, "w") as f:
                    json.dump({"ip": hd_ip, "channels": lineup}, f)
            except Exception:
                pass
            self.lineup_ready.emit(lineup, hd_ip)
        else:
            self.status_update.emit("Could not load channels. Check HDHomeRun connection.")

    def discover_ip(self):
        self.status_update.emit("Connecting to HDHomeRun...")
        try:
            req = urllib.request.Request(
                "http://ipv4-api.hdhomerun.com/discover",
                headers={"User-Agent": "KidsTV/1.0"}
            )
            with urllib.request.urlopen(req, timeout=3) as res:
                data = json.loads(res.read().decode())
                if isinstance(data, list) and len(data) > 0:
                    local_ip = data[0].get("LocalIP")
                    if local_ip:
                        return local_ip
        except Exception:
            pass

        try:
            req = urllib.request.Request(f"http://{self.fallback_ip}/discover.json")
            with urllib.request.urlopen(req, timeout=2) as res:
                return self.fallback_ip
        except Exception:
            pass

        return self.fallback_ip

    def fetch_lineup(self, ip):
        try:
            url = f"http://{ip}/lineup.json"
            req = urllib.request.Request(url, headers={"User-Agent": "KidsTV/1.0"})
            with urllib.request.urlopen(req, timeout=5) as res:
                channels = json.loads(res.read().decode())
                if isinstance(channels, list) and channels:
                    return channels
        except Exception:
            pass
        return None


class ChannelCard(QFrame):
    clicked = pyqtSignal(dict)
    fav_toggled = pyqtSignal(dict, bool)

    def __init__(self, channel_data, is_active=False, is_fav=False, has_signal=True, parent=None):
        super().__init__(parent)
        self.channel_data = channel_data
        self.is_active = is_active
        self.is_fav = is_fav
        self.has_signal = has_signal
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(66)
        self.setObjectName("ChannelCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 12, 6)
        layout.setSpacing(10)

        # Favorite star button
        self.fav_btn = QPushButton("★" if is_fav else "☆")
        self.fav_btn.setFixedSize(36, 36)
        self.fav_btn.setObjectName("FavButton")
        self.fav_btn.setToolTip("Star favorite channel")
        self.fav_btn.clicked.connect(self._toggle_fav)
        layout.addWidget(self.fav_btn)

        # Channel number badge
        num_str = str(channel_data.get("GuideNumber", ""))
        self.num_label = QLabel(num_str)
        self.num_label.setFixedWidth(58)
        self.num_label.setAlignment(Qt.AlignCenter)
        self.num_label.setObjectName("ChannelNumber")
        layout.addWidget(self.num_label)

        # Channel name
        name_str = channel_data.get("GuideName", "")
        self.name_label = QLabel(name_str)
        self.name_label.setObjectName("ChannelName")
        layout.addWidget(self.name_label, stretch=1)

        # Status badge (HD or Playing)
        self.badge_label = QLabel()
        self.badge_label.setObjectName("StatusBadge")
        layout.addWidget(self.badge_label)

        self.update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.channel_data)
        super().mousePressEvent(event)

    def _toggle_fav(self):
        self.is_fav = not self.is_fav
        self.fav_btn.setText("★" if self.is_fav else "☆")
        self.fav_toggled.emit(self.channel_data, self.is_fav)

    def set_active(self, active):
        self.is_active = active
        self.update_style()

    def set_favorite(self, fav):
        self.is_fav = fav
        self.fav_btn.setText("★" if self.is_fav else "☆")

    def update_style(self):
        is_hd = bool(self.channel_data.get("HD", 0))

        if self.is_active:
            self.badge_label.setText("▶ PLAYING")
            self.badge_label.setStyleSheet(
                "background-color: #10B981; color: white; font-weight: 800; "
                "font-size: 11px; padding: 4px 8px; border-radius: 6px;"
            )
            self.setStyleSheet(
                "#ChannelCard { background-color: #312E81; border: 2px solid #6366F1; border-radius: 12px; }"
                "#ChannelName { color: #FFFFFF; font-weight: bold; font-size: 17px; }"
                "#ChannelNumber { background-color: #6366F1; color: #FFFFFF; font-weight: bold; font-size: 15px; border-radius: 8px; padding: 4px; }"
                "#FavButton { background: transparent; border: none; font-size: 20px; color: #F59E0B; }"
            )
        else:
            if is_hd:
                self.badge_label.setText("HD")
                self.badge_label.setStyleSheet(
                    "background-color: #1E293B; color: #38BDF8; font-weight: bold; "
                    "font-size: 11px; padding: 3px 6px; border-radius: 4px;"
                )
            else:
                self.badge_label.setText("")
                self.badge_label.setStyleSheet("")

            fav_color = "#F59E0B" if self.is_fav else "#64748B"
            border_color = "#334155" if self.has_signal else "#1F2937"
            bg_color = "#1E293B" if self.has_signal else "#151D2A"
            text_color = "#E2E8F0" if self.has_signal else "#94A3B8"

            self.setStyleSheet(
                f"#ChannelCard {{ background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 12px; }}"
                f"#ChannelCard:hover {{ background-color: #2D3748; border-color: #6366F1; }}"
                f"#ChannelName {{ color: {text_color}; font-size: 16px; font-weight: 600; }}"
                f"#ChannelNumber {{ background-color: #0F172A; color: #94A3B8; font-weight: bold; font-size: 14px; border-radius: 8px; padding: 4px; }}"
                f"#FavButton {{ background: transparent; border: none; font-size: 20px; color: {fav_color}; }}"
            )


class KidsTVWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Watch TV")
        self.setMinimumSize(960, 600)
        self.resize(1280, 720)

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.channels = []
        self.filtered_channels = []
        self.current_channel = None
        self.current_channel_index = -1
        self.favorites = set(["9.1", "3.2", "9.4", "56.7"])
        self.filter_mode = "live"  # "live", "fav", or "all"
        self.is_muted = False
        self.volume = 80
        self.is_fullscreen = False

        self.mpv_proc = None
        self.card_widgets = []
        self.tune_timestamp = 0

        self.load_state()
        self.setup_ui()
        self.load_channels()

        # Start mpv after initial channels & UI are ready
        initial_ip = DEFAULT_HDHOMERUN_HOST
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    cached = json.load(f)
                    initial_ip = cached.get("ip", initial_ip)
            except Exception:
                pass
        initial_url = f"http://{initial_ip}:5004/auto/v9.1"
        self.start_mpv(initial_url)

        # Status check timer
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.check_playback_status)
        self.monitor_timer.start(800)

    def load_state(self):
        try:
            if os.path.exists(FAVORITES_FILE):
                with open(FAVORITES_FILE, "r") as f:
                    self.favorites = set(json.load(f))
        except Exception:
            pass

        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    st = json.load(f)
                    self.is_muted = st.get("muted", False)
                    self.volume = st.get("volume", 80)
                    self.last_channel_num = st.get("last_channel", "9.1")
                    self.filter_mode = st.get("filter_mode", "live")
            else:
                self.last_channel_num = "9.1"
        except Exception:
            self.last_channel_num = "9.1"

    def save_state(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "muted": self.is_muted,
                    "volume": self.volume,
                    "last_channel": self.current_channel.get("GuideNumber") if self.current_channel else "9.1",
                    "filter_mode": self.filter_mode
                }, f)
            with open(FAVORITES_FILE, "w") as f:
                json.dump(list(self.favorites), f)
        except Exception:
            pass

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0F172A;
            }
            QLabel {
                font-family: 'DejaVu Sans', 'Liberation Sans', sans-serif;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # LEFT SIDEBAR: CHANNEL GUIDE
        self.left_panel = QFrame()
        self.left_panel.setFixedWidth(350)
        self.left_panel.setStyleSheet("background-color: #111827; border-radius: 16px;")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        # Header Title
        title_box = QHBoxLayout()
        title_icon = QLabel("📺")
        title_icon.setStyleSheet("font-size: 26px;")
        title_box.addWidget(title_icon)

        title_lbl = QLabel("Channels")
        title_lbl.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: 800;")
        title_box.addWidget(title_lbl)
        title_box.addStretch()
        left_layout.addLayout(title_box)

        # Filter Buttons (Live / Favorites / All)
        filter_box = QHBoxLayout()
        filter_box.setSpacing(6)

        self.btn_filter_live = QPushButton("⚡ Live Signal")
        self.btn_filter_live.setFixedHeight(38)
        self.btn_filter_live.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_filter_live.clicked.connect(lambda: self.set_filter("live"))
        filter_box.addWidget(self.btn_filter_live)

        self.btn_filter_fav = QPushButton("⭐ Starred")
        self.btn_filter_fav.setFixedHeight(38)
        self.btn_filter_fav.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_filter_fav.clicked.connect(lambda: self.set_filter("fav"))
        filter_box.addWidget(self.btn_filter_fav)

        self.btn_filter_all = QPushButton("📺 All")
        self.btn_filter_all.setFixedHeight(38)
        self.btn_filter_all.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_filter_all.clicked.connect(lambda: self.set_filter("all"))
        filter_box.addWidget(self.btn_filter_all)

        left_layout.addLayout(filter_box)

        # Big Scroll Up Button
        self.btn_scroll_up = QPushButton("▲ Scroll Up")
        self.btn_scroll_up.setFixedHeight(34)
        self.btn_scroll_up.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_scroll_up.setStyleSheet("""
            QPushButton {
                background-color: #1F2937; color: #9CA3AF; font-size: 13px; font-weight: bold;
                border: 1px solid #374151; border-radius: 8px;
            }
            QPushButton:hover { background-color: #374151; color: white; }
        """)
        self.btn_scroll_up.clicked.connect(lambda: self.scroll_channel_list(-300))
        left_layout.addWidget(self.btn_scroll_up)

        # Channels Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #1F2937; width: 14px; border-radius: 7px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #4B5563; border-radius: 7px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #6B7280; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.channels_container = QWidget()
        self.channels_container.setStyleSheet("background: transparent;")
        self.channels_layout = QVBoxLayout(self.channels_container)
        self.channels_layout.setContentsMargins(0, 0, 0, 0)
        self.channels_layout.setSpacing(8)
        self.channels_layout.addStretch()

        self.scroll_area.setWidget(self.channels_container)
        left_layout.addWidget(self.scroll_area, stretch=1)

        # Big Scroll Down Button
        self.btn_scroll_down = QPushButton("▼ Scroll Down")
        self.btn_scroll_down.setFixedHeight(34)
        self.btn_scroll_down.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_scroll_down.setStyleSheet("""
            QPushButton {
                background-color: #1F2937; color: #9CA3AF; font-size: 13px; font-weight: bold;
                border: 1px solid #374151; border-radius: 8px;
            }
            QPushButton:hover { background-color: #374151; color: white; }
        """)
        self.btn_scroll_down.clicked.connect(lambda: self.scroll_channel_list(300))
        left_layout.addWidget(self.btn_scroll_down)

        self.update_filter_button_styles()
        main_layout.addWidget(self.left_panel)

        # RIGHT PANEL: VIDEO + CONTROLS
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #111827; border-radius: 16px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(12)

        # Top Bar: Channel Info & Fullscreen
        self.top_bar = QHBoxLayout()
        self.top_bar.setContentsMargins(6, 0, 6, 0)

        self.lbl_now_playing_badge = QLabel("NOW PLAYING:")
        self.lbl_now_playing_badge.setStyleSheet(
            "background-color: #3730A3; color: #A5B4FC; font-size: 13px; font-weight: 800; "
            "padding: 6px 12px; border-radius: 8px;"
        )
        self.top_bar.addWidget(self.lbl_now_playing_badge)

        self.lbl_channel_title = QLabel("9.1  •  WSYR-HD")
        self.lbl_channel_title.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: 800; margin-left: 6px;")
        self.top_bar.addWidget(self.lbl_channel_title, stretch=1)

        self.lbl_status = QLabel("● TUNING...")
        self.lbl_status.setStyleSheet("color: #60A5FA; font-size: 14px; font-weight: bold; margin-right: 12px;")
        self.top_bar.addWidget(self.lbl_status)

        self.btn_fullscreen = QPushButton("⛶ Fullscreen")
        self.btn_fullscreen.setFixedHeight(40)
        self.btn_fullscreen.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_fullscreen.setStyleSheet("""
            QPushButton {
                background-color: #1F2937; color: #E2E8F0; font-size: 14px; font-weight: bold;
                border: 1px solid #4B5563; border-radius: 10px; padding: 0 16px;
            }
            QPushButton:hover { background-color: #374151; border-color: #6B7280; }
        """)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        self.top_bar.addWidget(self.btn_fullscreen)

        right_layout.addLayout(self.top_bar)

        # Video Display Container
        self.video_widget = QWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_widget.setStyleSheet("background-color: #000000; border-radius: 12px;")
        self.video_widget.installEventFilter(self)
        right_layout.addWidget(self.video_widget, stretch=1)

        # Bottom Control Bar
        self.bottom_bar = QFrame()
        self.bottom_bar.setFixedHeight(86)
        self.bottom_bar.setStyleSheet("background-color: #1F2937; border-radius: 14px; border: 1px solid #374151;")
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        bottom_layout.setSpacing(14)

        # Previous Channel Button
        self.btn_prev_ch = QPushButton("◀ Prev Channel")
        self.btn_prev_ch.setFixedHeight(58)
        self.btn_prev_ch.setMinimumWidth(150)
        self.btn_prev_ch.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_prev_ch.setStyleSheet("""
            QPushButton {
                background-color: #374151; color: white; font-size: 16px; font-weight: bold;
                border-radius: 12px; border: 1px solid #4B5563;
            }
            QPushButton:hover { background-color: #4B5563; }
            QPushButton:pressed { background-color: #1F2937; }
        """)
        self.btn_prev_ch.clicked.connect(self.prev_channel)
        bottom_layout.addWidget(self.btn_prev_ch)

        # Next Channel Button
        self.btn_next_ch = QPushButton("Next Channel ▶")
        self.btn_next_ch.setFixedHeight(58)
        self.btn_next_ch.setMinimumWidth(150)
        self.btn_next_ch.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_next_ch.setStyleSheet("""
            QPushButton {
                background-color: #374151; color: white; font-size: 16px; font-weight: bold;
                border-radius: 12px; border: 1px solid #4B5563;
            }
            QPushButton:hover { background-color: #4B5563; }
            QPushButton:pressed { background-color: #1F2937; }
        """)
        self.btn_next_ch.clicked.connect(self.next_channel)
        bottom_layout.addWidget(self.btn_next_ch)

        bottom_layout.addSpacing(10)

        # GIANT MUTE BUTTON
        self.btn_mute = QPushButton()
        self.btn_mute.setFixedHeight(58)
        self.btn_mute.setMinimumWidth(190)
        self.btn_mute.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.update_mute_button_style()
        bottom_layout.addWidget(self.btn_mute)

        bottom_layout.addSpacing(10)

        # Volume Controls
        self.btn_vol_down = QPushButton("🔉 -")
        self.btn_vol_down.setFixedSize(56, 56)
        self.btn_vol_down.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_vol_down.setStyleSheet("""
            QPushButton {
                background-color: #374151; color: white; font-size: 22px; font-weight: bold;
                border-radius: 12px; border: 1px solid #4B5563;
            }
            QPushButton:hover { background-color: #4B5563; }
        """)
        self.btn_vol_down.clicked.connect(lambda: self.change_volume(-10))
        bottom_layout.addWidget(self.btn_vol_down)

        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(self.volume)
        self.slider_vol.setFixedWidth(120)
        self.slider_vol.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 10px; background: #374151; border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #6366F1; border-radius: 5px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF; width: 24px; height: 24px; margin-top: -7px; margin-bottom: -7px; border-radius: 12px;
            }
        """)
        self.slider_vol.valueChanged.connect(self.on_volume_slider_changed)
        bottom_layout.addWidget(self.slider_vol)

        self.btn_vol_up = QPushButton("🔊 +")
        self.btn_vol_up.setFixedSize(56, 56)
        self.btn_vol_up.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_vol_up.setStyleSheet("""
            QPushButton {
                background-color: #374151; color: white; font-size: 22px; font-weight: bold;
                border-radius: 12px; border: 1px solid #4B5563;
            }
            QPushButton:hover { background-color: #4B5563; }
        """)
        self.btn_vol_up.clicked.connect(lambda: self.change_volume(10))
        bottom_layout.addWidget(self.btn_vol_up)

        self.lbl_volume = QLabel(f"{self.volume}%")
        self.lbl_volume.setFixedWidth(46)
        self.lbl_volume.setAlignment(Qt.AlignCenter)
        self.lbl_volume.setStyleSheet("color: #E2E8F0; font-size: 15px; font-weight: bold;")
        bottom_layout.addWidget(self.lbl_volume)

        right_layout.addWidget(self.bottom_bar)
        main_layout.addWidget(right_panel, stretch=1)

    def eventFilter(self, obj, event):
        if obj == self.video_widget and event.type() == QEvent.MouseButtonDblClick:
            self.toggle_fullscreen()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.is_fullscreen:
                self.toggle_fullscreen()
        elif event.key() == Qt.Key_F:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_M or event.key() == Qt.Key_Space:
            self.toggle_mute()
        elif event.key() == Qt.Key_Up or event.key() == Qt.Key_Left:
            self.prev_channel()
        elif event.key() == Qt.Key_Down or event.key() == Qt.Key_Right:
            self.next_channel()
        else:
            super().keyPressEvent(event)

    def scroll_channel_list(self, delta):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.value() + delta)

    def update_filter_button_styles(self):
        active_style = """
            QPushButton {
                background-color: #4F46E5; color: white; font-size: 13px; font-weight: bold;
                border-radius: 8px; border: 2px solid #818CF8;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #1F2937; color: #9CA3AF; font-size: 13px; font-weight: bold;
                border-radius: 8px; border: 1px solid #374151;
            }
            QPushButton:hover { background-color: #374151; color: white; }
        """
        self.btn_filter_live.setStyleSheet(active_style if self.filter_mode == "live" else inactive_style)
        self.btn_filter_fav.setStyleSheet(active_style if self.filter_mode == "fav" else inactive_style)
        self.btn_filter_all.setStyleSheet(active_style if self.filter_mode == "all" else inactive_style)

    def set_filter(self, mode):
        self.filter_mode = mode
        self.update_filter_button_styles()
        self.rebuild_channel_list()
        self.save_state()

    def update_mute_button_style(self):
        if self.is_muted:
            self.btn_mute.setText("🔇 MUTED\n(Click for Sound)")
            self.btn_mute.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444; color: white; font-size: 15px; font-weight: 800;
                    border-radius: 12px; border: 2px solid #F87171;
                }
                QPushButton:hover { background-color: #DC2626; }
            """)
        else:
            self.btn_mute.setText("🔊 SOUND ON\n(Click to Mute)")
            self.btn_mute.setStyleSheet("""
                QPushButton {
                    background-color: #059669; color: white; font-size: 15px; font-weight: 800;
                    border-radius: 12px; border: 2px solid #34D399;
                }
                QPushButton:hover { background-color: #047857; }
            """)

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self.update_mute_button_style()
        self.mpv_send(["set_property", "mute", self.is_muted])
        self.save_state()

    def change_volume(self, delta):
        new_vol = max(0, min(100, self.volume + delta))
        self.slider_vol.setValue(new_vol)

    def on_volume_slider_changed(self, val):
        self.volume = val
        self.lbl_volume.setText(f"{val}%")
        self.mpv_send(["set_property", "volume", self.volume])
        if self.is_muted and val > 0:
            self.is_muted = False
            self.update_mute_button_style()
            self.mpv_send(["set_property", "mute", False])
        self.save_state()

    def toggle_fullscreen(self):
        if not self.is_fullscreen:
            self.left_panel.hide()
            self.showFullScreen()
            self.btn_fullscreen.setText("⛶ Exit Fullscreen")
            self.is_fullscreen = True
        else:
            self.left_panel.show()
            self.showNormal()
            self.btn_fullscreen.setText("⛶ Fullscreen")
            self.is_fullscreen = False

    def start_mpv(self, initial_stream_url):
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except Exception:
                pass

        QApplication.processEvents()
        wid = int(self.video_widget.winId())

        # Start mpv directly playing initial stream URL
        cmd = [
            "mpv",
            f"--wid={wid}",
            "--gpu-context=x11egl",
            "--idle=yes",
            "--force-window=yes",
            f"--input-ipc-server={SOCKET_PATH}",
            "--deinterlace=yes",
            "--hwdec=auto",
            "--no-terminal",
            "--no-osc",
            "--no-osd-bar",
            "--keep-open=yes",
            f"--volume={self.volume}",
            f"--mute={'yes' if self.is_muted else 'no'}",
            initial_stream_url
        ]

        try:
            self.mpv_proc = subprocess.Popen(cmd)
            self.tune_timestamp = time.time()
        except Exception as e:
            self.lbl_channel_title.setText(f"Player error: {e}")

    def mpv_send(self, command_list, max_wait_sec=1.5):
        # Wait briefly for socket if starting up
        t0 = time.time()
        while not os.path.exists(SOCKET_PATH) and (time.time() - t0 < max_wait_sec):
            time.sleep(0.05)

        if not os.path.exists(SOCKET_PATH):
            return None

        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(SOCKET_PATH)
            msg = json.dumps({"command": command_list}) + "\n"
            s.sendall(msg.encode())
            raw = s.recv(2048).decode()
            s.close()

            # Parse lines to find command response
            for line in raw.strip().split("\n"):
                if line:
                    try:
                        data = json.loads(line)
                        if "error" in data:
                            return data
                    except Exception:
                        pass
            return None
        except Exception:
            return None

    def check_playback_status(self):
        # Poll playback-time to verify video stream is actually flowing
        res = self.mpv_send(["get_property", "playback-time"])
        if res and res.get("error") == "success" and res.get("data") is not None:
            curr_time = res.get("data")
            if curr_time > 0.05:
                self.lbl_status.setText("● LIVE PLAYING")
                self.lbl_status.setStyleSheet("color: #10B981; font-size: 14px; font-weight: bold; margin-right: 12px;")
                return

        # If more than 3.5 seconds passed since tuning and no playback time:
        if self.tune_timestamp > 0 and (time.time() - self.tune_timestamp > 3.5):
            self.lbl_status.setText("⚠️ NO ANTENNA SIGNAL (Try 9.1 or 3.2)")
            self.lbl_status.setStyleSheet("color: #F59E0B; font-size: 14px; font-weight: bold; margin-right: 12px;")

    def load_channels(self):
        cached_channels = None
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    cached_data = json.load(f)
                    cached_channels = cached_data.get("channels", [])
            except Exception:
                pass

        if cached_channels:
            self.channels = cached_channels
            self.rebuild_channel_list()

        # Fetch fresh list in background
        self.fetcher = LineupFetcher()
        self.fetcher.lineup_ready.connect(self.on_lineup_loaded)
        t = Thread(target=self.fetcher.run, daemon=True)
        t.start()

    def on_lineup_loaded(self, channels, ip):
        if not channels:
            return
        self.channels = channels
        self.rebuild_channel_list()

    def rebuild_channel_list(self):
        for card in self.card_widgets:
            card.setParent(None)
            card.deleteLater()
        self.card_widgets.clear()

        while self.channels_layout.count():
            item = self.channels_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.filter_mode == "live":
            self.filtered_channels = [c for c in self.channels if str(c.get("GuideNumber", "")) in KNOWN_ACTIVE_CHANNELS]
            if not self.filtered_channels:
                self.filtered_channels = list(self.channels)
        elif self.filter_mode == "fav":
            self.filtered_channels = [c for c in self.channels if str(c.get("GuideNumber", "")) in self.favorites]
            if not self.filtered_channels:
                self.filtered_channels = [c for c in self.channels if str(c.get("GuideNumber", "")) in KNOWN_ACTIVE_CHANNELS]
        else:
            self.filtered_channels = list(self.channels)

        # Highlight current channel or default 9.1
        active_num = self.current_channel.get("GuideNumber") if self.current_channel else "9.1"

        for ch in self.filtered_channels:
            num = str(ch.get("GuideNumber", ""))
            is_active = (num == str(active_num))
            is_fav = num in self.favorites
            has_sig = num in KNOWN_ACTIVE_CHANNELS

            card = ChannelCard(ch, is_active=is_active, is_fav=is_fav, has_signal=has_sig)
            card.clicked.connect(self.play_channel)
            card.fav_toggled.connect(self.on_fav_toggled)
            self.card_widgets.append(card)
            self.channels_layout.addWidget(card)

            if is_active and not self.current_channel:
                self.current_channel = ch
                self.lbl_channel_title.setText(f"{num}  •  {ch.get('GuideName', '')}")

        self.channels_layout.addStretch()

    def on_fav_toggled(self, channel_data, is_fav):
        num = str(channel_data.get("GuideNumber", ""))
        if is_fav:
            self.favorites.add(num)
        else:
            self.favorites.discard(num)
        self.save_state()

        if self.filter_mode == "fav" and not is_fav:
            self.rebuild_channel_list()

    def play_channel(self, channel_data):
        self.current_channel = channel_data
        guide_num = str(channel_data.get("GuideNumber", ""))
        guide_name = channel_data.get("GuideName", "")
        url = channel_data.get("URL", "")

        for i, card in enumerate(self.card_widgets):
            is_match = (str(card.channel_data.get("GuideNumber", "")) == guide_num)
            card.set_active(is_match)
            if is_match:
                self.current_channel_index = i

        self.lbl_channel_title.setText(f"{guide_num}  •  {guide_name}")
        self.lbl_status.setText("● TUNING...")
        self.lbl_status.setStyleSheet("color: #60A5FA; font-size: 14px; font-weight: bold; margin-right: 12px;")
        self.tune_timestamp = time.time()

        # Send loadfile to mpv
        self.mpv_send(["loadfile", url, "replace"])
        self.save_state()

    def prev_channel(self):
        if not self.filtered_channels:
            return
        new_index = (self.current_channel_index - 1) % len(self.filtered_channels)
        self.play_channel(self.filtered_channels[new_index])

    def next_channel(self):
        if not self.filtered_channels:
            return
        new_index = (self.current_channel_index + 1) % len(self.filtered_channels)
        self.play_channel(self.filtered_channels[new_index])

    def bring_to_front(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        self.save_state()
        if self.mpv_proc:
            try:
                self.mpv_send(["quit"])
                time.sleep(0.1)
                self.mpv_proc.terminate()
            except Exception:
                pass
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except Exception:
                pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Watch TV")

    socket_client = QLocalSocket()
    socket_client.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
    if socket_client.waitForConnected(500):
        socket_client.write(b"raise\n")
        socket_client.waitForBytesWritten(500)
        socket_client.disconnectFromServer()
        sys.exit(0)

    server = QLocalServer()
    server.removeServer(SINGLE_INSTANCE_SERVER_NAME)
    server.listen(SINGLE_INSTANCE_SERVER_NAME)

    font = QFont("DejaVu Sans", 11)
    app.setFont(font)

    win = KidsTVWindow()

    def on_new_connection():
        client = server.nextPendingConnection()
        if client:
            client.waitForReadyRead(500)
            win.bring_to_front()
            client.disconnectFromServer()

    server.newConnection.connect(on_new_connection)

    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
