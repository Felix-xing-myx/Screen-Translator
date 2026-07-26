"""Theme tokens and the shared application style sheet.

The UI keeps its visual language in one place so the current dark, minimal
line-work theme can be replaced without changing workflow code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CHECKMARK_ASSET = (Path(__file__).resolve().parents[1] / "assets" / "checkbox-check.svg").as_posix()


@dataclass(frozen=True)
class ThemeTokens:
    """Design tokens for one complete application theme."""

    window: str = "#090e12"
    surface: str = "#0d1419"
    surface_alt: str = "#111b21"
    surface_elevated: str = "#162229"
    input_surface: str = "#0a1116"
    border: str = "#2c3c45"
    border_strong: str = "#5d707a"
    text: str = "#e7eef1"
    text_muted: str = "#a1afb5"
    text_dim: str = "#6b7b83"
    accent: str = "#6bd8ff"
    accent_bright: str = "#c3f1ff"
    accent_deep: str = "#1b617d"
    action: str = "#f39a32"
    action_bright: str = "#ffb55e"
    success: str = "#7bd69d"
    warning: str = "#f0c36d"
    danger: str = "#ff7777"


DARK_THEME = ThemeTokens()


def build_stylesheet(theme: ThemeTokens = DARK_THEME) -> str:
    """Build the application QSS from theme tokens."""

    return f"""
* {{
    font-family: "Bahnschrift", "Segoe UI", "Microsoft YaHei UI", sans-serif;
    outline: none;
}}

QLabel {{
    color: {theme.text};
}}

QMainWindow, QDialog, QWidget#mainRoot {{
    background: {theme.window};
    color: {theme.text};
}}

QDialog#settingsDialog {{
    background: {theme.window};
}}

QWidget#settingsPage {{
    background: {theme.surface};
    color: {theme.text};
}}

QWidget#mainRoot {{
    border: 1px solid {theme.border};
}}

QFrame#topBar {{
    background: {theme.surface};
    border: 1px solid {theme.border};
    border-left: 2px solid {theme.accent_deep};
    border-radius: 8px;
}}

QFrame#sectionCard, QFrame#heroCard, QFrame#controlGroup,
QFrame#resultPanel {{
    background: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: 8px;
}}

QFrame#heroCard {{
    background: {theme.surface_alt};
    border-color: {theme.border_strong};
    border-left: 2px solid {theme.accent_deep};
    border-top-color: {theme.accent_deep};
    border-top-width: 2px;
}}

QFrame#controlGroup {{
    background: {theme.input_surface};
}}

QFrame#sectionRule {{
    background: {theme.border};
    border: none;
    max-height: 1px;
}}

QLabel#brandMark {{
    background: rgba(107, 216, 255, 10);
    border: 1px solid {theme.border_strong};
    border-radius: 7px;
    padding: 2px;
}}

QLabel#brandTitle {{
    color: {theme.text};
    font-size: 20px;
    font-weight: 600;
}}

QLabel#brandSubtitle, QLabel#sectionSubtitle, QLabel#hintLabel {{
    color: {theme.text_muted};
}}

QLabel#externalLinkLabel {{
    color: {theme.accent_bright};
}}

QLabel#externalLinkLabel:hover {{
    color: {theme.text};
}}

QLabel#brandSubtitle {{
    font-size: 11px;
}}

QLabel#sectionSubtitle, QLabel#hintLabel {{
    font-size: 11px;
}}

QLabel#eyebrowLabel {{
    color: {theme.accent};
    font-size: 10px;
    font-weight: 600;
}}

QLabel#sectionTitle {{
    color: {theme.text};
    font-size: 14px;
    font-weight: 600;
}}

QLabel#statusBadge {{
    background: transparent;
    border: 1px solid {theme.border_strong};
    border-radius: 5px;
    color: {theme.accent_bright};
    padding: 6px 10px;
    font-size: 11px;
}}

QLabel#statusBadge[state="running"] {{
    border-color: {theme.action};
    color: {theme.action_bright};
}}

QLabel#statusBadge[state="error"] {{
    border-color: {theme.danger};
    color: {theme.danger};
}}

QLabel#microLabel {{
    color: {theme.accent_bright};
    font-size: 10px;
    font-weight: 600;
}}

QPushButton {{
    background: transparent;
    border: 1px solid {theme.border_strong};
    border-radius: 5px;
    color: {theme.text};
    min-height: 34px;
    padding: 6px 13px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: rgba(107, 216, 255, 16);
    border-color: {theme.accent};
    color: {theme.accent_bright};
}}

QPushButton:pressed {{
    background: rgba(107, 216, 255, 28);
    border-color: {theme.accent_bright};
}}

