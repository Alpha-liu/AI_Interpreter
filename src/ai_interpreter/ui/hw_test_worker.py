# -*- coding: utf-8 -*-
"""硬件链路异步测试 worker（在 QThread 中运行）。"""
import time
import queue
from PySide6.QtCore import QObject, Signal
from ai_interpreter.audio.utils import pcm_peak


class HardwareTestWorker(QObject):
    result = Signal(str, str, bool, str)
    finished = Signal(str)

    def __init__(self, channel: str, device_index: int, duration: float = 3.0):
        super().__init__()
        self.channel = channel
        self.device_index = device_index
        self.duration = duration
        self._stop = False
        self._audio_queue = queue.Queue()

    def request_stop(self):
        self._stop = True

    def run(self):
        try:
            if self.channel == "麦克风":
                self._test_mic()
            else:
                self._test_loopback()
        except Exception as e:
            self.result.emit(self.channel, "异常", False, str(e))
        finally:
            self.finished.emit(self.channel)

    def _on_pcm(self, pcm):
        self._audio_queue.put(pcm)

    def _process_and_report(self, capture):
        peaks = []
        try:
            capture.start()

            stream = getattr(capture, "stream", None)
            if stream is None:
                err = getattr(capture, "_start_error", "未知错误")
                self.result.emit(self.channel, "采集", False, f"启动失败: {err}")
                self.result.emit(self.channel, "结论", False, "设备未就绪")
                return

            sr = getattr(capture, "target_sr", None) or getattr(capture, "sample_rate", "?")
            self.result.emit(self.channel, "采集", True,
                             f"已启动 @ {sr}Hz，采样 {self.duration:.0f} 秒，请说话/播放声音")

            deadline = time.time() + self.duration
            while time.time() < deadline and not self._stop:
                batch = []
                for _ in range(50):
                    try:
                        batch.append(self._audio_queue.get_nowait())
                    except queue.Empty:
                        break
                for pcm in batch:
                    p = pcm_peak(pcm)
                    if p:
                        peaks.append(p)
                time.sleep(0.02)
        finally:
            # 无论成功失败都要释放设备：同一环回设备同时只能被打开一路，
            # 泄漏的流会让随后的“开始翻译”因设备占用而失败。
            try:
                capture.stop()
            except Exception as e:
                print(f"[hw_test] 关闭采集设备失败: {e}")

        if not peaks:
            self.result.emit(self.channel, "电平", False, "未采集到任何音频帧")
            self.result.emit(self.channel, "结论", False, "设备未产生数据")
            return

        peak_max = max(peaks)
        peak_avg = int(sum(peaks) / len(peaks))

        if peak_max < 100:
            self.result.emit(self.channel, "电平", False,
                             f"峰值 {peak_max}，判定为静音。请检查设备或播放声音")
            self.result.emit(self.channel, "结论", False, "设备采集静音")
        elif peak_max < 1000:
            self.result.emit(self.channel, "电平", True,
                             f"峰值 {peak_max}，有声音但偏弱，建议调大音量")
            self.result.emit(self.channel, "结论", True, "设备采集正常，可用于翻译")
        else:
            self.result.emit(self.channel, "电平", True,
                             f"峰值 {peak_max}，平均 {peak_avg}，音频正常")
            self.result.emit(self.channel, "结论", True, "设备采集正常，可用于翻译")

    def _test_mic(self):
        from ai_interpreter.audio.mic import MicCapture
        self.result.emit(self.channel, "设备", True,
                         f"使用输入设备 index={self.device_index}")
        capture = MicCapture(on_pcm=self._on_pcm, device_index=self.device_index)
        self._process_and_report(capture)

    def _test_loopback(self):
        from ai_interpreter.audio.loopback import LoopbackCapture
        self.result.emit(self.channel, "设备", True,
                         f"使用环回设备 index={self.device_index}")
        capture = LoopbackCapture(on_pcm=self._on_pcm, loopback_index=self.device_index)
        self._process_and_report(capture)