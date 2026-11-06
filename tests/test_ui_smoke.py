"""主控制台构建与基础交互的冒烟测试（无音频设备时也会跳过或降级）。"""
import pytest

pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("sounddevice")
pytest.importorskip("pyaudiowpatch")

from ai_interpreter.ui.bridge import UiBridge
from ai_interpreter.ui.main_window import ControlPanel


class DummyInterpreter:
    _started = False

    def set_audio_devices(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self, blocking=False):
        pass

    def set_subtitle(self, *args, **kwargs):
        pass


def test_panel_builds_and_updates(qapp):
    bridge = UiBridge()
    panel = ControlPanel(DummyInterpreter(), bridge)
    assert panel.cmb_mic.count() >= 1
    assert panel.cmb_spk.count() >= 1

    panel._on_level("user", 12345)
    assert panel.bar_mic.value() == 12345

    panel._on_source_done("user", "t1", "Hello")
    panel._on_target_done("user", "t1", "你好")
    assert "你好" in panel.view_me.toPlainText()

    panel._on_stopped()
    assert panel.btn_start.isEnabled()

    panel.close()
