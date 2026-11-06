# -*- coding: utf-8 -*-
"""主控制台的自定义控件：圆形聆听动效、滑动开关。"""

import math

from PySide6.QtWidgets import QWidget, QAbstractButton, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QFont


class ToggleSwitch(QAbstractButton):
    """iOS 风格滑动开关，可直接替换 QCheckBox（保留 isChecked/toggled/setChecked）。"""

    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._t = 1.0 if checked else 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._animate)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        if not self._timer.isActive():
            self._timer.start()

    def _animate(self):
        target = 1.0 if self.isChecked() else 0.0
        self._t += (target - self._t) * 0.25
        if abs(target - self._t) < 0.01:
            self._t = target
            self._timer.stop()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        track = QRectF(1, 3, w - 2, h - 6)
        on, off = QColor("#22c55e"), QColor("#334155")
        col = QColor(
            int(off.red() + (on.red() - off.red()) * self._t),
            int(off.green() + (on.green() - off.green()) * self._t),
            int(off.blue() + (on.blue() - off.blue()) * self._t),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        radius = track.height() / 2
        p.drawRoundedRect(track, radius, radius)
        knob = h - 10
        x = track.left() + 2 + (track.width() - knob - 4) * self._t
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, track.top() + 2, knob, knob))


class ListeningOrb(QWidget):
    """圆形“正在聆听”指示：渐变点阵环 + 随音量起伏的波形。"""

    _STATE_TEXT = {
        "idle": "就绪",
        "listening": "正在聆听",
        "paused": "已暂停",
        "saving": "保存中…",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(230, 230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._state = "idle"
        self._angle = 0.0
        self._level = 0.0
        self._amp = 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_state(self, state):
        self._state = state
        self.update()

    def set_level(self, peak):
        try:
            self._level = max(0.0, min(1.0, float(peak) / 20000.0))
        except (TypeError, ValueError):
            self._level = 0.0

    def _tick(self):
        active = self._state in ("listening", "saving")
        speed = 1.0 if active else 0.3
        self._angle = (self._angle + 1.6 * speed) % 360.0
        target = self._level if self._state == "listening" else 0.05
        self._amp += (target - self._amp) * 0.15
        self._phase += 0.28 * speed
        self.update()

    def _ring_color(self, t):
        stops = [
            (0.0, (244, 114, 182)),
            (0.35, (167, 139, 250)),
            (0.70, (52, 211, 153)),
            (1.0, (244, 114, 182)),
        ]
        t = t % 1.0
        for i in range(len(stops) - 1):
            a, ca = stops[i]
            b, cb = stops[i + 1]
            if a <= t <= b:
                f = (t - a) / (b - a) if b > a else 0.0
                return QColor(
                    int(ca[0] + (cb[0] - ca[0]) * f),
                    int(ca[1] + (cb[1] - ca[1]) * f),
                    int(ca[2] + (cb[2] - ca[2]) * f),
                )
        return QColor(244, 114, 182)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        cx, cy = rect.width() / 2.0, rect.height() / 2.0
        radius = max(10.0, min(rect.width(), rect.height()) / 2.0 - 18.0)

        # 渐变点阵环（右下留缺口，仿进度环）
        dots = 84
        for i in range(dots):
            frac = i / dots
            if 0.84 <= frac <= 0.97:
                continue
            ang = math.radians(frac * 360.0 + self._angle)
            x = cx + radius * math.cos(ang)
            y = cy + radius * math.sin(ang)
            col = self._ring_color(frac)
            col.setAlpha(235 if self._state == "listening" else 150)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            size = 2.4 if (i % 3 == 0) else 1.7
            p.drawEllipse(QPointF(x, y), size, size)

        # 内部波形
        bars = 9
        bw, gap = 4.0, 5.0
        total = bars * bw + (bars - 1) * gap
        for k in range(bars):
            base = 8.0 + 46.0 * self._amp * (
                0.45 + 0.55 * abs(math.sin(self._phase + k * 0.55)))
            x = cx - total / 2.0 + k * (bw + gap)
            col = self._ring_color(0.62 + 0.08 * math.sin(self._phase + k))
            col.setAlpha(235)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, cy - 22.0, bw, base), 2.0, 2.0)

        # 状态文字
        text = self._STATE_TEXT.get(self._state, "就绪")
        p.setPen(QColor("#e5e7eb" if self._state == "listening" else "#94a3b8"))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(15)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, cy + 30, rect.width(), 28),
                   Qt.AlignmentFlag.AlignCenter, text)
