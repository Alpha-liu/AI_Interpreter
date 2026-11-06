"""Turn 归属状态机。"""
from ai_interpreter.turn_tracker import TurnTracker


def test_normal_turn_pairs_source_and_target():
    tr = TurnTracker()
    tr.speech_started(0.0)
    tr.source_delta("Hel", item_id="i1")
    tr.source_delta("lo", item_id="i1")
    tr.speech_stopped(1.0)
    tr.source_final("Hello", item_id="i1")
    tr.target_delta("你", item_id="o1", response_id="r1")
    tr.target_final("你好", item_id="o1", response_id="r1")
    turns = tr.pop_ready()
    assert len(turns) == 1
    assert (turns[0].src, turns[0].tgt) == ("Hello", "你好")


def test_late_translation_pairs_fifo():
    tr = TurnTracker()
    tr.speech_started(0.0)
    tr.source_delta("A", item_id="i1")
    tr.speech_stopped(1.0)
    tr.source_final("A", item_id="i1")
    tr.speech_started(2.0)
    tr.source_delta("B", item_id="i2")
    tr.speech_stopped(3.0)
    tr.source_final("B", item_id="i2")
    tr.target_delta("甲", item_id="o1", response_id="r1")
    tr.target_final("甲", item_id="o1", response_id="r1")
    tr.target_delta("乙", item_id="o2", response_id="r2")
    tr.target_final("乙", item_id="o2", response_id="r2")
    turns = tr.pop_ready()
    assert [(t.src, t.tgt) for t in turns] == [("A", "甲"), ("B", "乙")]


def test_no_item_id_shares_one_turn():
    tr = TurnTracker()
    tr.speech_started(0.0)
    tr.source_delta("A")
    tr.source_final("A")
    tr.target_delta("甲")
    tr.target_final("甲")
    turns = tr.pop_ready()
    assert len(turns) == 1
    assert (turns[0].src, turns[0].tgt) == ("A", "甲")


def test_flush_emits_source_only_turn():
    tr = TurnTracker()
    tr.speech_started(0.0)
    tr.source_final("A", item_id="i1")
    assert tr.pop_ready() == []
    turns = tr.flush()
    assert len(turns) == 1
    assert turns[0].src == "A" and turns[0].tgt == ""
