# -*- coding: utf-8 -*-
"""Turn 归属状态机：消除“译文晚于下一句 speech_started”导致的原文/译文错配。

背景
----
服务端事件里，原文与译文各自带自己的 item_id，二者通常并不相同。旧实现用
“收到 speech_started 时生成本地时间戳 id”作为当前 turn，下一句开始就会覆盖
它，于是上一句迟到的译文会被记到新一句名下。

本模块的做法
------------
- 原文：按它自己的 item_id 建 Turn（服务端没给就用本地序号，并复用当前活动 Turn）。
- 译文：按它自己的 item_id / response_id 建“目标键”。配对优先级：
    1) 目标键已出现过（同一 response 的续帧）；
    2) 目标键恰好等于某个原文 item_id（直接命中）；
    3) 与“最早一个尚未配对译文的原文 Turn”配对（FIFO，解决迟到译文错配）；
    4) 若当前原文 Turn 尚未完成，则先挂到它上面（译文先于原文 final 的兜底）；
    5) 以上都没有，才新建一个只有译文的 Turn。
- 原文与译文都完成才 finalize；close 时 flush 剩余 Turn，避免丢最后一句。
"""

import time
from collections import OrderedDict, deque


class _Turn:
    __slots__ = (
        "tid", "src_buf", "src", "src_done",
        "tgt_buf", "tgt", "tgt_done", "tgt_assigned",
        "start_ts", "end_ts", "finalized",
    )

    def __init__(self, tid, start_ts):
        self.tid = tid
        self.src_buf = []
        self.src = ""
        self.src_done = False
        self.tgt_buf = []
        self.tgt = ""
        self.tgt_done = False
        self.tgt_assigned = False
        self.start_ts = start_ts
        self.end_ts = None
        self.finalized = False


