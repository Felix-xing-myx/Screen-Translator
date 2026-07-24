"""Main application window and high-level UI orchestration."""

from __future__ import annotations

from mss import MSS
from PIL import Image
from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..capture import CaptureOverlay, MultiRegionOverlay
from ..config import AppSettings, load_settings, save_settings
from ..hotkeys import GlobalHotkeyFilter
from ..models import MonitorRegion
from ..workers import TranslationWorker
from .monitor import MonitorSetupDialog
from .results import MonitorResultWindow
from .settings import SettingsDialog
from .styles import MAIN_STYLE_SHEET


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.worker: TranslationWorker | None = None
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
        self.hotkey_filter: GlobalHotkeyFilter | None = None
        self.setWindowTitle("Screen Translator")
        self.resize(760, 560)

        self.start_button = QPushButton("截图翻译")
        self.start_button.setMinimumHeight(42)
        self.start_button.clicked.connect(self.start_capture)
        self.settings_button = QPushButton("设置")
        self.settings_button.clicked.connect(self.open_settings)
        self.monitor_button = QPushButton("开始持续监控")
        self.monitor_button.setMinimumHeight(42)
        self.monitor_button.clicked.connect(self.start_monitor)
        self.overlay_lock_button = QPushButton("锁定翻译窗口")
        self.overlay_lock_button.setEnabled(False)
        self.overlay_lock_button.clicked.connect(self.toggle_overlay_lock)
        self.manage_regions_button = QPushButton("管理监控区域")
        self.manage_regions_button.setEnabled(False)
        self.manage_regions_button.clicked.connect(self.manage_monitor_regions)
        self.monitor_result_window = MonitorResultWindow()
        self.monitor_result_window.stop_requested.connect(self.stop_monitor)
        self.monitor_result_window.lock_changed.connect(self.sync_overlay_lock_button)
        self.background_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.background_opacity_slider.setRange(0, 100)
        self.background_opacity_slider.setValue(
            max(0, min(100, self.settings.overlay_opacity))
        )
        self.background_opacity_slider.valueChanged.connect(self.set_overlay_opacity)
        self.background_opacity_value_label = QLabel(
            f"{self.background_opacity_slider.value()}%"
        )
        self.background_opacity_value_label.setObjectName("opacityLabel")
        background_opacity_row = QHBoxLayout()
        background_opacity_row.addWidget(QLabel("窗口背景不透明度"))
        background_opacity_row.addWidget(self.background_opacity_slider, 1)
        background_opacity_row.addWidget(self.background_opacity_value_label)

        self.text_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_opacity_slider.setRange(30, 100)
        self.text_opacity_slider.setValue(
            max(30, min(100, self.settings.overlay_text_opacity))
        )
        self.text_opacity_slider.valueChanged.connect(self.set_overlay_text_opacity)
        self.text_opacity_value_label = QLabel(
            f"{self.text_opacity_slider.value()}%"
        )
        self.text_opacity_value_label.setObjectName("opacityLabel")
        text_opacity_row = QHBoxLayout()
        text_opacity_row.addWidget(QLabel("翻译文字不透明度"))
        text_opacity_row.addWidget(self.text_opacity_slider, 1)
        text_opacity_row.addWidget(self.text_opacity_value_label)

        self.mask_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.mask_opacity_slider.setRange(0, 100)
        self.mask_opacity_slider.setValue(
            max(0, min(100, self.settings.overlay_mask_opacity))
        )
        self.mask_opacity_slider.valueChanged.connect(self.set_overlay_mask_opacity)
        self.mask_opacity_value_label = QLabel(
            f"{self.mask_opacity_slider.value()}%"
        )
        self.mask_opacity_value_label.setObjectName("opacityLabel")
        mask_opacity_row = QHBoxLayout()
        mask_opacity_row.addWidget(QLabel("文字蒙版不透明度"))
        mask_opacity_row.addWidget(self.mask_opacity_slider, 1)
        mask_opacity_row.addWidget(self.mask_opacity_value_label)

        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(9, 28)
        self.font_size_slider.setValue(
            max(9, min(28, self.settings.overlay_font_size))
        )
        self.font_size_slider.valueChanged.connect(self.set_overlay_font_size)
        self.font_size_value_label = QLabel(f"{self.font_size_slider.value()} pt")
        self.font_size_value_label.setObjectName("opacityLabel")
        font_size_row = QHBoxLayout()
        font_size_row.addWidget(QLabel("翻译字体大小"))
        font_size_row.addWidget(self.font_size_slider, 1)
        font_size_row.addWidget(self.font_size_value_label)

        self.monitor_result_window.set_background_opacity(
            self.background_opacity_slider.value()
        )
        self.monitor_result_window.set_text_opacity(self.text_opacity_slider.value())
        self.monitor_result_window.set_mask_opacity(self.mask_opacity_slider.value())
        self.monitor_result_window.set_translation_font_size(self.font_size_slider.value())

        self.status_label = QLabel("准备就绪。点击“截图翻译”后框选英文区域。")
        self.status_label.setObjectName("statusLabel")
        self.original_edit = QPlainTextEdit()
        self.original_edit.setReadOnly(True)
        self.original_edit.setPlaceholderText("OCR 识别出的英文会显示在这里")
        self.translated_edit = QPlainTextEdit()
        self.translated_edit.setReadOnly(True)
        self.translated_edit.setPlaceholderText("中文翻译会显示在这里")

        original_box = QGroupBox("识别结果")
        original_layout = QVBoxLayout(original_box)
        original_layout.addWidget(self.original_edit)
        translated_box = QGroupBox("翻译结果")
        translated_layout = QVBoxLayout(translated_box)
        translated_layout.addWidget(self.translated_edit)

        top = QVBoxLayout()
        top.addWidget(self.start_button)
        top.addWidget(self.monitor_button)
        top.addWidget(self.manage_regions_button)
        top.addWidget(self.overlay_lock_button)
        top.addWidget(self.settings_button)
        top.addLayout(background_opacity_row)
        top.addLayout(text_opacity_row)
        top.addLayout(mask_opacity_row)
        top.addLayout(font_size_row)
        top.addWidget(self.status_label)

        body = QWidget()
        body.setObjectName("mainRoot")
        layout = QVBoxLayout(body)
        layout.addLayout(top)
        layout.addWidget(original_box)
        layout.addWidget(translated_box)
        self.setCentralWidget(body)
        self.setStyleSheet(MAIN_STYLE_SHEET)

        try:
            self.hotkey_filter = GlobalHotkeyFilter(
                self.winId(), self.settings.hotkey, self.start_capture
            )
            QApplication.instance().installNativeEventFilter(self.hotkey_filter)
            self.status_label.setText(
                f"准备就绪。点击“截图翻译”或按 {self.settings.hotkey}，然后框选英文区域。"
            )
        except (RuntimeError, ValueError) as exc:
            self.status_label.setText(f"热键不可用：{exc}")

    def open_settings(self) -> None:
        old_hotkey = self.settings.hotkey
        if SettingsDialog(self.settings, self).exec() != QDialog.DialogCode.Accepted:
            return
        if self.settings.hotkey == old_hotkey:
            return
        self.unregister_hotkey()
        try:
            self.register_hotkey()
        except (RuntimeError, ValueError) as exc:
            self.settings.hotkey = old_hotkey
            save_settings(self.settings)
            try:
                self.register_hotkey()
            except (RuntimeError, ValueError):
                pass
            QMessageBox.warning(self, "热键设置失败", str(exc))

    def register_hotkey(self) -> None:
        self.hotkey_filter = GlobalHotkeyFilter(
            self.winId(), self.settings.hotkey, self.start_capture
        )
        QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        self.status_label.setText(
            f"准备就绪。点击“截图翻译”或按 {self.settings.hotkey}，然后框选英文区域。"
        )

    def unregister_hotkey(self) -> None:
        if self.hotkey_filter is not None:
            QApplication.instance().removeNativeEventFilter(self.hotkey_filter)
            self.hotkey_filter.unregister()
            self.hotkey_filter = None

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
        if dialog.monitor_full_screen:
            geometry = screen.geometry()
            full_rect = QRect(0, 0, geometry.width(), geometry.height())
            self.begin_monitor(screen, [full_rect], interval_ms)
            return

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

    def monitor_tick(self) -> None:
        if (
            not self.monitor_active
            or self.monitor_editing
            or self.monitor_screen is None
        ):
            return
        generation = self.monitor_generation
        for region_id, region in enumerate(self.monitor_regions):
            worker_key = (generation, region_id)
            if not region.enabled or worker_key in self.monitor_workers:
                continue
            try:
                image = self.capture_region(self.monitor_screen, region.rect)
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

    def capture_region(self, screen, rect: QRect) -> Image.Image:
        dpr = screen.devicePixelRatio()
        screen_geometry = screen.geometry()
        monitor = {
            "left": round((screen_geometry.x() + rect.x()) * dpr),
            "top": round((screen_geometry.y() + rect.y()) * dpr),
            "width": max(1, round(rect.width() * dpr)),
            "height": max(1, round(rect.height() * dpr)),
        }
        with MSS() as screen_capture:
            shot = screen_capture.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)

    def show_result(self, original: str, translated: str) -> None:
        self.original_edit.setPlainText(original)
        self.translated_edit.setPlainText(translated)
        self.status_label.setText("完成。")

    def show_error(self, message: str) -> None:
        self.status_label.setText("处理失败。")
        self.start_button.setEnabled(True)
        QMessageBox.warning(self, "Screen Translator", message)

    def closeEvent(self, event) -> None:
        self.stop_monitor()
        self.monitor_result_window.close()
        self.unregister_hotkey()
        super().closeEvent(event)


