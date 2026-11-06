# -*- coding: utf-8 -*-
"""主控制台深色主题（参照仪表盘设计稿）。仅作用于控制台窗口，不影响悬浮字幕。"""

DARK_QSS = """
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    color: #e5e7eb;
    font-size: 13px;
}
QWidget#root {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #060a12, stop:0.55 #0a1224, stop:1 #0d1830);
}

/* 通用按钮/勾选（对话框等未单独指定 objectName 时使用） */
QPushButton {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 8px; color: #e2e8f0; padding: 6px 14px;
}
QPushButton:hover { border-color: #3b82f6; }
QPushButton:disabled { color: #64748b; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid rgba(148, 163, 184, 0.4);
    background: rgba(30, 41, 59, 0.6);
}
QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }

/* ---------- 侧边栏 ---------- */
QFrame#sidebar {
    background: rgba(8, 13, 24, 245);
    border-right: 1px solid rgba(148, 163, 184, 0.12);
}
QLabel#brandIcon { color: #60a5fa; font-size: 18px; }
QLabel#brandTitle { color: #f1f5f9; font-size: 14px; font-weight: 700; }
QPushButton#nav, QPushButton#navActive {
    text-align: left; padding: 0 12px;
    border: none; border-radius: 8px;
    background: transparent; color: #94a3b8; font-size: 13px;
}
QPushButton#nav:hover { background: rgba(59, 130, 246, 0.12); color: #e2e8f0; }
QPushButton#navActive {
    background: rgba(37, 99, 235, 0.18); color: #dbeafe;
    border-left: 3px solid #3b82f6;
}

/* ---------- 卡片 ---------- */
QFrame#card {
    background: rgba(15, 23, 42, 0.72);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 14px;
}
QFrame#card[flash="true"] { border: 1px solid #3b82f6; }
QFrame#orbCard {
    background: qradialgradient(cx:0.5, cy:0.42, radius:0.95, fx:0.5, fy:0.42,
        stop:0 rgba(124, 58, 237, 0.38),
        stop:0.45 rgba(49, 46, 129, 0.30),
        stop:1 rgba(15, 23, 42, 0.28));
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 14px;
}
QLabel#cardTitle { color: #e2e8f0; font-size: 14px; font-weight: 700; }
QLabel#muted { color: #94a3b8; font-size: 12px; }
QLabel#timerLabel { color: #e2e8f0; font-size: 15px; font-weight: 700; }
QFrame#divider { background: rgba(148, 163, 184, 0.16); max-height: 1px; }

/* ---------- 输入控件 ---------- */
QComboBox {
    background: rgba(30, 41, 59, 0.55);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 8px; padding: 5px 10px; color: #e2e8f0; min-height: 20px;
}
QComboBox:hover { border-color: #3b82f6; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #0f172a; color: #e2e8f0;
    border: 1px solid #1e293b; selection-background-color: #1d4ed8;
}
QPushButton#ghostBtn {
    background: rgba(30, 41, 59, 0.45);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 8px; color: #cbd5e1; padding: 4px 10px;
}
QPushButton#ghostBtn:hover { border-color: #3b82f6; color: #e2e8f0; }
QPushButton#ghostBtn:disabled { color: #64748b; }

/* ---------- 主控按钮 ---------- */
QPushButton#btnStart {
    background: #16a34a; color: white; border: none; border-radius: 10px;
    font-weight: 700; font-size: 13px;
}
QPushButton#btnStart:hover { background: #22c55e; }
QPushButton#btnStart:disabled { background: #153a2a; color: #5f7a6c; }
QPushButton#btnPause {
    background: #f59e0b; color: #1f2937; border: none; border-radius: 10px;
    font-weight: 700; font-size: 13px;
}
QPushButton#btnPause:hover { background: #fbbf24; }
QPushButton#btnPause:disabled { background: #3a2f14; color: #8a7a52; }
QPushButton#btnStop {
    background: #ec4899; color: white; border: none; border-radius: 10px;
    font-weight: 700; font-size: 13px;
}
QPushButton#btnStop:hover { background: #f472b6; }
QPushButton#btnStop:disabled { background: #3a1a2b; color: #9a6b80; }
QPushButton#btnSettings {
    background: rgba(71, 85, 105, 0.9); color: #e2e8f0;
    border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 10px;
    font-weight: 600; font-size: 13px;
}
QPushButton#btnSettings:hover { background: #475569; }

/* ---------- 字幕列表 ---------- */
QTextEdit#chatView {
    background: transparent; border: none; padding: 4px; color: #e5e7eb;
}
QListWidget#testResult {
    background: rgba(2, 6, 23, 0.5);
    border: 1px solid rgba(148, 163, 184, 0.12);
    border-radius: 8px; color: #cbd5e1; font-size: 11px;
}
QProgressBar#levelBar {
    border: none; border-radius: 2px;
    background: rgba(148, 163, 184, 0.18);
}
QProgressBar#levelBar::chunk { border-radius: 2px; background: #34d399; }

/* ---------- 状态栏 ---------- */
QFrame#statusBar {
    background: rgba(8, 13, 24, 200);
    border-top: 1px solid rgba(148, 163, 184, 0.12);
    border-radius: 10px;
}
QLabel#statusDot { color: #22c55e; font-size: 12px; }
QLabel#statusText { color: #cbd5e1; font-weight: 600; }

/* ---------- 对话框（模型设置） ---------- */
QDialog { background: #0b1220; }
QLineEdit {
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 8px; padding: 5px 10px; color: #e2e8f0;
    selection-background-color: #1d4ed8;
}
QLineEdit:focus { border-color: #3b82f6; }
QSpinBox, QDoubleSpinBox {
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 6px; color: #e2e8f0; padding: 2px 6px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #3b82f6; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 16px; background: rgba(148, 163, 184, 0.12); border: none;
}
QCheckBox { color: #cbd5e1; spacing: 6px; }
QDialogButtonBox QPushButton {
    background: rgba(30, 41, 59, 0.85);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 8px; color: #e2e8f0; padding: 6px 18px; min-width: 72px;
}
QDialogButtonBox QPushButton:hover { border-color: #3b82f6; }

/* ---------- 滚动条 / 提示 ---------- */
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical {
    background: rgba(148, 163, 184, 0.35); border-radius: 4px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QToolTip {
    background: #0f172a; color: #e2e8f0;
    border: 1px solid #334155; padding: 4px 8px;
}
"""
