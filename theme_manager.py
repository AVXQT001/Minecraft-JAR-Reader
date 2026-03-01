from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication
import os

MINECRAFT_QSS = """
* {
    font-family: "Minecraft", "Segoe UI", "Tahoma", sans-serif;
    color: #E0E0E0;
    font-size: 10pt;
}

QMainWindow {
    background-color: rgba(49, 50, 51, {alpha}); /* Dark Stone Gray with transparency */
}

QSplitter::handle {
    background-color: rgba(26, 26, 26, {alpha});
    width: 4px;
}

/* Tree Views and Lists (File explorers) */
QListView, QTreeView, QListWidget, QScrollArea, QWidget#metaWidget {
    background-color: rgba(30, 30, 32, {alpha}); /* Deep Obsidian */
    border: 2px solid rgba(85, 85, 85, {alpha});
    border-radius: 4px;
    padding: 4px;
    color: #D3D3D3;
}

QListView::item:selected, QTreeView::item:selected, QListWidget::item:selected {
    background-color: #3E8E41; /* Creeper Green highlight */
    color: #FFFFFF;
}

/* Buttons mimicking MC Buttons */
QPushButton {
    background-color: rgba(140, 140, 140, {alpha}); /* Lighter base color for classic MC button */
    border-top: 2px solid rgba(255, 255, 255, {alpha});     /* Pure white top light */
    border-left: 2px solid rgba(255, 255, 255, {alpha});    /* Pure white left light */
    border-bottom: 2px solid rgba(55, 55, 55, {alpha});  /* Dark shadow bottom */
    border-right: 2px solid rgba(55, 55, 55, {alpha});   /* Dark shadow right */
    color: #FFFFFF;
    padding: 6px 12px 0px 12px; /* Asymmetrical to remove lower font blank space */
    outline: none;
}

QPushButton:hover {
    background-color: rgba(160, 160, 160, {alpha});
    color: #FFFFAA; /* Slight yellow tint on hover like true MC */
}

QPushButton:pressed {
    /* Invert the border lights for pressed effect */
    border-top: 2px solid rgba(55, 55, 55, {alpha});
    border-left: 2px solid rgba(55, 55, 55, {alpha});
    border-bottom: 2px solid rgba(255, 255, 255, {alpha});
    border-right: 2px solid rgba(255, 255, 255, {alpha});
    padding: 8px 10px -2px 14px; /* Shift text to simulate pressing down */
}

/* Metadata Labels */
QLabel {
    color: #DDDDDD;
}

QLabel#titleLabel {
    font-size: 14pt;
    color: #55FF55; /* Minecraft Green color code mapped roughly */
    margin-bottom: 10px;
}

QLabel#headerLabel {
    font-size: 12pt;
    color: #FFAA00; /* Gold */
    margin-top: 10px;
}

QLabel#infoLabel {
    font-size: 10pt;
    color: #AAAAAA; /* Gray */
}

/* ScrollBars */
QScrollBar:vertical {
    background: rgba(17, 17, 17, {alpha});
    width: 16px;
    margin: 0px 0px 0px 0px;
}

QScrollBar::handle:vertical {
    background: rgba(85, 85, 85, {alpha});
    min-height: 20px;
    border: 2px solid rgba(17, 17, 17, {alpha});
}

QScrollBar::handle:vertical:hover {
    background: rgba(119, 119, 119, {alpha});
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}

QTabWidget::pane {
    border: 2px solid rgba(85, 85, 85, {alpha});
    background-color: rgba(30, 30, 32, {alpha});
}

QTabBar::tab {
    background-color: rgba(140, 140, 140, {alpha});
    color: white;
    padding: 4px 12px;
    border: 2px solid rgba(55, 55, 55, {alpha});
    border-top: 2px solid rgba(255, 255, 255, {alpha});
    border-left: 2px solid rgba(255, 255, 255, {alpha});
}

QTabBar::tab:selected {
    background-color: rgba(100, 100, 100, {alpha});
    border-top: 2px solid rgba(55, 55, 55, {alpha});
    border-left: 2px solid rgba(55, 55, 55, {alpha});
    border-bottom: 2px solid rgba(255, 255, 255, {alpha});
    border-right: 2px solid rgba(255, 255, 255, {alpha});
}
"""


def apply_theme(app: QApplication, opacity: float = 1.0):
    """Applies the custom Minecraft QSS to the application, scaling alpha for background widgets."""

    # Check if font exists
    font_path = os.path.join(
        os.path.dirname(__file__), "assets", "fonts", "Minecraft.ttf"
    )
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QFont(families[0], 10))

    # Calculate CSS Alpha from 0-255 based on 0.0-1.0 float
    alpha_int = int(opacity * 255)

    app.setStyleSheet(MINECRAFT_QSS.replace("{alpha}", str(alpha_int)))
