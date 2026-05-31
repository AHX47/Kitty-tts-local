"""
Kitten TTS — Flet cross-platform app
Works on: Android APK · Windows · Linux · macOS · Web
"""
from __future__ import annotations
import os, sys, time, threading, tempfile, math, random
from pathlib import Path
from datetime import datetime

import flet as ft
import numpy as np

# ── resolve core package ──────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from core.tts_engine    import TTSEngine, AVAILABLE_MODELS, DEFAULT_VOICES
from core.voice_cloner  import extract_embedding, save_voice, load_all_custom_voices, delete_voice
from core.audio_utils   import save_audio, waveform_bars, duration_str as dur_str
from core.download_models import download_model, model_is_ready, MODELS_CONFIG

TEMP_DIR = Path(tempfile.gettempdir()) / "kittentts_flet"
TEMP_DIR.mkdir(exist_ok=True)

#ft.alignment.center = ft.alignment.Alignment.CENTER
#ft.alignment.center_left = ft.alignment.Alignment.CENTER_LEFT
#ft.alignment.center_right = ft.alignment.Alignment.CENTER_RIGHT
#ft.alignment.top_center = ft.alignment.Alignment.TOP_CENTER
#ft.alignment.bottom_left = ft.alignment.Alignment.BOTTOM_LEFT
#ft.alignment.bottom_right = ft.alignment.Alignment.BOTTOM_RIGHT
#ft.alignment.bottom_center = ft.alignment.Alignment.BOTTOM_CENTER
#ft.ImageFit = ft.BoxFit
#ft.colors = ft.Colors
#ft.icons = ft.Icons

# ─────────────────────────────────────────────────────────────────────────────
# Colour palette
# ─────────────────────────────────────────────────────────────────────────────
BG        = "#0f172a"
BG2       = "#1e293b"
BG3       = "#1f2937"
CARD      = "#1a2332"
ACCENT    = "#3b82f6"
ACCENT2   = "#60a5fa"
TEXT      = "#e2e8f0"
TEXT_DIM  = "#94a3b8"
MSG_USER  = "#334155"
DANGER    = "#ef4444"
SUCCESS   = "#22c55e"


# ─────────────────────────────────────────────────────────────────────────────
# Message data model
# ─────────────────────────────────────────────────────────────────────────────
class Message:
    _id = 0

    def __init__(self, text: str, role: str,
                 audio_path: str | None = None,
                 duration: str = "00:00",
                 bars: list[float] | None = None):
        Message._id += 1
        self.id          = Message._id
        self.text        = text
        self.role        = role            # "user" | "ai"
        self.audio_path  = audio_path
        self.duration    = duration
        self.bars        = bars or []
        self.ts          = datetime.now().strftime("%H:%M")
        self.expanded    = False


# ─────────────────────────────────────────────────────────────────────────────
# Waveform widget helper
# ─────────────────────────────────────────────────────────────────────────────
def _waveform_row(bars: list[float], playing: bool = False, n: int = 22) -> ft.Row:
    """Build a waveform bar row from energy values."""
    heights = [max(4, int(b * 30)) for b in (bars[:n] + [0.2] * n)[:n]]
    controls = []
    for h in heights:
        color = ACCENT2 if playing else ft.Colors.with_opacity(0.7, ACCENT2)
        controls.append(
            ft.Container(
                width=3, height=h,
                bgcolor=color,
                border_radius=2,
            )
        )
    return ft.Row(controls=controls, spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER)


