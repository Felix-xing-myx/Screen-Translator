"""Application settings dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
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
from ..audio_translation import AUDIO_TRANSLATION_MODEL_OPTIONS
from ..hotkeys import HotkeyEdit
from .styles import DARK_THEME, MAIN_STYLE_SHEET


QWEN_MT_MODEL_PRESETS = (
    ("qwen-mt-flash", "qwen-mt-flash（通用推荐）"),
    ("qwen-mt-plus", "qwen-mt-plus（质量优先）"),
    ("qwen-mt-lite", "qwen-mt-lite（低延迟）"),
    ("qwen-mt-turbo", "qwen-mt-turbo（旧版，不建议新配置使用）"),
)
CUSTOM_QWEN_MODEL = "__custom__"


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
        current_model_id = settings.translation_qwen_model.strip()
        self.translation_qwen_model_preset_combo = QComboBox()
        for model_id, label in QWEN_MT_MODEL_PRESETS:
            self.translation_qwen_model_preset_combo.addItem(label, model_id)
        self.translation_qwen_model_preset_combo.addItem(
            "自定义模型 ID…", CUSTOM_QWEN_MODEL
        )
        preset_index = self.translation_qwen_model_preset_combo.findData(
            current_model_id
        )
        if preset_index < 0:
            preset_index = self.translation_qwen_model_preset_combo.findData(
                CUSTOM_QWEN_MODEL
            )
        self.translation_qwen_model_preset_combo.setCurrentIndex(preset_index)
        self.translation_qwen_model_edit = QLineEdit(current_model_id)
        self.translation_qwen_model_edit.setPlaceholderText(
            "例如：qwen-mt-plus"
        )
        self.translation_qwen_model_edit.setToolTip(
            "填写百炼控制台中已开通、且兼容 Qwen-MT 翻译接口的模型 ID。"
        )
        self.qwen_console_link = QLabel(
            f'<a href="{self.QWEN_CONSOLE_URL}">打开阿里云百炼控制台，申请 API Key</a>'
        )
        self.qwen_console_link.setObjectName("externalLinkLabel")
        self.qwen_console_link.setStyleSheet(
            f"QLabel#externalLinkLabel {{ color: {DARK_THEME.action_bright}; }}"
        )
        link_palette = self.qwen_console_link.palette()
        link_palette.setColor(
            QPalette.ColorRole.Link,
            DARK_THEME.accent_bright,
        )
        link_palette.setColor(
            QPalette.ColorRole.LinkVisited,
            DARK_THEME.accent,
        )
        self.qwen_console_link.setPalette(link_palette)
        self.qwen_console_link.setOpenExternalLinks(True)
        self.qwen_console_link.setEnabled(True)
        self.qwen_console_link.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.monitor_ocr_concurrency_spin = QSpinBox()
        self.monitor_ocr_concurrency_spin.setRange(1, 4)
        self.monitor_ocr_concurrency_spin.setValue(
            max(1, min(4, settings.monitor_ocr_concurrency))
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
        translation_form.addRow(
            "持续监控 OCR 并发数：", self.monitor_ocr_concurrency_spin
        )
        translation_form.addRow("截图翻译服务商：", self.translation_provider_combo)
        translation_form.addRow("阿里云 Qwen-MT API Key：", self.translation_qwen_key_edit)
        translation_form.addRow("申请地址：", self.qwen_console_link)
        translation_form.addRow(
            "常用模型：", self.translation_qwen_model_preset_combo
        )
        translation_form.addRow(
            "Qwen-MT 模型 ID：", self.translation_qwen_model_edit
        )
        self.qwen_cost_note = QLabel(
            "提示：阿里云百炼 API 提供一定免费额度；如果返回 403，说明额度可能已用尽，需要充值后继续使用。"
        )
        self.qwen_cost_note.setWordWrap(True)
        self.qwen_cost_note.setObjectName("hintLabel")
        translation_form.addRow("使用提示：", self.qwen_cost_note)
        self.translation_provider_combo.currentIndexChanged.connect(
            self.sync_translation_provider_fields
        )
        self.translation_qwen_model_preset_combo.currentIndexChanged.connect(
            self.apply_qwen_model_preset
        )
        self.translation_qwen_model_edit.textChanged.connect(
            self.sync_qwen_model_preset_from_text
        )
        self.hotkey_enabled_check.toggled.connect(self.sync_hotkey_fields)
        self.monitor_hotkey_enabled_check.toggled.connect(self.sync_hotkey_fields)

        self.audio_key_edit = QLineEdit(settings.dashscope_api_key)
        self.audio_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.audio_model_combo = QComboBox()
        for model_id, model_label in AUDIO_TRANSLATION_MODEL_OPTIONS:
            self.audio_model_combo.addItem(model_label, model_id)
        model_index = self.audio_model_combo.findData(
            settings.audio_translation_model
        )
        self.audio_model_combo.setCurrentIndex(model_index if model_index >= 0 else 0)
        self.audio_model_combo.setToolTip(
            "Qwen3.5 是当前推荐模型；Gummy 已被百炼列入计划下线模型。"
        )
        self.audio_model_id_edit = QLineEdit()
        self.audio_model_id_edit.setPlaceholderText(
            "选择“自定义模型”后填写模型 ID"
        )
        self.audio_model_id_edit.setToolTip(
            "选择预设模型时此处会自动同步；选择自定义模型时可填写百炼中的模型 ID。"
        )
        self._sync_audio_model_fields()
        self.audio_model_combo.currentIndexChanged.connect(
            self._sync_audio_model_fields
        )
        self.audio_workspace_edit = QLineEdit(settings.dashscope_workspace_id)
        self.audio_workspace_edit.setPlaceholderText("Qwen 实时翻译需要时填写")
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
        audio_form.addRow("实时翻译模型：", self.audio_model_combo)
        audio_form.addRow("模型 ID（自定义时可编辑）：", self.audio_model_id_edit)
        audio_form.addRow("百炼工作空间 ID：", self.audio_workspace_edit)
        audio_form.addRow("VAD 灵敏度（0-3）：", self.audio_vad_mode_spin)
        audio_form.addRow("句尾静音阈值（毫秒）：", self.audio_vad_post_spin)
        self.audio_vad_post_spin.setToolTip(
            "实际还会额外保留约 320 毫秒的短停顿合并窗口，避免快速语音中间断词。"
        )
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
        self.translation_qwen_model_preset_combo.setEnabled(use_qwen)
        self.translation_qwen_model_edit.setEnabled(use_qwen)
        # The console link is useful for every provider state and must not be
        # disabled together with the Qwen-only credential fields.
        self.qwen_console_link.setEnabled(True)

    def apply_qwen_model_preset(self, index: int) -> None:
        model_id = self.translation_qwen_model_preset_combo.itemData(index)
        if model_id and model_id != CUSTOM_QWEN_MODEL:
            self.translation_qwen_model_edit.setText(str(model_id))

    def sync_qwen_model_preset_from_text(self, text: str) -> None:
        model_id = text.strip()
        preset_index = self.translation_qwen_model_preset_combo.findData(model_id)
        if preset_index < 0:
            preset_index = self.translation_qwen_model_preset_combo.findData(
                CUSTOM_QWEN_MODEL
            )
        if self.translation_qwen_model_preset_combo.currentIndex() == preset_index:
            return
        self.translation_qwen_model_preset_combo.blockSignals(True)
        self.translation_qwen_model_preset_combo.setCurrentIndex(preset_index)
        self.translation_qwen_model_preset_combo.blockSignals(False)

    def sync_hotkey_fields(self) -> None:
        self.hotkey_edit.setEnabled(self.hotkey_enabled_check.isChecked())
        self.monitor_hotkey_edit.setEnabled(
            self.monitor_hotkey_enabled_check.isChecked()
        )
        self.audio_hotkey_edit.setEnabled(self.audio_hotkey_enabled_check.isChecked())

    def _sync_audio_model_fields(self, _index: int = -1) -> None:
        model = str(self.audio_model_combo.currentData() or "")
        if model == "custom":
            self.audio_model_id_edit.setText(
                self.settings.audio_custom_translation_model_id.strip()
            )
            self.audio_model_id_edit.setReadOnly(False)
            return
        self.audio_model_id_edit.setText(model)
        self.audio_model_id_edit.setReadOnly(True)

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
        if (
            self.translation_provider_combo.currentData() == "qwen_mt"
            and not self.translation_qwen_model_edit.text().strip()
        ):
            QMessageBox.warning(
                self,
                "设置",
                "请填写 Qwen-MT 模型 ID，例如 qwen-mt-plus。",
            )
            return
        self.settings.hotkey = self.hotkey_edit.text().strip()
        self.settings.hotkey_enabled = self.hotkey_enabled_check.isChecked()
        self.settings.monitor_hotkey = self.monitor_hotkey_edit.text().strip()
        self.settings.monitor_hotkey_enabled = (
            self.monitor_hotkey_enabled_check.isChecked()
        )
        self.settings.monitor_ocr_concurrency = (
            self.monitor_ocr_concurrency_spin.value()
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
            self.translation_qwen_model_edit.text().strip() or "qwen-mt-flash"
        )
        if self.settings.translation_provider == "mymemory":
            self.settings.translation_url = "https://api.mymemory.translated.net/get"
        self.settings.dashscope_api_key = self.audio_key_edit.text().strip()
        selected_audio_model = str(
            self.audio_model_combo.currentData()
            or "qwen3.5-livetranslate-flash-realtime"
        )
        self.settings.audio_translation_model = selected_audio_model
        self.settings.audio_custom_translation_model_id = (
            self.audio_model_id_edit.text().strip()
            if selected_audio_model == "custom"
            else selected_audio_model
        )
        self.settings.dashscope_workspace_id = self.audio_workspace_edit.text().strip()
        self.settings.audio_vad_mode = self.audio_vad_mode_spin.value()
        self.settings.audio_vad_post_roll_ms = self.audio_vad_post_spin.value()
        self.settings.audio_history_limit = self.audio_history_spin.value()
        save_settings(self.settings)
        super().accept()
