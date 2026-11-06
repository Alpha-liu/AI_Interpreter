# -*- coding: utf-8 -*-
"""将后台翻译事件桥接到 UI 线程。"""
from PySide6.QtCore import QObject, Signal


class UiBridge(QObject):
    # channel, text
    source_delta = Signal(str, str)
    # channel, item_id, text
    source_done = Signal(str, str, str)

    # channel, text
    target_delta = Signal(str, str)
    # channel, item_id, text
    target_done = Signal(str, str, str)

    status_update = Signal(str)
    # channel, peak (0-32767)
    level = Signal(str, int)
    # 后台收尾（保存/混音）完成
    stopped = Signal()

    def emit_source_delta(self, channel, text):
        self.source_delta.emit(channel, text)

    def emit_source_done(self, channel, item_id, text):
        self.source_done.emit(channel, item_id, text)

    def emit_target_delta(self, channel, text):
        self.target_delta.emit(channel, text)

    def emit_target_done(self, channel, item_id, text):
        self.target_done.emit(channel, item_id, text)

    def emit_status(self, msg):
        self.status_update.emit(msg)

    def emit_level(self, channel, peak):
        self.level.emit(channel, peak)

    def emit_stopped(self):
        self.stopped.emit()