QPushButton:disabled {{
    background: transparent;
    border-color: {theme.border};
    color: {theme.text_dim};
}}

QPushButton[role="primary"] {{
    background: transparent;
    border: 1px solid {theme.action};
    border-radius: 5px;
    color: {theme.action_bright};
    min-height: 42px;
}}

QPushButton[role="primary"]:hover {{
    background: rgba(243, 154, 50, 24);
    border-color: {theme.action_bright};
    color: #fff1df;
}}

QPushButton[role="primary"]:pressed {{
    background: rgba(243, 154, 50, 42);
}}

QPushButton[role="settings"] {{
    background: transparent;
    border-color: {theme.accent};
    color: {theme.accent_bright};
    min-height: 34px;
}}

QPushButton[role="settings"]:hover {{
    background: rgba(107, 216, 255, 22);
}}

QPushButton[role="ghost"] {{
    background: transparent;
    border-color: transparent;
    color: {theme.text_muted};
}}

QPushButton[role="ghost"]:hover {{
    background: rgba(107, 216, 255, 12);
    border-color: {theme.border};
    color: {theme.text};
}}

QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {theme.input_surface};
    border: 1px solid {theme.border};
    border-radius: 5px;
    color: {theme.text};
    selection-background-color: {theme.accent_deep};
    padding: 7px 9px;
    font-size: 12px;
}}

QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {theme.accent};
}}

QPlainTextEdit {{
    padding: 10px;
}}

QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QLineEdit:hover, QPlainTextEdit:hover {{
    border-color: {theme.border_strong};
}}

QComboBox::drop-down {{
    width: 28px;
    border: none;
    border-left: 1px solid {theme.border};
}}

QComboBox QAbstractItemView {{
    background: {theme.surface_elevated};
    border: 1px solid {theme.border_strong};
    color: {theme.text};
    selection-background-color: {theme.accent_deep};
    selection-color: {theme.text};
    padding: 4px;
}}

QCheckBox {{
    color: {theme.text_muted};
    spacing: 8px;
    font-size: 12px;
}}

QCheckBox:hover {{
    color: {theme.text};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background: transparent;
    border: 1px solid {theme.border_strong};
    border-radius: 4px;
}}

QCheckBox::indicator:hover {{
    border-color: {theme.accent};
}}

QCheckBox::indicator:checked {{
    background: {theme.accent_deep};
    border-color: {theme.accent};
    image: url("{CHECKMARK_ASSET}");
}}

QTabWidget::pane {{
    background: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background: transparent;
    color: {theme.text_dim};
    padding: 10px 20px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-bottom-color: {theme.border};
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    font-size: 12px;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    color: {theme.accent_bright};
    border-color: {theme.accent};
    border-bottom-color: {theme.surface};
    background: {theme.surface};
}}

QTabBar::tab:hover:!selected {{
    color: {theme.text};
    border-top-color: {theme.border_strong};
}}

QSlider::groove:horizontal {{
    height: 1px;
    background: {theme.border_strong};
}}

QSlider::sub-page:horizontal {{
    background: {theme.accent};
}}

QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -5px 0;
    background: {theme.window};
    border: 1px solid {theme.accent};
    border-radius: 6px;
}}

QSlider::handle:horizontal:hover {{
    background: {theme.accent};
}}

QProgressBar {{
    background: {theme.border};
    border: none;
    border-radius: 2px;
    text-align: center;
}}

QProgressBar::chunk {{
    background: {theme.accent};
    border-radius: 2px;
}}

QSplitter::handle {{
    background: {theme.border};
}}

QSplitter::handle:hover {{
    background: {theme.accent_deep};
}}

QScrollArea, QScrollArea > QWidget,
QScrollArea > QWidget#qt_scrollarea_viewport {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical {{ width: 8px; }}
QScrollBar:horizontal {{ height: 8px; }}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {theme.border_strong};
    border-radius: 0;
    min-height: 24px;
    min-width: 24px;
}}

QScrollBar::handle:hover {{
    background: {theme.accent_deep};
}}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    border: none;
}}

QDialogButtonBox QPushButton {{
    min-width: 80px;
}}

QGroupBox {{
    background: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    color: {theme.text};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {theme.accent};
    background: {theme.window};
}}

QLabel#statusLabel {{ color: {theme.accent_bright}; }}

QToolTip {{
    background: {theme.surface_elevated};
    border: 1px solid {theme.border_strong};
    color: {theme.text};
    padding: 5px 7px;
}}
"""


MAIN_STYLE_SHEET = build_stylesheet()
