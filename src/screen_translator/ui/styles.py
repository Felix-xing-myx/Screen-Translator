"""Shared application style sheet and theme extension point."""

from __future__ import annotations


MAIN_STYLE_SHEET = """
QMainWindow, QWidget#mainRoot {
    background: #0b1020;
    color: #e5e7eb;
}
QGroupBox {
    background: #111827;
    border: 1px solid #26344d;
    border-radius: 12px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
    color: #bfdbfe;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QPlainTextEdit {
    background: #0f172a;
    border: 1px solid #24324a;
    border-radius: 8px;
    color: #f8fafc;
    selection-background-color: #2563eb;
    padding: 8px;
}
QPushButton {
    background: #2563eb;
    border: 1px solid #3b82f6;
    border-radius: 8px;
    color: white;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #3b82f6; }
QPushButton:pressed { background: #1d4ed8; }
QPushButton:disabled { background: #26344d; color: #94a3b8; border-color: #26344d; }
QSlider::groove:horizontal { height: 5px; background: #26344d; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; background: #60a5fa; border-radius: 8px; }
QLabel#statusLabel { color: #93c5fd; padding: 4px 0; }
QLabel#opacityLabel { color: #cbd5e1; }
"""
