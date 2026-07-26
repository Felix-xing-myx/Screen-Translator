"""Shared interaction helpers for frameless translation overlays."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget


class OverlayResizeMixin:
    """Resize a frameless overlay from one consistent client-side hit map.

    Native ``WM_NCHITTEST`` is still used by the windows for click-through and
    title-bar dragging.  Resizing itself is handled here so the visible edge,
    the cursor feedback and the geometry delta all share the same coordinate
    system.
    """

    resize_border = 14
    corner_border = 26

    def install_overlay_resize_filter(self) -> None:
        self._resize_edges: set[str] = set()
        self._resize_start_global: QPoint | None = None
        self._resize_origin_geometry: QRect | None = None
        self._drag_start_global: QPoint | None = None
        self._drag_origin_geometry: QRect | None = None
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def remove_overlay_resize_filter(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def _overlay_is_widget(self, watched) -> bool:
        if watched is self:
            return True
        card = getattr(self, "card", None)
        return isinstance(watched, QWidget) and card is not None and (
            watched is card or card.isAncestorOf(watched)
        )

    def _overlay_local_position(self, global_position: QPoint) -> QPoint:
        """Convert a screen position using the top-level frame geometry."""
        return global_position - self.frameGeometry().topLeft()

    def _overlay_edges(self, global_position: QPoint) -> set[str]:
        if getattr(self, "locked", False):
            return set()
        local = self._overlay_local_position(global_position)
        width = self.width()
        height = self.height()
        border = max(4, int(self.resize_border))
        corner = max(border + 4, int(self.corner_border))
        edges: set[str] = set()

        near_left = local.x() <= border
        near_right = local.x() >= width - border
        near_top = local.y() <= border
        near_bottom = local.y() >= height - border
        corner_left = local.x() <= corner
        corner_right = local.x() >= width - corner
        corner_top = local.y() <= corner
        corner_bottom = local.y() >= height - corner

        # Corner zones take priority over edge zones.
        if corner_left and corner_top:
            return {"left", "top"}
        if corner_right and corner_top:
            return {"right", "top"}
        if corner_left and corner_bottom:
            return {"left", "bottom"}
        if corner_right and corner_bottom:
            return {"right", "bottom"}
        if near_left:
            edges.add("left")
        if near_right:
            edges.add("right")
        if near_top:
            edges.add("top")
        if near_bottom:
            edges.add("bottom")
        return edges

    @staticmethod
    def _cursor_for_edges(edges: set[str]) -> Qt.CursorShape:
        diagonal = {
            frozenset(("left", "top")): Qt.CursorShape.SizeFDiagCursor,
            frozenset(("right", "bottom")): Qt.CursorShape.SizeFDiagCursor,
            frozenset(("right", "top")): Qt.CursorShape.SizeBDiagCursor,
            frozenset(("left", "bottom")): Qt.CursorShape.SizeBDiagCursor,
        }
        if frozenset(edges) in diagonal:
            return diagonal[frozenset(edges)]
        if edges & {"left", "right"}:
            return Qt.CursorShape.SizeHorCursor
        if edges & {"top", "bottom"}:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _set_resize_cursor(self, edges: set[str]) -> None:
        self.setCursor(self._cursor_for_edges(edges))

    def _resize_to(self, global_position: QPoint) -> None:
        origin = self._resize_origin_geometry
        start = self._resize_start_global
        if origin is None or start is None or not self._resize_edges:
            return
        delta = global_position - start
        left = origin.left()
        right = origin.right()
        top = origin.top()
        bottom = origin.bottom()
        minimum_width = self.minimumWidth()
        minimum_height = self.minimumHeight()

        if "left" in self._resize_edges:
            left = min(origin.left() + delta.x(), right - minimum_width + 1)
        if "right" in self._resize_edges:
            right = max(origin.right() + delta.x(), left + minimum_width - 1)
        if "top" in self._resize_edges:
            top = min(origin.top() + delta.y(), bottom - minimum_height + 1)
        if "bottom" in self._resize_edges:
            bottom = max(origin.bottom() + delta.y(), top + minimum_height - 1)

        self.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)).normalized())

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()

        # Keep an active drag/resize alive while the pointer passes over a
        # different child widget in this process.  Without this, a release on
        # a child could be forwarded to Qt and leave the interaction state
        # stuck.
        if event_type == QEvent.Type.MouseMove:
            if self._resize_edges:
                self._resize_to(event.globalPosition().toPoint())
                return True
            if self._drag_start_global is not None and self._drag_origin_geometry is not None:
                global_position = event.globalPosition().toPoint()
                delta = global_position - self._drag_start_global
                self.move(self._drag_origin_geometry.topLeft() + delta)
                return True

        if event_type == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if self._resize_edges or self._drag_start_global is not None:
                    self._resize_edges.clear()
                    self._resize_start_global = None
                    self._resize_origin_geometry = None
                    self._drag_start_global = None
                    self._drag_origin_geometry = None
                    self._set_resize_cursor(set())
                    return True

        if not self._overlay_is_widget(watched):
            return super().eventFilter(watched, event)
        if getattr(self, "locked", False):
            return super().eventFilter(watched, event)

        if event_type == QEvent.Type.MouseMove:
            global_position = event.globalPosition().toPoint()
            self._set_resize_cursor(self._overlay_edges(global_position))
        elif event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                global_position = event.globalPosition().toPoint()
                edges = self._overlay_edges(global_position)
                if edges:
                    self._resize_edges = edges
                    self._resize_start_global = global_position
                    self._resize_origin_geometry = QRect(self.geometry())
                    self._set_resize_cursor(edges)
                    return True
                # The result overlays have no editable controls.  Make the
                # whole non-edge surface draggable, preserving the original
                # interaction model while leaving all border zones to resize.
                self._drag_start_global = global_position
                self._drag_origin_geometry = QRect(self.frameGeometry())
                return True
        elif event_type == QEvent.Type.MouseButtonRelease:
            return False
        return super().eventFilter(watched, event)

    @staticmethod
    def _message_global_position(message) -> QPoint | None:
        """Read the signed screen coordinates carried by WM_NCHITTEST."""
        import ctypes

        try:
            value = int(message.lParam)
        except (AttributeError, TypeError, ValueError):
            return None
        x = ctypes.c_short(value & 0xFFFF).value
        y = ctypes.c_short((value >> 16) & 0xFFFF).value
        return QPoint(x, y)

    def _overlay_title_hit_test(self, global_position: QPoint | None = None) -> bool:
        title_bar = getattr(self, "title_bar", None)
        if title_bar is None:
            return False
        position = global_position if global_position is not None else QCursor.pos()
        top_left = title_bar.mapTo(self, QPoint(0, 0))
        return QRect(top_left, title_bar.size()).contains(self.mapFromGlobal(position))
