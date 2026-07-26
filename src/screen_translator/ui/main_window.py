"""Main application window and high-level UI orchestration."""

from __future__ import annotations

import csv
import ctypes
import io
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from mss import MSS
from PIL import Image
from PySide6.QtCore import QEvent, QRect, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QLabel,
    QMenu,
    QMainWindow,
    QMessageBox,
    QFormLayout,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..audio_capture import AudioCaptureError, list_audio_devices
from ..capture import CaptureOverlay, MultiRegionOverlay
from ..audio_translation import AudioTranslationWorker
from ..config import AppSettings, load_settings, save_settings
from ..hotkeys import GlobalHotkeyFilter
from ..models import MonitorRegion
from ..screen_capture import mask_excluded_regions
from ..workers import TranslationWorker
from .monitor import MonitorSetupDialog
from .results import MonitorResultWindow
from .audio_results import AudioTranslationWindow
from .components import ActionButton, SectionCard, SliderRow, StatusBadge
from .settings import SettingsDialog
from .styles import MAIN_STYLE_SHEET


HOTKEY_IDS = {
    "capture": 0x53435254,
    "monitor": 0x53435255,
    "audio": 0x53435256,
}


AUDIO_LANGUAGE_LABELS = {
    "auto": "自动检测",
    "zh": "中文",
    "yue": "粤语",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "de": "德语",
    "fr": "法语",
    "ru": "俄语",
    "es": "西班牙语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "id": "印尼语",
    "ar": "阿拉伯语",
    "th": "泰语",
    "hi": "印地语",
    "da": "丹麦语",
    "ur": "乌尔都语",
    "tr": "土耳其语",
    "nl": "荷兰语",
    "ms": "马来语",
    "vi": "越南语",
}
AUDIO_SOURCE_LANGUAGES = (
    "auto", "zh", "en", "ja", "ko", "yue", "de", "fr", "ru", "es",
    "it", "pt", "id", "ar", "th",
)
AUDIO_TARGET_LANGUAGES = {
    "zh": ("en", "ja", "ko", "fr", "de", "es", "ru", "it"),
    "yue": ("zh", "en"),
    "en": ("zh", "ja", "ko", "pt", "fr", "de", "ru", "vi", "es", "nl", "da", "ar", "it", "hi", "yue", "tr", "ms", "ur", "id"),
    "ja": ("th", "en", "zh", "vi", "fr", "it", "de", "es"),
    "ko": ("th", "en", "zh", "vi", "fr", "es", "ru", "de"),
    "fr": ("th", "en", "ja", "zh", "vi", "de", "it", "es", "ru", "pt"),
    "de": ("th", "en", "ja", "zh", "fr", "vi", "ru", "es", "it", "pt"),
    "es": ("th", "en", "ja", "zh", "fr", "vi", "it", "de", "ru", "pt"),
    "ru": ("th", "en", "ja", "zh", "fr", "vi", "de", "es", "it", "yue", "pt"),
    "it": ("th", "en", "ja", "zh", "fr", "vi", "es", "ru", "de"),
    "pt": ("en",),
    "id": ("en",),
    "ar": ("en",),
    "th": ("ja", "vi", "fr"),
    "hi": ("en",),
    "da": ("en",),
    "ur": ("en",),
    "tr": ("en",),
    "nl": ("en",),
    "ms": ("en",),
    "vi": ("ja", "fr"),
}

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.worker: TranslationWorker | None = None
        self.audio_worker: AudioTranslationWorker | None = None
        self._audio_stop_requested = False
        self.monitor_workers: dict[tuple[int, int], TranslationWorker] = {}
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.monitor_tick)
        self.monitor_active = False
        self.monitor_screen = None
        self.monitor_regions: list[MonitorRegion] = []
        self.monitor_interval_ms = 2000
        self.monitor_generation = 0
        self.monitor_editing = False
        self.monitor_edit_previous_lock = False
        self.capture_active = False
        self.hotkey_filters: dict[str, GlobalHotkeyFilter] = {}
        self._quitting = False
        self.audio_result_window = AudioTranslationWindow()
        self.audio_result_window.stop_requested.connect(self.stop_audio_translation)
        self.audio_result_window.lock_changed.connect(self.sync_audio_lock_button)
        self.setWindowTitle("Screen Translator")
        self.setWindowIcon(self.tray_icon())
        self.setMinimumSize(900, 600)
        self.resize(1040, 680)

        self.start_button = ActionButton("截图翻译", role="primary")
        self.start_button.clicked.connect(self.start_capture)
        self.settings_button = ActionButton("设置中心", role="settings")
        self.settings_button.clicked.connect(self.open_settings)
        self.monitor_button = ActionButton("开始持续监控")
        self.monitor_button.clicked.connect(self.start_monitor)
        self.audio_button = ActionButton("开始音频翻译")
        self.audio_button.clicked.connect(self.start_audio_translation)
        self.overlay_lock_button = ActionButton("锁定翻译窗口")
        self.overlay_lock_button.setEnabled(False)
        self.overlay_lock_button.clicked.connect(self.toggle_overlay_lock)
        self.manage_regions_button = ActionButton("管理监控区域")
        self.manage_regions_button.setEnabled(False)
        self.manage_regions_button.clicked.connect(self.manage_monitor_regions)
        self.monitor_result_window = MonitorResultWindow()
        self.monitor_result_window.stop_requested.connect(self.stop_monitor)
        self.monitor_result_window.lock_changed.connect(self.sync_overlay_lock_button)
        self.background_opacity_row = SliderRow(
            "窗口背景", 0, 100, max(0, min(100, self.settings.overlay_opacity))
        )
        self.background_opacity_slider = self.background_opacity_row.slider
        self.background_opacity_value_label = self.background_opacity_row.value_label
        self.background_opacity_slider.valueChanged.connect(self.set_overlay_opacity)

        self.text_opacity_row = SliderRow(
            "翻译文字", 30, 100, max(30, min(100, self.settings.overlay_text_opacity))
        )
        self.text_opacity_slider = self.text_opacity_row.slider
        self.text_opacity_value_label = self.text_opacity_row.value_label
        self.text_opacity_slider.valueChanged.connect(self.set_overlay_text_opacity)

        self.mask_opacity_row = SliderRow(
            "文字蒙版", 0, 100, max(0, min(100, self.settings.overlay_mask_opacity))
        )
        self.mask_opacity_slider = self.mask_opacity_row.slider
        self.mask_opacity_value_label = self.mask_opacity_row.value_label
        self.mask_opacity_slider.valueChanged.connect(self.set_overlay_mask_opacity)

        self.font_size_row = SliderRow(
            "翻译字号", 9, 28, max(9, min(28, self.settings.overlay_font_size)), " pt"
        )
        self.font_size_slider = self.font_size_row.slider
        self.font_size_value_label = self.font_size_row.value_label
        self.font_size_slider.valueChanged.connect(self.set_overlay_font_size)

        self.audio_lock_button = ActionButton("锁定音频窗口")
        self.audio_lock_button.setEnabled(False)
        self.audio_lock_button.clicked.connect(self.toggle_audio_lock)

        self.audio_mode_combo = QComboBox()
        self.audio_mode_combo.addItem("系统全局声音", "global")
        self.audio_mode_combo.addItem("指定进程（含子进程）", "process")
        self.audio_mode_combo.addItem("麦克风", "microphone")
        mode_index = self.audio_mode_combo.findData(self.settings.audio_source_mode)
        self.audio_mode_combo.setCurrentIndex(max(0, mode_index))

        self.audio_device_combo = QComboBox()
        self.audio_device_combo.addItem("默认设备", -1)
        try:
            for device in list_audio_devices():
                self.audio_device_combo.addItem(
                    f"[{device.kind}] {device.name}", device.index
                )
        except AudioCaptureError:
            self.audio_device_combo.setToolTip(
                "Install audio dependencies to select devices"
            )
        device_index = self.audio_device_combo.findData(self.settings.audio_device_id)
        if device_index >= 0:
            self.audio_device_combo.setCurrentIndex(device_index)

        self.audio_process_combo = QComboBox()
        self.audio_process_combo.addItem("请选择应用进程", 0)
        for process_id, process_name in self._list_application_processes():
            self.audio_process_combo.addItem(
                f"{process_name} (PID {process_id})", process_id
            )
        process_index = self.audio_process_combo.findData(self.settings.audio_process_id)
        if process_index >= 0:
            self.audio_process_combo.setCurrentIndex(process_index)
        self.audio_process_refresh_button = QPushButton("刷新应用列表")
        self.audio_process_refresh_button.clicked.connect(
            self.refresh_audio_processes
        )
        self.audio_children_check = QCheckBox("包含目标进程的子进程")
        self.audio_children_check.setChecked(self.settings.audio_include_children)
        self.audio_mode_combo.currentIndexChanged.connect(
            self._sync_audio_source_fields
        )
        self.audio_device_combo.currentIndexChanged.connect(
            self._audio_device_changed
        )
        self.audio_process_combo.currentIndexChanged.connect(
            self._audio_process_changed
        )
        self.audio_children_check.toggled.connect(self._audio_children_changed)

        self.audio_source_language_combo = QComboBox()
        for code in AUDIO_SOURCE_LANGUAGES:
            self.audio_source_language_combo.addItem(
                AUDIO_LANGUAGE_LABELS[code], code
            )
        source_index = self.audio_source_language_combo.findData(
            self.settings.audio_source_language
        )
        self.audio_source_language_combo.setCurrentIndex(
            source_index if source_index >= 0 else 0
        )
        self.audio_target_language_combo = QComboBox()
        self._populate_audio_target_languages(
            self.settings.audio_source_language,
            self.settings.audio_target_language,
        )
        self.audio_source_language_combo.currentIndexChanged.connect(
            self._audio_source_language_changed
        )
        self.audio_target_language_combo.currentIndexChanged.connect(
            self._audio_target_language_changed
        )
        language_row = QWidget()
        language_layout = QHBoxLayout(language_row)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setSpacing(8)
        language_layout.addWidget(QLabel("输入语言"))
        language_layout.addWidget(self.audio_source_language_combo, 1)
        language_layout.addWidget(QLabel("输出语言"))
        language_layout.addWidget(self.audio_target_language_combo, 1)
        self.audio_language_row = language_row

        self.audio_background_row = SliderRow(
            "主背景", 0, 100, max(0, min(100, self.settings.audio_background_opacity))
        )
        self.audio_background_opacity_slider = self.audio_background_row.slider
        self.audio_background_opacity_value_label = self.audio_background_row.value_label
        self.audio_background_opacity_slider.valueChanged.connect(self.set_audio_background_opacity)

        self.audio_text_row = SliderRow(
            "当前文字", 30, 100, max(30, min(100, self.settings.audio_text_opacity))
        )
        self.audio_text_opacity_slider = self.audio_text_row.slider
        self.audio_text_opacity_value_label = self.audio_text_row.value_label
        self.audio_text_opacity_slider.valueChanged.connect(self.set_audio_text_opacity)

        self.audio_history_text_row = SliderRow(
            "历史文字", 30, 100, max(30, min(100, self.settings.audio_history_text_opacity))
        )
        self.audio_history_text_opacity_slider = self.audio_history_text_row.slider
        self.audio_history_text_opacity_value_label = self.audio_history_text_row.value_label
        self.audio_history_text_opacity_slider.valueChanged.connect(
            self.set_audio_history_text_opacity
        )

        self.audio_show_original_checkbox = QCheckBox("显示当前翻译原文")
        self.audio_show_original_checkbox.setChecked(
            bool(self.settings.audio_show_original)
        )
        self.audio_show_original_checkbox.toggled.connect(
            self.set_audio_show_original
        )

        self.audio_font_scale_row = SliderRow(
            "字体缩放", 50, 400, max(50, min(400, self.settings.audio_font_scale))
        )
        self.audio_font_scale_slider = self.audio_font_scale_row.slider
        self.audio_font_scale_slider.valueChanged.connect(
            self.set_audio_font_scale
        )

        self.audio_mask_row = SliderRow(
            "文字蒙版", 0, 100, max(0, min(100, self.settings.audio_mask_opacity))
        )
        self.audio_mask_opacity_slider = self.audio_mask_row.slider
        self.audio_mask_opacity_value_label = self.audio_mask_row.value_label
        self.audio_mask_opacity_slider.valueChanged.connect(self.set_audio_mask_opacity)

        self.monitor_result_window.set_background_opacity(
            self.background_opacity_slider.value()
        )
        self.monitor_result_window.set_text_opacity(self.text_opacity_slider.value())
        self.monitor_result_window.set_mask_opacity(self.mask_opacity_slider.value())
        self.monitor_result_window.set_translation_font_size(self.font_size_slider.value())

        self.status_label = StatusBadge("准备就绪")
        self.original_edit = QPlainTextEdit()
        self.original_edit.setReadOnly(True)
        self.original_edit.setPlaceholderText("OCR 识别出的英文会显示在这里")
        self.translated_edit = QPlainTextEdit()
        self.translated_edit.setReadOnly(True)
        self.translated_edit.setPlaceholderText("中文翻译会显示在这里")

        body = QWidget()
        body.setObjectName("mainRoot")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(14)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(18, 14, 18, 14)
        brand = QVBoxLayout()
        brand.setSpacing(1)
        brand_title = QLabel("Screen Translator")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("屏幕、字幕与声音的即时翻译工作台")
        brand_subtitle.setObjectName("brandSubtitle")
        brand.addWidget(brand_title)
        brand.addWidget(brand_subtitle)
        brand_mark = QLabel()
        brand_mark.setObjectName("brandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(34, 34)
        brand_mark.setPixmap(self.tray_icon().pixmap(28, 28))
        top_bar_layout.addWidget(brand_mark)
        top_bar_layout.addSpacing(10)
        top_bar_layout.addLayout(brand, 1)
        top_bar_layout.addWidget(self.settings_button)
        top_bar_layout.addWidget(self.status_label)
        layout.addWidget(top_bar)

        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")
        self.main_tabs.setDocumentMode(True)

        capture_page = QWidget()
        capture_layout = QVBoxLayout(capture_page)
        capture_layout.setContentsMargins(4, 16, 4, 4)
        capture_layout.setSpacing(12)
        capture_intro = SectionCard(
            "截图翻译",
            "框选屏幕上的文字区域，完成 OCR 识别与在线翻译。",
            object_name="heroCard",
        )
        capture_intro.add_widget(self.start_button)
        capture_hint = QLabel("快捷键：按下全局热键后直接框选区域，截图不会自动保存。")
        capture_hint.setObjectName("hintLabel")
        capture_intro.add_widget(capture_hint)
        capture_layout.addWidget(capture_intro)

        original_box = SectionCard("识别文本", "Tesseract OCR 识别出的原文")
        original_box.add_widget(self.original_edit, 1)
        translated_box = SectionCard("翻译结果", "在线翻译接口返回的译文")
        translated_box.add_widget(self.translated_edit, 1)
        result_splitter = QSplitter(Qt.Orientation.Vertical)
        result_splitter.setObjectName("resultSplitter")
        result_splitter.addWidget(original_box)
        result_splitter.addWidget(translated_box)
        result_splitter.setSizes([210, 290])
        capture_layout.addWidget(result_splitter, 1)
        self.main_tabs.addTab(capture_page, "截图翻译")

        monitor_page = QWidget()
        monitor_layout = QHBoxLayout(monitor_page)
        monitor_layout.setContentsMargins(4, 16, 4, 4)
        monitor_layout.setSpacing(12)
        monitor_control = SectionCard(
            "持续监控",
            "检测指定区域的文字变化，并自动更新翻译浮窗。",
            object_name="heroCard",
        )
        monitor_control.setMinimumWidth(280)
        monitor_control.add_widget(self.monitor_button)
        monitor_control.add_widget(self.manage_regions_button)
        monitor_control.add_widget(self.overlay_lock_button)
        monitor_note = QLabel("运行后可以重新编辑监控区域，浮窗支持拖动、缩放和锁定。")
        monitor_note.setObjectName("hintLabel")
        monitor_note.setWordWrap(True)
        monitor_control.add_widget(monitor_note)
        monitor_layout.addWidget(monitor_control)
        monitor_appearance = SectionCard(
            "持续翻译窗口外观",
            "调节会即时作用于置顶翻译浮窗。",
        )
        monitor_appearance.add_widget(self.background_opacity_row)
        monitor_appearance.add_widget(self.text_opacity_row)
        monitor_appearance.add_widget(self.mask_opacity_row)
        monitor_appearance.add_widget(self.font_size_row)
        monitor_layout.addWidget(monitor_appearance, 1)
        self.main_tabs.addTab(monitor_page, "持续监控")

        audio_page = QWidget()
        audio_layout = QHBoxLayout(audio_page)
        audio_layout.setContentsMargins(4, 16, 4, 4)
        audio_layout.setSpacing(12)
        audio_control = SectionCard(
            "音频实时翻译",
            "监听系统声音、指定进程或麦克风，并实时显示翻译。",
            object_name="heroCard",
        )
        audio_control.setMinimumWidth(280)
        audio_source_form = QFormLayout()
        audio_source_form.setContentsMargins(0, 0, 0, 0)
        audio_source_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        audio_source_form.addRow("监听模式", self.audio_mode_combo)
        audio_source_form.addRow("音频设备", self.audio_device_combo)
        audio_source_form.addRow("应用进程", self.audio_process_combo)
        audio_source_form.addRow("", self.audio_process_refresh_button)
        audio_control.add_layout(audio_source_form)
        audio_control.add_widget(self.audio_children_check)
        audio_control.add_widget(self.audio_button)
        audio_control.add_widget(self.audio_lock_button)
        audio_note = QLabel("API Key、VAD 和历史记录数量仍在“设置中心”调整。")
        audio_note.setObjectName("hintLabel")
        audio_note.setWordWrap(True)
        audio_control.add_widget(audio_note)
        audio_layout.addWidget(audio_control)
        audio_appearance = SectionCard(
            "音频翻译窗口外观",
            "当前句子和历史记录的透明度可以独立调整。",
        )
        audio_appearance.add_widget(self.audio_language_row)
        audio_appearance.add_widget(self.audio_background_row)
        audio_appearance.add_widget(self.audio_text_row)
        audio_appearance.add_widget(self.audio_history_text_row)
        audio_appearance.add_widget(self.audio_show_original_checkbox)
        audio_appearance.add_widget(self.audio_font_scale_row)
        audio_appearance.add_widget(self.audio_mask_row)
        audio_layout.addWidget(audio_appearance, 1)
        self.main_tabs.addTab(audio_page, "音频翻译")

        layout.addWidget(self.main_tabs, 1)
        self.setCentralWidget(body)
        self.setStyleSheet(MAIN_STYLE_SHEET)
        self._sync_audio_source_fields()
        self.setup_tray()

        try:
            self.register_hotkeys()
        except (RuntimeError, ValueError) as exc:
            self.status_label.setText(f"热键不可用：{exc}")

    @staticmethod
    def tray_icon() -> QIcon:
        """Load the shared brand mark, with a code-only fallback for dev runs."""
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "screen_translator.ico"
        if icon_path.is_file():
            return QIcon(str(icon_path))

        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#177d9d"))
        painter.setPen(QColor("#75e3f5"))
        painter.drawRoundedRect(3, 3, 26, 26, 8, 8)
        painter.setPen(QColor("#081018"))
        painter.drawLine(9, 11, 23, 11)
        painter.drawLine(9, 16, 20, 16)
        painter.drawLine(9, 21, 17, 21)
        painter.end()
        return QIcon(pixmap)

    def setup_tray(self) -> None:
        self.tray_icon_widget = QSystemTrayIcon(self)
        self.tray_icon_widget.setIcon(self.tray_icon())
        self.tray_icon_widget.setToolTip("Screen Translator")
        menu = QMenu(self)
        self.tray_show_action = QAction("打开主窗口", self)
        self.tray_show_action.triggered.connect(self.show_from_tray)
        self.tray_capture_action = QAction("截图翻译", self)
        self.tray_capture_action.triggered.connect(self.start_capture_from_tray)
        self.tray_monitor_action = QAction("开始持续监控", self)
        self.tray_monitor_action.triggered.connect(self.toggle_monitor_from_tray)
        self.tray_audio_action = QAction("开始音频翻译", self)
        self.tray_audio_action.triggered.connect(self.toggle_audio_from_tray)
        self.tray_quit_action = QAction("退出程序", self)
        self.tray_quit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(self.tray_show_action)
        menu.addSeparator()
        menu.addAction(self.tray_capture_action)
        menu.addAction(self.tray_monitor_action)
        menu.addAction(self.tray_audio_action)
        menu.addSeparator()
        menu.addAction(self.tray_quit_action)
        self.tray_icon_widget.setContextMenu(menu)
        self.tray_icon_widget.activated.connect(self.handle_tray_activation)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon_widget.show()
        self.sync_tray_actions()

    def handle_tray_activation(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_from_tray()

    def sync_tray_actions(self) -> None:
        if not hasattr(self, "tray_monitor_action"):
            return
        self.tray_monitor_action.setText(
            "停止持续监控" if self.monitor_active else "开始持续监控"
        )
        self.tray_audio_action.setText(
            "停止音频翻译"
            if self.audio_worker is not None
            else "开始音频翻译"
        )

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()

    def start_capture_from_tray(self) -> None:
        self.show_from_tray()
        self.main_tabs.setCurrentIndex(0)
        QTimer.singleShot(0, self.start_capture)

    def toggle_monitor_from_tray(self) -> None:
        self.show_from_tray()
        self.main_tabs.setCurrentIndex(1)
        QTimer.singleShot(0, self.start_monitor)

    def toggle_audio_from_tray(self) -> None:
        self.show_from_tray()
        self.main_tabs.setCurrentIndex(2)
        QTimer.singleShot(0, self.start_audio_translation)

    def quit_from_tray(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.stop_monitor()
        self.stop_translation_workers(wait=True)
        self.stop_audio_translation(wait=True)
        self.audio_result_window.close()
        self.monitor_result_window.close()
        self.unregister_hotkeys()
        self.tray_icon_widget.hide()
        self.close()
        QApplication.quit()

    def stop_translation_workers(self, wait: bool = False) -> None:
        """Stop OCR/translation threads before the application is destroyed."""
        workers: list[TranslationWorker] = []
        if self.worker is not None:
            workers.append(self.worker)
        workers.extend(self.monitor_workers.values())

        unique_workers: list[TranslationWorker] = []
        seen: set[int] = set()
        for worker in workers:
            if id(worker) not in seen:
                seen.add(id(worker))
                unique_workers.append(worker)

        for worker in unique_workers:
            try:
                if worker.isRunning():
                    worker.stop()
            except RuntimeError:
                continue

        if not wait:
            return

        # OCR and the translation adapters are synchronous.  Their network
        # calls have a finite timeout, so wait for them to leave QThread
        # before QApplication.quit() destroys the Qt object graph.
        deadline = time.monotonic() + 35.0
        for worker in unique_workers:
            try:
                if worker.isRunning():
                    remaining_ms = max(0, round((deadline - time.monotonic()) * 1000))
                    worker.wait(remaining_ms)
                if not worker.isRunning():
                    worker.deleteLater()
            except RuntimeError:
                pass

        if self.worker is not None:
            try:
                if not self.worker.isRunning():
                    self.worker = None
            except RuntimeError:
                self.worker = None
        self.monitor_workers = {
            key: worker
            for key, worker in self.monitor_workers.items()
            if self._worker_is_running(worker)
        }

    @staticmethod
    def _worker_is_running(worker: TranslationWorker) -> bool:
        try:
            return worker.isRunning()
        except RuntimeError:
            return False

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and not self._quitting
        ):
            self.hide_to_tray()

    def open_settings(self) -> None:
        old_hotkeys = self.hotkey_settings_snapshot()
        if SettingsDialog(self.settings, self).exec() != QDialog.DialogCode.Accepted:
            return
        if self.hotkey_settings_snapshot() == old_hotkeys:
            return
        self.unregister_hotkeys()
        try:
            self.register_hotkeys()
        except (RuntimeError, ValueError) as exc:
            (
                self.settings.hotkey,
                self.settings.hotkey_enabled,
                self.settings.monitor_hotkey,
                self.settings.monitor_hotkey_enabled,
                self.settings.audio_hotkey,
                self.settings.audio_hotkey_enabled,
            ) = old_hotkeys
            save_settings(self.settings)
            try:
                self.register_hotkeys()
            except (RuntimeError, ValueError):
                pass
            QMessageBox.warning(self, "热键设置失败", str(exc))

    def hotkey_settings_snapshot(self) -> tuple[str, bool, str, bool, str, bool]:
        return (
            self.settings.hotkey,
            self.settings.hotkey_enabled,
            self.settings.monitor_hotkey,
            self.settings.monitor_hotkey_enabled,
            self.settings.audio_hotkey,
            self.settings.audio_hotkey_enabled,
        )

    def register_hotkeys(self) -> None:
        self.unregister_hotkeys()
        specifications = (
            (
                "capture",
                self.settings.hotkey_enabled,
                self.settings.hotkey,
                self.start_capture,
            ),
            (
                "monitor",
                self.settings.monitor_hotkey_enabled,
                self.settings.monitor_hotkey,
                self.toggle_monitor_from_tray,
            ),
            (
                "audio",
                self.settings.audio_hotkey_enabled,
                self.settings.audio_hotkey,
                self.toggle_audio_from_tray,
            ),
        )
        registered: dict[str, GlobalHotkeyFilter] = {}
        try:
            for name, enabled, hotkey, callback in specifications:
                if not enabled:
                    continue
                hotkey_filter = GlobalHotkeyFilter(
                    self.winId(), hotkey, callback, HOTKEY_IDS[name]
                )
                QApplication.instance().installNativeEventFilter(hotkey_filter)
                registered[name] = hotkey_filter
        except (RuntimeError, ValueError):
            for hotkey_filter in registered.values():
                QApplication.instance().removeNativeEventFilter(hotkey_filter)
                hotkey_filter.unregister()
            raise
        self.hotkey_filters = registered
        self.status_label.setText(
            "准备就绪。可在设置中心启用或调整三个功能的全局热键。"
        )

    def unregister_hotkeys(self) -> None:
        for hotkey_filter in self.hotkey_filters.values():
            QApplication.instance().removeNativeEventFilter(hotkey_filter)
            hotkey_filter.unregister()
        self.hotkey_filters.clear()

    def start_capture(self) -> None:
        if self.capture_active:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.show_error("找不到可用的屏幕。")
            return
        self.capture_active = True
        self.hide()
        overlay = CaptureOverlay(screen.geometry())
        overlay.selected.connect(lambda rect: self.capture_finished(screen, rect, overlay))
        overlay.finished.connect(self.capture_overlay_finished)
        overlay.show()
        overlay.exec()

    def start_monitor(self) -> None:
        if self.monitor_active:
            self.stop_monitor()
            return
        if any(worker.isRunning() for worker in self.monitor_workers.values()):
            QMessageBox.information(self, "持续监控", "上一轮识别还没有结束，请稍候再启动。")
            return
        dialog = MonitorSetupDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.show_error("找不到可用的屏幕。")
            return
        interval_ms = max(500, round(dialog.interval_seconds * 1000))
        self.capture_active = True
        self.hide()
        overlay = MultiRegionOverlay(
            screen.geometry(),
        )
        overlay.regions_selected.connect(
            lambda rects: self.monitor_region_selected(
                screen, rects, overlay, interval_ms
            )
        )
        overlay.finished.connect(self.capture_overlay_finished)
        overlay.show()
        overlay.exec()

    def monitor_region_selected(
        self, screen, rects: list[QRect], overlay: MultiRegionOverlay, interval_ms: int
    ) -> None:
        overlay.hide()
        # 让遮罩层的隐藏操作先提交到窗口系统，避免第一次监控截图
        # 仍然截到半透明的框选层。
        QApplication.processEvents()
        self.begin_monitor(screen, rects, interval_ms, overlay.enabled)

    def begin_monitor(
        self,
        screen,
        rects: list[QRect],
        interval_ms: int,
        enabled: list[bool] | None = None,
    ) -> None:
        self.monitor_active = True
        self.monitor_screen = screen
        enabled_values = enabled or [True] * len(rects)
        self.monitor_regions = [
            MonitorRegion(QRect(rect), enabled=enabled_values[index])
            for index, rect in enumerate(rects)
        ]
        self.monitor_interval_ms = interval_ms
        self.monitor_generation += 1
        self.monitor_button.setText("停止持续监控")
        self.manage_regions_button.setEnabled(True)
        self.overlay_lock_button.setEnabled(True)
        self.sync_tray_actions()
        self.status_label.setText(
            f"持续监控中，共 {len(self.monitor_regions)} 个区域，每 {interval_ms / 1000:g} 秒检查一次。"
        )
        self.monitor_result_window.set_locked(False)
        self.monitor_result_window.restore_geometry(self.settings, screen.geometry())
        self.monitor_result_window.clear_result()
        self.monitor_result_window.show()
        self.monitor_timer.start(interval_ms)
        self.monitor_tick()

    def manage_monitor_regions(self) -> None:
        if not self.monitor_active or self.monitor_screen is None or self.monitor_editing:
            return
        self.monitor_editing = True
        self.monitor_timer.stop()
        self.monitor_generation += 1
        self.monitor_edit_previous_lock = self.monitor_result_window.locked
        self.monitor_result_window.set_locked(True)

        overlay = MultiRegionOverlay(
            self.monitor_screen.geometry(),
            self,
            [region.rect for region in self.monitor_regions],
            [region.enabled for region in self.monitor_regions],
        )
        overlay.regions_selected.connect(
            lambda rects: self.monitor_regions_selected(rects, overlay)
        )
        overlay.finished.connect(self.monitor_region_editor_finished)
        overlay.show()
        overlay.exec()

    def monitor_regions_selected(
        self, rects: list[QRect], overlay: MultiRegionOverlay
    ) -> None:
        if not rects:
            return
        overlay.hide()
        QApplication.processEvents()
        self.monitor_regions = [
            MonitorRegion(QRect(rect), enabled=overlay.enabled[index])
            for index, rect in enumerate(rects)
        ]
        self.monitor_editing = False
        self.monitor_generation += 1
        self.monitor_result_window.set_locked(self.monitor_edit_previous_lock)
        self.refresh_monitor_result_window()
        self.status_label.setText(
            f"持续监控中，已更新为 {len(self.monitor_regions)} 个区域。"
        )
        self.monitor_timer.start(self.monitor_interval_ms)
        self.monitor_tick()

    def monitor_region_editor_finished(self, _code: int) -> None:
        if not self.monitor_editing:
            return
        self.monitor_editing = False
        self.monitor_result_window.set_locked(self.monitor_edit_previous_lock)
        self.monitor_generation += 1
        self.monitor_timer.start(self.monitor_interval_ms)
        self.status_label.setText("持续监控中，区域没有修改。")
        self.monitor_tick()

    def stop_monitor(self) -> None:
        if not self.monitor_active and not self.monitor_timer.isActive():
            return
        self.monitor_active = False
        self.monitor_editing = False
        self.monitor_generation += 1
        self.monitor_timer.stop()
        self.monitor_result_window.save_geometry(self.settings)
        self.monitor_result_window.set_locked(False)
        save_settings(self.settings)
        self.monitor_result_window.hide()
        self.monitor_button.setText("开始持续监控")
        self.manage_regions_button.setEnabled(False)
        self.overlay_lock_button.setEnabled(False)
        self.sync_tray_actions()
        self.status_label.setText("持续监控已停止。")

    def toggle_overlay_lock(self) -> None:
        if self.monitor_active:
            self.monitor_result_window.set_locked(not self.monitor_result_window.locked)

    def set_overlay_opacity(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.background_opacity_value_label.setText(f"{value}%")
        self.monitor_result_window.set_background_opacity(value)
        self.settings.overlay_opacity = value
        save_settings(self.settings)
    def set_overlay_text_opacity(self, value: int) -> None:
        value = max(30, min(100, int(value)))
        self.text_opacity_value_label.setText(f"{value}%")
        self.monitor_result_window.set_text_opacity(value)
        self.settings.overlay_text_opacity = value
        save_settings(self.settings)

    def set_overlay_mask_opacity(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.mask_opacity_value_label.setText(f"{value}%")
        self.monitor_result_window.set_mask_opacity(value)
        self.settings.overlay_mask_opacity = value
        save_settings(self.settings)

    def set_overlay_font_size(self, value: int) -> None:
        value = max(9, min(28, int(value)))
        self.font_size_value_label.setText(f"{value} pt")
        self.monitor_result_window.set_translation_font_size(value)
        self.settings.overlay_font_size = value
        save_settings(self.settings)

    def sync_overlay_lock_button(self, locked: bool) -> None:
        self.overlay_lock_button.setText(
            "解锁翻译窗口" if locked else "锁定翻译窗口"
        )

    def toggle_audio_lock(self) -> None:
        if self.audio_worker is not None:
            self.audio_result_window.set_locked(not self.audio_result_window.locked)

    def sync_audio_lock_button(self, locked: bool) -> None:
        self.audio_lock_button.setText("解锁音频窗口" if locked else "锁定音频窗口")

    def _sync_audio_source_fields(self) -> None:
        mode = self.audio_mode_combo.currentData()
        process_mode = mode == "process"
        self.audio_process_combo.setEnabled(process_mode)
        self.audio_children_check.setEnabled(process_mode)
        self.audio_device_combo.setEnabled(not process_mode)
        if mode and mode != self.settings.audio_source_mode:
            self.settings.audio_source_mode = mode
            save_settings(self.settings)

    def _audio_device_changed(self, _index: int) -> None:
        self.settings.audio_device_id = int(
            self.audio_device_combo.currentData() or -1
        )
        save_settings(self.settings)

    def _audio_process_changed(self, _index: int) -> None:
        process_id = int(self.audio_process_combo.currentData() or 0)
        self.settings.audio_process_id = process_id
        self.settings.audio_process_name = (
            "" if process_id == 0 else self.audio_process_combo.currentText()
        )
        save_settings(self.settings)

    def _audio_children_changed(self, checked: bool) -> None:
        self.settings.audio_include_children = bool(checked)
        save_settings(self.settings)

    def refresh_audio_processes(self) -> None:
        selected_process_id = int(self.audio_process_combo.currentData() or 0)
        self.audio_process_combo.blockSignals(True)
        self.audio_process_combo.clear()
        self.audio_process_combo.addItem("请选择应用进程", 0)
        for process_id, display_name in self._list_application_processes():
            self.audio_process_combo.addItem(
                f"{display_name} (PID {process_id})", process_id
            )
        selected_index = self.audio_process_combo.findData(selected_process_id)
        self.audio_process_combo.setCurrentIndex(
            selected_index if selected_index >= 0 else 0
        )
        self.audio_process_combo.blockSignals(False)
        if selected_index < 0:
            self._audio_process_changed(0)

    @staticmethod
    def _list_application_processes() -> list[tuple[int, str]]:
        system_names = {
            "audiodg.exe", "conhost.exe", "csrss.exe", "dwm.exe",
            "fontdrvhost.exe", "idle", "lsass.exe", "lsm.exe",
            "msmpeng.exe", "registry", "services.exe", "smss.exe",
            "spoolsv.exe", "sppsvc.exe", "svchost.exe", "system",
            "system idle process", "wininit.exe", "winlogon.exe",
            "wudfhost.exe",
        }
        visible_titles: dict[int, str] = {}
        if os.name == "nt":
            user32 = ctypes.windll.user32
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.restype = wintypes.BOOL
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            user32.GetWindowTextW.argtypes = [
                wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
            ]
            user32.GetWindowTextW.restype = ctypes.c_int
            user32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
            ]
            user32.GetWindowThreadProcessId.restype = wintypes.DWORD
            enum_windows_proc = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )

            def collect_window(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value.strip()
                if not title:
                    return True
                process_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
                visible_titles.setdefault(process_id.value, title)
                return True

            user32.EnumWindows(enum_windows_proc(collect_window), 0)
        try:
            output = subprocess.check_output(
                ["tasklist", "/fo", "csv", "/nh"],
                text=True,
                encoding="mbcs",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return []

        result: list[tuple[int, str]] = []
        seen: set[int] = set()
        for row in csv.reader(io.StringIO(output)):
            if len(row) < 2:
                continue
            process_name = row[0].strip()
            try:
                process_id = int(row[1])
            except ValueError:
                continue
            normalized_name = process_name.lower()
            if process_id in seen or process_id <= 4:
                continue
            if normalized_name in system_names:
                continue
            window_title = visible_titles.get(process_id)
            if not window_title:
                continue
            seen.add(process_id)
            result.append((process_id, f"{window_title} [{process_name}]"))
        return sorted(result, key=lambda item: item[1].lower())

    def _populate_audio_target_languages(
        self, source_language: str, preferred_target: str
    ) -> None:
        if source_language == "auto":
            target_codes = tuple(
                code for code in AUDIO_LANGUAGE_LABELS if code != "auto"
            )
        else:
            target_codes = AUDIO_TARGET_LANGUAGES.get(source_language, ("zh",))
        self.audio_target_language_combo.blockSignals(True)
        self.audio_target_language_combo.clear()
        for code in target_codes:
            self.audio_target_language_combo.addItem(
                AUDIO_LANGUAGE_LABELS[code], code
            )
        target_index = self.audio_target_language_combo.findData(preferred_target)
        self.audio_target_language_combo.setCurrentIndex(
            target_index if target_index >= 0 else 0
        )
        self.audio_target_language_combo.blockSignals(False)

    def _audio_source_language_changed(self, _index: int) -> None:
        source_language = self.audio_source_language_combo.currentData() or "auto"
        preferred_target = self.settings.audio_target_language
        self._populate_audio_target_languages(source_language, preferred_target)
        self.settings.audio_source_language = source_language
        self.settings.audio_target_language = (
            self.audio_target_language_combo.currentData() or "zh"
        )
        save_settings(self.settings)

    def _audio_target_language_changed(self, _index: int) -> None:
        target_language = self.audio_target_language_combo.currentData()
        if not target_language:
            return
        self.settings.audio_target_language = target_language
        save_settings(self.settings)

    def set_audio_background_opacity(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.audio_background_opacity_value_label.setText(f"{value}%")
        self.audio_result_window.set_background_opacity(value)
        self.settings.audio_background_opacity = value
        save_settings(self.settings)

    def set_audio_text_opacity(self, value: int) -> None:
        value = max(30, min(100, int(value)))
        self.audio_text_opacity_value_label.setText(f"{value}%")
        self.audio_result_window.set_text_opacity(value)
        self.settings.audio_text_opacity = value
        save_settings(self.settings)

    def set_audio_history_text_opacity(self, value: int) -> None:
        value = max(30, min(100, int(value)))
        self.audio_history_text_opacity_value_label.setText(f"{value}%")
        self.audio_result_window.set_history_text_opacity(value)
        self.settings.audio_history_text_opacity = value
        save_settings(self.settings)

    def set_audio_show_original(self, checked: bool) -> None:
        checked = bool(checked)
        self.audio_result_window.set_show_original(checked)
        self.settings.audio_show_original = checked
        save_settings(self.settings)

    def set_audio_font_scale(self, value: int) -> None:
        value = max(50, min(400, int(value)))
        self.audio_result_window.set_font_scale(value)
        self.settings.audio_font_scale = value
        save_settings(self.settings)

    def set_audio_mask_opacity(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.audio_mask_opacity_value_label.setText(f"{value}%")
        self.audio_result_window.set_mask_opacity(value)
        self.settings.audio_mask_opacity = value
        save_settings(self.settings)

    def monitor_tick(self) -> None:
        if (
            not self.monitor_active
            or self.monitor_editing
            or self.monitor_screen is None
        ):
            return
        generation = self.monitor_generation
        excluded_rects = self.monitor_excluded_rects()

        for region_id, region in enumerate(self.monitor_regions):
            worker_key = (generation, region_id)
            if not region.enabled or worker_key in self.monitor_workers:
                continue
            try:
                image = self.capture_region(
                    self.monitor_screen,
                    region.rect,
                    excluded_rects=excluded_rects,
                )
            except Exception as exc:  # noqa: BLE001 - 将截图后端错误展示给用户
                self.monitor_failed(
                    f"区域 {region_id + 1} 截图失败：{exc}",
                    generation,
                )
                continue

            worker = TranslationWorker(image, self.settings, region.last_text)
            self.monitor_workers[worker_key] = worker
            worker.completed.connect(
                lambda original, translated, rid=region_id, g=generation: self.monitor_result(
                    rid, original, translated, g
                )
            )
            worker.unchanged.connect(
                lambda _text, rid=region_id, g=generation: self.monitor_unchanged(
                    rid, g
                )
            )
            worker.no_text.connect(
                lambda rid=region_id, g=generation: self.monitor_no_text(rid, g)
            )
            worker.failed.connect(
                lambda message, rid=region_id, g=generation: self.monitor_failed(
                    f"区域 {rid + 1}：{message}", g
                )
            )
            worker.finished.connect(lambda w=worker: self.monitor_worker_finished(w))
            worker.start()

    def monitor_worker_finished(self, worker: TranslationWorker) -> None:
        for region_id, active_worker in list(self.monitor_workers.items()):
            if active_worker is worker:
                self.monitor_workers.pop(region_id, None)
                break
        worker.deleteLater()

    def monitor_result(
        self, region_id: int, original: str, translated: str, generation: int
    ) -> None:
        if not self.monitor_active or generation != self.monitor_generation:
            return
        if region_id >= len(self.monitor_regions):
            return
        region = self.monitor_regions[region_id]
        region.last_text = original
        region.translated = translated
        self.refresh_monitor_result_window()
        self.status_label.setText(f"持续监控中：区域 {region_id + 1} 发现新的英文内容。")

    def monitor_unchanged(self, region_id: int, generation: int) -> None:
        if self.monitor_active and generation == self.monitor_generation:
            self.status_label.setText(f"持续监控中：区域 {region_id + 1} 文字没有变化。")

    def monitor_no_text(self, region_id: int, generation: int) -> None:
        if self.monitor_active and generation == self.monitor_generation:
            if region_id < len(self.monitor_regions):
                self.monitor_regions[region_id].last_text = ""
                self.monitor_regions[region_id].translated = ""
                self.refresh_monitor_result_window()
            self.status_label.setText(
                f"持续监控中：区域 {region_id + 1} 没有检测到英文。"
            )

    def monitor_failed(self, message: str, generation: int) -> None:
        if self.monitor_active and generation == self.monitor_generation:
            self.status_label.setText(f"持续监控错误：{message}")

    def refresh_monitor_result_window(self) -> None:
        regions = []
        for index, region in enumerate(self.monitor_regions):
            if region.enabled and region.translated:
                regions.append((index, region.translated))
        if regions:
            self.monitor_result_window.update_regions(regions)
        else:
            self.monitor_result_window.clear_result()

    def capture_overlay_finished(self, _code: int) -> None:
        self.capture_active = False
        self.show()
        self.activateWindow()

    def capture_finished(self, screen, rect: QRect, overlay: CaptureOverlay) -> None:
        overlay.hide()
        QApplication.processEvents()
        try:
            image = self.capture_region(screen, rect)
        except Exception as exc:  # noqa: BLE001 - 将截图后端错误展示给用户
            self.show_error(f"截图失败：{exc}")
            return
        self.original_edit.clear()
        self.translated_edit.clear()
        self.status_label.setText("正在识别和翻译，请稍候……")
        self.start_button.setEnabled(False)
        self.worker = TranslationWorker(image, self.settings)
        self.worker.completed.connect(self.show_result)
        self.worker.no_text.connect(
            lambda: self.show_error("没有识别到英文，请尝试扩大区域或提高文字清晰度。")
        )
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(lambda: self.start_button.setEnabled(True))
        self.worker.start()

    def monitor_excluded_rects(self) -> list[QRect]:
        """Return overlay rectangles that must not feed back into OCR."""
        window = self.monitor_result_window
        if not window.isVisible():
            return []
        # A top-level Qt window's frame geometry is in virtual-screen
        # coordinates, which is also the coordinate system used by mss.
        return [QRect(window.frameGeometry())]

    def capture_region(
        self,
        screen,
        rect: QRect,
        *,
        excluded_rects: list[QRect] | None = None,
    ) -> Image.Image:
        dpr = screen.devicePixelRatio()
        screen_geometry = screen.geometry()
        capture_rect = QRect(
            screen_geometry.x() + rect.x(),
            screen_geometry.y() + rect.y(),
            rect.width(),
            rect.height(),
        )
        monitor = {
            "left": round(capture_rect.x() * dpr),
            "top": round(capture_rect.y() * dpr),
            "width": max(1, round(rect.width() * dpr)),
            "height": max(1, round(rect.height() * dpr)),
        }
        with MSS() as screen_capture:
            shot = screen_capture.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        if excluded_rects:
            mask_excluded_regions(image, capture_rect, excluded_rects)
        return image

    def show_result(self, original: str, translated: str) -> None:
        self.original_edit.setPlainText(original)
        self.translated_edit.setPlainText(translated)
        self.status_label.setText("完成。")

    def show_error(self, message: str) -> None:
        self.status_label.setText("处理失败。")
        self.start_button.setEnabled(True)
        QMessageBox.warning(self, "Screen Translator", message)

    def start_audio_translation(self) -> None:
        if not (
            self.settings.dashscope_api_key.strip()
            or os.environ.get("DASHSCOPE_API_KEY", "").strip()
        ):
            QMessageBox.warning(
                self,
                "音频翻译",
                "请先在设置中填写阿里云 DashScope API Key，或设置 DASHSCOPE_API_KEY 环境变量。",
            )
            return
        worker = self.audio_worker
        if worker is not None:
            try:
                running = worker.isRunning()
            except RuntimeError:
                self.audio_worker = None
                worker = None
                running = False
            if running:
                self.stop_audio_translation()
                return
            self.audio_worker = None
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
        self._audio_stop_requested = False
        self.audio_result_window.set_background_opacity(self.audio_background_opacity_slider.value())
        self.audio_result_window.set_text_opacity(self.audio_text_opacity_slider.value())
        self.audio_result_window.set_history_text_opacity(self.audio_history_text_opacity_slider.value())
        self.audio_result_window.set_show_original(
            self.audio_show_original_checkbox.isChecked()
        )
        self.audio_result_window.set_font_scale(self.audio_font_scale_slider.value())
        self.audio_result_window.set_mask_opacity(self.audio_mask_opacity_slider.value())
        self.audio_result_window.set_locked(False)
        self.audio_lock_button.setEnabled(True)
        self.audio_result_window.set_history_limit(self.settings.audio_history_limit)
        self.audio_result_window.restore_geometry(self.settings)
        self.audio_result_window.clear()
        self.audio_result_window.show()
        self.audio_result_window.raise_()
        self.audio_worker = AudioTranslationWorker(self.settings)
        self.audio_worker.partial.connect(self.audio_result_window.update_partial)
        self.audio_worker.completed.connect(self.audio_result_window.append_result)
        self.audio_worker.state_changed.connect(self.audio_result_window.set_state)
        self.audio_worker.source_changed.connect(self.audio_result_window.set_source)
        self.audio_worker.level_changed.connect(self.audio_result_window.set_level)
        self.audio_worker.speech_changed.connect(self.audio_result_window.set_speech_state)
        self.audio_worker.state_changed.connect(self.audio_state_changed)
        self.audio_worker.failed.connect(self.audio_translation_failed)
        self.audio_worker.finished.connect(
            lambda worker=self.audio_worker: self.audio_worker_finished(worker)
        )
        self.audio_button.setText("停止音频翻译")
        self.sync_tray_actions()
        self.audio_worker.start()

    def audio_translation_failed(self, message: str) -> None:
        if self._audio_stop_requested:
            return
        self.audio_result_window.set_state(f"错误：{message}")
        self.status_label.setText(f"音频翻译错误：{message}")

    def audio_state_changed(self, state: str) -> None:
        if not self._audio_stop_requested:
            self.status_label.setText(f"音频翻译：{state}")

    def audio_worker_finished(self, worker=None) -> None:
        if worker is None:
            worker = self.sender()
        if worker is self.audio_worker:
            was_stopping = self._audio_stop_requested
            self.audio_worker = None
            self.audio_button.setEnabled(True)
            self.audio_button.setText("开始音频翻译")
            self.sync_tray_actions()
            if was_stopping:
                self.status_label.setText("音频翻译：已停止")
                self._audio_stop_requested = False
        if worker is not None:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass

    def stop_audio_translation(self, wait: bool = False) -> None:
        worker = self.audio_worker
        self._audio_stop_requested = True
        if worker is not None:
            self.audio_button.setEnabled(False)
            self.audio_button.setText("正在停止音频翻译")
            self.status_label.setText("音频翻译：正在停止...")
            try:
                worker.stop()
                if wait and worker.isRunning():
                    worker.wait(5000)
                if wait and not worker.isRunning():
                    self.audio_worker = None
                    worker.deleteLater()
            except RuntimeError:
                self.audio_worker = None
        else:
            self.audio_button.setEnabled(True)
            self.audio_button.setText("开始音频翻译")
            self.status_label.setText("音频翻译：已停止")
            self._audio_stop_requested = False
        self.audio_result_window.set_locked(False)
        self.audio_lock_button.setEnabled(False)
        self.audio_result_window.save_geometry(self.settings)
        save_settings(self.settings)
        self.audio_result_window.hide()
        self.sync_tray_actions()
        if wait:
            self.audio_button.setEnabled(True)
            self.audio_button.setText("开始音频翻译")
            self.status_label.setText("音频翻译：已停止")
            self._audio_stop_requested = False
    def closeEvent(self, event) -> None:
        if not self._quitting:
            self.hide_to_tray()
            event.ignore()
            return
        super().closeEvent(event)


