# -*- coding: utf-8 -*-
"""字幕悬浮窗：打字机、节流重绘、HTML 转义、左右拖拽、全屏、长文本保护、
隐藏、平滑滚动、鼠标穿透、turn 原子提交、按标点截断拆分。
"""
import math
from html import escape as html_escape

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel,
    QPushButton, QSlider, QColorDialog, QFrame, QApplication,
)
from PySide6.QtCore import Qt, Slot, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QCursor

from ai_interpreter.text_utils import split_aligned
from ai_interpreter.ui.theme import DARK_QSS


# ============ 悬浮控制栏 ============
class TopControlBar(QFrame):
    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.main_win = parent_window
        self.setStyleSheet("""
            TopControlBar { background-color: rgba(30, 30, 30, 230); border-radius: 8px; }
            QLabel { color: white; font-family: "Microsoft YaHei"; font-size: 12px; }
            QPushButton {
                color: white; background-color: transparent;
                border: 1px solid rgba(255,255,255,50);
                border-radius: 4px; padding: 2px 8px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,30); }
            QPushButton:checked { background-color: #1976d2; border: none; }
            QSlider::groove:horizontal {
                border: 1px solid #999; height: 4px; background: #333; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #1976d2; width: 12px; margin: -5px 0; border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        self.btn_bilingual = QPushButton("双语")
        self.btn_bilingual.setCheckable(True)
        self.btn_bilingual.setChecked(True)
        self.btn_source = QPushButton("原文")
        self.btn_source.setCheckable(True)
        self.btn_target = QPushButton("译文")
        self.btn_target.setCheckable(True)
        self.btn_bilingual.clicked.connect(lambda: self._set_mode("bilingual"))
        self.btn_source.clicked.connect(lambda: self._set_mode("source"))
        self.btn_target.clicked.connect(lambda: self._set_mode("target"))
        layout.addWidget(self.btn_bilingual)
        layout.addWidget(self.btn_source)
        layout.addWidget(self.btn_target)
        layout.addWidget(QLabel(" | "))

        layout.addWidget(QLabel("译文:"))
        self.btn_tgt_font_minus = QPushButton("-")
        self.btn_tgt_font_minus.setFixedSize(22, 22)
        self.lbl_tgt_font_size = QLabel("36")
        self.btn_tgt_font_plus = QPushButton("+")
        self.btn_tgt_font_plus.setFixedSize(22, 22)
        self.btn_tgt_font_minus.clicked.connect(lambda: self._change_tgt_font(-2))
        self.btn_tgt_font_plus.clicked.connect(lambda: self._change_tgt_font(2))
        layout.addWidget(self.btn_tgt_font_minus)
        layout.addWidget(self.lbl_tgt_font_size)
        layout.addWidget(self.btn_tgt_font_plus)
        layout.addWidget(QLabel(" | "))

        layout.addWidget(QLabel("原文:"))
        self.btn_src_font_minus = QPushButton("-")
        self.btn_src_font_minus.setFixedSize(22, 22)
        self.lbl_src_font_size = QLabel("22")
        self.btn_src_font_plus = QPushButton("+")
        self.btn_src_font_plus.setFixedSize(22, 22)
        self.btn_src_font_minus.clicked.connect(lambda: self._change_src_font(-2))
        self.btn_src_font_plus.clicked.connect(lambda: self._change_src_font(2))
        layout.addWidget(self.btn_src_font_minus)
        layout.addWidget(self.lbl_src_font_size)
        layout.addWidget(self.btn_src_font_plus)
        layout.addWidget(QLabel(" | "))

        self.btn_color_tgt = QPushButton("译文色")
        self.btn_color_src = QPushButton("原文色")
        self.btn_color_bg = QPushButton("背景色")
        self.btn_color_tgt.clicked.connect(self._pick_tgt_color)
        self.btn_color_src.clicked.connect(self._pick_src_color)
        self.btn_color_bg.clicked.connect(self._pick_bg_color)
        layout.addWidget(self.btn_color_tgt)
        layout.addWidget(self.btn_color_src)
        layout.addWidget(self.btn_color_bg)
        layout.addWidget(QLabel(" | "))

        layout.addWidget(QLabel("透明:"))
        self.slider_bg = QSlider(Qt.Orientation.Horizontal)
        self.slider_bg.setRange(0, 255)
        self.slider_bg.setValue(180)
        self.slider_bg.setFixedWidth(60)
        self.slider_bg.valueChanged.connect(self.main_win.set_bg_alpha)
        layout.addWidget(self.slider_bg)

        self.btn_typing = QPushButton("打字机")
        self.btn_typing.setCheckable(True)
        self.btn_typing.setChecked(True)
        self.btn_typing.clicked.connect(lambda c: self.main_win.set_typing_enabled(c))
        layout.addWidget(self.btn_typing)

        layout.addStretch()

        self.btn_hide = QPushButton("隐藏")
        self.btn_hide.setStyleSheet("""
            QPushButton { color: #ff8a80; border: 1px solid rgba(255,138,128,100); }
            QPushButton:hover { background-color: rgba(255,138,128,50); }
        """)
        self.btn_hide.clicked.connect(self.main_win.hide_requested.emit)
        layout.addWidget(self.btn_hide)

        self.btn_fullscreen = QPushButton("全屏")
        self.btn_fullscreen.clicked.connect(self.main_win.toggle_fullscreen)
        layout.addWidget(self.btn_fullscreen)

    def _set_mode(self, mode):
        self.btn_bilingual.setChecked(mode == "bilingual")
        self.btn_source.setChecked(mode == "source")
        self.btn_target.setChecked(mode == "target")
        self.main_win.set_display_mode(mode)

    def _change_tgt_font(self, delta):
        new_size = max(12, self.main_win._base_tgt_font_size + delta)
        self.main_win.set_font_sizes(tgt_size=new_size)

    def _change_src_font(self, delta):
        new_size = max(10, self.main_win._base_src_font_size + delta)
        self.main_win.set_font_sizes(src_size=new_size)

    def _pick_color(self, initial, title):
        """打开与主界面同配色的取色窗（强制非原生 + 深色样式）。"""
        self.main_win._hide_timer.stop()
        dlg = QColorDialog(initial, self.main_win)
        dlg.setWindowTitle(title)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setStyleSheet(DARK_QSS)
        if dlg.exec():
            return dlg.selectedColor()
        return None

    def _pick_tgt_color(self):
        c = self._pick_color(self.main_win._text_color, "选择译文颜色")
        if c is not None and c.isValid():
            self.main_win.set_text_color(c)

    def _pick_src_color(self):
        c = self._pick_color(self.main_win._source_color, "选择原文颜色")
        if c is not None and c.isValid():
            self.main_win.set_source_color(c)

    def _pick_bg_color(self):
        c = self._pick_color(self.main_win._bg_color, "选择背景颜色")
        if c is not None and c.isValid():
            self.main_win.set_bg_color(c)


# ============ 字幕主窗口 ============
class LyricWindow(QWidget):
    hide_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None
        self._resize_edge = None
        self._resize_start_geom = None
        self._resize_start_pos = None

        self._base_tgt_font_size = 36
        self._base_src_font_size = 30
        self._tgt_font_size = self._base_tgt_font_size
        self._src_font_size = self._base_src_font_size

        self._text_color = QColor(255, 255, 255)
        self._source_color = QColor(180, 180, 180)
        self._bg_color = QColor(0, 0, 0, 255)

        self.is_fullscreen = False
        self._normal_geometry = None
        self.display_mode = "bilingual"
        self._click_through = False

        self._history = []
        self._pending_source = ""
        self._pending_target = ""
        self._max_history = 50

        self._turn_src_full = ""
        self._turn_tgt_full = ""
        self._src_done = False
        self._tgt_done = False
        self._turn_committed = False

        self._auto_follow = True
        self._render_pending = False

        self._typing_enabled = True
        self._type_tick_ms = 15
        self._type_min_chars = 1
        self._type_fast_threshold = 40
        self._type_max_chars = 4
        self._type_finishing_speed = 3

        self._src_char_buf = []
        self._tgt_char_buf = []
        self._src_finishing = False
        self._tgt_finishing = False

        self._type_timer = QTimer(self)
        self._type_timer.setInterval(self._type_tick_ms)
        self._type_timer.timeout.connect(self._on_type_tick)

        self._commit_timeout = QTimer(self)
        self._commit_timeout.setSingleShot(True)
        self._commit_timeout.timeout.connect(self._force_commit)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(300)
        self._hide_timer.timeout.connect(self._hide_control_bar)

        self._build_ui()
        self.apply_style()

    def _build_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            init_width = int(sg.width() * 0.67)
            init_height = 160
            x = sg.x() + (sg.width() - init_width) // 2
            y = sg.y() + sg.height() - init_height - 20
            self.setGeometry(x, y, init_width, init_height)
        else:
            self.resize(1000, 160)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)

        self.history_area = QTextEdit()
        self.history_area.setReadOnly(True)
        self.history_area.setFrameShape(QTextEdit.Shape.NoFrame)
        self.history_area.setStyleSheet("background: transparent; border: none;")
        self.history_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_layout.addWidget(self.history_area, 1)

        # 连续平滑上滚（类似电影片头）：定时器逐帧缓动，不再反复重启补间动画
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(16)
        self._scroll_timer.timeout.connect(self._scroll_tick)
        self._programmatic_scroll = False
        self._history_rev = 0
        self._history_rendered_rev = -1
        self._history_window = 8
        self._crawl_pending = False
        self._render_jump = False
        self._history_rendered_exclude = None

        # 全屏阅读停留：当前大字幕在提交后再停留一段时间才推入历史区，
        # 时长随句长增加（按人类阅读习惯），避免刚读完就被推走。
        self._hold_entry = None
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_timeout)
        self._hold_base_ms = 500
        self._hold_per_char_ms = 30
        self._hold_min_ms = 800
        self._hold_max_ms = 2200
        self.history_area.verticalScrollBar().valueChanged.connect(
            self._on_history_scroll_changed)

        self.current_area = QLabel("等待字幕…")
        self.current_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_area.setWordWrap(True)
        self.current_area.setMaximumHeight(200)
        self.main_layout.addWidget(self.current_area, 0)

        self.control_bar = TopControlBar(self)
        self.control_bar.hide()
        self.control_bar.setFixedHeight(60)

    def _schedule_render(self):
        if self._render_pending:
            return
        self._render_pending = True
        QTimer.singleShot(16, self._do_render)

    def _do_render(self):
        self._render_pending = False
        self._render_content()

    def _on_history_scroll_changed(self, value):
        if self._programmatic_scroll:
            return
        sb = self.history_area.verticalScrollBar()
        self._auto_follow = (sb.maximum() - value < 40)

    def _set_scroll_value(self, value):
        self._programmatic_scroll = True
        try:
            self.history_area.verticalScrollBar().setValue(value)
        finally:
            self._programmatic_scroll = False

    def _start_scroll(self):
        """启动平滑上滚；用户手动上滚后不再自动跟随。"""
        if not self._auto_follow:
            return
        if not self._scroll_timer.isActive():
            self._scroll_timer.start()

    def _scroll_tick(self):
        """每帧向底部缓动一小步，形成平滑的向上滚动。"""
        sb = self.history_area.verticalScrollBar()
        target = sb.maximum()
        cur = sb.value()
        if self._auto_follow and cur < target:
            diff = target - cur
            step = max(1, min(24, int(diff * 0.08) + 1))
            self._set_scroll_value(min(target, cur + step))
            return
        # 已到底：结束本次滚动，并裁掉为制造位移而临时多留的旧字幕
        self._scroll_timer.stop()
        if self._crawl_pending:
            self._crawl_pending = False
            self._render_history(self._history_rendered_exclude, extra=0)

    def _smooth_scroll_to_bottom(self):
        self._start_scroll()

    # ---- 阅读停留：当前大字幕 → 历史 ----
    def _hold_ms(self, entry):
        src, tgt = entry
        chars = max(len(tgt or ""), len(src or ""))
        ms = self._hold_base_ms + chars * self._hold_per_char_ms
        return int(max(self._hold_min_ms, min(ms, self._hold_max_ms)))

    def _start_hold(self, entry):
        self._hold_entry = entry
        self._hold_timer.start(self._hold_ms(entry))
        self._schedule_render()

    def _on_hold_timeout(self):
        self._hold_entry = None
        self._schedule_render()

    def _compute_exclude_last(self):
        """历史区是否要排除最后一条（因为它正作为大字幕显示中）。"""
        if self._hold_entry is not None:
            return True
        if self._pending_source or self._pending_target:
            return False
        return bool(self._history)

    def _calc_chars(self, queue_len):
        if queue_len <= self._type_min_chars:
            return self._type_min_chars
        ratio = min(1.0, queue_len / self._type_fast_threshold)
        return max(self._type_min_chars,
                   int(self._type_max_chars * math.sqrt(ratio)))

    def _on_type_tick(self):
        speed = self._type_finishing_speed if (
            self._src_finishing or self._tgt_finishing) else 1
        changed = False

        if self._src_char_buf:
            n = min(self._calc_chars(len(self._src_char_buf)) * speed,
                    len(self._src_char_buf))
            self._pending_source += "".join(self._src_char_buf[:n])
            del self._src_char_buf[:n]
            changed = True

        if self._tgt_char_buf:
            n = min(self._calc_chars(len(self._tgt_char_buf)) * speed,
                    len(self._tgt_char_buf))
            self._pending_target += "".join(self._tgt_char_buf[:n])
            del self._tgt_char_buf[:n]
            changed = True

        if changed:
            self._schedule_render()

        if self._src_finishing and not self._src_char_buf:
            self._do_finish_source()
        if self._tgt_finishing and not self._tgt_char_buf:
            self._do_finish_target()

        if (not self._src_char_buf and not self._tgt_char_buf
                and not self._src_finishing and not self._tgt_finishing):
            self._type_timer.stop()
            if self._turn_committed:
                self._finalize_committed_turn()

    def _ensure_typing(self):
        if self._typing_enabled and not self._type_timer.isActive():
            self._type_timer.start()

    def _flush_all_buffers(self):
        if self._src_char_buf:
            self._pending_source += "".join(self._src_char_buf)
            self._src_char_buf.clear()
        if self._tgt_char_buf:
            self._pending_target += "".join(self._tgt_char_buf)
            self._tgt_char_buf.clear()

    def _maybe_commit_turn(self):
        if self._src_done and self._tgt_done:
            self._commit_timeout.stop()
            self._turn_committed = True
            if (not self._src_char_buf and not self._tgt_char_buf
                    and not self._src_finishing and not self._tgt_finishing):
                self._finalize_committed_turn()
        elif self._src_done or self._tgt_done:
            if not self._commit_timeout.isActive():
                self._commit_timeout.start(8000)

    def _finalize_committed_turn(self):
        if not self._turn_committed:
            return
        src = self._turn_src_full.strip()
        tgt = self._turn_tgt_full.strip()
        if src or tgt:
            entry = (src, tgt)
            if not self._history or self._history[-1] != entry:
                self._history.append(entry)
                if len(self._history) > self._max_history:
                    self._history.pop(0)
                self._history_rev += 1
                # 全屏时让这一条继续作为大字幕停留一会儿，再推入历史
                if self.is_fullscreen:
                    self._start_hold(entry)
        self._pending_source = ""
        self._pending_target = ""
        self._turn_src_full = ""
        self._turn_tgt_full = ""
        self._src_done = False
        self._tgt_done = False
        self._turn_committed = False
        self._schedule_render()

    def _force_commit(self):
        self._turn_committed = True
        self._src_finishing = True
        self._tgt_finishing = True
        self._ensure_typing()
        if not self._src_char_buf and not self._tgt_char_buf:
            self._finalize_committed_turn()

    @Slot(str)
    def append_source(self, delta):
        if not delta:
            return
        if not self._typing_enabled:
            self._pending_source += delta
            self._schedule_render()
            return
        self._src_char_buf.extend(delta)
        self._ensure_typing()

    @Slot(str)
    def finish_source(self, full_text):
        self._turn_src_full = (full_text or "").strip()
        self._src_done = True
        if not self._typing_enabled:
            self._pending_source = self._turn_src_full
            self._schedule_render()
        elif self._src_char_buf:
            self._src_finishing = True
            self._ensure_typing()
        else:
            self._do_finish_source()
        self._maybe_commit_turn()

    def _do_finish_source(self):
        self._src_finishing = False
        if self._turn_src_full:
            self._pending_source = self._turn_src_full
            self._schedule_render()
        self._maybe_commit_turn()

    @Slot(str)
    def append_target(self, delta):
        if not delta:
            return
        if not self._typing_enabled:
            self._pending_target += delta
            self._schedule_render()
            return
        self._tgt_char_buf.extend(delta)
        self._ensure_typing()

    @Slot(str)
    def finish_target(self, full_text):
        self._turn_tgt_full = (full_text or "").strip()
        self._tgt_done = True
        if not self._typing_enabled:
            self._pending_target = self._turn_tgt_full
            self._schedule_render()
        elif self._tgt_char_buf:
            self._tgt_finishing = True
            self._ensure_typing()
        else:
            self._do_finish_target()
        self._maybe_commit_turn()

    def _do_finish_target(self):
        if self._src_char_buf:
            self._pending_source += "".join(self._src_char_buf)
            self._src_char_buf.clear()
        if self._turn_src_full:
            self._pending_source = self._turn_src_full
        self._src_finishing = False

        self._tgt_finishing = False
        if self._turn_tgt_full:
            self._pending_target = self._turn_tgt_full
        self._maybe_commit_turn()

    def set_typing_enabled(self, enabled):
        self._typing_enabled = enabled
        if not enabled:
            self._flush_all_buffers()
            self._type_timer.stop()
            if self._src_finishing and not self._src_char_buf:
                self._do_finish_source()
            if self._tgt_finishing and not self._tgt_char_buf:
                self._do_finish_target()
            self._schedule_render()

    def reset(self):
        self._history.clear()
        self._pending_source = ""
        self._pending_target = ""
        self._src_char_buf.clear()
        self._tgt_char_buf.clear()
        self._turn_src_full = ""
        self._turn_tgt_full = ""
        self._src_done = False
        self._tgt_done = False
        self._turn_committed = False
        self._src_finishing = False
        self._tgt_finishing = False
        self._type_timer.stop()
        self._commit_timeout.stop()
        self._scroll_timer.stop()
        self._hold_timer.stop()
        self._hold_entry = None
        self._auto_follow = True
        self._history_rev += 1
        self._history_rendered_rev = -1
        self._history_rendered_exclude = None
        self._render_jump = True
        self._render_content()

    def resizeEvent(self, event):
        if hasattr(self, 'control_bar'):
            self.control_bar.setGeometry(10, 5, self.width() - 20, 45)
        super().resizeEvent(event)

    def mouseMoveEvent(self, event):
        if not self.is_fullscreen:
            if not self.control_bar.isVisible():
                self.control_bar.show()
                self.control_bar.raise_()
            self._hide_timer.stop()
        else:
            gy = event.globalPosition().y()
            if gy < 50:
                if not self.control_bar.isVisible():
                    self.control_bar.show()
                    self.control_bar.raise_()
                self._hide_timer.stop()
            elif gy > 100 and self.control_bar.isVisible():
                self._hide_timer.start()

        if not self.is_fullscreen:
            if (event.buttons() & Qt.MouseButton.LeftButton
                    and self._resize_edge in ("left", "right")
                    and self._resize_start_geom is not None):
                dx = event.globalPosition().toPoint().x() - self._resize_start_pos.x()
                start = self._resize_start_geom
                if self._resize_edge == "right":
                    new_w = max(300, start.width() + dx)
                    self.setGeometry(start.x(), start.y(), new_w, start.height())
                else:
                    new_w = max(300, start.width() - dx)
                    new_x = start.x() + (start.width() - new_w)
                    self.setGeometry(new_x, start.y(), new_w, start.height())
                return
            if event.buttons() == Qt.MouseButton.NoButton:
                edge = self._get_resize_edge(event.position().toPoint())
                self.setCursor(Qt.SizeHorCursor if edge else Qt.ArrowCursor)
            elif event.buttons() & Qt.MouseButton.LeftButton:
                if self._drag_pos is not None:
                    self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if not self.is_fullscreen:
            self._hide_timer.start()
        super().leaveEvent(event)

    def _hide_control_bar(self):
        pos = QCursor.pos()
        if self.is_fullscreen:
            if pos.y() >= 50:
                self.control_bar.hide()
        else:
            if not self.geometry().contains(pos):
                self.control_bar.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        bg = self._bg_color
        if self.is_fullscreen:
            if bg.alpha() < 200:
                bg = QColor(bg.red(), bg.green(), bg.blue(), 200)
            painter.setBrush(bg)
            painter.drawRect(self.rect())
        else:
            painter.setBrush(bg)
            painter.drawRoundedRect(self.rect(), 16, 16)

    def apply_style(self):
        if self.is_fullscreen:
            self._tgt_font_size = int(self._base_tgt_font_size * 1.2)
            self._src_font_size = int(self._base_src_font_size * 1.2)
            self.history_area.show()
            self.control_bar.btn_fullscreen.setText("退出全屏")
            screen = self.screen()
            if screen is not None:
                sh = screen.availableGeometry().height()
                self.current_area.setMaximumHeight(int(sh * 0.35))
            else:
                self.current_area.setMaximumHeight(500)
        else:
            self._tgt_font_size = self._base_tgt_font_size
            self._src_font_size = self._base_src_font_size
            self.history_area.hide()
            self.control_bar.btn_fullscreen.setText("全屏")
            self.current_area.setMaximumHeight(200)
            # 退出全屏后不再需要阅读停留
            self._hold_timer.stop()
            self._hold_entry = None
        self.control_bar.lbl_tgt_font_size.setText(str(self._base_tgt_font_size))
        self.control_bar.lbl_src_font_size.setText(str(self._base_src_font_size))
        self._history_rendered_rev = -1   # 字号/全屏变化后强制重排历史
        self._history_rendered_exclude = None
        self._render_jump = True
        self._render_content()
        self.update()

    def set_display_mode(self, mode):
        self.display_mode = mode
        self._history_rendered_rev = -1
        self._render_jump = True
        self._render_content()

    def _build_history_html(self, exclude_last, extra=0):
        show_src = self.display_mode in ("bilingual", "source")
        show_tgt = self.display_mode in ("bilingual", "target")
        html = "<div style='text-align: center; max-width: 80%; margin: 0 auto;'>"
        recent = self._history[:-1] if exclude_last else list(self._history)
        limit = self._history_window + max(0, int(extra))
        recent = recent[-limit:]
        for src, tgt in recent:
            for s, t in split_aligned(src, tgt):
                if not s and not t:
                    continue
                html += "<div style='margin-bottom: 10px;'>"
                if show_tgt and t:
                    html += (f"<p style='color:rgba(205,205,205,190); "
                             f"font-size:{int(self._tgt_font_size * 0.8)}px; "
                             f"margin:2px 0; line-height:1.35;'>{html_escape(t)}</p>")
                if show_src and s:
                    html += (f"<p style='color:rgba(160,160,160,170); "
                             f"font-size:{int(self._src_font_size * 0.8)}px; "
                             f"margin:0 0 2px 0; line-height:1.35;'>{html_escape(s)}</p>")
                html += "</div>"
        html += "</div>"
        return html

    def _render_history(self, exclude_last, extra=0):
        """重建历史区；extra=1 时多保留一条旧字幕，用于制造“向上滚动”的距离。

        重建时屏蔽重绘并恢复滚动位置，避免闪屏；随后由定时器缓动到最新一行。
        """
        sb = self.history_area.verticalScrollBar()
        old_val = sb.value()
        at_bottom = self._auto_follow
        self._programmatic_scroll = True
        self.history_area.setUpdatesEnabled(False)
        try:
            self.history_area.setHtml(self._build_history_html(exclude_last, extra))
            if at_bottom and extra == 0:
                sb.setValue(sb.maximum())      # 收尾：贴住底部，不产生位移
            else:
                sb.setValue(old_val)           # 保留当前视点，由缓动滚上去
        finally:
            self.history_area.setUpdatesEnabled(True)
            self._programmatic_scroll = False
        if at_bottom:
            self._start_scroll()

    def _render_content(self):
        show_src = self.display_mode in ("bilingual", "source")
        show_tgt = self.display_mode in ("bilingual", "target")

        # 历史区只在内容真正变化时重建；新字幕临时多留一条，滚动后再裁掉，
        # 这样每次都是平滑上滚而不是原地换字。
        exclude_last = self._compute_exclude_last()
        needs = (self._history_rev != self._history_rendered_rev
                 or exclude_last != self._history_rendered_exclude)
        if self.is_fullscreen and self._history and needs:
            jump = self._render_jump
            self._render_jump = False
            if jump:
                # 进全屏 / 换字号 / 换模式：直接贴底，不做滚动动画
                self._crawl_pending = False
                self._render_history(exclude_last, extra=0)
            else:
                # 只有“当前字幕被推入历史”（exclude_last 由 True 变 False）时才上滚
                pushed = (self._history_rendered_exclude is True
                          and exclude_last is False)
                crawl = bool(pushed and self._auto_follow and len(self._history) > 1)
                self._crawl_pending = crawl
                self._render_history(exclude_last, extra=1 if crawl else 0)
            self._history_rendered_rev = self._history_rev
            self._history_rendered_exclude = exclude_last

        # ===== current_area 渲染 =====
        if self._hold_entry is not None:
            src, tgt = self._hold_entry
        else:
            src = self._pending_source
            tgt = self._pending_target
            if not src and not tgt and self._history:
                src, tgt = self._history[-1]
        if not src and not tgt:
            self.current_area.setText("等待字幕…")
            return

        # 当前字幕只显示最后一组“整句配对”，原文与译文一一对应，不再错位
        pairs = split_aligned(src, tgt)
        if pairs:
            disp_src, disp_tgt = pairs[-1]
        else:
            disp_src, disp_tgt = src, tgt

        cur_tgt_fs = self._tgt_font_size
        cur_src_fs = self._src_font_size
        if not self.is_fullscreen:
            if len(disp_tgt) > 25:
                cur_tgt_fs = int(self._tgt_font_size * 0.85)
            if len(disp_src) > 25:
                cur_src_fs = int(self._src_font_size * 0.85)

        html = "<div style='text-align: center; line-height: 1.4; max-width: 85%; margin: 0 auto;'>"
        if disp_tgt and show_tgt:
            html += (f"<p style='color:{self._text_color.name()}; "
                     f"font-size:{cur_tgt_fs}px; font-weight:bold; "
                     f"margin-bottom:6px; margin-top:0;'>{html_escape(disp_tgt)}</p>")
        if disp_src and show_src:
            html += (f"<p style='color:{self._source_color.name()}; "
                     f"font-size:{cur_src_fs}px; margin-top:0;'>{html_escape(disp_src)}</p>")
        html += "</div>"
        self.current_area.setText(html)

    def set_font_sizes(self, tgt_size=None, src_size=None):
        if tgt_size is not None:
            self._base_tgt_font_size = tgt_size
        if src_size is not None:
            self._base_src_font_size = src_size
        self.apply_style()

    def set_text_color(self, color):
        self._text_color = color
        self.apply_style()

    def set_source_color(self, color):
        self._source_color = color
        self.apply_style()

    def set_bg_alpha(self, alpha):
        self._bg_color.setAlpha(alpha)
        self.update()

    def set_bg_color(self, color):
        cur_alpha = self._bg_color.alpha()
        self._bg_color = QColor(color)
        self._bg_color.setAlpha(cur_alpha)
        self.update()

    def set_click_through(self, enabled):
        self._click_through = bool(enabled)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, self._click_through)
        if self._click_through:
            self.control_bar.hide()

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self._normal_geometry = self.geometry()
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
            self._auto_follow = True
            self._history_rendered_rev = -1
            QTimer.singleShot(50, self._start_scroll)
        else:
            self._scroll_timer.stop()
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.showNormal()
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
        self.apply_style()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def _get_resize_edge(self, pos):
        margin = 15
        if pos.x() < margin:
            return "left"
        if pos.x() > self.width() - margin:
            return "right"
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.is_fullscreen:
            self._resize_edge = self._get_resize_edge(event.position().toPoint())
            if self._resize_edge:
                self._resize_start_geom = self.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
            else:
                self._drag_pos = (event.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        self._resize_start_geom = None
        self._resize_start_pos = None
        super().mouseReleaseEvent(event)