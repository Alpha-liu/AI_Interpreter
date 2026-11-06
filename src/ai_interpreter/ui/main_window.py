# -*- coding: utf-8 -*-
"""主控制台（深色仪表盘布局，参照设计稿）。

保留原有全部功能：设备选择与自检、语言选择、开始/暂停/停止、实时预览、
电平与计时、设置、后台收尾。仅重做外观与布局。
"""
import os
import time
from collections import OrderedDict
from html import escape as html_escape

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QListWidget, QListWidgetItem, QComboBox, QPushButton,
    QFrame, QProgressBar, QMessageBox,
)
from PySide6.QtCore import Slot, QThread, QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QTextCursor, QDesktopServices

from ai_interpreter.config import TARGET_LANGUAGES
from ai_interpreter.ui.lyric_window import LyricWindow
from ai_interpreter.audio.mic import list_input_devices
from ai_interpreter.audio.loopback import list_loopback_devices
from ai_interpreter.ui.hw_test_worker import HardwareTestWorker
from ai_interpreter.ui.settings_dialog import SettingsDialog
from ai_interpreter.text_utils import split_aligned
from ai_interpreter.ui.theme import DARK_QSS
from ai_interpreter.ui.widgets import ToggleSwitch, ListeningOrb


class ControlPanel(QWidget):
    _MAX_SRC_CACHE = 500

    def __init__(self, interpreter, bridge):
        super().__init__()
        self.interpreter = interpreter
        self.bridge = bridge
        self.lyric_window = LyricWindow()
        self._test_thread = None
        self._test_worker = None
        self._src_cache = OrderedDict()
        self._mic_level = 0
        self._spk_level = 0

        # 录音计时
        self._session_start = None
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

        self._build_ui()
        self._connect_signals()

    # ================= UI =================
    def _build_ui(self):
        self.setWindowTitle("会议实时翻译控制台")
        self.resize(1440, 860)
        self.setMinimumSize(1280, 720)
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(DARK_QSS)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(20, 16, 20, 12)
        cl.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(self._build_device_card())
        top.addWidget(self._build_center_card(), 1)
        top.addWidget(self._build_language_card())
        cl.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        bottom.addWidget(self._build_chat_card("user"), 1)
        bottom.addWidget(self._build_chat_card("participant"), 1)
        cl.addLayout(bottom, 1)

        cl.addWidget(self._build_status_bar())
        root.addWidget(content, 1)

        self._populate_devices()

    # ---- 侧边栏 ----
    def _build_sidebar(self):
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(200)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(14, 18, 14, 18)
        lay.setSpacing(6)

        title = QHBoxLayout()
        title.setSpacing(8)
        icon = QLabel("▦")
        icon.setObjectName("brandIcon")
        brand = QLabel("会议实时翻译控制台")
        brand.setObjectName("brandTitle")
        brand.setWordWrap(True)
        title.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        title.addWidget(brand, 1)
        lay.addLayout(title)
        lay.addSpacing(20)

        self.btn_nav_sub = self._make_nav("💬   实时字幕", "navActive")
        self.btn_nav_hist = self._make_nav("🕘   历史记录", "nav")
        self.btn_nav_settings = self._make_nav("⚙   系统设置", "nav")
        for b in (self.btn_nav_sub, self.btn_nav_hist, self.btn_nav_settings):
            lay.addWidget(b)
        lay.addStretch()
        return bar

    def _make_nav(self, text, obj_name):
        b = QPushButton(text)
        b.setObjectName(obj_name)
        b.setFixedHeight(42)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    # ---- 音频设备卡片 ----
    def _build_device_card(self):
        self.card_dev = QFrame()
        self.card_dev.setObjectName("card")
        self.card_dev.setFixedWidth(330)
        lay = QVBoxLayout(self.card_dev)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(self._title("音频设备"))
        head.addStretch()
        self.btn_refresh_dev = QPushButton("↻")
        self.btn_refresh_dev.setObjectName("ghostBtn")
        self.btn_refresh_dev.setFixedSize(28, 28)
        self.btn_refresh_dev.setToolTip("重新扫描可用设备")
        head.addWidget(self.btn_refresh_dev)
        lay.addLayout(head)

        lay.addWidget(self._muted("麦克风输入（我的声音）"))
        self.cmb_mic = QComboBox()
        lay.addWidget(self.cmb_mic)
        self.bar_mic = self._make_level_bar()
        lay.addWidget(self.bar_mic)

        lay.addWidget(self._muted("扬声器环回（对方声音）"))
        self.cmb_spk = QComboBox()
        lay.addWidget(self.cmb_spk)
        self.bar_spk = self._make_level_bar()
        lay.addWidget(self.bar_spk)

        lay.addSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_test_mic = QPushButton("测试麦克风")
        self.btn_test_mic.setObjectName("ghostBtn")
        self.btn_test_spk = QPushButton("测试扬声器")
        self.btn_test_spk.setObjectName("ghostBtn")
        row.addWidget(self.btn_test_mic)
        row.addWidget(self.btn_test_spk)
        lay.addLayout(row)

        self.test_result = QListWidget()
        self.test_result.setObjectName("testResult")
        self.test_result.setFixedHeight(62)
        self.test_result.setVisible(False)
        lay.addWidget(self.test_result)
        lay.addStretch()
        return self.card_dev

    # ---- 中央聆听卡片 ----
    def _build_center_card(self):
        card = QFrame()
        card.setObjectName("orbCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        self.orb = ListeningOrb()
        lay.addWidget(self.orb, 1)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()
        self.btn_start = QPushButton("开始翻译")
        self.btn_start.setObjectName("btnStart")
        self.btn_pause = QPushButton("暂停")
        self.btn_pause.setObjectName("btnPause")
        self.btn_pause.setEnabled(False)
        self.btn_stop = QPushButton("停止并保存")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setEnabled(False)
        for b in (self.btn_start, self.btn_pause, self.btn_stop):
            b.setFixedHeight(40)
            b.setMinimumWidth(96)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b, 1)
        row.addStretch()
        lay.addLayout(row)
        return card

    # ---- 语言设置卡片 ----
    def _build_language_card(self):
        self.card_lang = QFrame()
        self.card_lang.setObjectName("card")
        self.card_lang.setFixedWidth(310)
        lay = QVBoxLayout(self.card_lang)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        lay.addWidget(self._title("翻译语言设置"))

        self.cmb_user_lang = QComboBox()
        for code, name in TARGET_LANGUAGES.items():
            self.cmb_user_lang.addItem(f"{name} ({code})", code)
        idx = self.cmb_user_lang.findData("en")
        if idx >= 0:
            self.cmb_user_lang.setCurrentIndex(idx)
        lay.addLayout(self._setting_row("我说话的语言", self.cmb_user_lang))

        self.cmb_part_lang = QComboBox()
        for code, name in TARGET_LANGUAGES.items():
            self.cmb_part_lang.addItem(f"{name} ({code})", code)
        idx = self.cmb_part_lang.findData("zh")
        if idx >= 0:
            self.cmb_part_lang.setCurrentIndex(idx)
        lay.addLayout(self._setting_row("对方说话的语言", self.cmb_part_lang))

        lay.addWidget(self._divider())

        self.cb_lyric_float = ToggleSwitch(checked=True)
        lay.addLayout(self._toggle_row("显示悬浮字幕", self.cb_lyric_float))

        self.cb_click_through = ToggleSwitch(checked=False)
        self.cb_click_through.setToolTip(
            "开启后字幕窗不接收鼠标事件，无法拖拽/点击控制栏。\n"
            "如需关闭请取消勾选本选项。")
        lay.addLayout(self._toggle_row("字幕鼠标穿透", self.cb_click_through))

        self.cb_show_source = ToggleSwitch(checked=True)
        lay.addLayout(self._toggle_row("显示原文", self.cb_show_source))
        lay.addStretch()
        return self.card_lang

    # ---- 字幕列表卡片 ----
    def _build_chat_card(self, channel):
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        accent = "#2dd4bf" if channel == "user" else "#60a5fa"
        head = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {accent}; font-size: 11px;")
        head.addWidget(dot)
        head.addWidget(self._title("我说的" if channel == "user" else "对方说的"))
        head.addStretch()
        btn = QPushButton("清空")
        btn.setObjectName("ghostBtn")
        btn.setFixedSize(52, 26)
        head.addWidget(btn)
        lay.addLayout(head)

        view = QTextEdit()
        view.setReadOnly(True)
        view.setObjectName("chatView")
        view.setPlaceholderText(
            "开始翻译后，这里会显示「我说的」实时字幕"
            if channel == "user"
            else "开始翻译后，这里会显示「对方说的」实时字幕")
        lay.addWidget(view, 1)

        if channel == "user":
            self.view_me = view
            self.btn_clear_me = btn
        else:
            self.view_them = view
            self.btn_clear_them = btn
        return card

    # ---- 状态栏 ----
    def _build_status_bar(self):
        bar = QFrame()
        bar.setObjectName("statusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(8)

        self.lbl_dot = QLabel("●")
        self.lbl_dot.setObjectName("statusDot")
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setObjectName("statusText")
        lay.addWidget(self.lbl_dot)
        lay.addWidget(self.lbl_status)
        lay.addStretch()

        save = QLabel("文件保存至 record/")
        save.setObjectName("muted")
        lay.addWidget(save)
        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setObjectName("timerLabel")
        lay.addWidget(self.lbl_timer)
        return bar

    # ---- 小部件工厂 ----
    def _title(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("cardTitle")
        return lbl

    def _muted(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("muted")
        return lbl

    def _divider(self):
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        return line

    def _setting_row(self, label, widget):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(label))
        row.addStretch()
        widget.setFixedWidth(150)
        row.addWidget(widget)
        return row

    def _toggle_row(self, label, toggle):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addStretch()
        row.addWidget(toggle)
        return row

    def _make_level_bar(self):
        bar = QProgressBar()
        bar.setObjectName("levelBar")
        bar.setRange(0, 30000)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        return bar

    def _populate_devices(self):
        self.cmb_mic.blockSignals(True)
        self.cmb_mic.clear()
        try:
            for idx, name in list_input_devices():
                self.cmb_mic.addItem(name, idx)
        except Exception as e:
            print("加载麦克风设备失败:", e)
        if self.cmb_mic.count() == 0:
            self.cmb_mic.addItem("（未检测到输入设备）", None)
        self.cmb_mic.blockSignals(False)

        self.cmb_spk.blockSignals(True)
        self.cmb_spk.clear()
        try:
            for idx, name in list_loopback_devices():
                self.cmb_spk.addItem(name, idx)
        except Exception as e:
            print("加载扬声器设备失败:", e)
        if self.cmb_spk.count() == 0:
            self.cmb_spk.addItem("（未检测到环回设备）", None)
        self.cmb_spk.blockSignals(False)

    # ================= 信号 =================
    def _connect_signals(self):
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_refresh_dev.clicked.connect(self._on_refresh_devices)

        self.btn_nav_hist.clicked.connect(self._open_record_dir)
        self.btn_nav_settings.clicked.connect(self._on_open_settings)

        self.cb_lyric_float.toggled.connect(self._on_lyric_float_toggled)
        self.cb_click_through.toggled.connect(self.lyric_window.set_click_through)
        self.cb_show_source.toggled.connect(self._on_show_source_toggled)

        self.lyric_window.hide_requested.connect(
            lambda: self.cb_lyric_float.setChecked(False))

        self.btn_test_mic.clicked.connect(lambda: self._run_hw_test("麦克风"))
        self.btn_test_spk.clicked.connect(lambda: self._run_hw_test("扬声器"))

        self.btn_clear_me.clicked.connect(self.view_me.clear)
        self.btn_clear_them.clicked.connect(self.view_them.clear)

        self.cmb_user_lang.currentIndexChanged.connect(
            lambda: self.interpreter.set_subtitle(
                "user", target_lang=self.cmb_user_lang.currentData()))
        self.cmb_part_lang.currentIndexChanged.connect(
            lambda: self.interpreter.set_subtitle(
                "participant", target_lang=self.cmb_part_lang.currentData()))

        self.bridge.source_delta.connect(self._on_source_delta)
        self.bridge.source_done.connect(self._on_source_done)
        self.bridge.target_delta.connect(self._on_target_delta)
        self.bridge.target_done.connect(self._on_target_done)
        self.bridge.status_update.connect(self._on_status_update)
        self.bridge.level.connect(self._on_level)
        self.bridge.stopped.connect(self._on_stopped)

    def _open_record_dir(self):
        path = os.path.abspath("record")
        try:
            os.makedirs(path, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            print(f"[ui] 打开录音目录失败: {e}")

    @Slot(bool)
    def _on_show_source_toggled(self, checked):
        self.interpreter.set_subtitle("user", show_source=checked)
        self.interpreter.set_subtitle("participant", show_source=checked)

    # ---- 状态 / 电平 / 计时 ----
    def _on_status_update(self, text):
        self.lbl_status.setText(text)

    def _set_status(self, text, color="#cbd5e1", dot="#22c55e"):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.lbl_dot.setStyleSheet(f"color: {dot}; font-size: 12px;")

    @Slot(str, int)
    def _on_level(self, channel, peak):
        peak = max(0, min(int(peak), 30000))
        if channel == "user":
            self._mic_level = peak
            self.bar_mic.setValue(peak)
        else:
            self._spk_level = peak
            self.bar_spk.setValue(peak)
        self.orb.set_level(max(self._mic_level, self._spk_level))

    def _update_elapsed(self):
        if self._session_start is None:
            return
        secs = max(0, int(time.time() - self._session_start))
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        self.lbl_timer.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _start_timer(self):
        self._session_start = time.time()
        self.lbl_timer.setText("00:00:00")
        self._elapsed_timer.start()

    def _stop_timer(self):
        self._elapsed_timer.stop()
        if self._session_start is not None:
            self._update_elapsed()

    # ---- 字幕回显 ----
    def _on_source_delta(self, channel, text):
        if self.cb_lyric_float.isChecked():
            self.lyric_window.append_source(text)

    def _on_source_done(self, channel, item_id, text):
        if self.cb_lyric_float.isChecked():
            self.lyric_window.finish_source(text)
        self._src_cache[(channel, item_id)] = text
        while len(self._src_cache) > self._MAX_SRC_CACHE:
            self._src_cache.popitem(last=False)

    def _on_target_delta(self, channel, text):
        if self.cb_lyric_float.isChecked():
            self.lyric_window.append_target(text)

    def _on_target_done(self, channel, item_id, text):
        if self.cb_lyric_float.isChecked():
            self.lyric_window.finish_target(text)

        src_text = self._src_cache.pop((channel, item_id), "")
        target_view = self.view_me if channel == "user" else self.view_them
        accent = "#2dd4bf" if channel == "user" else "#60a5fa"

        pairs = split_aligned(src_text, text)
        html = "<div style='margin-bottom: 12px; line-height: 1.5;'>"
        for s, t in pairs:
            if t:
                html += (f"<p style='margin:0 0 2px 0;'>"
                         f"<span style='color:{accent};'>●</span> "
                         f"<span style='color:#f1f5f9; font-weight:600;'>"
                         f"{html_escape(t)}</span></p>")
            if s:
                html += (f"<p style='margin:0 0 6px 0; color:#94a3b8;'>"
                         f"&nbsp;&nbsp;&nbsp;{html_escape(s)}</p>")
        html += "</div>"

        target_view.append(html)
        self._trim_preview(target_view)
        target_view.moveCursor(QTextCursor.MoveOperation.End)
        target_view.ensureCursorVisible()

    def _trim_preview(self, text_edit):
        doc = text_edit.document()
        if doc.blockCount() > 50:
            cursor = text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    @Slot(bool)
    def _on_lyric_float_toggled(self, checked):
        if checked:
            self.lyric_window.show()
        else:
            self.lyric_window.hide()

    @Slot()
    def _on_refresh_devices(self):
        self._populate_devices()
        self._set_status("已刷新设备列表", color="#93c5fd", dot="#3b82f6")

    # ---- 会话控制 ----
    @Slot()
    def _on_start(self):
        if self._test_thread is not None and self._test_thread.isRunning():
            self._set_status("设备测试进行中，请稍候再开始", color="#fde68a", dot="#f59e0b")
            return
        if self.cmb_mic.currentData() is None or self.cmb_spk.currentData() is None:
            self._set_status("请先选择有效的麦克风与扬声器设备", color="#fca5a5", dot="#ef4444")
            return
        try:
            self.interpreter.set_audio_devices(
                self.cmb_mic.currentData(), self.cmb_spk.currentData())
            self.interpreter.start()
        except Exception as e:
            # 启动失败时确保按钮状态可重试（尤其是环回设备被其他进程占用时）
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self._set_status(f"启动失败: {e}", color="#fca5a5", dot="#ef4444")
            return

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("暂停")
        self.btn_stop.setEnabled(True)
        self.btn_stop.setText("停止并保存")
        self._set_status("已连接 · 正在聆听", color="#bbf7d0", dot="#22c55e")

        self.view_me.clear()
        self.view_them.clear()
        self._src_cache.clear()
        self._mic_level = 0
        self._spk_level = 0
        self.bar_mic.setValue(0)
        self.bar_spk.setValue(0)
        self.orb.set_level(0)
        self.orb.set_state("listening")

        self.lyric_window.reset()
        self._start_timer()

        if self.cb_lyric_float.isChecked() and not self.lyric_window.is_fullscreen:
            self.lyric_window.show()

    @Slot()
    def _on_pause(self):
        if self.btn_pause.text() == "暂停":
            self.interpreter.pause()
            self.btn_pause.setText("继续")
            self._set_status("已暂停", color="#fde68a", dot="#f59e0b")
            self._elapsed_timer.stop()
            self.orb.set_state("paused")
        else:
            self.interpreter.resume()
            self.btn_pause.setText("暂停")
            self._set_status("已连接 · 正在聆听", color="#bbf7d0", dot="#22c55e")
            self._elapsed_timer.start()
            self.orb.set_state("listening")

    @Slot()
    def _on_stop(self):
        if not getattr(self.interpreter, "_started", False):
            return
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("保存中…")
        self._set_status("正在停止并保存录音与字幕…", color="#fde68a", dot="#f59e0b")
        self._stop_timer()
        self.bar_mic.setValue(0)
        self.bar_spk.setValue(0)
        self.orb.set_level(0)
        self.orb.set_state("saving")
        self.interpreter.stop()

    @Slot()
    def _on_stopped(self):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("暂停")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("停止并保存")
        self._stop_timer()
        self._set_status("已停止 · 文件已保存至 record/", color="#cbd5e1", dot="#94a3b8")
        self.orb.set_state("idle")

    # ---- 设置 ----
    @Slot()
    def _on_open_settings(self):
        dlg = SettingsDialog(self)
        if not dlg.exec():
            return

        was_running = getattr(self.interpreter, "_started", False)
        if not was_running:
            self._set_status("设置已保存，下次开始翻译时生效",
                             color="#93c5fd", dot="#3b82f6")
            return

        self.btn_start.setEnabled(False)
        self._set_status("正在应用新设置…", color="#fde68a", dot="#f59e0b")
        try:
            self.interpreter.stop(blocking=True)
        except Exception as e:
            print(f"[ui] 应用新设置时停止旧会话失败: {e}")

        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("暂停")
        self.btn_stop.setEnabled(False)
        self.btn_start.setEnabled(True)
        self._stop_timer()
        self.orb.set_state("idle")

        answer = QMessageBox.question(
            self, "设置已保存",
            "配置已更新。是否立即用新配置重新开始翻译？\n"
            "（选择\"No\"可稍后手动点击\"开始翻译\"）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._on_start()
        else:
            self._set_status("设置已保存，点击\"开始翻译\"以使用新配置",
                             color="#93c5fd", dot="#3b82f6")

    # ---- 硬件测试 ----
    def _run_hw_test(self, channel: str):
        if getattr(self.interpreter, "_started", False):
            self._add_test_result(channel, "提示", False, "请先停止翻译再测试设备")
            return
        if channel == "麦克风":
            device_index = self.cmb_mic.currentData()
            btn = self.btn_test_mic
        else:
            device_index = self.cmb_spk.currentData()
            btn = self.btn_test_spk

        if device_index is None:
            self._add_test_result(channel, "设备", False, "未选择设备")
            return

        if self._test_thread is not None and self._test_thread.isRunning():
            self._add_test_result(channel, "提示", False, "已有测试在运行")
            return

        self.test_result.clear()
        self.test_result.setVisible(True)
        btn.setEnabled(False)
        btn.setText("测试中…")

        self._test_thread = QThread()
        self._test_worker = HardwareTestWorker(channel, device_index, duration=3.0)
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)
        self._test_worker.result.connect(self._on_test_result)
        self._test_worker.finished.connect(self._on_test_finished)
        self._test_worker.finished.connect(self._test_thread.quit)
        self._test_thread.finished.connect(self._on_test_thread_finished)
        self._test_thread.start()

    @Slot(str, str, bool, str)
    def _on_test_result(self, channel, step, ok, detail):
        self._add_test_result(channel, step, ok, detail)

    @Slot(str)
    def _on_test_finished(self, channel):
        btn = self.btn_test_mic if channel == "麦克风" else self.btn_test_spk
        btn.setEnabled(True)
        btn.setText(f"测{channel}")

    @Slot()
    def _on_test_thread_finished(self):
        if self._test_thread is not None:
            self._test_thread.deleteLater()
        self._test_thread = None
        self._test_worker = None

    def _add_test_result(self, channel, step, ok, detail):
        mark = "✓" if ok else "✗"
        item = QListWidgetItem(f"{mark} [{channel}] {step}: {detail}")
        item.setForeground(QColor("#34d399") if ok else QColor("#f87171"))
        self.test_result.addItem(item)
        self.test_result.scrollToBottom()

    def closeEvent(self, event):
        try:
            self.interpreter.stop(blocking=True)
        except Exception as e:
            print(f"[ui] 关闭时停止会话失败: {e}")
        self._elapsed_timer.stop()
        if self._test_worker is not None:
            self._test_worker.request_stop()
        if self._test_thread is not None and self._test_thread.isRunning():
            self._test_thread.quit()
            self._test_thread.wait(3000)
        self.lyric_window.close()
        super().closeEvent(event)
