"""Qt overlays used to select one or more screen regions."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QWidget


class CaptureOverlay(QDialog):
    selected = Signal(QRect)

    def __init__(
        self,
        screen_geometry: QRect,
        parent: QWidget | None = None,
        instruction: str = "拖动鼠标框选英文区域，按 Esc 取消",
    ):
        super().__init__(parent)
        self.setWindowTitle("选择翻译区域")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.instruction = instruction
        self.start_point: QPoint | None = None
        self.end_point: QPoint | None = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.reject()
            return True
        return super().event(event)

    def closeEvent(self, event) -> None:
        self.releaseKeyboard()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self.start_point is None or self.end_point is None:
            self.draw_instruction(painter, self.instruction)
            return
        selection = QRect(self.start_point, self.end_point).normalized()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(selection, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor(0, 190, 255), 2))
        painter.drawRect(selection)
        self.draw_selection_size(painter, selection)

    @staticmethod
    def draw_instruction(painter: QPainter, instruction: str) -> None:
        panel = QRect(20, 18, min(520, painter.device().width() - 40), 40)
        painter.setPen(QPen(QColor(117, 227, 245, 180), 1))
        painter.setBrush(QColor(8, 16, 24, 220))
        painter.drawRoundedRect(panel, 10, 10)
        painter.setPen(QColor(237, 246, 255))
        painter.drawText(panel.adjusted(14, 0, -14, 0), Qt.AlignmentFlag.AlignVCenter, instruction)

    @staticmethod
    def draw_selection_size(painter: QPainter, selection: QRect) -> None:
        label = f"{selection.width()} × {selection.height()}"
        label_rect = QRect(selection.left(), max(18, selection.top() - 28), 110, 22)
        painter.setPen(QPen(QColor(117, 227, 245, 180), 1))
        painter.setBrush(QColor(8, 16, 24, 220))
        painter.drawRoundedRect(label_rect, 6, 6)
        painter.setPen(QColor(237, 246, 255))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.position().toPoint()
            self.end_point = self.start_point
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start_point is not None:
            self.end_point = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.start_point is None:
            return
        self.end_point = event.position().toPoint()
        selection = QRect(self.start_point, self.end_point).normalized()
        if selection.width() >= 8 and selection.height() >= 8:
            self.selected.emit(selection)
            self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.reject()
        else:
            super().keyPressEvent(event)


class MultiRegionOverlay(QDialog):
    """用于一次选择多个监控区域，也支持运行中编辑已有区域。"""

    regions_selected = Signal(list)

    def __init__(
        self,
        screen_geometry: QRect,
        parent: QWidget | None = None,
        regions: list[QRect] | None = None,
        enabled: list[bool] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("选择监控区域")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self.regions = [QRect(rect) for rect in (regions or [])]
        self.enabled = list(enabled or [True] * len(self.regions))
        if len(self.enabled) < len(self.regions):
            self.enabled.extend([True] * (len(self.regions) - len(self.enabled)))
        self.active_index = -1
        self.hover_index = -1
        self.hover_action = ""
        self.hover_edges: set[str] = set()
        self.action = ""
        self.resize_edges: set[str] = set()
        self.start_point: QPoint | None = None
        self.origin_rect: QRect | None = None
        self.preview_rect: QRect | None = None
        # 四角用于双轴缩放，四边中点用于单轴缩放，框内用于整体移动。
        self.handle_size = 8
        self.handle_hit_size = 14
        self.move_hit_margin = 14
        self.minimum_region_size = 20

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

    def closeEvent(self, event) -> None:
        self.releaseKeyboard()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 145))

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        for region in self.regions:
            painter.fillRect(region, Qt.GlobalColor.transparent)
        if self.preview_rect is not None:
            painter.fillRect(self.preview_rect, Qt.GlobalColor.transparent)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        instruction = (
            "空白处拖动新增  ·  边中方块横/纵缩放  ·  四角斜向缩放  ·  "
            "框内整体拖动  ·  "
            "Space 启用/停用  ·  Delete 删除  ·  Enter 完成  ·  Esc 取消"
        )
        panel = QRect(20, 18, min(860, self.width() - 40), 40)
        painter.setPen(QPen(QColor(117, 227, 245, 180), 1))
        painter.setBrush(QColor(8, 16, 24, 220))
        painter.drawRoundedRect(panel, 10, 10)
        painter.setPen(QColor(237, 246, 255))
        painter.drawText(
            panel.adjusted(14, 0, -14, 0),
            Qt.AlignmentFlag.AlignVCenter,
            instruction,
        )

        colors = [
            QColor(0, 210, 255),
            QColor(255, 190, 60),
            QColor(120, 255, 150),
            QColor(220, 140, 255),
        ]
        for index, region in enumerate(self.regions):
            color = colors[index % len(colors)]
            if not self.enabled[index]:
                color = QColor(140, 150, 165)
            if index == self.active_index:
                color = QColor(255, 255, 255)
            painter.setPen(QPen(color, 2))
            # 画新区域边框前必须关闭填充，否则第二个及后续区域会被
            # 控制点画刷整块填满。
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(region)
            painter.fillRect(
                QRect(region.left(), region.top(), 54, 22),
                QColor(10, 15, 25, 210),
            )
            painter.setPen(color)
            label = f"区域 {index + 1}"
            if not self.enabled[index]:
                label += "（停用）"
            painter.drawText(region.left() + 7, region.top() + 16, label)

            painter.setPen(QPen(color, 1))
            painter.setBrush(QColor(255, 255, 255, 235))
            for handle in self.corner_handle_rects(region).values():
                painter.drawRect(handle)
            painter.setBrush(QColor(255, 205, 70, 240))
            for handle in self.edge_handle_rects(region).values():
                painter.drawRect(handle)

        if self.preview_rect is not None:
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine))
            # 预览框只画虚线边框，不能继承前一个控制点的黄色填充。
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.preview_rect)

    def corner_handle_rects(
        self, region: QRect, *, hit_test: bool = False
    ) -> dict[str, QRect]:
        """返回位于区域四角、用于斜向缩放的方形控制点。"""
        size = self.handle_hit_size if hit_test else self.handle_size
        half = size // 2
        return {
            "left|top": QRect(region.left() - half, region.top() - half, size, size),
            "right|top": QRect(region.right() - half, region.top() - half, size, size),
            "left|bottom": QRect(region.left() - half, region.bottom() - half, size, size),
            "right|bottom": QRect(region.right() - half, region.bottom() - half, size, size),
        }

    def edge_handle_rects(
        self, region: QRect, *, hit_test: bool = False
    ) -> dict[str, QRect]:
        """返回四边中点的方形单轴缩放控制点。"""
        size = self.handle_hit_size if hit_test else self.handle_size
        half = size // 2
        centers = {
            "top": QPoint(region.center().x(), region.top()),
            "right": QPoint(region.right(), region.center().y()),
            "bottom": QPoint(region.center().x(), region.bottom()),
            "left": QPoint(region.left(), region.center().y()),
        }
        return {
            edge: QRect(point.x() - half, point.y() - half, size, size)
            for edge, point in centers.items()
        }

    def move_hit_rect(self, region: QRect) -> QRect:
        """Expand the move hit area without changing the visible region."""
        margin = self.move_hit_margin
        return region.adjusted(-margin, -margin, margin, margin)

    def control_at(self, region: QRect, position: QPoint) -> tuple[str, set[str]]:
        # 小区域的控制点可能重叠，此时角点缩放优先。
        for edge_text, handle in self.corner_handle_rects(
            region, hit_test=True
        ).items():
            if handle.contains(position):
                return "resize", set(edge_text.split("|"))
        for edge, handle in self.edge_handle_rects(region, hit_test=True).items():
            if handle.contains(position):
                return "resize", {edge}
        if self.move_hit_rect(region).contains(position):
            return "move", set()
        return "", set()

    def hit_test(self, position: QPoint) -> tuple[int, str, set[str]]:
        # 重叠区域只允许最上层的一个区域响应。
        for index in range(len(self.regions) - 1, -1, -1):
            region = self.regions[index]
            action, edges = self.control_at(region, position)
            if action:
                return index, action or "select", edges
        return -1, "", set()

    def update_hover(self, position: QPoint) -> None:
        self.hover_index, self.hover_action, self.hover_edges = self.hit_test(position)
        if self.hover_action == "resize":
            if self.hover_edges in ({"left", "top"}, {"right", "bottom"}):
                cursor = Qt.CursorShape.SizeFDiagCursor
            elif self.hover_edges in ({"right", "top"}, {"left", "bottom"}):
                cursor = Qt.CursorShape.SizeBDiagCursor
            elif self.hover_edges in ({"left"}, {"right"}):
                cursor = Qt.CursorShape.SizeHorCursor
            else:
                cursor = Qt.CursorShape.SizeVerCursor
        elif self.hover_action == "move":
            cursor = Qt.CursorShape.SizeAllCursor
        elif self.hover_action == "select":
            cursor = Qt.CursorShape.ArrowCursor
        else:
            cursor = Qt.CursorShape.CrossCursor
        self.setCursor(cursor)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position().toPoint()
        index, action, edges = self.hit_test(position)
        if index < 0:
            self.active_index = -1
            self.action = "new"
            self.start_point = position
            self.preview_rect = QRect(position, position)
        else:
            self.active_index = index
            if action in ("move", "resize"):
                self.action = action
                self.start_point = position
                self.origin_rect = QRect(self.regions[index])
                self.resize_edges = edges
            else:
                self.action = ""
                self.start_point = None
                self.origin_rect = None
                self.resize_edges.clear()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start_point is None:
            self.update_hover(event.position().toPoint())
            return
        position = event.position().toPoint()
        delta = position - self.start_point
        if self.action == "new":
            self.preview_rect = QRect(self.start_point, position).normalized()
        elif self.action == "move" and self.origin_rect is not None:
            self.regions[self.active_index] = self.clamp_moved_rect(
                self.origin_rect.translated(delta)
            )
        elif self.action == "resize" and self.origin_rect is not None:
            self.regions[self.active_index] = self.resize_rect(
                self.origin_rect, delta, self.resize_edges
            )
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.start_point is None:
            return
        if self.action == "new" and self.preview_rect is not None:
            if (
                self.preview_rect.width() >= self.minimum_region_size
                and self.preview_rect.height() >= self.minimum_region_size
            ):
                self.regions.append(QRect(self.preview_rect))
                self.enabled.append(True)
                self.active_index = len(self.regions) - 1
        self.action = ""
        self.resize_edges.clear()
        self.start_point = None
        self.origin_rect = None
        self.preview_rect = None
        self.update_hover(event.position().toPoint())
        self.update()

    def clamp_moved_rect(self, rect: QRect) -> QRect:
        x = max(0, min(rect.x(), self.width() - rect.width()))
        y = max(0, min(rect.y(), self.height() - rect.height()))
        return QRect(x, y, rect.width(), rect.height())

    def resize_rect(self, origin: QRect, delta: QPoint, edges: set[str]) -> QRect:
        left = origin.left()
        right = origin.right()
        top = origin.top()
        bottom = origin.bottom()
        if "left" in edges:
            left = max(0, min(origin.left() + delta.x(), right - self.minimum_region_size + 1))
        if "right" in edges:
            right = min(self.width() - 1, max(origin.right() + delta.x(), left + self.minimum_region_size - 1))
        if "top" in edges:
            top = max(0, min(origin.top() + delta.y(), bottom - self.minimum_region_size + 1))
        if "bottom" in edges:
            bottom = min(self.height() - 1, max(origin.bottom() + delta.y(), top + self.minimum_region_size - 1))
        return QRect(QPoint(left, top), QPoint(right, bottom)).normalized()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.regions:
                self.regions_selected.emit([QRect(region) for region in self.regions])
                self.accept()
            return
        if event.key() == Qt.Key.Key_Delete and 0 <= self.active_index < len(self.regions):
            self.regions.pop(self.active_index)
            self.enabled.pop(self.active_index)
            self.active_index = min(self.active_index, len(self.regions) - 1)
            self.update()
            return
        if event.key() == Qt.Key.Key_Space and 0 <= self.active_index < len(self.regions):
            self.enabled[self.active_index] = not self.enabled[self.active_index]
            self.update()
            return
        super().keyPressEvent(event)
