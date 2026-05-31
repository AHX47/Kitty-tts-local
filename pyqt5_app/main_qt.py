"""
Kitten TTS — PyQt5 Desktop App
Targets: Windows (.exe via PyInstaller) · Linux (.deb / .AppImage)

Run:  python main_qt.py
Build exe:    python build_scripts/build_exe.py
Build deb:    bash build_scripts/build_deb.sh
Build AppImg: bash build_scripts/build_appimage.sh
"""
from __future__ import annotations
import os, sys, threading, math, tempfile, random
from pathlib import Path
from datetime import datetime

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QDialog, QDialogButtonBox, QComboBox,
    QSlider, QRadioButton, QButtonGroup, QGroupBox, QFileDialog,
    QListWidget, QListWidgetItem, QProgressDialog, QSplitter,
    QTabWidget, QCheckBox, QMessageBox, QStackedWidget,
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation,
    QEasingCurve, QRect, QUrl, QSize,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QFont, QFontDatabase, QIcon,
    QPainterPath, QPixmap, QLinearGradient, QPalette, QBrush,
)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

import numpy as np

from core.tts_engine    import TTSEngine, AVAILABLE_MODELS, DEFAULT_VOICES
from core.voice_cloner  import extract_embedding, save_voice, delete_voice
from core.audio_utils   import save_audio, waveform_bars, duration_str as dur_str, resample
from core.download_models import download_model, model_is_ready, MODELS_CONFIG

TEMP_DIR = Path(tempfile.gettempdir()) / "kittentts_qt"
TEMP_DIR.mkdir(exist_ok=True)

# ── Palette ──────────────────────────────────────────────────────────────────
BG     = "#0f172a"
BG2    = "#1e293b"
BG3    = "#1f2937"
CARD   = "#1a2332"
ACCENT = "#3b82f6"
ACC2   = "#60a5fa"
TEXT   = "#e2e8f0"
DIM    = "#94a3b8"
USER   = "#334155"
GREEN  = "#22c55e"
RED    = "#ef4444"


def qc(hex_str: str) -> QColor:
    return QColor(hex_str)


def apply_dark_palette(app: QApplication):
    pal = QPalette()
    pal.setColor(QPalette.Window,          qc(BG))
    pal.setColor(QPalette.WindowText,      qc(TEXT))
    pal.setColor(QPalette.Base,            qc(BG2))
    pal.setColor(QPalette.AlternateBase,   qc(BG3))
    pal.setColor(QPalette.ToolTipBase,     qc(BG2))
    pal.setColor(QPalette.ToolTipText,     qc(TEXT))
    pal.setColor(QPalette.Text,            qc(TEXT))
    pal.setColor(QPalette.Button,          qc(BG2))
    pal.setColor(QPalette.ButtonText,      qc(TEXT))
    pal.setColor(QPalette.BrightText,      Qt.red)
    pal.setColor(QPalette.Highlight,       qc(ACCENT))
    pal.setColor(QPalette.HighlightedText, qc(TEXT))
    app.setPalette(pal)
    app.setStyleSheet(f"""
        * {{ font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; color: {TEXT}; }}
        QMainWindow, QDialog, QWidget {{ background: {BG}; }}
        QScrollBar:vertical {{ background: {BG2}; width: 6px; border-radius: 3px; }}
        QScrollBar::handle:vertical {{ background: {ACCENT}; border-radius: 3px; min-height: 20px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QTextEdit, QLineEdit, QComboBox {{
            background: {BG2}; border: 1px solid {BG3};
            border-radius: 8px; padding: 6px 10px; color: {TEXT};
        }}
        QTextEdit:focus, QLineEdit:focus, QComboBox:focus {{
            border: 1px solid {ACCENT};
        }}
        QPushButton {{
            background: {BG2}; border: 1px solid {BG3}; border-radius: 8px;
            padding: 6px 14px; color: {TEXT};
        }}
        QPushButton:hover {{ background: {BG3}; border-color: {ACCENT}; }}
        QPushButton:pressed {{ background: {ACCENT}; }}
        QPushButton#accent {{ background: {ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
        QPushButton#accent:hover {{ background: {ACC2}; }}
        QPushButton#danger {{ background: {RED}; border-color: {RED}; }}
        QGroupBox {{
            border: 1px solid {BG3}; border-radius: 10px;
            margin-top: 14px; padding: 10px;
            font-weight: 600; color: {ACC2};
        }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background: {BG2}; selection-background-color: {ACCENT};
            border: 1px solid {BG3}; border-radius: 8px;
        }}
        QSlider::groove:horizontal {{
            background: {BG3}; height: 4px; border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT}; width: 14px; height: 14px;
            border-radius: 7px; margin: -5px 0;
        }}
        QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
        QLabel {{ background: transparent; }}
        QRadioButton::indicator {{ width: 14px; height: 14px; }}
        QRadioButton::indicator:checked {{ background: {ACCENT}; border-radius: 7px; }}
        QListWidget {{ background: {BG2}; border: 1px solid {BG3}; border-radius: 8px; }}
        QListWidget::item:selected {{ background: {ACCENT}; border-radius: 6px; }}
        QTabWidget::pane {{ border: 1px solid {BG3}; border-radius: 8px; }}
        QTabBar::tab {{
            background: {BG2}; padding: 6px 16px; border-radius: 6px; margin-right: 2px;
        }}
        QTabBar::tab:selected {{ background: {ACCENT}; }}
    """)


