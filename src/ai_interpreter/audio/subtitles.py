# -*- coding: utf-8 -*-
"""字幕时序记录器：按 VAD Turn 成对保存，并把长句切成多条短字幕。"""
import os
import time
import threading
from datetime import datetime, timedelta

from ai_interpreter.text_utils import split_aligned, UNIT_MAX_CHARS


class SubtitleRecorder:
    def __init__(self, channel: str, speaker_label: str,
                 output_dir: str = "record", base_ts: float = None,
                 max_chars: int = UNIT_MAX_CHARS):
        self.channel = channel
        self.speaker_label = speaker_label
        self.output_dir = output_dir
        self.base_ts = base_ts if base_ts is not None else time.time()
        self.max_chars = max_chars

        self._source_buf = {}
        self._target_buf = {}
        self._time_ranges = {}
        self.entries = []
        self._lock = threading.Lock()

    def on_source_delta(self, item_id: str, delta: str):
        with self._lock:
            self._source_buf.setdefault(item_id, []).append(delta)

    def on_source_done(self, item_id: str, transcript: str,
                       start_ts: float = None, end_ts: float = None):
        with self._lock:
            self._source_buf[item_id] = [transcript]
            if start_ts is None:
                start_ts = time.time()
            if end_ts is None or end_ts <= start_ts:
                end_ts = start_ts + 1.5
            self._time_ranges[item_id] = (start_ts, end_ts)

    def on_target_delta(self, item_id: str, delta: str):
        with self._lock:
            self._target_buf.setdefault(item_id, []).append(delta)

    def on_target_done(self, item_id: str, text: str):
        with self._lock:
            self._target_buf[item_id] = [text]
            self._finalize_locked(item_id)

    def _finalize_locked(self, item_id: str):
        source = "".join(self._source_buf.pop(item_id, [])).strip()
        target = "".join(self._target_buf.pop(item_id, [])).strip()
        if not source and not target:
            return

        abs_start, abs_end = self._time_ranges.pop(item_id, (time.time(), time.time() + 1.5))
        rel_start = max(0.0, abs_start - self.base_ts)
        rel_end = max(rel_start + 0.3, abs_end - self.base_ts)

        # 长句切成多条短字幕；原文/译文按句对齐，时间按文本长度占比分配
        pairs = split_aligned(source, target, self.max_chars)
        if len(pairs) <= 1:
            self.entries.append((rel_start, rel_end, self.speaker_label, source, target))
            return

        weights = [max(len(t), len(s), 1) for s, t in pairs]
        total = float(sum(weights)) or 1.0
        span = rel_end - rel_start
        cursor = rel_start
        for i, (s, t) in enumerate(pairs):
            if i == len(pairs) - 1:
                cue_end = rel_end
            else:
                cue_end = cursor + span * weights[i] / total
            if cue_end <= cursor:
                cue_end = cursor + 0.2
            self.entries.append((cursor, cue_end, self.speaker_label, s, t))
            cursor = cue_end

    def save(self) -> list:
        with self._lock:
            if not self.entries:
                return []

            self.entries.sort(key=lambda x: x[0])
            self._fix_overlaps_static(self.entries)

            os.makedirs(self.output_dir, exist_ok=True)
            now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"{self.output_dir}/{self.channel}_subtitles_{now_str}.srt"

            with open(filepath, "w", encoding="utf-8") as f:
                for idx, (s, e, speaker, src, tgt) in enumerate(self.entries, 1):
                    f.write(f"{idx}\n")
                    f.write(f"{self._fmt_seconds(s)} --> {self._fmt_seconds(e)}\n")
                    f.write(f"[原文] {src}\n")
                    f.write(f"[译文] {tgt}\n\n")
            print(f"[subtitle] 单通道字幕已保存: {filepath} (共 {len(self.entries)} 条)")
            return list(self.entries)

    @staticmethod
    def save_merged(all_entries: list, output_dir: str = "record"):
        if not all_entries:
            return
        all_entries = sorted(all_entries, key=lambda x: x[0])
        SubtitleRecorder._fix_overlaps_static(all_entries)

        os.makedirs(output_dir, exist_ok=True)
        now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f"{output_dir}/meeting_merged_{now_str}.srt"

        with open(filepath, "w", encoding="utf-8") as f:
            for idx, (s, e, speaker, src, tgt) in enumerate(all_entries, 1):
                f.write(f"{idx}\n")
                f.write(f"{SubtitleRecorder._fmt_seconds(s)} --> {SubtitleRecorder._fmt_seconds(e)}\n")
                f.write(f"[{speaker}] {tgt}\n")
                f.write(f"原音: {src}\n\n")
        print(f"[subtitle] 合并会议纪要已保存: {filepath}")

    @staticmethod
    def _fix_overlaps_static(entries: list):
        for i in range(len(entries) - 1):
            s, e, spk, src, tgt = entries[i]
            next_s = entries[i + 1][0]
            if e > next_s:
                new_e = next_s - 0.01
                if new_e > s + 0.05:
                    entries[i] = (s, new_e, spk, src, tgt)

    @staticmethod
    def _fmt_seconds(seconds: float) -> str:
        if seconds < 0:
            seconds = 0.0
        td = timedelta(seconds=seconds)
        total = int(td.total_seconds())
        h, m, s = total // 3600, (total % 3600) // 60, total % 60
        ms = int(td.microseconds / 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"