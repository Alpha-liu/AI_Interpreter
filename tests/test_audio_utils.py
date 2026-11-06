"""PCM 处理与 WAV 混音。"""
import wave

import numpy as np

from ai_interpreter.audio.utils import mix_wav_files, pcm_peak, resample_pcm


def _write(path, frames, value, channels=1, rate=16000):
    data = np.full(frames * channels, value, dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def test_pcm_peak_handles_negative():
    arr = np.array([100, -200], dtype=np.int16)
    assert pcm_peak(arr.tobytes()) == 200


def test_resample_fast_path_returns_same_bytes():
    data = np.zeros(1600, dtype=np.int16).tobytes()
    assert resample_pcm(data, 16000, 16000, 1) is data


def test_mix_truncates_to_shorter_track(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    out = tmp_path / "out.wav"
    _write(a, 1600, 1000)
    _write(b, 800, 2000)
    assert mix_wav_files(str(a), str(b), str(out)) is True
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() == 800
        assert w.getframerate() == 16000
