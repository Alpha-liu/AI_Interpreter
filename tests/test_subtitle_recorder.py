"""字幕时序记录与 SRT 落盘。"""
from ai_interpreter.audio.subtitles import SubtitleRecorder


def test_long_turn_is_split_into_short_cues(tmp_path):
    rec = SubtitleRecorder("user", "我", output_dir=str(tmp_path), base_ts=0)
    rec.on_source_done("t1", "第一句。第二句。第三句。", 10.0, 20.0)
    rec.on_target_done("t1", "First. Second. Third.")
    entries = rec.save()
    assert len(entries) == 3
    assert abs(entries[0][0] - 10.0) < 1e-6
    assert abs(entries[-1][1] - 20.0) < 1e-6
    assert [e[4] for e in entries] == ["First.", "Second.", "Third."]


def test_short_turn_stays_single_cue(tmp_path):
    rec = SubtitleRecorder("participant", "参会者", output_dir=str(tmp_path), base_ts=0)
    rec.on_source_done("s1", "你好。", 0.0, 2.0)
    rec.on_target_done("s1", "Hello.")
    entries = rec.save()
    assert len(entries) == 1
    assert entries[0][3] == "你好。" and entries[0][4] == "Hello."