# ─────────────────────────────────────────────────────────────────────────────
# Worker threads
# ─────────────────────────────────────────────────────────────────────────────
class TTSWorker(QThread):
    done    = pyqtSignal(object, str, str, list)  # audio, wav_path, duration, bars
    error   = pyqtSignal(str)
    status  = pyqtSignal(str)

    def __init__(self, engine: TTSEngine, text: str, voice: str, speed: float):
        super().__init__()
        self.engine = engine
        self.text   = text
        self.voice  = voice
        self.speed  = speed

    def run(self):
        try:
            self.status.emit("Generating speech…")
            audio    = self.engine.generate(self.text, self.voice, self.speed)
            path     = str(TEMP_DIR / f"tts_{id(self)}.wav")
            self.engine.save_wav(audio, path)
            bars = waveform_bars(audio)
            dur  = dur_str(audio)
            self.done.emit(audio, path, dur, bars)
        except Exception as exc:
            self.error.emit(str(exc))


class ModelLoadWorker(QThread):
    done   = pyqtSignal(bool)
    status = pyqtSignal(str)

    def __init__(self, engine: TTSEngine, model_key: str):
        super().__init__()
        self.engine    = engine
        self.model_key = model_key

    def run(self):
        ok = self.engine.load_model(
            self.model_key,
            progress_cb=lambda m: self.status.emit(m),
        )
        self.done.emit(ok)


class VoiceCloneWorker(QThread):
    done  = pyqtSignal(str, object)
    error = pyqtSignal(str)

    def __init__(self, audio_path: str, name: str):
        super().__init__()
        self.audio_path = audio_path
        self.name       = name

    def run(self):
        try:
            emb = extract_embedding(self.audio_path)
            save_voice(self.name, emb)
            self.done.emit(self.name, emb)
        except Exception as exc:
            self.error.emit(str(exc))


class DownloadWorker(QThread):
    progress = pyqtSignal(str)
    done     = pyqtSignal(bool)

    def __init__(self, model_key: str):
        super().__init__()
        self.model_key = model_key

    def run(self):
        ok = download_model(self.model_key, lambda m: self.progress.emit(m))
        self.done.emit(ok)


