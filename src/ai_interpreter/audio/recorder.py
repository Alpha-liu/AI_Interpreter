# -*- coding: utf-8 -*-
"""将 PCM 数据实时写入 WAV 文件（线程安全、可重入、幂等 close）。

为防“进程崩溃导致 WAV 头未回填、录音不可读”，本实现不再依赖 `wave` 模块
只在 close 时写长度，而是**自己写 RIFF 头并定期回填** data 长度字段：
即使程序被强杀，已回填的音频（最多丢失最后约 1 秒）仍可被任意播放器读取。
"""
import os
import struct
import threading


class WavRecorder:
    _HEADER_SIZE = 44
    # 每写满约 1 秒音频回填一次头：崩溃最多丢 1 秒，IO 开销可忽略
    _PATCH_SECONDS = 1.0

    def __init__(self, filepath: str, sample_rate: int = 16000,
                 channels: int = 1, sample_width: int = 2):
        self.filepath = filepath
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.wav_file = None          # 底层二进制文件句柄
        self._lock = threading.Lock()
        self._data_bytes = 0
        self._frames_dropped = 0
        self._patch_every = max(
            int(sample_rate * channels * sample_width * self._PATCH_SECONDS), 1)
        self._last_patch = 0

    @property
    def _block_align(self) -> int:
        return max(self.channels * self.sample_width, 1)

    def _write_header(self):
        f = self.wav_file
        byte_rate = self.sample_rate * self._block_align
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + self._data_bytes))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<H", 1))                       # PCM
        f.write(struct.pack("<H", self.channels))
        f.write(struct.pack("<I", self.sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", self._block_align))
        f.write(struct.pack("<H", self.sample_width * 8))
        f.write(b"data")
        f.write(struct.pack("<I", self._data_bytes))

    def _patch_header(self):
        """把当前 data 长度回填到头的两个长度字段并落盘。"""
        f = self.wav_file
        pos = f.tell()
        f.seek(4)
        f.write(struct.pack("<I", 36 + self._data_bytes))
        f.seek(40)
        f.write(struct.pack("<I", self._data_bytes))
        f.seek(pos)
        f.flush()
        self._last_patch = self._data_bytes

    def open(self):
        dir_name = os.path.dirname(self.filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with self._lock:
            if self.wav_file is not None:
                return
            self._data_bytes = 0
            self._frames_dropped = 0
            self._last_patch = 0
            self.wav_file = open(self.filepath, "wb")
            self._write_header()

    def write(self, pcm_bytes: bytes):
        if not pcm_bytes:
            return
        with self._lock:
            if self.wav_file is None:
                self._frames_dropped += 1
                return
            try:
                self.wav_file.write(pcm_bytes)
                self._data_bytes += len(pcm_bytes)
                if self._data_bytes - self._last_patch >= self._patch_every:
                    # 先落盘音频，再回填头，避免头声明的长度大于实际落盘数据
                    self.wav_file.flush()
                    self._patch_header()
            except OSError as e:
                self._frames_dropped += 1
                if self._frames_dropped == 1 or self._frames_dropped % 100 == 0:
                    print(f"[recorder] 磁盘写入失败(累计丢 {self._frames_dropped} 帧): {e}")

    def close(self):
        with self._lock:
            if self.wav_file is None:
                return
            try:
                self._patch_header()      # 收尾也回填，确保完整
                self.wav_file.flush()
                self.wav_file.close()
            except Exception as e:
                print(f"[recorder] 关闭异常: {e}")
            finally:
                self.wav_file = None
            frames = self._data_bytes // self._block_align
            dropped = self._frames_dropped
        print(f"[recorder] 音频已保存: {self.filepath} "
              f"(写入 {frames} 帧, 丢弃 {dropped} 帧)")
