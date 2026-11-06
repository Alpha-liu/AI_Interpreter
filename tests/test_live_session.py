"""WebSocket 会话的事件管线（不联网）。"""
import json

from ai_interpreter.live_session import TranslationSession


class FakeCfg:
    target_lang = "zh"
    show_source = True
    show_target = True


class FakeRecorder:
    def __init__(self):
        self.src = []
        self.tgt = []

    def on_source_done(self, item_id, text, start, end):
        self.src.append((item_id, text))

    def on_target_done(self, item_id, text):
        self.tgt.append((item_id, text))


def _session():
    rec = FakeRecorder()
    done = {"src": [], "tgt": []}
    s = TranslationSession(
        "user",
        FakeCfg(),
        lambda ch, text: None,
        lambda ch, iid, text: done["src"].append((iid, text)),
        lambda ch, text: None,
        lambda ch, iid, text: done["tgt"].append((iid, text)),
        rec,
    )
    return s, rec, done


def _send(s, **event):
    s._on_message(None, json.dumps(event))


def test_source_and_target_are_paired():
    s, rec, done = _session()
    _send(s, type="input_audio_buffer.speech_started")
    _send(s, type="conversation.item.input_audio_transcription.completed",
          transcript="Hello", item_id="i1")
    _send(s, type="response.text.done", text="你好", response_id="r1", item_id="o1")
    assert done["src"] == [("turn_1", "Hello")]
    assert done["tgt"] == [("turn_1", "你好")]
    assert rec.src == [("turn_1", "Hello")]
    assert rec.tgt == [("turn_1", "你好")]


def test_response_done_does_not_duplicate():
    s, rec, done = _session()
    _send(s, type="input_audio_buffer.speech_started")
    _send(s, type="conversation.item.input_audio_transcription.completed",
          transcript="A", item_id="i1")
    _send(s, type="response.text.done", text="甲", response_id="r1", item_id="o1")
    _send(s, type="response.done", response={
        "id": "r1", "output": [{"content": [{"transcript": "甲"}]}]})
    assert len(done["tgt"]) == 1
