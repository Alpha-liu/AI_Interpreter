# -*- coding: utf-8 -*-
"""麦克风采集。使用 audio_utils.resample_pcm，不依赖 pyaudiowpatch。"""
import sounddevice as sd
from ai_interpreter.audio.utils import resample_pcm, pcm_peak


def list_input_devices():
    devices, seen = [], set()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        name = d["name"]
        if name in seen:
            continue
        try:
            sr = int(d["default_samplerate"])
            sd.check_input_settings(device=i, channels=1, dtype="int16", samplerate=sr)
            devices.append((i, name))
            seen.add(name)
        except Exception:
            continue
    return devices


class MicCapture:
    def __init__(self, on_pcm, recorder=None, sample_rate=16000,
                 blocksize=1600, device_index=None, on_level=None):
        self.on_pcm = on_pcm
        self.recorder = recorder
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.device_index = device_index
        self.on_level = on_level
        self.stream = None
        self._running = False
        self._paused = False
        self._start_error = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        self._start_error = None

        target = self.device_index if self.device_index is not None else sd.default.device[0]
        try:
            dev = sd.query_devices(target)
        except Exception as e:
            self._start_error = str(e)
            print(f"[mic] 查询输入设备失败: {e}")
            self._running = False
            return

        actual_sr = self.sample_rate
        try:
            sd.check_input_settings(device=target, channels=1, dtype="int16",
                                    samplerate=self.sample_rate)
        except Exception:
            actual_sr = int(dev["default_samplerate"])
            print(f"[mic] 设备不支持 {self.sample_rate}Hz，回退到 {actual_sr}Hz")

        print(f"[mic] 使用输入设备: {dev['name']} (index={target}) @ {actual_sr}Hz")

        if self.recorder:
            self.recorder.open()

        def callback(indata, frames, time_info, status):
            if not (self._running and not self._paused):
                return
            try:
                pcm = bytes(indata)
                if actual_sr != self.sample_rate:
                    pcm = resample_pcm(pcm, actual_sr, self.sample_rate, 1)
                if pcm:
                    self.on_pcm(pcm)
                    if self.recorder:
                        self.recorder.write(pcm)
                    if self.on_level:
                        try:
                            self.on_level(pcm_peak(pcm))
                        except Exception:
                            pass
            except Exception as e:
                print(f"[mic] 回调异常: {e}")

        try:
            self.stream = sd.RawInputStream(
                samplerate=actual_sr, blocksize=self.blocksize,
                channels=1, dtype="int16", callback=callback,
                device=self.device_index,
            )
            self.stream.start()
        except Exception as e:
            self._start_error = str(e)
            print(f"[mic] 音频流启动失败: {e}")
            self._running = False
            self.stream = None
            if self.recorder:
                self.recorder.close()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"[mic] 关闭音频流失败: {e}")
            self.stream = None
        if self.recorder:
            self.recorder.close()