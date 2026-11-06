"""WAV 实时写入。"""
import wave

from ai_interpreter.audio.recorder import WavRecorder


def test_roundtrip_frames(tmp_path):
    path = tmp_path / "r.wav"
    rec = WavRecorder(str(path))
    rec.open()
    rec.write(b"\x00\x00" * 1600)
    rec.close()
    with wave.open(str(path), "rb") as w:
        assert w.getnframes() == 1600
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1


def test_close_is_idempotent(tmp_path):
    rec = WavRecorder(str(tmp_path / "r.wav"))
    rec.open()
    rec.close()
    rec.close()
