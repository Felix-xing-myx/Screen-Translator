"""Application settings dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings, save_settings
from ..hotkeys import HotkeyEdit
from .styles import MAIN_STYLE_SHEET


class SettingsDialog(QDialog):
    QWEN_CONSOLE_URL = (
        "https://bailian.console.aliyun.com/cn-beijing#/home"
    )

    def __init__(self, settings: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        # Top-level dialogs do not reliably inherit the main window's QSS.
        # Apply the shared theme here so page backgrounds do not fall back to
        # the Windows palette.
        self.setStyleSheet(MAIN_STYLE_SHEET)
        self.setWindowTitle("设置")
        self.setMinimumSize(680, 520)
        self.resize(760, 620)
        self.settings = settings

        self.translation_provider_combo = QComboBox()
        self.translation_provider_combo.addItem("阿里云 Qwen-MT", "qwen_mt")
        self.translation_provider_combo.addItem("MyMemory（备用）", "mymemory")
        provider_index = self.translation_provider_combo.findData(
            settings.translation_provider
        )
        self.translation_provider_combo.setCurrentIndex(
            provider_index if provider_index >= 0 else 0
        )

        self.translation_qwen_key_edit = QLineEdit(settings.translation_qwen_api_key)
        self.translation_qwen_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.translation_qwen_key_edit.setPlaceholderText(
            "仅供截图/持续监控翻译使用"
        )
        self.translation_qwen_model_combo = QComboBox()
        for model, label in (
            ("qwen-mt-flash", "qwen-mt-flash（推荐，速度快）"),
            ("qwen-mt-plus", "qwen-mt-plus（质量优先）"),
            ("qwen-mt-lite", "qwen-mt-lite（成本低）"),
            ("qwen-mt-turbo", "qwen-mt-turbo"),
        ):
            self.translation_qwen_model_combo.addItem(label, model)
        model_index = self.translation_qwen_model_combo.findData(
            settings.translation_qwen_model
        )
        self.translation_qwen_model_combo.setCurrentIndex(
            model_index if model_index >= 0 else 0
        )
        self.qwen_console_link = QLabel(
            f'<a href="{self.QWEN_CONSOLE_URL}">打开阿里云百炼控制台，申请 API Key</a>'
        )
        self.qwen_console_link.setOpenExternalLinks(True)
        self.qwen_console_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.hotkey_edit = HotkeyEdit(settings.hotkey)
        self.hotkey_enabled_check = QCheckBox("启用")
        self.hotkey_enabled_check.setChecked(settings.hotkey_enabled)
        self.monitor_hotkey_edit = HotkeyEdit(settings.monitor_hotkey)
        self.monitor_hotkey_enabled_check = QCheckBox("启用")
        self.monitor_hotkey_enabled_check.setChecked(
            settings.monitor_hotkey_enabled
        )

        translation_form = QFormLayout()
        translation_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        translation_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        translation_form.addRow("截图翻译热键：", self.hotkey_edit)
        translation_form.addRow("启用截图热键：", self.hotkey_enabled_check)
        translation_form.addRow("持续监控热键：", self.monitor_hotkey_edit)
        translation_form.addRow(
            "启用持续监控热键：", self.monitor_hotkey_enabled_check
        )
        translation_form.addRow("截图翻译服务商：", self.translation_provider_combo)
        translation_form.addRow("阿里云 Qwen-MT API Key：", self.translation_qwen_key_edit)
        translation_form.addRow("申请地址：", self.qwen_console_link)
        translation_form.addRow("Qwen-MT 模型：", self.translation_qwen_model_combo)
        self.qwen_cost_note = QLabel(
            "提示：阿里云百炼 API 提供一定免费额度；如果返回 403，说明额度可能已用尽，需要充值后继续使用。"
        )
        self.qwen_cost_note.setWordWrap(True)
        self.qwen_cost_note.setObjectName("hintLabel")
        translation_form.addRow("使用提示：", self.qwen_cost_note)
        self.translation_provider_combo.currentIndexChanged.connect(
            self.sync_translation_provider_fields
        )
        self.hotkey_enabled_check.toggled.connect(self.sync_hotkey_fields)
        self.monitor_hotkey_enabled_check.toggled.connect(self.sync_hotkey_fields)

        self.audio_key_edit = QLineEdit(settings.dashscope_api_key)
        self.audio_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.audio_vad_mode_spin = QSpinBox()
        self.audio_vad_mode_spin.setRange(0, 3)
        self.audio_vad_mode_spin.setValue(settings.audio_vad_mode)
        self.audio_vad_post_spin = QSpinBox()
        self.audio_vad_post_spin.setRange(200, 6000)
        self.audio_vad_post_spin.setValue(settings.audio_vad_post_roll_ms)
        self.audio_history_spin = QSpinBox()
        self.audio_history_spin.setRange(1, 10)
        self.audio_history_spin.setValue(settings.audio_history_limit)
        self.audio_hotkey_edit = HotkeyEdit(settings.audio_hotkey)
        self.audio_hotkey_enabled_check = QCheckBox("启用")
        self.audio_hotkey_enabled_check.setChecked(settings.audio_hotkey_enabled)
        self.audio_hotkey_enabled_check.toggled.connect(self.sync_hotkey_fields)

        audio_form = QFormLayout()
        audio_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        audio_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        audio_form.addRow("音频翻译热键：", self.audio_hotkey_edit)
        audio_form.addRow("启用音频热键：", self.audio_hotkey_enabled_check)
        audio_form.addRow("阿里云 DashScope API Key：", self.audio_key_edit)
        audio_form.addRow("VAD 灵敏度（0-3）：", self.audio_vad_mode_spin)
        audio_form.addRow("句尾静音阈值（毫秒）：", self.audio_vad_post_spin)
        audio_form.addRow("保留最近句数（最多 10）：", self.audio_history_spin)
        note = QLabel(
            "截图翻译和音频翻译可以使用相同或不同的 API Key；热键至少需要包含 Ctrl、Alt、Shift 或 Windows 键中的一个。"
        )
        note.setWordWrap(True)
        note.setObjectName("hintLabel")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        translation_page = QWidget()
        translation_page.setObjectName("settingsPage")
        translation_layout = QVBoxLayout(translation_page)
        translation_layout.setContentsMargins(18, 18, 18, 18)
        translation_layout.addLayout(translation_form)
        translation_layout.addStretch(1)

        audio_page = QWidget()
        audio_page.setObjectName("settingsPage")
        audio_layout = QVBoxLayout(audio_page)
        audio_layout.setContentsMargins(18, 18, 18, 18)
        audio_layout.addLayout(audio_form)
        audio_layout.addStretch(1)

        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")
        tabs.addTab(translation_page, "截图翻译")
        tabs.addTab(audio_page, "音频翻译")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(tabs, 1)
        layout.addWidget(note)
        layout.addWidget(buttons)
        self.sync_translation_provider_fields()
        self.sync_hotkey_fields()

    def sync_translation_provider_fields(self) -> None:
        provider = self.translation_provider_combo.currentData()
        use_qwen = provider == "qwen_mt"
        self.translation_qwen_key_edit.setEnabled(use_qwen)
        self.translation_qwen_model_combo.setEnabled(use_qwen)
        self.qwen_console_link.setEnabled(use_qwen)

    def sync_hotkey_fields(self) -> None:
        self.hotkey_edit.setEnabled(self.hotkey_enabled_check.isChecked())
        self.monitor_hotkey_edit.setEnabled(
            self.monitor_hotkey_enabled_check.isChecked()
        )
        self.audio_hotkey_edit.setEnabled(self.audio_hotkey_enabled_check.isChecked())

    def accept(self) -> None:
        hotkeys = (
            ("截图翻译", self.hotkey_enabled_check, self.hotkey_edit),
            ("持续监控", self.monitor_hotkey_enabled_check, self.monitor_hotkey_edit),
            ("音频翻译", self.audio_hotkey_enabled_check, self.audio_hotkey_edit),
        )
        for label, enabled_check, hotkey_edit in hotkeys:
            if enabled_check.isChecked() and not hotkey_edit.text().strip():
                QMessageBox.warning(
                    self, "设置", f"请为{label}录入热键，或关闭该热键。"
                )
                return
        self.settings.hotkey = self.hotkey_edit.text().strip()
        self.settings.hotkey_enabled = self.hotkey_enabled_check.isChecked()
        self.settings.monitor_hotkey = self.monitor_hotkey_edit.text().strip()
        self.settings.monitor_hotkey_enabled = (
            self.monitor_hotkey_enabled_check.isChecked()
        )
        self.settings.audio_hotkey = self.audio_hotkey_edit.text().strip()
        self.settings.audio_hotkey_enabled = (
            self.audio_hotkey_enabled_check.isChecked()
        )
        self.settings.translation_provider = (
            self.translation_provider_combo.currentData() or "mymemory"
        )
        self.settings.translation_qwen_api_key = (
            self.translation_qwen_key_edit.text().strip()
        )
        self.settings.translation_qwen_model = (
            self.translation_qwen_model_combo.currentData() or "qwen-mt-flash"
        )
        if self.settings.translation_provider == "mymemory":
            self.settings.translation_url = "https://api.mymemory.translated.net/get"
        self.settings.dashscope_api_key = self.audio_key_edit.text().strip()
        self.settings.audio_vad_mode = self.audio_vad_mode_spin.value()
        self.settings.audio_vad_post_roll_ms = self.audio_vad_post_spin.value()
        self.settings.audio_history_limit = self.audio_history_spin.value()
        save_settings(self.settings)
        super().accept()
