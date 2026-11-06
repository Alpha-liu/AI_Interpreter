# -*- coding: utf-8 -*-
"""与实时翻译服务的 WebSocket 会话。自动重连、VAD 时间戳透传、优雅关闭。

Turn 归属由 `TurnTracker` 负责：优先用服务端事件里的 item_id 绑定原文/译文，
译文按 FIFO 与“最早尚未配译文的原文 Turn”配对，避免迟到译文被记到新一句名下。
"""
import json
import base64
import threading
import time
from collections import deque, OrderedDict

import websocket
from ai_interpreter import config                      # 动态读取 API_KEY / WORKSPACE_ID / MODEL / WS_URL
from ai_interpreter.turn_tracker import TurnTracker


class TranslationSession:
    _MAX_AUDIO_BACKLOG = 500
    _FINISH_ACK_TIMEOUT = 2.0
    _MAX_DONE_RESPONSES = 500

    def __init__(self, channel: str, subtitle_cfg,
                 on_source_delta, on_source_done, on_target_delta, on_target_done,
                 subtitle_recorder=None):
        self.channel = channel
        self.subtitle_cfg = subtitle_cfg
        self.on_source_delta = on_source_delta
        self.on_source_done = on_source_done
        self.on_target_delta = on_target_delta
        self.on_target_done = on_target_done
        self.subtitle_recorder = subtitle_recorder

        self.ws = None
        self._running = False
        self._paused = False
        self._audio_queue = deque(maxlen=self._MAX_AUDIO_BACKLOG)
        self._session_ready = threading.Event()
        self._finish_acked = threading.Event()

        # Turn 归属状态机
        self._tracker = TurnTracker(max_turns=500)
        self._done_responses = OrderedDict()   # 已收尾的 response id，防止 response.done 重复出字幕

        self._reconnect_delay = 1.0
        self._dropped_audio = 0

    # ---------- 连接与重连 ----------
    def connect(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        threading.Thread(target=self._run_forever, daemon=True).start()
        threading.Thread(target=self._audio_sender, daemon=True).start()

    def _run_forever(self):
        while self._running:
            # 每次新建连接时动态读取当前配置，确保设置菜单保存后立即生效
            headers = config.build_auth_headers(
                config.API_KEY, config.WORKSPACE_ID)

            # 强制将模型名作为 URL 参数，并清理掉用户可能误填的旧参数
            base_url = config.WS_URL.split("?")[0]
            ws_url = f"{base_url}?model={config.MODEL}"

            print(f"[{self.channel}] 正在连接: {ws_url}")

            self.ws = websocket.WebSocketApp(
                ws_url, header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=lambda ws, e: print(f"[{self.channel}] WebSocket 错误: {e}"),
                on_close=self._on_close,
            )
            try:
                # 增加 ping 机制保活
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                print(f"[{self.channel}] run_forever 异常: {e}")
            if not self._running:
                break
            self._session_ready.clear()
            # 断线时把已完成的语音尽量落盘，然后为下一次连接重置状态
            self._flush_tracker()
            self._tracker.reset()
            print(f"[{self.channel}] {self._reconnect_delay:.1f}s 后重连...")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 15.0)

    def _on_open(self, ws):
        print(f"[{self.channel}] WebSocket 已连接")
        self._reconnect_delay = 1.0

    def _on_close(self, ws, code, msg):
        print(f"[{self.channel}] WebSocket 关闭 code={code}, msg={msg}")
        self._session_ready.clear()
        dropped = len(self._audio_queue)
        if dropped:
            self._audio_queue.clear()
            self._dropped_audio += dropped
            print(f"[{self.channel}] 断线清空积压音频 {dropped} 包")

    # ---------- 事件处理 ----------
    def _on_message(self, ws, message):
        try:
            evt = json.loads(message)
        except json.JSONDecodeError:
            return
        t = evt.get("type", "")

        if t == "session.created":
            self._send_session_update(ws)
            return
        if t == "session.updated":
            print(f"[{self.channel}] session.updated 会话配置成功，可以开始发送音频")
            self._session_ready.set()
            return
        if t == "session.finished":
            self._finish_acked.set()
            return
        if t == "error":
            print(f"[{self.channel}] 服务端错误: {json.dumps(evt, ensure_ascii=False)}")
            return

        ts = time.time()
        item_id = evt.get("item_id")
        response_id = evt.get("response_id")

        # ---- VAD ----
        if t == "input_audio_buffer.speech_started":
            self._tracker.speech_started(ts)
            return
        if t == "input_audio_buffer.speech_stopped":
            self._tracker.speech_stopped(ts)
            return

        # ---- 原文数据流 ----
        if t == "conversation.item.input_audio_transcription.delta":
            delta = evt.get("delta", "")
            if delta:
                self._tracker.source_delta(delta, item_id, ts)
                if self.subtitle_cfg.show_source:
                    self.on_source_delta(self.channel, delta)
            return

        if t in ("conversation.item.input_audio_transcription.text",
                 "conversation.item.input_audio_transcription.completed"):
            text = evt.get("text") or evt.get("transcript")
            self._tracker.source_final(text, item_id, ts)
            self._drain_ready()
            return

        # ---- 译文数据流 ----
        if t in ("response.text.delta", "response.audio_transcript.delta"):
            delta = evt.get("delta", "")
            if delta:
                self._tracker.target_delta(delta, item_id, response_id, ts)
                if self.subtitle_cfg.show_target:
                    self.on_target_delta(self.channel, delta)
            return

        if t in ("response.text.done", "response.audio_transcript.done"):
            text = evt.get("text") or evt.get("transcript")
            self._tracker.target_final(text, item_id, response_id, ts)
            self._mark_done(response_id)
            self._drain_ready()
            return

        if t == "response.done":
            resp = evt.get("response", {}) or {}
            rid = response_id or resp.get("id")
            if rid and rid in self._done_responses:
                return                      # 已由 xxx.done 收尾，跳过
            text = ""
            for out in resp.get("output", []) or []:
                for content in out.get("content", []) or []:
                    text = content.get("transcript") or content.get("text")
                    if text:
                        break
                if text:
                    break
            if text:
                self._tracker.target_final(text, item_id, rid, ts)
                self._mark_done(rid)
                self._drain_ready()
            return

    def _drain_ready(self):
        for turn in self._tracker.pop_ready():
            self._emit_turn(turn)

    def _emit_turn(self, turn):
        """把一条已完成的 Turn 交给 UI 与字幕记录器（先原文后译文）。"""
        src = (turn.src or "").strip()
        tgt = (turn.tgt or "").strip()
        if not src and not tgt:
            return
        if src:
            if self.subtitle_recorder:
                self.subtitle_recorder.on_source_done(
                    turn.tid, src, turn.start_ts, turn.end_ts)
            self.on_source_done(self.channel, turn.tid, src)
        if tgt:
            if self.subtitle_recorder:
                self.subtitle_recorder.on_target_done(turn.tid, tgt)
            self.on_target_done(self.channel, turn.tid, tgt)
        elif src and self.subtitle_recorder:
            # 只有原文（未产生译文 / 超时）：也落一条，避免丢字幕
            self.subtitle_recorder.on_target_done(turn.tid, "")

    def _flush_tracker(self):
        try:
            for turn in self._tracker.flush():
                self._emit_turn(turn)
        except Exception as e:
            print(f"[{self.channel}] 收尾字幕失败: {e}")

    def _mark_done(self, rid):
        if not rid:
            return
        self._done_responses[rid] = 1
        while len(self._done_responses) > self._MAX_DONE_RESPONSES:
            self._done_responses.popitem(last=False)

    def _send_session_update(self, ws):
        # 模型名已通过 URL 传递，不再写在 session 里
        ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "output_modalities": ["text"],
                "translation": {"language": self.subtitle_cfg.target_lang},
                "audio": {"input": {
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.0,
                        "silence_duration_ms": 800,
                    },
                }},
            },
        }))
        print(f"[{self.channel}] 已发送 session.update，目标语言: {self.subtitle_cfg.target_lang}")

    # ---------- 音频发送 ----------
    def feed_audio(self, pcm_bytes: bytes):
        try:
            self._audio_queue.append(
                base64.b64encode(pcm_bytes).decode("ascii"))
        except Exception:
            pass

    def _audio_sender(self):
        while self._running:
            if self._paused or not self._session_ready.is_set():
                time.sleep(0.05)
                continue
            ws = self.ws
            if not ws or not ws.sock:
                time.sleep(0.1)
                continue
            try:
                b64 = self._audio_queue.popleft()
            except IndexError:
                time.sleep(0.01)
                continue
            try:
                ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": b64,
                }))
            except Exception:
                time.sleep(0.1)

    # ---------- 控制 ----------
    def pause(self):
        self._paused = True
        self._audio_queue.clear()

    def resume(self):
        self._paused = False

    def update_target_language(self, lang: str):
        self.subtitle_cfg.target_lang = lang
        ws = self.ws
        if ws and ws.sock:
            try:
                ws.send(json.dumps({
                    "type": "session.update",
                    "session": {"translation": {"language": lang}},
                }))
            except Exception as e:
                print(f"[{self.channel}] 更新语言失败: {e}")

    def close(self):
        self._running = False
        self._session_ready.clear()
        # 收尾尚未完成的 Turn，避免丢掉最后一句
        self._flush_tracker()
        self._tracker.reset()
        ws = self.ws
        if ws:
            try:
                ws.send(json.dumps({"type": "session.finish"}))
                self._finish_acked.wait(timeout=self._FINISH_ACK_TIMEOUT)
            except Exception:
                pass
            try:
                ws.close()
            except Exception:
                pass
        if self._dropped_audio:
            print(f"[{self.channel}] 累计丢弃音频包: {self._dropped_audio}")