# ─────────────────────────────────────────────────────────────────────────────
# Waveform widget
# ─────────────────────────────────────────────────────────────────────────────
class WaveformWidget(QWidget):
    def __init__(self, bars: list[float], parent=None):
        super().__init__(parent)
        self.bars     = bars or [0.2] * 22
        self.playing  = False
        self._phase   = 0.0
        self.setMinimumSize(100, 36)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

    def set_playing(self, flag: bool):
        self.playing = flag
        if flag:
            self._timer.start(50)
        else:
            self._timer.stop()
            self.update()

    def _animate(self):
        self._phase += 0.25
        self.update()

    def paintEvent(self, _):
        p   = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w   = self.width()
        h   = self.height()
        n   = len(self.bars)
        bw  = max(3, (w - (n-1)*2) // n)
        cx  = (w - (n * bw + (n-1)*2)) // 2

        for i, val in enumerate(self.bars):
            if self.playing:
                val = val * (0.6 + 0.4 * math.sin(self._phase + i * 0.5))
            bh   = max(4, int(val * (h - 6)))
            x    = cx + i * (bw + 2)
            y    = (h - bh) // 2
            alpha = 200 if self.playing else 140
            clr  = QColor(ACC2)
            clr.setAlpha(alpha)
            p.setBrush(QBrush(clr))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(x, y, bw, bh, 2, 2)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Message bubble widgets
# ─────────────────────────────────────────────────────────────────────────────
class UserBubble(QWidget):
    def __init__(self, text: str, ts: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(60, 4, 8, 4)
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setStyleSheet(f"""
            background: {USER}; color: {TEXT}; border-radius: 14px 14px 2px 14px;
            padding: 10px 12px; font-size: 13px;
        """)
        lay.addStretch()
        lay.addWidget(bubble)


class AIBubble(QWidget):
    play_requested     = pyqtSignal(int)
    download_requested = pyqtSignal(int)

    def __init__(self, msg_id: int, bars: list[float], duration: str,
                 audio_path: str, parent=None):
        super().__init__(parent)
        self.msg_id    = msg_id
        self.audio_path = audio_path
        self.expanded  = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build(bars, duration)

    def _build(self, bars: list[float], duration: str):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 4, 60, 4)

        self._bubble = QFrame()
        self._bubble.setStyleSheet(f"""
            QFrame {{ background: {BG3}; border-radius: 14px 14px 14px 2px; }}
        """)

        inner = QVBoxLayout(self._bubble)
        inner.setContentsMargins(10, 10, 10, 10)
        inner.setSpacing(0)

        # Collapsed row
        self._collapsed = QWidget()
        row = QHBoxLayout(self._collapsed)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        dl_btn = QPushButton("↓")
        dl_btn.setFixedSize(32, 32)
        dl_btn.setStyleSheet(f"""
            QPushButton {{ background: {ACCENT}; border-radius: 16px;
                           font-weight: bold; font-size: 14px; border: none; }}
            QPushButton:hover {{ background: {ACC2}; }}
        """)
        dl_btn.clicked.connect(lambda: self.download_requested.emit(self.msg_id))

        self._wf_collapsed = WaveformWidget(bars)
        self._wf_collapsed.setFixedHeight(32)

        dur_lbl = QLabel(duration)
        dur_lbl.setStyleSheet(f"color: {ACC2}; font-size: 12px; font-weight: 500;")

        play_chip = QPushButton("▶A")
        play_chip.setFixedSize(36, 24)
        play_chip.setStyleSheet(f"""
            QPushButton {{ background: {BG2}; border-radius: 8px; font-size: 11px;
                           border: none; padding: 0; }}
        """)
        play_chip.clicked.connect(self._toggle_expand)

        row.addWidget(dl_btn)
        row.addWidget(self._wf_collapsed, 1)
        row.addWidget(dur_lbl)
        row.addWidget(play_chip)

        # Expanded player
        self._expanded = QWidget()
        self._expanded.setVisible(False)
        exp = QVBoxLayout(self._expanded)
        exp.setContentsMargins(0, 8, 0, 0)
        exp.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        icon_lbl = QLabel("♪")
        icon_lbl.setStyleSheet(f"""
            background: {ACCENT}; border-radius: 14px; padding: 4px 8px;
            font-size: 14px;
        """)
        sub_lbl = QLabel("Kitten TTS · Voice")
        sub_lbl.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {DIM}; font-size: 13px; }}
            QPushButton:hover {{ color: {TEXT}; }}
        """)
        close_btn.clicked.connect(self._collapse)
        hdr.addWidget(icon_lbl)
        hdr.addWidget(sub_lbl, 1)
        hdr.addWidget(close_btn)
        exp.addLayout(hdr)

        # Big waveform
        self._wf_expanded = WaveformWidget(bars)
        self._wf_expanded.setFixedHeight(44)
        exp.addWidget(self._wf_expanded)

        # Progress bar
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setValue(0)
        exp.addWidget(self._slider)

        # Time row
        time_row = QHBoxLayout()
        self._pos_lbl = QLabel("00:00")
        self._pos_lbl.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        self._dur_lbl = QLabel(duration)
        self._dur_lbl.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        time_row.addWidget(self._pos_lbl)
        time_row.addStretch()
        time_row.addWidget(self._dur_lbl)
        exp.addLayout(time_row)

        # Playback controls
        ctrl_row = QHBoxLayout()
        ctrl_row.setAlignment(Qt.AlignCenter)
        self._rw_btn  = QPushButton("⟲ 10")
        self._play_btn = QPushButton("▶")
        self._ff_btn  = QPushButton("10 ⟳")
        for btn in [self._rw_btn, self._play_btn, self._ff_btn]:
            btn.setFixedHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {BG2}; border-radius: 8px; border: none;
                               font-size: 14px; padding: 0 12px; }}
                QPushButton:hover {{ background: {ACCENT}; }}
            """)
        self._play_btn.setFixedSize(56, 56)
        self._play_btn.setStyleSheet(f"""
            QPushButton {{ background: {ACCENT}; border-radius: 28px; border: none;
                           font-size: 20px; color: white; }}
            QPushButton:hover {{ background: {ACC2}; }}
        """)
        self._play_btn.clicked.connect(lambda: self.play_requested.emit(self.msg_id))
        self._rw_btn.setFixedSize(46, 36)
        self._ff_btn.setFixedSize(46, 36)
        ctrl_row.addWidget(self._rw_btn)
        ctrl_row.addSpacing(8)
        ctrl_row.addWidget(self._play_btn)
        ctrl_row.addSpacing(8)
        ctrl_row.addWidget(self._ff_btn)
        exp.addLayout(ctrl_row)

        # Speed + download row
        bot_row = QHBoxLayout()
        speed_group = QButtonGroup(self)
        for spd in ["0.5×", "0.75×", "1×", "1.25×", "1.5×", "2×"]:
            btn = QPushButton(spd)
            btn.setFixedHeight(26)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {BG2}; border-radius: 6px; border: none;
                               font-size: 10px; padding: 0 6px; color: {DIM}; }}
                QPushButton:checked {{ background: {ACCENT}; color: white; }}
            """)
            if spd == "1×":
                btn.setChecked(True)
            speed_group.addButton(btn)
            bot_row.addWidget(btn)
        bot_row.addStretch()
        dl2_btn = QPushButton("↓ Download")
        dl2_btn.setStyleSheet(f"""
            QPushButton {{ background: {ACCENT}; border-radius: 8px; border: none;
                           padding: 4px 10px; font-size: 12px; }}
        """)
        dl2_btn.clicked.connect(lambda: self.download_requested.emit(self.msg_id))
        bot_row.addWidget(dl2_btn)
        exp.addLayout(bot_row)

        inner.addWidget(self._collapsed)
        inner.addWidget(self._expanded)

        outer.addWidget(self._bubble)

        # Click on collapsed to expand
        self._collapsed.mousePressEvent = lambda e: self._toggle_expand()

        # Timer for player position simulation
        self._pos_timer = QTimer(self)
        self._pos_timer.timeout.connect(self._tick)
        self._pos_secs = 0

    def _toggle_expand(self):
        if not self.expanded:
            self._expand()
        else:
            self._collapse()

    def _expand(self):
        self.expanded = True
        self._collapsed.setVisible(False)
        self._expanded.setVisible(True)
        self._wf_expanded.set_playing(False)
        self.play_requested.emit(self.msg_id)

    def _collapse(self):
        self.expanded = False
        self._collapsed.setVisible(True)
        self._expanded.setVisible(False)
        self._wf_expanded.set_playing(False)
        self._pos_timer.stop()

    def set_playing(self, playing: bool):
        self._wf_expanded.set_playing(playing)
        self._wf_collapsed.set_playing(playing)
        self._play_btn.setText("‖" if playing else "▶")
        if playing:
            self._pos_timer.start(1000)
        else:
            self._pos_timer.stop()

    def _tick(self):
        self._pos_secs += 1
        m = self._pos_secs // 60
        s = self._pos_secs % 60
        self._pos_lbl.setText(f"{m:02d}:{s:02d}")
        self._slider.setValue(min(self._pos_secs * 10, 1000))


# ─────────────────────────────────────────────────────────────────────────────
# Settings dialog
# ─────────────────────────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    model_changed = pyqtSignal(str)
    voice_changed = pyqtSignal(str)

    def __init__(self, engine: TTSEngine, current_model: str, current_voice: str,
                 current_speed: float, current_fmt: str, parent=None):
        super().__init__(parent)
        self.engine       = engine
        self.cur_model    = current_model
        self.cur_voice    = current_voice
        self.cur_speed    = current_speed
        self.cur_fmt      = current_fmt
        self._clone_path  = None
        self._dl_worker   = None
        self._clone_worker = None
        self.setWindowTitle("Settings — Kitten TTS")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        tabs = QTabWidget()
        tabs.addTab(self._model_tab(),  "Model")
        tabs.addTab(self._voice_tab(),  "Voice")
        tabs.addTab(self._export_tab(), "Export")
        lay.addWidget(tabs)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    # ── Model tab ─────────────────────────────────────────────────────────────
    def _model_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.addWidget(QLabel("Select active model:"))
        self._model_combo = QComboBox()
        for k, info in AVAILABLE_MODELS.items():
            ready = model_is_ready(k)
            label = f"{info['name']} ({info['size']}) {'✓' if ready else '— not downloaded'}"
            self._model_combo.addItem(label, k)
            if k == self.cur_model:
                self._model_combo.setCurrentIndex(self._model_combo.count() - 1)
        v.addWidget(self._model_combo)

        # Download section
        grp = QGroupBox("Download Models")
        gv  = QVBoxLayout(grp)
        self._dl_combo = QComboBox()
        for k, info in MODELS_CONFIG.items():
            self._dl_combo.addItem(info["name"], k)
        dl_btn = QPushButton("Download Selected Model")
        dl_btn.setObjectName("accent")
        dl_btn.clicked.connect(self._start_download)
        self._dl_status = QLabel("")
        self._dl_status.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        gv.addWidget(QLabel("Choose model to download:"))
        gv.addWidget(self._dl_combo)
        gv.addWidget(dl_btn)
        gv.addWidget(self._dl_status)
        v.addWidget(grp)
        v.addStretch()
        return w

    def _start_download(self):
        key = self._dl_combo.currentData()
        self._dl_status.setText(f"Starting download of {key}…")
        self._dl_worker = DownloadWorker(key)
        self._dl_worker.progress.connect(lambda m: self._dl_status.setText(m))
        self._dl_worker.done.connect(lambda ok: self._dl_status.setText(
            f"✓ {key} ready!" if ok else f"❌ Download failed"))
        self._dl_worker.start()

    # ── Voice tab ─────────────────────────────────────────────────────────────
    def _voice_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.addWidget(QLabel("Active voice:"))
        self._voice_combo = QComboBox()
        for voice in self.engine.all_voices():
            self._voice_combo.addItem(voice)
            if voice == self.cur_voice:
                self._voice_combo.setCurrentIndex(self._voice_combo.count()-1)
        v.addWidget(self._voice_combo)

        grp = QGroupBox("Clone New Voice")
        gv  = QVBoxLayout(grp)
        pick_btn = QPushButton("📁 Choose Audio File (WAV / MP3)")
        pick_btn.clicked.connect(self._pick_audio)
        self._clone_file_lbl = QLabel("No file selected")
        self._clone_file_lbl.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        self._clone_name_edit = QLineEdit()
        self._clone_name_edit.setPlaceholderText("Voice name (e.g. My Voice)")
        clone_btn = QPushButton("Extract & Save Voice")
        clone_btn.setObjectName("accent")
        clone_btn.clicked.connect(self._start_clone)
        self._clone_status = QLabel("")
        self._clone_status.setStyleSheet(f"color: {DIM}; font-size: 11px;")
        gv.addWidget(pick_btn)
        gv.addWidget(self._clone_file_lbl)
        gv.addWidget(QLabel("Voice name:"))
        gv.addWidget(self._clone_name_edit)
        gv.addWidget(clone_btn)
        gv.addWidget(self._clone_status)

        # Custom voice list
        grp2 = QGroupBox("Saved Custom Voices")
        gv2  = QVBoxLayout(grp2)
        self._custom_list = QListWidget()
        self._refresh_custom_list()
        del_btn = QPushButton("🗑 Delete Selected")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_voice)
        gv2.addWidget(self._custom_list)
        gv2.addWidget(del_btn)

        v.addWidget(grp)
        v.addWidget(grp2)
        v.addStretch()
        return w

    def _pick_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio", "", "Audio (*.wav *.mp3 *.ogg *.flac)")
        if path:
            self._clone_path = path
            self._clone_file_lbl.setText(f"📁 {Path(path).name}")

    def _start_clone(self):
        if not self._clone_path:
            self._clone_status.setText("⚠ Choose an audio file first")
            return
        name = self._clone_name_edit.text().strip()
        if not name:
            self._clone_status.setText("⚠ Enter a voice name")
            return
        self._clone_status.setText("Extracting embedding…")
        self._clone_worker = VoiceCloneWorker(self._clone_path, name)
        self._clone_worker.done.connect(self._on_clone_done)
        self._clone_worker.error.connect(lambda e: self._clone_status.setText(f"❌ {e}"))
        self._clone_worker.start()

    def _on_clone_done(self, name: str, _emb):
        self.engine.reload_custom_voices()
        self._clone_status.setText(f"✓ Voice '{name}' saved!")
        self._refresh_voice_combo()
        self._refresh_custom_list()

    def _refresh_voice_combo(self):
        cur = self._voice_combo.currentText()
        self._voice_combo.clear()
        for v in self.engine.all_voices():
            self._voice_combo.addItem(v)
        idx = self._voice_combo.findText(cur)
        if idx >= 0:
            self._voice_combo.setCurrentIndex(idx)

    def _refresh_custom_list(self):
        self._custom_list.clear()
        for name in self.engine.custom_voices:
            self._custom_list.addItem(name)

    def _delete_voice(self):
        item = self._custom_list.currentItem()
        if not item:
            return
        name = item.text()
        if QMessageBox.question(self, "Delete", f"Delete voice '{name}'?") == QMessageBox.Yes:
            delete_voice(name)
            self.engine.reload_custom_voices()
            self._refresh_custom_list()
            self._refresh_voice_combo()

    # ── Export tab ────────────────────────────────────────────────────────────
    def _export_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(12)

        fmt_grp = QGroupBox("Output Format")
        fv = QHBoxLayout(fmt_grp)
        self._fmt_bg = QButtonGroup()
        for fmt in ["wav", "mp3", "ogg"]:
            rb = QRadioButton(fmt.upper())
            rb.setChecked(fmt == self.cur_fmt)
            self._fmt_bg.addButton(rb)
            fv.addWidget(rb)

        sr_grp = QGroupBox("Sample Rate")
        sv = QHBoxLayout(sr_grp)
        self._sr_bg = QButtonGroup()
        for sr, lbl in [(22050, "22 kHz"), (24000, "24 kHz"), (44100, "44.1 kHz")]:
            rb = QRadioButton(lbl)
            rb.setProperty("sr_val", sr)
            rb.setChecked(sr == 24000)
            self._sr_bg.addButton(rb)
            sv.addWidget(rb)

        spd_grp = QGroupBox("Generation Speed")
        sv2 = QVBoxLayout(spd_grp)
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(25, 200)
        self._speed_slider.setValue(int(self.cur_speed * 100))
        self._speed_slider.setTickInterval(25)
        self._speed_lbl = QLabel(f"{self.cur_speed:.2f}×")
        self._speed_lbl.setAlignment(Qt.AlignCenter)
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_lbl.setText(f"{v/100:.2f}×"))
        sv2.addWidget(self._speed_slider)
        sv2.addWidget(self._speed_lbl)

        v.addWidget(fmt_grp)
        v.addWidget(sr_grp)
        v.addWidget(spd_grp)
        v.addStretch()
        return w

    # ── Results ────────────────────────────────────────────────────────────────
    def selected_model(self) -> str:
        return self._model_combo.currentData()

    def selected_voice(self) -> str:
        return self._voice_combo.currentText()

    def selected_speed(self) -> float:
        return self._speed_slider.value() / 100.0

    def selected_format(self) -> str:
        btn = self._fmt_bg.checkedButton()
        return btn.text().lower() if btn else "wav"

    def selected_sr(self) -> int:
        btn = self._sr_bg.checkedButton()
        return btn.property("sr_val") if btn else 24000


# ─────────────────────────────────────────────────────────────────────────────
# Chat area widget
# ─────────────────────────────────────────────────────────────────────────────
class ChatArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"background: {BG};")
        self._inner = QWidget()
        self._inner.setStyleSheet(f"background: {BG};")
        self._lay   = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(0, 8, 0, 8)
        self._lay.setSpacing(2)
        self._lay.addStretch()
        self.setWidget(self._inner)
        self._bubbles: dict[int, AIBubble] = {}

    def add_user(self, text: str, ts: str):
        w = UserBubble(text, ts)
        self._lay.addWidget(w)
        self._scroll_bottom()

    def add_ai(self, msg_id: int, bars: list[float], duration: str,
               audio_path: str) -> AIBubble:
        b = AIBubble(msg_id, bars, duration, audio_path)
        self._bubbles[msg_id] = b
        self._lay.addWidget(b)
        self._scroll_bottom()
        return b

    def add_loading(self) -> QLabel:
        lbl = QLabel("  ● Generating…")
        lbl.setStyleSheet(f"color: {DIM}; font-size: 12px; padding: 8px 16px;")
        self._lay.addWidget(lbl)
        self._scroll_bottom()
        return lbl

    def remove_widget(self, w: QWidget):
        self._lay.removeWidget(w)
        w.deleteLater()

    def _scroll_bottom(self):
        QTimer.singleShot(50, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()))

    def get_bubble(self, msg_id: int) -> AIBubble | None:
        return self._bubbles.get(msg_id)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kitten TTS")
        self.setMinimumSize(420, 700)
        self.resize(480, 820)

        self.engine        = TTSEngine()
        self.current_model = "nano_int8"
        self.current_voice = "Bella"
        self.current_speed = 1.0
        self.current_fmt   = "wav"
        self.current_sr    = 24000
        self._msg_counter  = 0
        self._tts_worker:  TTSWorker | None    = None
        self._load_worker: ModelLoadWorker | None = None
        self._player       = QMediaPlayer(self)
        self._active_bubble: AIBubble | None = None

        self._player.stateChanged.connect(self._player_state_changed)

        self._build_ui()
        QTimer.singleShot(200, self._load_model)

    # ── UI build ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # AppBar
        v.addWidget(self._build_appbar())

        # Status bar
        self._status_lbl = QLabel("Initialising…")
        self._status_lbl.setStyleSheet(f"""
            background: {BG}; color: {DIM}; font-size: 11px;
            padding: 2px 16px;
        """)
        v.addWidget(self._status_lbl)

        # Chat area
        self._chat = ChatArea()
        v.addWidget(self._chat, 1)

        # Input bar
        v.addWidget(self._build_input_bar())

    def _build_appbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background: {BG2};")
        bar.setFixedHeight(56)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 8, 0)

        icon_lbl = QLabel("🐱")
        icon_lbl.setStyleSheet("font-size: 22px;")
        title = QLabel("Kitten TTS")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT};")

        self._loading_lbl = QLabel("●")
        self._loading_lbl.setStyleSheet(f"color: {DIM}; font-size: 18px;")
        self._loading_lbl.setVisible(False)

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(38, 38)
        settings_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                           font-size: 18px; color: {DIM}; }}
            QPushButton:hover {{ color: {TEXT}; }}
        """)
        settings_btn.clicked.connect(self._open_settings)

        h.addWidget(icon_lbl)
        h.addWidget(title)
        h.addStretch()
        h.addWidget(self._loading_lbl)
        h.addWidget(settings_btn)
        return bar

    def _build_input_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background: {BG}; border-top: 1px solid {BG2};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 8, 12, 16)
        h.setSpacing(8)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Type text to synthesise…")
        self._input.setFixedHeight(54)
        self._input.setStyleSheet(f"""
            background: {BG2}; border: 1px solid {BG3};
            border-radius: 24px; padding: 10px 16px; color: {TEXT};
        """)
        self._input.installEventFilter(self)

        send_btn = QPushButton("➤")
        send_btn.setFixedSize(48, 48)
        send_btn.setStyleSheet(f"""
            QPushButton {{ background: {ACCENT}; border-radius: 24px; border: none;
                           font-size: 18px; color: white; }}
            QPushButton:hover {{ background: {ACC2}; }}
            QPushButton:disabled {{ background: {BG3}; color: {DIM}; }}
        """)
        send_btn.clicked.connect(self._send)
        self._send_btn = send_btn

        h.addWidget(self._input, 1)
        h.addWidget(send_btn)
        return bar

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if obj is self._input and event.type() == QEvent.KeyPress:
            from PyQt5.QtCore import Qt as _Qt
            if (event.key() == _Qt.Key_Return
                    and not (event.modifiers() & _Qt.ShiftModifier)):
                self._send()
                return True
        return super().eventFilter(obj, event)

    # ── Model loading ──────────────────────────────────────────────────────────
    def _load_model(self):
        if not model_is_ready(self.current_model):
            self._set_status(f"Model '{self.current_model}' not found — use Settings → Download", False)
            return
        self._set_status("Loading model…", True)
        self._load_worker = ModelLoadWorker(self.engine, self.current_model)
        self._load_worker.status.connect(lambda m: self._set_status(m, True))
        self._load_worker.done.connect(self._on_model_loaded)
        self._load_worker.start()

    def _on_model_loaded(self, ok: bool):
        name = AVAILABLE_MODELS.get(self.current_model, {}).get("name", self.current_model)
        self._set_status(f"✓ {name} ready" if ok else "❌ Failed to load model", False)

    # ── Send / generate ────────────────────────────────────────────────────────
    def _send(self):
        text = self._input.toPlainText().strip()
        if not text or self._tts_worker is not None:
            return
        self._input.clear()

        ts = datetime.now().strftime("%H:%M")
        self._chat.add_user(text, ts)

        loading = self._chat.add_loading()
        self._send_btn.setEnabled(False)
        self._set_status("Generating…", True)

        self._pending_loading = loading
        self._msg_counter += 1
        mid = self._msg_counter

        self._tts_worker = TTSWorker(self.engine, text,
                                     self.current_voice, self.current_speed)
        self._tts_worker.done.connect(
            lambda audio, path, dur, bars: self._on_tts_done(mid, audio, path, dur, bars))
        self._tts_worker.error.connect(self._on_tts_error)
        self._tts_worker.start()

    def _on_tts_done(self, mid: int, audio, wav_path: str, dur: str, bars: list):
        self._chat.remove_widget(self._pending_loading)
        bubble = self._chat.add_ai(mid, bars, dur, wav_path)
        bubble.play_requested.connect(self._play_msg)
        bubble.download_requested.connect(self._open_download)
        self._tts_worker = None
        self._send_btn.setEnabled(True)
        self._set_status("✓ Ready", False)

    def _on_tts_error(self, err: str):
        self._chat.remove_widget(self._pending_loading)
        self._chat.add_user(f"❌ {err}", "")
        self._tts_worker = None
        self._send_btn.setEnabled(True)
        self._set_status(f"Error: {err}", False)

    # ── Audio playback ─────────────────────────────────────────────────────────
    def _play_msg(self, mid: int):
        bubble = self._chat.get_bubble(mid)
        if not bubble:
            return
        path = bubble.audio_path
        if not path or not Path(path).exists():
            return
        if self._active_bubble:
            self._active_bubble.set_playing(False)
        self._active_bubble = bubble
        bubble.set_playing(True)
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self._player.play()

    def _player_state_changed(self, state):
        from PyQt5.QtMultimedia import QMediaPlayer as _MP
        if state == _MP.StoppedState and self._active_bubble:
            self._active_bubble.set_playing(False)
            self._active_bubble = None

    # ── Download dialog ────────────────────────────────────────────────────────
    def _open_download(self, mid: int):
        bubble = self._chat.get_bubble(mid)
        if not bubble:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Download Audio")
        dlg.setMinimumWidth(300)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Format:"))
        fmt_cb = QComboBox()
        for f in ["wav", "mp3", "ogg"]:
            fmt_cb.addItem(f.upper(), f)
        v.addWidget(fmt_cb)
        v.addWidget(QLabel("Sample rate:"))
        sr_cb = QComboBox()
        for sr, lbl in [(22050, "22 kHz"), (24000, "24 kHz"), (44100, "44.1 kHz")]:
            sr_cb.addItem(lbl, sr)
        sr_cb.setCurrentIndex(1)
        v.addWidget(sr_cb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec_() != QDialog.Accepted:
            return
        fmt = fmt_cb.currentData()
        sr  = sr_cb.currentData()
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Audio", f"kittentts_{mid}.{fmt}",
            f"Audio (*.{fmt})")
        if not save_path:
            return
        import soundfile as sf
        audio, orig_sr = sf.read(bubble.audio_path)
        if orig_sr != sr:
            audio = resample(audio, orig_sr, sr)
        save_audio(audio, save_path, sr, fmt)
        QMessageBox.information(self, "Saved", f"Saved to:\n{save_path}")

    # ── Settings ───────────────────────────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(
            self.engine, self.current_model, self.current_voice,
            self.current_speed, self.current_fmt, self)
        if dlg.exec_() == QDialog.Accepted:
            new_model = dlg.selected_model()
            if new_model != self.current_model:
                self.current_model = new_model
                threading.Thread(target=self._load_model, daemon=True).start()
            self.current_voice = dlg.selected_voice()
            self.current_speed = dlg.selected_speed()
            self.current_fmt   = dlg.selected_format()
            self.current_sr    = dlg.selected_sr()

    # ── Status ─────────────────────────────────────────────────────────────────
    def _set_status(self, msg: str, busy: bool):
        self._status_lbl.setText(f"  {msg}")
        self._loading_lbl.setVisible(busy)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Kitten TTS")
    apply_dark_palette(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