# ─────────────────────────────────────────────────────────────────────────────
# Main Flet application
# ─────────────────────────────────────────────────────────────────────────────
def main(page: ft.Page):
    # ── Page setup ────────────────────────────────────────────────────────────
    page.title           = "Kitten TTS"
    page.theme_mode      = ft.ThemeMode.DARK
    page.bgcolor         = BG
    page.padding         = 0
    page.fonts           = {"Sora": "https://fonts.gstatic.com/s/sora/v12/xMQOuFFYT72X5wkB_18qmnndmSdSnn-KIwNhBti0.woff2"}
    page.theme           = ft.Theme(font_family="Sora")
    page.window_min_width  = 360
    page.window_min_height = 600
    page.window_width      = 420
    page.window_height     = 820

    # ── App state ─────────────────────────────────────────────────────────────
    engine          = TTSEngine()
    messages:  list[Message]  = []
    generating      = [False]
    current_model   = ["nano_int8"]
    current_voice   = ["Bella"]
    current_speed   = [1.0]
    current_fmt     = ["wav"]
    current_sr      = [24000]
    audio_controls: dict[int, ft.Audio] = {}   # msg.id → ft.Audio

    # ── Shared refs ───────────────────────────────────────────────────────────
    chat_list_ref    = ft.Ref[ft.ListView]()
    input_field_ref  = ft.Ref[ft.TextField]()
    status_bar_ref   = ft.Ref[ft.Text]()
    loading_ref      = ft.Ref[ft.ProgressRing]()
    page_container_ref = ft.Ref[ft.Container]()

    # ─────────────────────────────────────────────────────────────────────────
    # Audio playback
    # ─────────────────────────────────────────────────────────────────────────
    def play_audio(msg: Message):
        if not msg.audio_path or not Path(msg.audio_path).exists():
            return
        ctrl = audio_controls.get(msg.id)
        if ctrl is None:
            ctrl = ft.Audio(src=msg.audio_path, autoplay=True)
            audio_controls[msg.id] = ctrl
            page.overlay.append(ctrl)
            page.update()
        else:
            ctrl.play()
            page.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Message bubble builder
    # ─────────────────────────────────────────────────────────────────────────
    def build_user_bubble(msg: Message) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(msg.text, color=TEXT, size=14, selectable=True),
                    ft.Text(msg.ts,   color=TEXT_DIM, size=10),
                ],
                spacing=4, tight=True,
            ),
            bgcolor=MSG_USER,
            border_radius=ft.BorderRadius(14, 14, 2, 14),
            padding=ft.Padding(12, 10, 12, 8),
            margin=ft.Margin(60, 4, 8, 4),
        )

    def build_ai_bubble(msg: Message) -> ft.Container:
        """Compact audio bubble — expands on tap to full player."""
        expanded_ref = ft.Ref[ft.Column]()
        collapsed_ref = ft.Ref[ft.Row]()

        # ── collapsed row ──────────────────────────────────────────────────
        collapsed_row = ft.Row(
            ref=collapsed_ref,
            controls=[
                # Download button circle
                ft.Container(
                    content=ft.Icon(ft.Icons.DOWNLOAD, color=ft.Colors.WHITE, size=16),
                    width=32, height=32,
                    bgcolor=ACCENT,
                    border_radius=16,
                    on_click=lambda e: open_download_dialog(msg),
                    tooltip="Download",
                ),
                # Waveform
                ft.Container(
                    content=_waveform_row(msg.bars),
                    expand=True,
                ),
                # Duration
                ft.Text(msg.duration, color=ACCENT2, size=12, weight=ft.FontWeight.W_500),
                # Play chip
                ft.Container(
                    content=ft.Text("▶A", color=TEXT, size=11),
                    bgcolor=BG2,
                    border_radius=8,
                    padding=ft.Padding(6, 3, 6, 3),
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ── expanded player ────────────────────────────────────────────────
        speed_buttons = ft.Row(
            controls=[
                ft.TextButton(s, on_click=lambda e, v=s: None,
                              style=ft.ButtonStyle(color=TEXT_DIM, padding=4))
                for s in ["0.5×", "0.75×", "1×", "1.25×", "1.5×", "2×"]
            ],
            spacing=0,
        )

        expanded_col = ft.Column(
            ref=expanded_ref,
            visible=False,
            controls=[
                # Header
                ft.Row(controls=[
                    ft.Container(
                        content=ft.Icon(ft.Icons.AUDIO_FILE, color=ft.Colors.WHITE, size=16),
                        width=32, height=32, bgcolor=ACCENT, border_radius=16,
                    ),
                    ft.Text("Kitten TTS · Voice", color=TEXT_DIM, size=12, expand=True),
                    ft.IconButton(ft.Icons.CLOSE, icon_color=TEXT_DIM, icon_size=18,
                                  on_click=lambda e: toggle_expand(msg.id, False)),
                ], spacing=8),
                # Big waveform
                ft.Container(
                    content=_waveform_row(msg.bars, playing=True, n=30),
                    height=40,
                    alignment=ft.alignment.center,
                ),
                # Time row
                ft.Row(controls=[
                    ft.Text("00:00", color=TEXT_DIM, size=11),
                    ft.Container(expand=True),
                    ft.Text(msg.duration, color=TEXT_DIM, size=11),
                ]),
                # Playback controls
                ft.Row(
                    controls=[
                        ft.IconButton(ft.Icons.REPLAY_10, icon_color=TEXT, icon_size=26),
                        ft.Container(
                            content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED,
                                            color=ACCENT2, size=52),
                            on_click=lambda e: play_audio(msg),
                        ),
                        ft.IconButton(ft.Icons.FORWARD_10, icon_color=TEXT, icon_size=26),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, spacing=16,
                ),
                # Speed + download row
                ft.Row(controls=[
                    speed_buttons,
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.DOWNLOAD_ROUNDED, icon_color=ACCENT,
                                  tooltip="Download", on_click=lambda e: open_download_dialog(msg)),
                ]),
            ],
            spacing=10,
        )

        bubble_container = ft.Container(
            content=ft.Column(controls=[collapsed_row, expanded_col], spacing=6, tight=True),
            bgcolor=BG3,
            border_radius=ft.BorderRadius(14, 14, 14, 2),
            padding=ft.Padding(10, 10, 10, 10),
            margin=ft.Margin(8, 4, 60, 4),
            on_click=lambda e: toggle_expand(msg.id, True),
        )

        # Keep refs for later
        msg._collapsed_ref = collapsed_ref
        msg._expanded_ref  = expanded_ref
        msg._bubble        = bubble_container
        return bubble_container

    # ── expand / collapse helpers ──────────────────────────────────────────
    def toggle_expand(msg_id: int, to_expanded: bool):
        for m in messages:
            if m.id == msg_id:
                if m._collapsed_ref.current:
                    m._collapsed_ref.current.visible = not to_expanded
                if m._expanded_ref.current:
                    m._expanded_ref.current.visible  = to_expanded
                if to_expanded:
                    play_audio(m)
                page.update()
                break

    # ─────────────────────────────────────────────────────────────────────────
    # Download dialog
    # ─────────────────────────────────────────────────────────────────────────
    dl_fmt_dd  = ft.Dropdown(
        value="wav", width=110,
        options=[ft.dropdown.Option(f) for f in ["wav", "mp3", "ogg"]],
        bgcolor=BG2, color=TEXT, border_color=ACCENT,
    )
    dl_sr_dd   = ft.Dropdown(
        value="24000", width=130,
        options=[ft.dropdown.Option(s, f"{int(s)//1000}kHz")
                 for s in ["22050", "24000", "44100"]],
        bgcolor=BG2, color=TEXT, border_color=ACCENT,
    )
    _dl_msg: list[Message | None] = [None]

    def do_download(_):
        m = _dl_msg[0]
        if not m or not m.audio_path:
            return
        import soundfile as sf
        audio, sr = sf.read(m.audio_path)
        tgt_sr    = int(dl_sr_dd.value)
        from core.audio_utils import resample
        if sr != tgt_sr:
            audio = resample(audio, sr, tgt_sr)
        ext  = dl_fmt_dd.value
        path = str(TEMP_DIR / f"kittentts_{m.id}.{ext}")
        save_audio(audio, path, tgt_sr, ext)
        page.snack_bar = ft.SnackBar(ft.Text(f"Saved → {path}", color=TEXT), bgcolor=BG2)
        page.snack_bar.open = True
        download_dlg.open = False
        page.update()

    download_dlg = ft.AlertDialog(
        modal=True,
        bgcolor=BG2,
        title=ft.Text("Download Audio", color=TEXT, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            ft.Text("Format", color=TEXT_DIM, size=12),
            dl_fmt_dd,
            ft.Text("Sample rate", color=TEXT_DIM, size=12),
            dl_sr_dd,
        ], tight=True, spacing=8),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: close_dlg(download_dlg),
                          style=ft.ButtonStyle(color=TEXT_DIM)),
            ft.ElevatedButton("Download", bgcolor=ACCENT, color=ft.Colors.WHITE,
                              on_click=do_download),
        ],
    )

    def open_download_dialog(msg: Message):
        _dl_msg[0] = msg
        download_dlg.open = True
        page.dialog = download_dlg
        page.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Status helpers
    # ─────────────────────────────────────────────────────────────────────────
    def set_status(text: str, busy: bool = False):
        if status_bar_ref.current:
            status_bar_ref.current.value = text
        if loading_ref.current:
            loading_ref.current.visible = busy
        page.update()

    def close_dlg(dlg):
        dlg.open = False
        page.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Model loading
    # ─────────────────────────────────────────────────────────────────────────
    def load_current_model():
        key = current_model[0]
        if not model_is_ready(key):
            set_status(f"Model '{key}' not found — run download_models.py", False)
            return
        set_status("Loading model…", True)
        ok = engine.load_model(key, lambda m: set_status(m, True))
        set_status(f"✓ {AVAILABLE_MODELS[key]['name']} ready" if ok
                   else "❌ Failed to load model", False)

    # ─────────────────────────────────────────────────────────────────────────
    # Generate TTS
    # ─────────────────────────────────────────────────────────────────────────
    def send_message(e=None):
        tf = input_field_ref.current
        if tf is None:
            return
        text = tf.value.strip()
        if not text or generating[0]:
            return
        tf.value = ""
        page.update()

        # User bubble
        user_msg = Message(text, "user")
        messages.append(user_msg)
        chat_list_ref.current.controls.append(build_user_bubble(user_msg))
        page.update()
        scroll_chat()

        # Generate in thread
        generating[0] = True
        set_status("Generating speech…", True)
        _disable_input(True)

        def _gen():
            try:
                audio = engine.generate(text, current_voice[0], current_speed[0])
                wav_path = str(TEMP_DIR / f"kittentts_{user_msg.id}.wav")
                engine.save_wav(audio, wav_path)
                bars   = waveform_bars(audio)
                dur    = dur_str(audio)
                ai_msg = Message(text, "ai", wav_path, dur, bars)
                messages.append(ai_msg)
                chat_list_ref.current.controls.append(build_ai_bubble(ai_msg))
                set_status("✓ Ready", False)
            except Exception as ex:
                ai_msg = Message(f"Error: {ex}", "ai")
                messages.append(ai_msg)
                chat_list_ref.current.controls.append(build_user_bubble(ai_msg))
                set_status(f"❌ {ex}", False)
            finally:
                generating[0] = False
                _disable_input(False)
                scroll_chat()

        threading.Thread(target=_gen, daemon=True).start()

    def scroll_chat():
        if chat_list_ref.current:
            chat_list_ref.current.scroll_to(offset=-1, duration=300)
            page.update()

    def _disable_input(flag: bool):
        if input_field_ref.current:
            input_field_ref.current.disabled = flag
        page.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Voice Cloning Dialog
    # ─────────────────────────────────────────────────────────────────────────
    clone_name_field = ft.TextField(
        label="Voice name", bgcolor=BG2, color=TEXT,
        border_color=ACCENT, label_style=ft.TextStyle(color=TEXT_DIM),
        hint_text="e.g. My Arabic Voice",
    )
    clone_status = ft.Text("", color=TEXT_DIM, size=12)
    clone_progress = ft.ProgressRing(visible=False, color=ACCENT, width=24, height=24)
    _clone_audio_path: list[str | None] = [None]

    def _do_clone(_):
        path = _clone_audio_path[0]
        name = clone_name_field.value.strip()
        if not path or not name:
            clone_status.value = "⚠ Provide audio file + name"
            page.update()
            return
        clone_status.value = "Extracting voice embedding…"
        clone_progress.visible = True
        page.update()

        def _extract():
            try:
                emb = extract_embedding(path)
                save_voice(name, emb)
                engine.reload_custom_voices()
                _rebuild_voice_chips()
                clone_status.value = f"✓ Voice '{name}' saved!"
                clone_progress.visible = False
                page.update()
            except Exception as ex:
                clone_status.value = f"❌ {ex}"
                clone_progress.visible = False
                page.update()

        threading.Thread(target=_extract, daemon=True).start()

    def _pick_audio_for_clone(_):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.wav *.mp3 *.ogg *.flac")])
        root.destroy()
        if path:
            _clone_audio_path[0] = path
            clone_status.value = f"📁 {Path(path).name}"
            page.update()

    clone_dialog = ft.AlertDialog(
        modal=True, bgcolor=BG2,
        title=ft.Text("Clone a New Voice", color=TEXT, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            ft.Text("Record or upload a WAV sample (≥5s recommended)", color=TEXT_DIM, size=12),
            ft.ElevatedButton(
                "📁 Choose Audio File", bgcolor=BG3, color=TEXT,
                on_click=_pick_audio_for_clone,
            ),
            clone_name_field,
            ft.Row([clone_progress, clone_status]),
        ], tight=True, spacing=12, width=300),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: close_dlg(clone_dialog),
                          style=ft.ButtonStyle(color=TEXT_DIM)),
            ft.ElevatedButton("Extract & Save", bgcolor=ACCENT, color=ft.Colors.WHITE,
                              on_click=_do_clone),
        ],
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Download model dialog
    # ─────────────────────────────────────────────────────────────────────────
    dl_model_status = ft.Text("", color=TEXT_DIM, size=12)
    dl_model_prog   = ft.ProgressRing(visible=False, color=ACCENT, width=24, height=24)
    _dl_model_key: list[str] = ["nano_int8"]

    def _start_model_download(key: str):
        _dl_model_key[0] = key
        dl_model_status.value = f"Downloading {key}…"
        dl_model_prog.visible = True
        page.update()

        def _dl():
            ok = download_model(key, lambda m: (
                dl_model_status.__setattr__("value", m),
                page.update()
            ))
            dl_model_prog.visible = False
            dl_model_status.value = "✓ Download complete!" if ok else "❌ Download failed"
            page.update()

        threading.Thread(target=_dl, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Settings page
    # ─────────────────────────────────────────────────────────────────────────
    voice_chip_row_ref = ft.Ref[ft.Row]()

    def _rebuild_voice_chips():
        """Refresh voice chips after new voice added."""
        row = voice_chip_row_ref.current
        if not row:
            return
        row.controls.clear()
        for v in engine.all_voices():
            is_sel = v == current_voice[0]
            row.controls.append(
                ft.Container(
                    content=ft.Text(v, color=ft.Colors.WHITE if is_sel else TEXT_DIM, size=12),
                    bgcolor=ACCENT if is_sel else BG3,
                    border_radius=16,
                    padding=ft.Padding(10, 5, 10, 5),
                    on_click=lambda e, voice=v: _select_voice(voice),
                )
            )
        page.update()

    def _select_voice(voice: str):
        current_voice[0] = voice
        _rebuild_voice_chips()

    # Model cards
    def _model_card(key: str) -> ft.Container:
        info   = AVAILABLE_MODELS[key]
        ready  = model_is_ready(key)
        is_sel = key == current_model[0]
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(info["name"], color=TEXT, size=14, weight=ft.FontWeight.W_600),
                    ft.Text(info["size"], color=TEXT_DIM, size=11),
                    ft.Text("✓ Ready" if ready else "Not downloaded",
                            color=SUCCESS if ready else TEXT_DIM, size=11),
                ], spacing=2, expand=True),
                ft.Column([
                    ft.ElevatedButton(
                        "Select" if not is_sel else "Active",
                        bgcolor=ACCENT if not is_sel else SUCCESS,
                        color=ft.Colors.WHITE,
                        height=32,
                        on_click=lambda e, k=key: _switch_model(k),
                        disabled=is_sel,
                    ),
                    ft.TextButton(
                        "Download" if not ready else "Re-DL",
                        style=ft.ButtonStyle(color=ACCENT),
                        on_click=lambda e, k=key: _start_model_download(k),
                    ),
                ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.END),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=ACCENT if is_sel else BG3,
            border=ft.border.all(1, ACCENT if is_sel else BG2),
            border_radius=12,
            padding=12,
            margin=ft.Margin(0, 4, 0, 4),
        )

    def _switch_model(key: str):
        current_model[0] = key
        settings_models_col.controls = [_model_card(k) for k in AVAILABLE_MODELS]
        threading.Thread(target=load_current_model, daemon=True).start()
        page.update()

    # Speed radio
    speed_rg = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(value=str(v), label=f"{v}×",
                     fill_color={ft.ControlState.SELECTED: ACCENT})
            for v in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        ]),
        value="1.0",
        on_change=lambda e: current_speed.__setitem__(0, float(e.control.value)),
    )

    # Export format
    fmt_rg = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(value=f, label=f.upper(),
                     fill_color={ft.ControlState.SELECTED: ACCENT})
            for f in ["wav", "mp3", "ogg"]
        ]),
        value="wav",
        on_change=lambda e: current_fmt.__setitem__(0, e.control.value),
    )

    settings_models_col = ft.Column(
        controls=[_model_card(k) for k in AVAILABLE_MODELS],
        spacing=0,
    )
    def _section_header(title: str) -> ft.Text:
        return ft.Text(title, color=ACCENT2, size=13,
                       weight=ft.FontWeight.W_600,
                       style=ft.TextStyle(letter_spacing=0.5))

    settings_page = ft.Container(
        visible=False,
        expand=True,
        bgcolor=BG,
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=[
                # Header
                ft.Container(
                    content=ft.Row([
                        ft.IconButton(ft.Icons.ARROW_BACK, icon_color=TEXT,
                                      on_click=lambda e: _show_chat()),
                        ft.Text("Settings", color=TEXT, size=20, weight=ft.FontWeight.BOLD),
                    ]),
                    bgcolor=BG2, padding=ft.Padding(8, 12, 8, 12),
                ),
            
                ft.Container(
                    padding=ft.Padding(16, 12, 16, 80),
                    content=ft.Column([
                        # ── Model selection ────────────────────────────────
                        _section_header("Model Selection"),
                        settings_models_col,
                        ft.Row([dl_model_prog, dl_model_status]),

                        ft.Divider(color=BG2, height=24),

                        # ── Voice selection ────────────────────────────────
                        _section_header("Voice"),
                        ft.Row(
                            ref=voice_chip_row_ref,
                            wrap=True,
                            spacing=8, run_spacing=8,
                        ),
                        ft.ElevatedButton(
                            "＋ Clone New Voice",
                            bgcolor=ACCENT, color=ft.Colors.WHITE,
                            icon=ft.Icons.GRAPHIC_EQ,
                            on_click=lambda e: _open_clone(),
                        ),
                        ft.ElevatedButton(
                            "↻ Refresh Voices",
                            bgcolor=BG3, color=TEXT,
                            on_click=lambda e: (_refresh_voices()),
                        ),

                        ft.Divider(color=BG2, height=24),

                        # ── Speed ──────────────────────────────────────────
                        _section_header("Speech Speed"),
                        speed_rg,

                        ft.Divider(color=BG2, height=24),

                        # ── Export format ──────────────────────────────────
                        _section_header("Export Format"),
                        fmt_rg,
                    ], spacing=8),
                ),
            ],
        ),
    )

    
    def _refresh_voices():
        engine.reload_custom_voices()
        _rebuild_voice_chips()

    def _open_clone():
        clone_name_field.value = ""
        clone_status.value     = ""
        clone_progress.visible = False
        _clone_audio_path[0]   = None
        clone_dialog.open      = True
        page.dialog            = clone_dialog
        page.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Chat page
    # ─────────────────────────────────────────────────────────────────────────
    # App-bar
    app_bar = ft.Container(
        content=ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.RECORD_VOICE_OVER, color=ACCENT, size=22),
                ft.Text("Kitten TTS", color=TEXT, size=18, weight=ft.FontWeight.BOLD),
            ], spacing=8),
            ft.Row([
                ft.Container(
                    ref=loading_ref,
                    visible=False,
                    content=ft.ProgressRing(color=ACCENT, width=18, height=18, stroke_width=2),
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS_OUTLINED, icon_color=TEXT,
                    on_click=lambda e: _show_settings(),
                ),
            ], spacing=0),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        bgcolor=BG2,
        padding=ft.Padding(16, 12, 8, 12),
    )

    # Status bar
    status_bar = ft.Container(
        content=ft.Text(ref=status_bar_ref, value="Loading model…",
                        color=TEXT_DIM, size=11),
        bgcolor=BG,
        padding=ft.Padding(16, 4, 16, 4),
    )

    # Chat list
    chat_list = ft.ListView(
        ref=chat_list_ref,
        expand=True,
        spacing=2,
        padding=ft.Padding(0, 8, 0, 8),
        auto_scroll=True,
    )

    # Welcome message
    def _add_welcome():
        wc = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.RECORD_VOICE_OVER, color=ACCENT, size=40),
                ft.Text("Kitten TTS", color=TEXT, size=22, weight=ft.FontWeight.BOLD),
                ft.Text("Type text below and press Send to synthesise speech.\n"
                        "Tap ⚙ to change model, voice, or clone a custom voice.",
                        color=TEXT_DIM, size=13, text_align=ft.TextAlign.CENTER),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            alignment=ft.alignment.center,
            padding=40,
        )
        chat_list.controls.append(wc)

    _add_welcome()

    # Input bar
    input_bar = ft.Container(
        content=ft.Row([
            ft.TextField(
                ref=input_field_ref,
                hint_text="Type text or press mic to record…",
                hint_style=ft.TextStyle(color=TEXT_DIM),
                bgcolor=BG2, color=TEXT,
                border_color=ft.Colors.TRANSPARENT,
                focused_border_color=ACCENT,
                border_radius=24,
                multiline=True,
                max_lines=4,
                min_lines=1,
                expand=True,
                content_padding=ft.Padding(16, 10, 16, 10),
                on_submit=send_message,
            ),
            ft.IconButton(
                ft.Icons.SEND_ROUNDED,
                icon_color=ACCENT, icon_size=28,
                tooltip="Generate speech",
                on_click=send_message,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    bgcolor={ft.ControlState.DEFAULT: BG2},
                ),
            ),
        ], spacing=8),
        bgcolor=BG,
        padding=ft.Padding(12, 8, 12, 16),
    )

    chat_page = ft.Container(
        visible=True,
        expand=True,
        bgcolor=BG,
        content=ft.Column([
            app_bar,
            status_bar,
            chat_list,
            input_bar,
        ], spacing=0, expand=True),
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Navigation helpers
    # ─────────────────────────────────────────────────────────────────────────
    def _show_settings():
        _rebuild_voice_chips()
        settings_models_col.controls = [_model_card(k) for k in AVAILABLE_MODELS]
        chat_page.visible     = False
        settings_page.visible = True
        page.update()

    def _show_chat():
        settings_page.visible = False
        chat_page.visible     = True
        page.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Page assembly
    # ─────────────────────────────────────────────────────────────────────────
    page.add(
        ft.Stack(
            controls=[chat_page, settings_page],
            expand=True,
        )
    )

    # Kick off model load
    threading.Thread(target=load_current_model, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