class TurnTracker:
    def __init__(self, max_turns: int = 500):
        self.max_turns = max_turns
        self._turns = OrderedDict()      # tid -> _Turn
        self._src_key = {}               # 原文 item_id -> tid
        self._tgt_key = {}               # 目标键(item_id/response_id) -> tid
        self._src_waiting = deque()      # 原文已完成、等待译文的 tid
        self._ready = []                 # 已 finalize、等待上层取走
        self._seq = 0
        self._speech_start = None
        self._speech_end = None
        self._active_tid = None
        self._active_tgt_tid = None

    # ---------- 生命周期 ----------
    def reset(self):
        self._turns.clear()
        self._src_key.clear()
        self._tgt_key.clear()
        self._src_waiting.clear()
        self._ready.clear()
        self._seq = 0
        self._speech_start = None
        self._speech_end = None
        self._active_tid = None
        self._active_tgt_tid = None

    def speech_started(self, ts=None):
        self._speech_start = ts if ts is not None else time.time()
        self._speech_end = None
        self._active_tid = None

    def speech_stopped(self, ts=None):
        self._speech_end = ts if ts is not None else time.time()

    # ---------- 内部 ----------
    def _new_tid(self):
        self._seq += 1
        return f"turn_{self._seq}"

    def _start_ts_for_new(self, ts):
        if self._speech_start is not None:
            return self._speech_start
        return ts if ts is not None else time.time()

    def _ensure_source_turn(self, item_id, ts):
        if item_id and item_id in self._src_key:
            turn = self._turns.get(self._src_key[item_id])
            if turn is not None:
                self._active_tid = turn.tid
                return turn
        # 无 item_id 时复用当前活动 Turn，避免每个 delta 都新建
        if not item_id and self._active_tid:
            turn = self._turns.get(self._active_tid)
            if turn is not None and not turn.src_done:
                return turn
        tid = self._new_tid()
        turn = _Turn(tid, self._start_ts_for_new(ts))
        self._turns[tid] = turn
        if item_id:
            self._src_key[item_id] = tid
        self._active_tid = tid
        self._trim()
        return turn

    def _remove_from_waiting(self, tid):
        try:
            self._src_waiting.remove(tid)
        except ValueError:
            pass

    def _finish(self, turn):
        """标记 finalize 并放进 ready 队列（幂等）。"""
        if turn.finalized:
            return
        turn.finalized = True
        self._remove_from_waiting(turn.tid)
        self._ready.append(turn)

    def _maybe_finish(self, turn):
        if turn.src_done and turn.tgt_done:
            self._finish(turn)

    def _clean_maps(self, tid):
        for d in (self._src_key, self._tgt_key):
            for k in [k for k, v in d.items() if v == tid]:
                d.pop(k, None)
        self._remove_from_waiting(tid)

    def _trim(self):
        while len(self._turns) > self.max_turns:
            tid, turn = next(iter(self._turns.items()))
            if not turn.finalized:
                break
            self._turns.popitem(last=False)
            self._clean_maps(tid)

    def _pair_target(self, item_id, response_id, ts):
        key = item_id or response_id
        # 1) 同一目标键已出现过
        if key and key in self._tgt_key:
            turn = self._turns.get(self._tgt_key[key])
            if turn is not None:
                self._active_tgt_tid = turn.tid
                return turn
        # 1b) 无任何键时，沿用当前正在写入的译文 Turn（同一 response 的续帧）
        if not key and self._active_tgt_tid:
            turn = self._turns.get(self._active_tgt_tid)
            if turn is not None and not turn.tgt_done:
                return turn
        # 2) 目标键等于某个原文 item_id
        if key and key in self._src_key:
            turn = self._turns.get(self._src_key[key])
            if turn is not None:
                turn.tgt_assigned = True
                self._tgt_key[key] = turn.tid
                self._remove_from_waiting(turn.tid)
                self._active_tgt_tid = turn.tid
                return turn
        # 3) FIFO：最早尚未配译文的原文 Turn
        while self._src_waiting:
            tid = self._src_waiting[0]
            turn = self._turns.get(tid)
            if turn is None:
                self._src_waiting.popleft()
                continue
            if not turn.tgt_assigned:
                turn.tgt_assigned = True
                if key:
                    self._tgt_key[key] = tid
                self._src_waiting.popleft()
                self._active_tgt_tid = turn.tid
                return turn
            self._src_waiting.popleft()
        # 4) 原文尚未 final，但已经有活动 Turn：先挂上去
        if self._active_tid:
            turn = self._turns.get(self._active_tid)
            if turn is not None and not turn.src_done and not turn.tgt_assigned:
                turn.tgt_assigned = True
                if key:
                    self._tgt_key[key] = turn.tid
                self._active_tgt_tid = turn.tid
                return turn
        # 5) 兜底：只有译文
        tid = self._new_tid()
        turn = _Turn(tid, self._start_ts_for_new(ts))
        turn.src_done = True        # 视为没有原文，可直接 finalize
        turn.tgt_assigned = True
        self._turns[tid] = turn
        if key:
            self._tgt_key[key] = tid
        self._active_tgt_tid = tid
        self._trim()
        return turn

    # ---------- 事件入口 ----------
    def source_delta(self, delta, item_id=None, ts=None):
        if not delta:
            return None
        turn = self._ensure_source_turn(item_id, ts)
        turn.src_buf.append(delta)
        return turn.tid

    def source_final(self, text, item_id=None, ts=None):
        turn = self._ensure_source_turn(item_id, ts)
        if text:
            turn.src = text
        elif turn.src_buf:
            turn.src = "".join(turn.src_buf)
        turn.src_done = True
        turn.end_ts = self._speech_end if self._speech_end is not None else (
            ts if ts is not None else time.time())
        if not turn.tgt_assigned:
            if turn.tid not in self._src_waiting:
                self._src_waiting.append(turn.tid)
        self._maybe_finish(turn)
        return turn.tid

    def target_delta(self, delta, item_id=None, response_id=None, ts=None):
        if not delta:
            return None
        turn = self._pair_target(item_id, response_id, ts)
        turn.tgt_buf.append(delta)
        return turn.tid

    def target_final(self, text, item_id=None, response_id=None, ts=None):
        turn = self._pair_target(item_id, response_id, ts)
        if text:
            turn.tgt = text
        elif turn.tgt_buf:
            turn.tgt = "".join(turn.tgt_buf)
        turn.tgt_done = True
        if self._active_tgt_tid == turn.tid:
            self._active_tgt_tid = None
        self._maybe_finish(turn)
        return turn.tid

    # ---------- 上层取结果 ----------
    def pop_ready(self):
        ready, self._ready = self._ready, []
        return ready

    def flush(self):
        """把所有尚未 finalize 的 Turn 全部收尾（用于关闭/断线）。"""
        for turn in list(self._turns.values()):
            if not turn.finalized:
                if turn.src_buf and not turn.src:
                    turn.src = "".join(turn.src_buf)
                if turn.tgt_buf and not turn.tgt:
                    turn.tgt = "".join(turn.tgt_buf)
                turn.src_done = turn.src_done or bool(turn.src)
                turn.tgt_done = turn.tgt_done or bool(turn.tgt)
                self._finish(turn)
        return self.pop_ready()
